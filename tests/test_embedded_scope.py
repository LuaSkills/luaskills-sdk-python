"""
Prove scope drainage through actual native lifetimes and independently retained SDK ownership.
通过实际原生寿命及独立保留的 SDK 所有权证明作用域排空。
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, PropertyMock, patch

from luaskills import (
    CallbackPumpConfig, EmbeddedCallbackPump, EmbeddedClient, EmbeddedCommandDriver,
    EmbeddedDriverConfig, EmbeddedNativeStatus, EmbeddedResultReleaseError,
    EmbeddedRuntimeError, EmbeddedRuntimeScope, EmbeddedTransport, EmbeddedTransportConfig,
    EmbeddedTransportError,
    HostCapability, create_engine_options,
)

from test_embedded_native_e2e import EmbeddedNativeFixture
from test_embedded_pump import PumpReleaseFault
from test_embedded_transport import NativeLibrary


class EmbeddedScopeBudgetTests(unittest.TestCase):
    """
    Validate native control capacity before creating any lifecycle thread or native runtime mutation.
    在创建任何生命周期线程或原生运行时变更前验证原生控制容量。
    """

    def test_control_checkpoints_reject_wrong_identity_and_malformed_status(self):
        """
        Exercise checkpoint validation without starting a thread or manufacturing native ownership.
        不启动线程也不制造原生所有权，验证检查点校验。
        Every consumed identity and status field must have its exact contract type before advancement.
        推进前每个消费的身份及状态字段都必须具有精确契约类型。
        """
        scope = object.__new__(EmbeddedRuntimeScope)
        scope._runtime = SimpleNamespace(runtime_id="exact-slot")
        scope._lock = threading.Lock()
        for command, phase, following in [("runtime_close", "closing_runtime", "draining_runtime"),
                                          ("runtime_free", "releasing_runtime", "released")]:
            for value in [None, [], {}, {"runtime_id": "other-slot"}, {"runtime_id": 1}]:
                for failed_release in [False, True]:
                    with self.subTest(command=command, value=value, failed_release=failed_release):
                        scope._phase = phase
                        scope._release_failure = False
                        scope._uncertain_delivery = False
                        scope._transport = Mock()
                        if failed_release:
                            failure = EmbeddedResultReleaseError(EmbeddedNativeStatus.INTERNAL,
                                json.dumps({"protocol_version": 1, "status": "ok", "result": value}).encode())
                            scope._transport.request.side_effect = failure
                            with self.assertRaises(EmbeddedResultReleaseError) as observed:
                                scope._transition(command, following)
                            self.assertIs(observed.exception, failure)
                            self.assertTrue(scope._uncertain_delivery)
                        else:
                            scope._transport.request.return_value = value
                            with self.assertRaisesRegex(RuntimeError, "slot identity"):
                                scope._transition(command, following)
                        self.assertEqual(scope._phase, phase)
                        scope._transport.request.assert_called_once_with({"type": command, "runtime_id": "exact-slot"})
                        scope._transport._release_runtime_scope.assert_not_called()

        # Only the fields consumed for shutdown are validated here; full wire typing remains generated.
        # 此处只校验关闭所消费字段；完整线类型仍由生成契约提供。
        for value in [{"runtime_id": "other-slot", "closed": True, "initialization": "ready"},
                      {"runtime_id": "exact-slot", "closed": "true", "initialization": "ready"},
                      {"runtime_id": "exact-slot", "closed": 1, "initialization": "ready"},
                      {"runtime_id": "exact-slot", "closed": True, "initialization": "unknown"},
                      {"runtime_id": "exact-slot", "closed": True},
                      {"runtime_id": "exact-slot", "initialization": "ready"}]:
            with self.subTest(status=value), self.assertRaises(RuntimeError):
                scope._validate_control("runtime_status", value)
        value = {"runtime_id": "exact-slot", "closed": True, "initialization": "reserved"}
        self.assertIs(scope._validate_control("runtime_status", value), value)

    def test_scope_cannot_overcommit_driver_native_reservations(self):
        """
        Exhaust count and byte reservations with the driver; reject scope adoption without a leaked claim.
        使用驱动器耗尽数量及字节预留；拒绝作用域接管且不泄漏声明。
        """
        native = NativeLibrary()
        with patch("luaskills.embedded_transport.ctypes.CDLL", return_value=native):
            transport = EmbeddedTransport(EmbeddedTransportConfig(max_runtimes=1, max_result_buffers=2,
                max_result_bytes=16384, max_response_bytes=8192, max_request_bytes=8192), library_path=Path(__file__))
        driver = EmbeddedCommandDriver(transport, EmbeddedDriverConfig(work_threads=1, max_work_commands=2, max_control_commands=2))
        try:
            with self.assertRaises(EmbeddedRuntimeError) as error:
                EmbeddedRuntimeScope(EmbeddedClient(driver).runtime("known-slot"))
            self.assertEqual(error.exception.code, "capacity_exceeded")
            self.assertFalse(transport._runtime_scopes)
            self.assertFalse(native.received)
        finally:
            driver.close(5)
            transport.close()
            transport.free()


@unittest.skipUnless(os.environ.get("LUASKILLS_LIB"), "requires the matching actual core library")
class EmbeddedScopeNativeTests(EmbeddedNativeFixture, unittest.TestCase):
    """
    Verify actual core release barriers, context exits and failure recovery using the matching DLL.
    使用匹配 DLL 验证实际核心释放屏障、上下文退出及失败恢复。
    """

    def setUp(self):
        """
        Start the trusted core fixture and borrowed driver; close scopes before driver and transport cleanup.
        启动可信核心夹具及借用驱动器；在驱动器和传输清理前关闭作用域。
        """
        super().setUp()
        self.driver = EmbeddedCommandDriver(self.transport, EmbeddedDriverConfig(
            work_threads=1, max_work_commands=4, max_control_commands=4))
        self.addCleanup(self.driver.close, 5)
        self.client = EmbeddedClient(self.driver)
        self.runtime = self.client.runtime(self.runtime_id)
        self.scopes = []
        self.addCleanup(self._close_scopes)

    def _close_scopes(self):
        """
        Finish known scope cleanup and prevent the fixture from freeing an already removed native slot.
        完成已知作用域清理，并防止夹具释放已经移除的原生槽。
        """
        for scope in self.scopes:
            if scope.status["retryable"]:
                scope.retry_close(5)
            else:
                scope.close(5)
            self.assertFalse(scope._thread.is_alive())
            if scope.runtime.runtime_id == self.runtime_id:
                self.runtime_id = None

    def scope(self, pump=None):
        """
        Adopt the exact fixture runtime and optional pump, recording the scope for guaranteed test cleanup.
        接管精确夹具运行时及可选 pump，记录作用域以保证测试清理。
        """
        scope = EmbeddedRuntimeScope(self.runtime, pump=pump, poll_interval=0.001)
        self.scopes.append(scope)
        return scope

    def test_sync_context_preserves_body_error_and_releases_only_its_runtime(self):
        """
        Release the native slot on exceptional context exit while leaving the borrowed driver usable.
        在异常上下文退出时释放原生槽，同时保持借用驱动器可用。
        """
        scope = self.scope()
        with self.assertRaisesRegex(LookupError, "body failure"):
            with scope as entered:
                self.assertIs(entered.runtime, self.runtime)
                with self.assertRaisesRegex(RuntimeError, "more than once"):
                    scope.__enter__()
                with self.assertRaisesRegex(RuntimeError, "owning embedded runtime scope"):
                    self.runtime.free()
                raise LookupError("body failure")
        self.assertTrue(scope.status["closed"])
        self.assertFalse(scope._thread.is_alive())
        self.assertFalse(self.transport._runtime_scopes)
        description = self.client.describe()
        self.assertEqual(description.result(5)["protocol_version"], 1)
        description.forget()
        with self.assertRaisesRegex(RuntimeError, "already closing"):
            scope.__enter__()
        scope.close(0)

    def test_failed_initialization_inside_scope_releases_the_reserved_slot(self):
        """
        Read retained initialization failure before context exit, then release the already reserved native slot.
        在上下文退出前读取保留的初始化失败，然后释放已预留原生槽。
        """
        self.scope().close(5)
        self.runtime_id = None
        reserved = self.client.reserve()
        self.runtime = reserved.result(5)
        self.runtime_id = self.runtime.runtime_id
        reserved.forget()
        scope = self.scope()
        with self.assertRaises(EmbeddedRuntimeError) as error:
            with scope:
                # Initialization acknowledges its one-shot attempt; its actual failure lives in runtime_status.
                # 初始化确认单次尝试；实际失败保存在 runtime_status 中。
                limits = dict(self.runtime_limits, max_effect_bytes_per_operation=0)
                initialization = self.runtime.initialize(create_engine_options(self.root, host_options={
                    "system_lua_lib_dir": self.system_root.as_posix(), "allow_network_download": False,
                }), limits)
                initialization.result(5)
                initialization.forget()
                status = self.runtime.status()
                snapshot = status.result(5)
                status.forget()
                self.assertEqual(snapshot["initialization"], "failed")
                failure = snapshot["error"]
                self.assertIsNotNone(failure)
                raise EmbeddedRuntimeError(failure["code"], failure["message"])
        self.assertEqual(error.exception.code, "invalid_argument")
        self.assertTrue(scope.status["closed"])
        self.assertFalse(self.driver.commands)

    def test_closing_one_scope_keeps_another_runtime_on_the_same_transport_usable(self):
        """
        Create two actual runtimes on one transport and prove closing one leaves the other ready and queryable.
        在一个传输创建两个实际运行时，并证明关闭一个后另一个仍就绪且可查询。
        """
        transport = EmbeddedTransport(EmbeddedTransportConfig(max_runtimes=2, max_result_buffers=4,
            max_result_bytes=131072, max_response_bytes=32768, max_request_bytes=65536),
            library_path=os.environ["LUASKILLS_LIB"])
        driver = EmbeddedCommandDriver(transport, EmbeddedDriverConfig(
            work_threads=1, max_work_commands=4, max_control_commands=4))
        client = EmbeddedClient(driver)
        scopes = {}

        def take(pending):
            """
            Consume a successful test receipt without conflating SDK quota release with core resource removal.
            消费成功测试回执，不混淆 SDK 配额释放和核心资源移除。
            """
            value = pending.result(5)
            pending.forget()
            return value

        try:
            for name in ("first", "second"):
                # Native engine construction canonicalizes an existing explicit runtime root.
                # 原生引擎构造规范化已经存在的显式运行时根目录。
                runtime_root = self.root / name
                runtime_root.mkdir()
                runtime = take(client.reserve())
                scopes[name] = EmbeddedRuntimeScope(runtime, poll_interval=0.001)
                take(runtime.initialize(create_engine_options(runtime_root, host_options={
                    "system_lua_lib_dir": self.system_root.as_posix(), "allow_network_download": False,
                }), self.runtime_limits))
                initialized = take(runtime.status())
                self.assertEqual(initialized["initialization"], "ready", initialized)
            scopes["first"].close(5)
            remaining = take(scopes["second"].runtime.status())
            self.assertEqual(remaining["initialization"], "ready")
            self.assertFalse(remaining["closing"])
            self.assertFalse(scopes["second"].status["closing"])
            self.assertEqual(set(transport._runtime_scopes), {scopes["second"].runtime.runtime_id})
        finally:
            for scope in scopes.values():
                scope.close(5)
            driver.close(5)
            transport.close()
            transport.free()

    def test_scope_drains_with_all_driver_control_receipts_retained(self):
        """
        Fill every driver control receipt slot and prove lifecycle controls still finish independently.
        占满全部驱动器控制回执槽，并证明生命周期控制仍独立完成。
        """
        scope = self.scope()
        retained = [self.runtime.status() for _ in range(4)]
        for pending in retained:
            self.assertEqual(pending.result(5)["initialization"], "ready")
        with self.assertRaises(EmbeddedRuntimeError) as error:
            self.runtime.status()
        self.assertEqual(error.exception.code, "capacity_exceeded")
        asyncio.run(scope.close_async())
        self.assertTrue(scope.status["closed"])
        self.assertEqual(len(self.driver.commands), len(retained))
        for pending in retained:
            pending.forget()

    def test_start_failure_before_and_after_thread_creation_returns_claim_once(self):
        """
        Fault thread startup before execution and after actual creation; neither path may close the runtime.
        在线程执行前及实际创建后注入启动故障；两条路径均不得关闭运行时。
        """
        original_start = threading.Thread.start
        with patch("luaskills.embedded_scope.threading.Thread", side_effect=MemoryError("injected allocation failure")):
            with self.assertRaises(MemoryError):
                EmbeddedRuntimeScope(self.runtime)
        self.assertFalse(self.transport._runtime_scopes)
        for late in (False, True):
            with self.subTest(late=late):
                def start(thread):
                    """
                    Raise at the selected startup boundary for this test's scope thread only.
                    仅为本测试作用域线程在选定启动边界抛错。
                    """
                    if late:
                        original_start(thread)
                    raise KeyboardInterrupt("injected scope startup interruption")

                with patch.object(threading.Thread, "start", start), patch.object(
                    self.transport, "_release_runtime_scope", wraps=self.transport._release_runtime_scope,
                ) as release, patch.object(self.transport, "_request_encoded", wraps=self.transport._request_encoded) as request:
                    with self.assertRaises(KeyboardInterrupt):
                        EmbeddedRuntimeScope(self.runtime)
                    self.assertEqual(release.call_count, 1)
                    self.assertEqual(request.call_count, 0)
                self.assertFalse(self.transport._runtime_scopes)
        # Simulate the interruption window where a native thread exists but its Python identity is not visible yet.
        # 模拟原生线程已存在但 Python 身份尚不可见的中断窗口。
        delayed_threads = []

        def start_without_visible_identity(thread):
            """
            Retain the started thread and interrupt its caller before exposing the identity observation.
            保留已启动线程，并在暴露身份观察前中断调用方。
            """
            original_start(thread)
            delayed_threads.append(thread)
            raise KeyboardInterrupt("injected interruption before visible thread identity")

        with patch.object(threading.Thread, "start", start_without_visible_identity), patch.object(
            threading.Thread, "ident", new_callable=PropertyMock, return_value=None,
        ), patch.object(self.transport, "_release_runtime_scope", wraps=self.transport._release_runtime_scope) as release:
            with self.assertRaises(KeyboardInterrupt):
                EmbeddedRuntimeScope(self.runtime)
        for thread in delayed_threads:
            thread.join(5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(release.call_count, 1)
        self.assertFalse(self.transport._runtime_scopes)
        pending = self.runtime.status()
        self.assertFalse(pending.result(5)["closing"])
        pending.forget()

    def test_adoption_requires_exact_pump_and_prevents_duplicate_owners(self):
        """
        Reject an omitted live pump and a second scope without disturbing the first actual owner.
        拒绝遗漏活动泵及第二个作用域，不干扰第一个实际所有者。
        """
        config = CallbackPumpConfig(max_concurrent_handlers=1, max_pending_commands=4, poll_interval_ms=1)
        pump = EmbeddedCallbackPump(self.transport, self.runtime_id, config)
        self.addCleanup(pump.close, 5)
        with self.assertRaisesRegex(RuntimeError, "exact existing callback pump"):
            EmbeddedRuntimeScope(self.runtime)
        scope = self.scope(pump)
        with self.assertRaisesRegex(RuntimeError, "already has a lifecycle scope"):
            EmbeddedRuntimeScope(self.runtime, pump=pump)
        scope.close(5)
        self.assertTrue(pump.status["closed"])
        self.assertTrue(scope.status["closed"])

    def test_async_exit_cancellation_keeps_live_callbacks_owned_until_return(self):
        """
        Cancel the caller loop during context exit while a real callback remains live, then join actual cleanup.
        在实际回调仍存活的上下文退出期间取消调用方循环，然后汇合实际清理。
        """
        pump = EmbeddedCallbackPump(self.transport, self.runtime_id, CallbackPumpConfig(
            max_concurrent_handlers=1, max_pending_commands=4, poll_interval_ms=1))
        self.addCleanup(pump.close, 5)
        entered = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)
        calls = []

        def handler(arguments, context):
            """
            Hold actual host work until release and publish a late committed effect before returning.
            保持实际宿主工作直到 release，并在返回前发布迟到提交副作用。
            """
            calls.append(arguments)
            entered.set()
            self.assertTrue(release.wait(5))
            context.report_effects("committed")
            return None

        pump.register([HostCapability({
            "name": "scope.callback", "version": "1.0.0", "description": "Owned scope callback",
            "input_schema": True, "output_schema": True, "execution": "queued", "permissions": ["python.host"],
            "scope": "invocation", "max_concurrent": 1, "max_call_ms": 10000,
            "max_input_bytes": 1024, "max_output_bytes": 1024, "effects": "mutating", "idempotency": "none",
        }, handler, "sync")], 5)
        operation_id = self.submit(self.pool("return {call=function(a) return vulcan.capabilities.call('scope.callback',a) end, shutdown=function() local r=vulcan.capabilities.call('scope.callback','closing'); assert(r.ok); return r.value end}", {"export":"shutdown", "arguments":None, "timeout_ms":5000}, reuse="single_call"), None)
        self.assertTrue(entered.wait(2))
        scope = self.scope(pump)

        async def caller():
            """
            Enter and exit asynchronously, then cancel only the blocked close observer before closing its loop.
            异步进入及退出，然后在关闭循环前仅取消阻塞的关闭观察者。
            """
            async def body():
                """
                Enter the adopted scope and request normal context exit without replacing runtime ownership.
                进入接管作用域并请求正常上下文退出，不替换运行时所有权。
                """
                async with scope:
                    pass

            waiting = asyncio.create_task(body())
            deadline = time.monotonic() + 2
            while scope.status["phase"] != "draining_runtime":
                self.assertLess(time.monotonic(), deadline, scope.status)
                await asyncio.sleep(0.001)
            waiting.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await waiting

        asyncio.run(caller())
        self.assertTrue(scope._thread.is_alive())
        self.assertFalse(scope.status["closed"])
        self.assertTrue(self.command({"type": "operation_status", "operation_id": operation_id})["cancellation_requested"])
        with self.assertRaises(TimeoutError):
            scope.close(0.01)
        release.set()
        scope.close(5)
        self.assertTrue(scope.status["closed"])
        self.assertTrue(pump.status["closed"])
        self.assertFalse(scope._thread.is_alive())
        self.assertEqual(calls, [None, "closing"])

    def test_scope_retains_prewarm_initializer_after_close_observer_timeout(self):
        """
        Keep prewarm ownership through a timed-out scope observer until the real initializer callback returns.
        跨作用域观察超时保留预热归属，直到真实初始化回调返回。
        """
        # The release gate also runs during cleanup after assertion failures.
        # 断言失败后的清理也执行释放门禁。
        pump = EmbeddedCallbackPump(self.transport, self.runtime_id, CallbackPumpConfig(
            max_concurrent_handlers=1, max_pending_commands=4, poll_interval_ms=1))
        self.addCleanup(pump.close, 5)
        entered = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)
        calls = []

        def handler(arguments, context):
            """
            Hold real initialization work until release, reporting its actual late effect before returning null.
            保持真实初始化工作直到释放，在返回空值前报告其实际迟到副作用。
            """
            calls.append(arguments)
            entered.set()
            self.assertTrue(release.wait(5))
            context.report_effects("committed")
            return None

        pump.register([HostCapability({
            "name": "scope.prewarm", "version": "1.0.0", "description": "Owned prewarm callback",
            "input_schema": True, "output_schema": True, "execution": "queued", "permissions": ["python.host"],
            "scope": "invocation", "max_concurrent": 1, "max_call_ms": 10000,
            "max_input_bytes": 1024, "max_output_bytes": 1024, "effects": "mutating", "idempotency": "none",
        }, handler, "sync")], 5)
        # A typed operation wraps the exact pool registered by the existing trusted native fixture.
        # 类型化操作包装既有可信原生夹具注册的精确池。
        pool = self.runtime.pool(self.pool(
            "assert(vulcan.host.call('scope.prewarm','initialization').ok); return {call=function() error('business must not execute') end}"))
        pending = pool.prewarm_instance({"request_context": None, "client_budget": None, "tool_config": None}, 10000)
        operation = pending.result(5)
        pending.forget()
        self.assertTrue(entered.wait(2))
        self.assertTrue(self.command({"type": "operation_status", "operation_id": operation.operation_id})["context"]["prewarm"])
        scope = self.scope(pump)
        with self.assertRaises(TimeoutError):
            scope.close(0.01)
        self.assertFalse(scope.status["closed"])
        self.assertFalse(pump.status["closed"])
        self.assertEqual(self.command({"type": "pool_status", "pool_id": pool.pool_id})["resident"], 1)
        release.set()
        scope.close(5)
        self.assertTrue(scope.status["closed"])
        self.assertTrue(pump.status["closed"])
        self.assertEqual(calls, ["initialization"])

    def test_scope_reports_callback_recovery_then_retries_without_replaying_handler(self):
        """
        Surface pump delivery failure as retryable drainage, then join exact cleanup after explicit recovery.
        将泵交付失败报告为可重试排空，再于显式恢复后汇合精确清理。
        """
        pump = EmbeddedCallbackPump(self.transport, self.runtime_id, CallbackPumpConfig(
            max_concurrent_handlers=1, max_pending_commands=4, poll_interval_ms=1))
        self.addCleanup(pump.close, 5)
        calls = []

        def handler(arguments, context):
            """
            Record arguments once and retain committed effects in context; return null for completion validation.
            记录 arguments 一次并在 context 中保留已提交副作用；返回空值用于完成校验。
            """
            calls.append(arguments)
            context.report_effects("committed")
            return None

        pump.register([HostCapability({
            "name": "scope.recovery", "version": "1.0.0", "description": "Scope delivery recovery callback",
            "input_schema": True, "output_schema": True, "execution": "queued", "permissions": ["python.host"],
            "scope": "invocation", "max_concurrent": 1, "max_call_ms": 10000,
            "max_input_bytes": 1024, "max_output_bytes": 1024, "effects": "mutating", "idempotency": "none",
        }, handler, "sync")], 5)
        pool = self.pool("return {call=function(a) return vulcan.capabilities.call('scope.recovery',a) end}")
        scope = self.scope(pump)
        with PumpReleaseFault(self.transport, "host_request_complete") as fault:
            operation = self.submit(pool, "once")
            self.assertTrue(fault.failed.wait(5))
            done = self.terminal(operation)
            with self.assertRaisesRegex(EmbeddedRuntimeError, "explicit delivery recovery"):
                scope.close(5)
            self.assertEqual(scope.status["phase"], "draining_runtime")
            self.assertTrue(scope.status["retryable"])
            self.assertTrue(pump.recovery_required)
            with self.assertRaises(EmbeddedRuntimeError):
                scope.close(5)
            self.assertEqual(len(fault.successes), 1)
            scope.retry_close(5)
            self.assertTrue(scope.status["closed"])
            self.assertTrue(pump.status["closed"])
            self.assertFalse(pump.recovery_required)
            self.assertIsNotNone(pump.status["failure"])
            self.assertFalse(self.transport._results)
            self.assertEqual(calls, ["once"])
            self.assertEqual(len(fault.successes), 1)
            self.assertTrue(any(effect["effects"] == "committed" for effect in done["host_effects"]))

    def test_pre_mutation_capacity_rejection_allows_explicit_close_retry(self):
        """
        Reject one control frame before actual dispatch, then resume only through explicit retry.
        在实际分发前拒绝一个控制帧，然后仅通过显式重试继续。
        """
        scope = self.scope()
        original_request = self.transport._request_encoded
        rejected = []

        def request(encoded):
            """
            Reject the first close frame with the core's pre-mutation capacity status; forward all later frames.
            以核心变更前容量状态拒绝首个关闭帧；转发全部后续帧。
            """
            frame = json.loads(encoded)["command"]
            if frame["type"] == "runtime_close" and not rejected:
                rejected.append(frame["runtime_id"])
                raise EmbeddedTransportError("luaskills_ffi_embedded_request_v1", EmbeddedNativeStatus.CAPACITY_EXCEEDED)
            return original_request(encoded)

        self.transport._request_encoded = request
        try:
            with self.assertRaises(EmbeddedTransportError):
                scope.close(5)
            self.assertTrue(scope.status["retryable"])
            self.assertEqual(scope.status["phase"], "closing_runtime")
            self.assertFalse(self.transport.request({"type": "runtime_status", "runtime_id": self.runtime_id})["closing"])
            scope.retry_close(5)
            self.assertTrue(scope.status["closed"])
        finally:
            self.transport._request_encoded = original_request

    def test_release_failure_recovers_without_repeating_actual_slot_removal(self):
        """
        Fail the result release after actual runtime_free, then recover from the copied successful receipt once.
        在实际 runtime_free 后使结果释放失败，再从复制的成功回执恢复一次。
        """
        scope = self.scope()
        original_request = self.transport._request_encoded
        original_free = self.transport._result_free
        removals = []

        def request(encoded):
            """
            Inject one post-mutation buffer-release failure for exact runtime_free and record its real dispatch.
            为精确 runtime_free 注入一次变更后缓冲释放失败，并记录真实分发。
            """
            frame = json.loads(encoded)["command"]
            if frame["type"] == "runtime_free":
                removals.append(frame["runtime_id"])
                self.transport._result_free = lambda identity, result: EmbeddedNativeStatus.INTERNAL
                try:
                    return original_request(encoded)
                finally:
                    self.transport._result_free = original_free
            return original_request(encoded)

        self.transport._request_encoded = request
        try:
            with self.assertRaises(EmbeddedResultReleaseError):
                scope.close(5)
            self.assertEqual(scope.status["phase"], "released")
            self.assertTrue(scope.status["retryable"])
            self.assertFalse(scope.status["closed"])
            with self.assertRaises(EmbeddedResultReleaseError):
                scope.close(5)
            self.assertEqual(removals, [self.runtime_id])
            asyncio.run(scope.retry_close_async())
            self.assertTrue(scope.status["closed"])
            self.assertFalse(self.transport._results)
            self.assertEqual(removals, [self.runtime_id])
        finally:
            self.transport._request_encoded = original_request
            self.transport._result_free = original_free


if __name__ == "__main__":
    unittest.main()
