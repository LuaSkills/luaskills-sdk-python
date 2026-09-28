"""
Exercise typed receipt recovery and native high-level lifecycle semantics.
验证类型回执恢复及原生高层生命周期语义。
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from luaskills import (
    CallbackPumpConfig, EmbeddedCallbackPump, EmbeddedClient, EmbeddedCommandDriver,
    EmbeddedDriverConfig, EmbeddedNativeStatus, EmbeddedResultReleaseError,
    EmbeddedRuntimeError, EmbeddedTransport, HostCapability, create_engine_options,
)

from test_embedded_native_e2e import EmbeddedNativeFixture
from test_embedded_transport import NativeLibrary, config


class EmbeddedClientReceiptTests(unittest.TestCase):
    """
    Verify local observation and identity behavior without treating a fake library as native runtime proof.
    验证本地观察及身份行为，不将模拟动态库视为原生运行时证据。
    """

    def setUp(self):
        """
        Bind an isolated C-shaped fake transport and one real SDK command driver; register joined cleanup.
        绑定隔离 C 形状模拟传输及一个实际 SDK 命令驱动器；注册汇合清理。
        """
        # The fake provides native-shaped allocation ownership for receipt-only assertions.
        # 模拟器为纯回执断言提供原生形状的分配所有权。
        self.native = NativeLibrary()
        with patch("luaskills.embedded_transport.ctypes.CDLL", return_value=self.native):
            self.transport = EmbeddedTransport(config(), library_path=Path(__file__))
        self.driver = EmbeddedCommandDriver(self.transport, EmbeddedDriverConfig(
            work_threads=1, max_work_commands=4, max_control_commands=4))
        self.client = EmbeddedClient(self.driver)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        """
        Release test gates, join SDK workers and release actual fake result ownership; return nothing.
        释放测试门控、汇合 SDK 工作线程并释放实际模拟结果所有权；无返回值。
        """
        self.native.proceed.set()
        self.driver.close(5)
        self.native.release_status = 0
        self.transport.release_results()
        self.transport.close()
        self.transport.free()

    def test_typed_identity_survives_cancelled_observer_and_repeated_projection(self):
        """
        Cancel a reserve observer and recover the same native identity without issuing another reserve.
        取消预留观察者并恢复同一原生身份，不发起另一次预留。
        """
        self.native.reply = b'{"protocol_version":1,"status":"ok","result":{"runtime_id":"native-slot"}}'
        self.native.proceed.clear()
        pending = self.client.reserve()
        self.assertTrue(self.native.entered.wait(2))

        async def observe():
            """
            Cancel only the caller-owned observation and then let its event loop close.
            仅取消调用方拥有的观察，然后允许其事件循环关闭。
            """
            waiting = asyncio.create_task(pending.result_async())
            await asyncio.sleep(0)
            waiting.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await waiting

        asyncio.run(observe())
        self.assertEqual(self.driver.commands, (pending.receipt,))
        self.native.proceed.set()
        runtime = pending.result(2)
        self.assertEqual(runtime.runtime_id, "native-slot")
        self.assertEqual(asyncio.run(pending.result_async()).runtime_id, runtime.runtime_id)
        self.assertEqual(len(self.native.received), 1)
        with self.assertRaises(AttributeError):
            runtime.runtime_id = "replacement"
        pending.forget()
        self.assertFalse(self.driver.commands)

    def test_failed_typed_projection_retains_original_receipt(self):
        """
        Reject a response without its declared runtime identity while retaining exact delivery evidence.
        拒绝缺少声明运行时身份的响应，同时保留精确交付证据。
        """
        self.native.reply = b'{"protocol_version":1,"status":"ok","result":{}}'
        pending = self.client.reserve()
        with self.assertRaises(KeyError):
            pending.result(2)
        self.assertEqual(self.driver.commands, (pending.receipt,))
        self.assertEqual(pending.receipt.result(0), {})
        self.assertEqual(len(self.native.received), 1)

    def test_invalid_polling_intervals_fail_before_submission(self):
        """
        Reject booleans, nonfinite values and platform overflow before any native status request.
        在任何原生状态请求前拒绝布尔值、非有限值及平台溢出。
        """
        operation = self.client.runtime("known-slot").operation("known-operation")
        for invalid in (True, -1, float("nan"), float("inf"), 10 ** 1000):
            with self.subTest(value=repr(invalid)[:30]):
                with self.assertRaises(ValueError):
                    operation.wait(timeout=invalid)
                with self.assertRaises(ValueError):
                    asyncio.run(operation.wait_async(poll_interval=invalid))
        with self.assertRaises(ValueError):
            operation.wait(poll_interval=0)
        self.assertFalse(self.native.received)
        self.assertFalse(self.driver.commands)


@unittest.skipUnless(os.environ.get("LUASKILLS_LIB"), "requires the matching actual core library")
class EmbeddedClientNativeTests(EmbeddedNativeFixture, unittest.TestCase):
    """
    Run typed handles against actual native Lua, fixed sessions, host effects and release barriers.
    对实际原生 Lua、固定会话、宿主副作用及释放屏障运行类型句柄。
    """

    def setUp(self):
        """
        Start the trusted fixture and bounded SDK driver; leave native cleanup to the existing fixture.
        启动可信夹具及有界 SDK 驱动器；由既有夹具负责原生清理。
        """
        super().setUp()
        # Three native slots cover one business worker, driver controls and one callback pump.
        # 三个原生槽覆盖一个业务线程、驱动器控制及一个回调泵。
        self.driver = EmbeddedCommandDriver(self.transport, EmbeddedDriverConfig(
            work_threads=1, max_work_commands=8, max_control_commands=4))
        self.addCleanup(self.driver.close, 5)
        self.client = EmbeddedClient(self.driver)
        self.runtime = self.client.runtime(self.runtime_id)
        # Host context is explicit even when no client-specific budget or tool configuration is supplied.
        # 即使没有客户端特定预算或工具配置，宿主上下文也保持显式。
        self.context = {"request_context": None, "client_budget": None, "tool_config": None}

    def take(self, pending):
        """
        Observe a test receipt for five seconds, forget only after success, and return its typed value.
        在五秒内观察测试回执，仅在成功后遗忘，并返回类型值。
        """
        result = pending.result(5)
        pending.forget()
        return result

    def make_pool(self, source, *, reuse="reusable", kind="shared"):
        """
        Register source through the typed API using explicit reuse and kind fixture policies; return its handle.
        使用显式 reuse 和 kind 夹具策略通过类型接口注册 source；返回句柄。
        """
        return self.take(self.runtime.register_pool({
            "plugin_id": self.plugin_id, "generation": "typed-generation-1",
            "package_root": self.package_root.as_posix(), "dependencies_file": "dependencies.yaml",
            "workspace_root": None, "cwd": None, "mounts": {}, "security_partition": "python-test",
            "source": source, "exports": [{"name": "call", "input_schema": True, "output_schema": True}],
        }, {"kind": kind, "min_resident_vms": 1 if kind == "dedicated" else 0,
            "max_resident_vms": 2, "max_running_calls": 2, "max_queued_calls": 4,
            "reuse": reuse, "serial": False, "backend": "in_process", "idle_ttl_ms": None, "max_uses": None,
        }, ["python.host"], "typed-v1"))

    def test_persistent_history_preserves_original_context_across_reopen(self):
        """
        Exercise typed storage initialization, history and conservative retention through the actual DLL.
        通过实际 DLL 验证类型化存储初始化、历史与保守保留。
        """
        # The database belongs to the fixture host and outlives both actual runtimes.
        # 数据库属于夹具宿主，比两个实际运行时存活更久。
        persistence = {"path": str(self.root / "operations.db"),
            "journal": {"max_records": 16, "max_record_bytes": 32768, "max_database_bytes": 262144},
            "worker": {"max_pending_writes": 8, "max_pending_bytes": 131072}}

        def replace_runtime():
            """
            Release the current known slot and initialize the next through the typed persistent facade.
            释放当前已知槽，并通过类型化持久外观初始化下一个槽。
            """
            self.take(self.runtime.request_close())
            # Finite observation does not replace the core's actual worker closure proof.
            # 有限观察不替代核心实际工作线程关闭证明。
            deadline = time.monotonic() + 5
            while not self.take(self.runtime.status())["closed"]:
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.001)
            self.take(self.runtime.free())
            self.runtime_id = None
            self.runtime = self.take(self.client.reserve())
            self.runtime_id = self.runtime.runtime_id
            self.take(self.runtime.initialize(create_engine_options(self.root, host_options={
                "system_lua_lib_dir": self.system_root.as_posix(), "allow_network_download": False,
            }), self.runtime_limits, persistence))
            self.assertEqual(self.take(self.runtime.status())["initialization"], "ready")
            self.take(self.runtime.register_plugin(self.plugin_id, {name: self.runtime_limits[name] for name in (
                "max_registered_pools", "max_sessions", "max_resident_vms", "max_running_calls",
                "max_queued_calls", "max_queued_bytes", "max_operations")}))

        replace_runtime()
        # This namespace comes from the actual core, never the FFI control slot.
        # 此命名空间来自实际核心，绝非 FFI 控制槽。
        namespace = self.take(self.runtime.status())["core_runtime_id"]
        self.assertIsNotNone(self.take(self.runtime.status())["persistence"])
        self.assertFalse(self.take(self.runtime.recover_storage()))
        self.assertFalse(self.take(self.runtime.storage_status())["closing"])
        # No callback is needed to retain the exact module admission context.
        # 保留精确模块入场上下文不需要回调。
        pool = self.make_pool("return {call=function(a) return a end}")
        # Preserve one actual JSON result across native release and reopen.
        # 跨原生释放与重新打开保留一个实际 JSON 结果。
        operation = self.take(pool.submit("call", {"durable": "中文"}, self.context, 10000))
        # Terminal publication occurs after its persistent checkpoint is acknowledged.
        # 终态在持久检查点确认后发布。
        done = operation.wait(5)
        self.assertIsNone(self.take(operation.persistence_failure()))
        # No failed checkpoint is an explicit conflict, not implicit success or business replay.
        # 不存在失败检查点是明确冲突，不是隐式成功或业务重放。
        retry = operation.retry_checkpoint()
        with self.assertRaises(EmbeddedRuntimeError) as error:
            retry.result(5)
        self.assertEqual(error.exception.code, "busy")
        retry.forget()
        # The entire original row remains comparable after another runtime owns the database.
        # 另一个运行时拥有数据库后，整个原始行仍可比较。
        history = self.take(self.runtime.history_get(namespace, operation.operation_id))
        self.assertEqual(history["snapshot"], done)
        self.assertEqual(self.take(self.runtime.history_next()), history)
        self.assertIsNone(self.take(self.runtime.history_next({"runtime_id": namespace, "operation_id": operation.operation_id})))
        self.take(operation.forget())
        # Successful ordinary Lua cannot prove all possible side effects were reconciled.
        # 成功的普通 Lua 无法证明所有可能副作用均已对账。
        deletion = self.runtime.history_forget(namespace, operation.operation_id, history["revision"])
        with self.assertRaises(EmbeddedRuntimeError) as error:
            deletion.result(5)
        self.assertEqual(error.exception.code, "busy")
        deletion.forget()
        replace_runtime()
        self.assertNotEqual(self.take(self.runtime.status())["core_runtime_id"], namespace)
        self.assertEqual(self.take(self.runtime.history_get(namespace, operation.operation_id)), history)
        # Original historical operations are not adopted into the new live namespace.
        # 原始历史操作不会被接管进新活动命名空间。
        missing = self.runtime.operation(operation.operation_id).status()
        with self.assertRaises(EmbeddedRuntimeError) as error:
            missing.result(5)
        self.assertEqual(error.exception.code, "not_found")
        missing.forget()

    def test_shared_pool_calls_preserve_results_errors_and_explicit_forgetting(self):
        """
        Execute successful and failing Lua calls through typed handles; preserve snapshots until explicit forget.
        通过类型句柄执行成功及失败 Lua 调用；在显式遗忘前保留快照。
        """
        pool = self.make_pool("return {call=function(a) if a == 'fail' then error('typed failure') end return a end}")
        operation = self.take(pool.submit("call", {"unicode": "类型回执", "null": None}, self.context, 10000))
        outcome = operation.wait(5)
        self.assertEqual(outcome["value"], {"unicode": "类型回执", "null": None})
        self.assertEqual(outcome["operation_id"], operation.operation_id)
        self.assertEqual(outcome["context"]["kind"], "module")
        self.assertEqual(outcome["context"]["pool_id"], pool.pool_id)
        self.assertEqual(outcome["context"]["caller"]["plugin_id"], self.plugin_id)
        self.assertEqual(outcome["context"]["caller"]["operation_id"], operation.operation_id)
        self.assertEqual(outcome["context"]["export"], "call")
        self.assertEqual(outcome["host_effects"], [])
        self.assertFalse(self.take(operation.cancel()))
        self.assertEqual(self.take(operation.status()), outcome)
        self.take(operation.forget())
        missing = operation.status()
        with self.assertRaises(EmbeddedRuntimeError) as error:
            missing.result(5)
        self.assertEqual(error.exception.code, "not_found")
        missing.forget()
        failed = self.take(pool.submit("call", "fail", self.context, 10000))
        snapshot = asyncio.run(failed.wait_async())
        self.assertEqual(snapshot["phase"], "failed")
        self.assertIn("typed failure", snapshot["error"]["message"])
        self.assertIn("host_effects", snapshot)
        self.assertFalse(self.driver.commands)

    def test_dedicated_fixed_session_keeps_state_and_closes_explicitly(self):
        """
        Prove session initialization has its own operation and repeated calls use the same stateful VM.
        证明会话初始化拥有独立操作，且重复调用使用相同有状态 VM。
        """
        pool = self.make_pool("local count=0; return {call=function(a) count=count+1; return count end}",
                              reuse="session", kind="dedicated")
        opening = self.take(pool.open_session(10000))
        # Session opening has its own trusted identity before any exported call or callback.
        # 在任何导出调用或回调前，会话开启已拥有自身可信身份。
        initialized = opening.initialization.wait(5)
        self.assertEqual(initialized["phase"], "succeeded")
        self.assertEqual(initialized["context"]["kind"], "module")
        self.assertEqual(initialized["context"]["caller"]["session_id"], opening.session.session_id)
        self.assertIsNone(initialized["context"]["export"])
        self.assertEqual(self.take(opening.session.status())["pool_id"], pool.pool_id)
        for expected in (1, 2):
            operation = self.take(opening.session.submit("call", None, self.context, 10000))
            # A later operation keeps the pinned session while acquiring a new operation identity.
            # 后续操作保持固定会话，同时取得新的操作身份。
            completed = operation.wait(5)
            self.assertEqual(completed["value"], expected)
            self.assertEqual(completed["context"]["caller"]["operation_id"], operation.operation_id)
            self.assertEqual(completed["context"]["caller"]["session_id"], opening.session.session_id)
            self.assertEqual(completed["context"]["export"], "call")
            self.take(operation.forget())
        self.take(opening.initialization.forget())
        self.take(opening.session.request_close())
        deadline = time.monotonic() + 5
        while self.take(opening.session.status())["phase"] != "closed":
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.001)
        self.take(opening.session.forget())
        self.take(pool.request_close())
        self.take(pool.forget())
        plugin = self.runtime.plugin(self.plugin_id)
        self.assertEqual(self.take(plugin.status())["retained_pools"], 0)
        self.take(plugin.request_close())
        self.take(plugin.forget())

    def test_reserve_initialize_and_release_obey_native_lifecycle(self):
        """
        Recreate the fixture through typed reserve and initialization; native release rejects a live runtime.
        通过类型预留及初始化重建夹具；原生释放拒绝仍存活的运行时。
        """
        self.take(self.runtime.request_close())
        deadline = time.monotonic() + 5
        while not self.take(self.runtime.status())["closed"]:
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.001)
        self.take(self.runtime.free())
        self.runtime_id = None
        pending = self.client.reserve()
        self.runtime = self.take(pending)
        self.runtime_id = self.runtime.runtime_id
        self.assertEqual(self.take(self.runtime.status())["initialization"], "reserved")
        self.take(self.runtime.initialize(create_engine_options(self.root, host_options={
            "system_lua_lib_dir": self.system_root.as_posix(), "allow_network_download": False,
        }), self.runtime_limits))
        self.assertEqual(self.take(self.runtime.status())["initialization"], "ready")
        premature = self.runtime.free()
        with self.assertRaises(EmbeddedRuntimeError) as error:
            premature.result(5)
        self.assertEqual(error.exception.code, "busy")
        premature.forget()
        plugin = self.take(self.runtime.register_plugin(self.plugin_id, {
            name: self.runtime_limits[name] for name in (
                "max_registered_pools", "max_sessions", "max_resident_vms", "max_running_calls",
                "max_queued_calls", "max_queued_bytes", "max_operations",
            )}))
        self.assertEqual(self.take(plugin.status())["plugin_id"], self.plugin_id)

    def test_actual_operation_handle_survives_failed_result_release(self):
        """
        Recover the typed operation identity after real admission but failed native buffer release, without replay.
        在实际入场但原生缓冲释放失败后恢复类型操作身份，不重放。
        """
        pool = self.make_pool("local count=0; return {call=function(a) count=count+1; return count end}")
        original_free = self.transport._result_free
        self.transport._result_free = lambda identity, result: EmbeddedNativeStatus.INTERNAL
        try:
            pending = pool.submit("call", None, self.context, 10000)
            with self.assertRaises(EmbeddedResultReleaseError):
                pending.result(5)
        finally:
            self.transport._result_free = original_free
        self.transport.release_results()
        operation = pending.delivered_result()
        self.assertEqual(operation.wait(5)["value"], 1)
        self.assertEqual(pending.delivered_result().operation_id, operation.operation_id)
        self.assertEqual(self.take(self.runtime.plugin(self.plugin_id).status())["retained_operations"], 1)
        pending.forget()

    def test_cancelled_polling_preserves_late_committed_host_effects(self):
        """
        Keep a real host callback alive across observer timeout and explicit cancellation, then retain its commit.
        在观察超时及显式取消后保持实际宿主回调存活，然后保留其提交证据。
        """
        pump = EmbeddedCallbackPump(self.transport, self.runtime_id, CallbackPumpConfig(
            max_concurrent_handlers=1, max_pending_commands=4, poll_interval_ms=1))
        self.addCleanup(pump.close, 5)
        entered = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)

        def handler(arguments, context):
            """
            Wait for the test gate and report an actual late commit; return an explicit null result.
            等待测试门控并报告实际迟到提交；返回显式空值结果。
            """
            entered.set()
            self.assertTrue(release.wait(5))
            context.report_effects("committed")
            return None

        pump.register([HostCapability({
            "name": "typed.callback", "version": "1.0.0", "description": "Typed client integration callback",
            "input_schema": True, "output_schema": True, "execution": "queued", "permissions": ["python.host"],
            "scope": "invocation", "max_concurrent": 1, "max_call_ms": 10000,
            "max_input_bytes": 1024, "max_output_bytes": 1024, "effects": "mutating", "idempotency": "none",
        }, handler, "sync")], 5)
        pool = self.make_pool("return {call=function(a) return vulcan.capabilities.call('typed.callback',a) end}")
        operation = self.take(pool.submit("call", None, self.context, 10000))
        self.assertTrue(entered.wait(2))
        with self.assertRaises(TimeoutError):
            operation.wait(0.01, poll_interval=0.001)

        async def observe():
            """
            Apply an asyncio observer timeout without cancelling native execution or occupying its worker.
            应用 asyncio 观察超时，不取消原生执行，也不占用其工作线程。
            """
            with self.assertRaises(asyncio.TimeoutError):
                await asyncio.wait_for(operation.wait_async(poll_interval=0.001), 0.01)

        asyncio.run(observe())
        # Cancelled read-only observations remain explicit receipts and can be consumed without mutation replay.
        # 已取消只读观察保持显式回执，可被消费而无需重放变更。
        for command in self.driver.commands:
            command.result(5)
            command.forget()
        self.assertFalse(self.take(operation.status())["cancellation_requested"])
        self.assertTrue(self.take(operation.cancel()))
        before_return = self.take(operation.status())
        self.assertTrue(before_return["cancellation_requested"])
        self.assertNotIn(before_return["phase"], ("succeeded", "failed", "cancelled"))
        release.set()
        outcome = operation.wait(5)
        self.assertTrue(any(effect["effects"] == "committed" for effect in outcome["host_effects"]), outcome)
        self.assertEqual(outcome["operation_id"], operation.operation_id)
        self.assertFalse(self.driver.commands)


if __name__ == "__main__":
    unittest.main()
