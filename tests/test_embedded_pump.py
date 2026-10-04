"""
Exercise the owned Python callback pump with actual Lua and the newly built native core.
使用实际 Lua 及新构建原生核心验证拥有型 Python 回调事件泵。
"""

from __future__ import annotations

import asyncio
import ctypes
import json
import os
import sys
import threading
import time
import unittest
from unittest.mock import patch

from luaskills import EmbeddedResultReleaseError, EmbeddedRuntimeError, EmbeddedTransportError
from luaskills.embedded_callbacks import HOST_CALLBACK_RUNTIME, HostCapability
from luaskills.embedded_contract import EmbeddedNativeStatus
from luaskills.embedded_pump import CallbackPumpConfig, EmbeddedCallbackPump
from test_embedded_native_e2e import EmbeddedNativeFixture


class PumpReleaseFault:
    """
    Fail one exact command's actual native result release while retaining its real success bytes.
    保留真实成功字节，同时使一个精确命令的实际原生结果释放失败。
    """

    def __init__(self, transport, kind):
        """
        Bind transport and exact kind; count successful selected deliveries, excluding empty queue polls.
        绑定 transport 及精确 kind；统计所选成功交付，不包含空队列轮询。
        """
        # Per-thread selection prevents unrelated driver or scope calls from receiving the injected failure.
        # 线程局部选择防止无关驱动器或作用域调用收到注入失败。
        self.transport = transport
        self.kind = kind
        self.local = threading.local()
        self.failed = threading.Event()
        self.successes = []
        self.original_request = transport._request_encoded
        self.original_free = transport._result_free

    def request(self, encoded):
        """
        Execute encoded unchanged and identify only this thread's runtime operation for release injection.
        原样执行 encoded，并仅标记此线程的运行时操作用于释放注入。
        Return the real result or the original transport error.
        返回真实结果或原始传输错误。
        """
        command = json.loads(encoded)["command"]
        self.local.selected = command["type"] == "runtime" and command["operation"]["type"] == self.kind
        try:
            return self.original_request(encoded)
        finally:
            self.local.selected = False

    def free(self, identity, result):
        """
        Return one native release failure for a proven success; all other identity/result pairs free normally.
        对已证明成功返回一次原生释放失败；所有其他 identity/result 对正常释放。
        """
        if getattr(self.local, "selected", False):
            envelope = json.loads(ctypes.string_at(result.ptr, result.len))
            if envelope["status"] == "ok" and (self.kind != "host_requests_take" or envelope["result"]):
                self.successes.append(envelope["result"])
                if not self.failed.is_set():
                    self.failed.set()
                    return EmbeddedNativeStatus.INTERNAL
        return self.original_free(identity, result)

    def __enter__(self):
        """
        Install exact request/release interception and return this fault's observable evidence.
        安装精确请求／释放拦截，并返回此故障的可观察证据。
        """
        self.transport._request_encoded = self.request
        self.transport._result_free = self.free
        return self

    def __exit__(self, kind, error, traceback):
        """
        Restore both native adapters after the test body; preserve any kind/error/traceback by returning nothing.
        测试主体结束后恢复两个原生适配器；无返回值以保留 kind/error/traceback。
        """
        self.transport._request_encoded = self.original_request
        self.transport._result_free = self.original_free


@unittest.skipUnless(os.environ.get("LUASKILLS_LIB"), "LUASKILLS_LIB is not configured")
class EmbeddedPumpIntegrationTests(EmbeddedNativeFixture, unittest.TestCase):
    """
    Verify real handler lifetime, owned loops, cancellation and acknowledgement recovery through the core queue.
    通过核心队列验证实际处理器寿命、拥有循环、取消及确认恢复。
    """

    def setUp(self):
        """
        Start one independently owned callback loop after the shared native runtime is ready.
        共享原生运行时就绪后启动一个独立拥有的回调循环。
        """
        super().setUp()
        self.pump_config = CallbackPumpConfig(max_concurrent_handlers=1, max_pending_commands=4, poll_interval_ms=2)
        self.pump = EmbeddedCallbackPump(self.transport, self.runtime_id, self.pump_config)
        self.addCleanup(self.pump.close, 5)

    def capability(self, handler, mode="sync"):
        """
        Bind an exact queued mutating descriptor to the test's explicit Python handler mode.
        将精确队列变更描述符绑定到测试的显式 Python 处理器模式。
        """
        return HostCapability({
            "name":"python.callback", "version":"1.0.0", "description":"Python pump integration callback",
            "input_schema":True, "output_schema":True, "execution":"queued", "permissions":["python.host"],
            "scope":"invocation", "max_concurrent":2, "max_call_ms":10000,
            "max_input_bytes":1024, "max_output_bytes":1024, "effects":"mutating", "idempotency":"none",
        }, handler, mode)

    def callback_pool(self):
        """
        Register a real Lua module that calls the snapshot-bound Python capability.
        注册调用绑定快照 Python 能力的实际 Lua 模块。
        """
        return self.pool("return {call=function(a) return vulcan.capabilities.call('python.callback',a) end}")

    def wait_for(self, predicate):
        """
        Wait for observable ownership transitions within a finite test deadline.
        在有限测试截止时间内等待可观察所有权转换。
        """
        deadline = time.monotonic() + 5
        while not predicate():
            self.assertLess(time.monotonic(), deadline, self.pump.status)
            time.sleep(0.001)

    def test_unsafe_integer_completion_keeps_committed_ledger(self):
        """
        Complete an unsafe integer callback once, preserve committed effects and prove subsequent reuse.
        单次完成不安全整数回调、保留已提交副作用并证明后续复用。
        Return nothing after pump closure proves no pending callback ownership.
        泵关闭证明没有待处理回调所有权后无返回值。
        """
        # Exact request identities bind assertions to the original ledger rather than array positions.
        # 精确请求身份将断言绑定到原账本，而非数组位置。
        requests = []

        def handler(value, context):
            """
            Record context's request, report actual commit and return a wide integer only for unsafe value.
            记录 context 的请求、报告实际提交，仅对 unsafe value 返回宽整数。
            """
            requests.append(context.request_id)
            context.report_effects("committed")
            return 2**64 - 1 if value == "unsafe" else value

        self.pump.register([self.capability(handler)], timeout=5)
        # One reusable Lua module returns the full capability envelope without asserting success.
        # 同一个可复用 Lua 模块返回完整能力信封，不断言能力成功。
        pool_id = self.callback_pool()
        rejected = self.terminal(self.submit(pool_id, "unsafe"))
        self.assertEqual(rejected["phase"], "succeeded", rejected)
        # A single committed callback does not determine the effects of the complete Lua execution.
        # 单次已提交回调不能确定完整 Lua 执行的副作用。
        self.assertEqual(rejected["effects"], "unknown")
        self.assertFalse(rejected["value"]["ok"])
        self.assertEqual(rejected["value"]["error"]["code"], "invalid_argument")
        self.assertEqual(rejected["value"]["effects"], "committed")
        # Find the exact original callback's retained completion evidence.
        # 查找精确原回调保留的完成证据。
        effect = next(entry for entry in rejected["host_effects"] if entry["request_id"] == requests[0])
        self.assertEqual(effect["phase"], "completed")
        self.assertEqual(effect["effects"], "committed")
        self.assertEqual(self.terminal(self.submit(pool_id, "normal"))["value"]["value"], "normal")
        self.pump.close(5)
        self.assertEqual(len(requests), 2)
        self.assertIsNone(self.pump.status["failure"])
        self.assertEqual(self.pump.status["request_ids"], ())
        self.assertEqual(self.pump.status["pending_acknowledgements"], ())

    def test_sync_callback_receives_trusted_identity_and_preserves_null(self):
        """
        Invoke a synchronous handler off the pump loop and preserve explicit host commit and successful null.
        在事件泵循环外调用同步处理器，并保留显式宿主提交及成功空值。
        """
        # Retain the actual trusted callback identity independently of the final operation response.
        # 独立于最终操作响应，保留真实可信回调身份。
        callers = []
        def handler(arguments, context):
            """
            Check authenticated identity separately from arguments, then report an actual test commit.
            独立于参数检查已认证身份，随后报告实际测试提交。
            """
            self.assertEqual(context.caller["plugin_id"], self.plugin_id)
            callers.append(dict(context.caller))
            self.assertEqual(arguments["plugin_id"], "forged")
            self.assertEqual(HOST_CALLBACK_RUNTIME.get(), self.runtime_id)
            self.assertIsNot(threading.current_thread(), self.pump._thread)
            with self.assertRaises(TypeError):
                context.caller["plugin_id"] = "changed"
            context.report_effects("committed")
            return None

        registration, = self.pump.register([self.capability(handler)], timeout=5)
        operation = self.submit(self.callback_pool(), {"plugin_id":"forged"})
        done = self.terminal(operation)
        self.assertEqual(done["value"], {"ok":True, "value":None, "effects":"committed"}, done)
        self.assertEqual([effect["caller"] for effect in done["host_effects"] if effect["registration_id"] == registration], callers)
        self.assertTrue(any(effect["effects"] == "committed" for effect in done["host_effects"]))
        self.pump.unregister(registration, timeout=5)
        self.assertEqual(self.pump.status["registration_ids"], ())
        self.assertIsNone(self.pump.status["failure"])

    def test_async_callback_survives_caller_loop_cancellation_and_closure(self):
        """
        Caller-loop cancellation cannot cancel the pump's handler, unregister owner or late completion acknowledgement.
        调用方循环取消不能取消事件泵处理器、注销所有者或迟到完成确认。
        """
        entered = threading.Event()
        cancelled = threading.Event()
        release = threading.Event()
        operations = []

        async def handler(arguments, context):
            """
            Observe real core cancellation on the owned loop, then remain active until the external test gate opens.
            在拥有循环上观察实际核心取消，随后保持活动直到外部测试门打开。
            """
            self.assertIs(asyncio.get_running_loop(), self.pump._loop)
            entered.set()
            await context.wait_cancelled_async()
            cancelled.set()
            while not release.is_set():
                await asyncio.sleep(0.001)
            context.report_effects("committed")
            return {"done":True}

        async def caller():
            """
            Cancel only an observer waiting for unregister, then close this unrelated caller loop.
            仅取消等待注销的观察者，随后关闭此无关调用方循环。
            """
            registration, = await self.pump.register_async([self.capability(handler, "async")])
            operations.append(self.submit(self.callback_pool(), None))
            self.assertTrue(await asyncio.to_thread(entered.wait, 5))
            waiting = asyncio.create_task(self.pump.unregister_async(registration))
            # Unregister drains dispatched handlers; only explicit operation cancellation supplies this cancellation signal.
            # 注销会排空已分发处理器；只有显式操作取消提供此取消信号。
            self.command({"type":"operation_cancel", "operation_id":operations[0]})
            self.assertTrue(await asyncio.to_thread(cancelled.wait, 5))
            waiting.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await waiting

        try:
            asyncio.run(caller())
            self.assertTrue(self.pump.status["request_ids"])
            self.assertTrue(self.pump._thread.is_alive())
        finally:
            release.set()
        done = self.terminal(operations[0])
        self.assertTrue(any(effect["effects"] == "committed" for effect in done["host_effects"]), done)
        asyncio.run(self.pump.close_async())
        self.assertTrue(self.pump.status["closed"])
        self.assertIsNone(self.pump.status["failure"])

    def test_close_timeout_preserves_running_sync_handler_and_core_ownership(self):
        """
        A handler that ignores cancellation keeps both its closure and native capacity until its real return.
        忽略取消的处理器在真实返回前同时保留闭包及原生容量。
        """
        entered = threading.Event()
        release = threading.Event()

        def handler(arguments, context):
            """
            Hold actual synchronous work past close and report a late committed effect.
            在关闭之后保持实际同步工作，并报告迟到已提交副作用。
            """
            entered.set()
            self.assertTrue(release.wait(5))
            context.report_effects("committed")
            return None

        registration, = self.pump.register([self.capability(handler)], timeout=5)
        operation = self.submit(self.callback_pool(), None)
        try:
            self.assertTrue(entered.wait(5))
            with self.assertRaises(TimeoutError):
                self.pump.close(timeout=0.01)
            self.assertTrue(self.pump.status["request_ids"])
            self.assertFalse(self.command({"type":"capability_status", "registration_id":registration})["drained"])
            with self.assertRaises(RuntimeError):
                self.transport.free()
        finally:
            release.set()
        self.pump.close(timeout=5)
        done = self.terminal(operation)
        self.assertTrue(any(effect["effects"] == "committed" for effect in done["host_effects"]), done)
        self.assertTrue(self.pump.status["closed"])

    def test_exceptions_and_invalid_results_preserve_committed_effects(self):
        """
        Exceptions and invalid JSON after host commit become bounded failures without erasing transaction evidence.
        宿主提交后的异常及无效 JSON 成为有界失败，不抹除事务证据。
        """
        def handler(arguments, context):
            """
            Commit first, then deliberately fail through Python exception or an unserializable value.
            先提交，随后通过 Python 异常或不可序列化值故意失败。
            """
            context.report_effects("committed")
            if arguments == "raise":
                raise ValueError("secret must not enter Lua error diagnostics")
            if arguments == "oversized":
                return "x" * self.transport.config.max_request_bytes
            if arguments == "deeply-nested":
                # The result exceeds parser nesting while remaining below the transport's byte ceiling.
                # 结果超过解析器嵌套限制，同时仍低于传输字节上限。
                value = None
                for _ in range(sys.getrecursionlimit() * 2):
                    value = [value]
                return value
            if arguments == "unknown-code":
                raise EmbeddedRuntimeError("custom-code-outside-core-contract", "secret host error")
            return {object()}

        self.pump.register([self.capability(handler)], timeout=5)
        pool_id = self.callback_pool()
        for arguments in ("raise", "invalid-json", "oversized", "deeply-nested", "unknown-code"):
            done = self.terminal(self.submit(pool_id, arguments))
            outcome = done["value"]
            self.assertFalse(outcome["ok"], done)
            self.assertEqual(outcome["effects"], "committed")
            self.assertNotIn("secret", outcome["error"]["message"])
            self.assertTrue(any(effect["effects"] == "committed" for effect in done["host_effects"]))
        self.assertIsNone(self.pump.status["failure"])

    def _exercise_invalid_completion_effect_snapshot(self, mode, result_kind):
        """
        Execute one real callback in mode with invalid/oversized result_kind and verify its returned effect snapshot.
        以 mode 执行一个真实回调并返回非法或超限的 result_kind，验证返回时的副作用快照。
        Return nothing after the real acknowledgement, mutator thread and pump ownership have drained.
        真实确认、修改线程及事件泵所有权排空后无返回值。
        """
        # One deadline bounds both coordination waits without changing the native callback budget.
        # 同一个期限约束两个协调等待，不改变原生回调预算。
        wait_seconds = 5
        # The encoding window proves that production has already captured the returned committed snapshot.
        # 编码窗口证明生产方法已经捕获返回时的已提交快照。
        encoding_entered = threading.Event()
        late_reported = threading.Event()
        # Retain the actual handler's context alias, separately from the core completion record.
        # 保留实际处理器的上下文别名，与核心完成记录分别保存。
        retained_context = None
        # Actual request identities and encoding attempts expose replay or replacement-frame mistakes.
        # 实际请求身份及编码次数暴露重放或替代帧错误。
        handler_requests = []
        encoding_observations = []
        thread_errors = []
        # Preserve the original bound production method; the wrapper only coordinates the first window.
        # 保留原绑定生产方法；包装器仅协调首次窗口。
        original_encode = self.pump._encode_completion

        def handler(arguments, context):
            """
            Retain context, report committed and return the declared bad value; arguments carries no authority.
            保留 context、报告已提交并返回声明的坏值；arguments 不携带权威。
            Return an actual set or a string exceeding the owning transport's original encoding limit.
            返回真实集合，或超过所属传输原编码上限的字符串。
            """
            nonlocal retained_context
            retained_context = context
            handler_requests.append(context.request_id)
            context.report_effects("committed")
            return {object()} if result_kind == "invalid" else "x" * self.transport.config.max_request_bytes

        async def async_handler(arguments, context):
            """
            Invoke the same actual handler on the pump loop with arguments/context and return its bad value.
            在泵循环以 arguments/context 调用同一实际处理器并返回其坏值。
            """
            return handler(arguments, context)

        def mutate_after_return():
            """
            Wait for the original returned snapshot, then modify only the retained context alias on this thread.
            等待原返回快照，随后仅在本线程修改保留的上下文别名。
            Return nothing and retain any thread error for assertions on the test thread.
            无返回值，将线程错误保留给测试线程断言。
            """
            try:
                if not encoding_entered.wait(wait_seconds):
                    raise TimeoutError("callback did not reach its original encoding window")
                if retained_context is None:
                    raise RuntimeError("actual returned callback context is unavailable")
                retained_context.report_effects("rolled_back")
            except BaseException as error:
                thread_errors.append(error)
            finally:
                late_reported.set()

        def encode_after_late_report(record):
            """
            Observe record's real outcome and release the mutator before calling the unchanged production encoder.
            观察 record 的真实结果，释放修改线程后调用未修改的生产编码器。
            Return original encoded bytes or its actual invalid/oversized-value exception without substitution.
            返回原编码字节或其真实非法／超限异常，不提供替代结果。
            """
            if not encoding_entered.is_set():
                self.assertTrue(record.outcome["ok"])
                self.assertEqual(record.outcome["effects"], "committed")
                encoding_entered.set()
                self.assertTrue(late_reported.wait(wait_seconds))
            encoding_observations.append((record.context.request_id, record.outcome["effects"]))
            return original_encode(record)

        # Each test method owns a fresh real registration/pool, preventing same-name generation cross-talk.
        # 每个测试方法拥有全新的真实注册／池，避免同名代次串扰。
        selected_handler = handler if mode == "sync" else async_handler
        self.pump.register([self.capability(selected_handler, mode)], timeout=wait_seconds)
        # This independent thread changes the public alias only after the actual handler has returned.
        # 此独立线程仅在实际处理器返回后修改公开别名。
        mutator = threading.Thread(target=mutate_after_return, name="callback-late-effects")
        mutator.start()
        try:
            with patch.object(self.pump, "_encode_completion", side_effect=encode_after_late_report):
                # Admission, Lua execution and acknowledgement all use the matching real Core DLL.
                # 入场、Lua执行及确认均使用匹配的真实Core动态库。
                done = self.terminal(self.submit(self.callback_pool(), result_kind))
        finally:
            encoding_entered.set()
            mutator.join(wait_seconds)
            self.pump.close(wait_seconds)
        self.assertFalse(mutator.is_alive())
        self.assertEqual(thread_errors, [])
        self.assertEqual(retained_context.effects, "rolled_back")
        self.assertEqual(handler_requests, [retained_context.request_id])
        self.assertEqual(len(encoding_observations), 2)
        self.assertEqual(done["phase"], "succeeded", done)
        self.assertFalse(done["value"]["ok"])
        self.assertEqual(done["value"]["error"], {"code": "execution_failed",
            "message": "Python host callback produced an invalid or oversized result"})
        # Find the original effect by identity, never by ledger order or a mutable array index.
        # 按身份查找原副作用，不绑定账本顺序或可变数组下标。
        effect = next(entry for entry in done["host_effects"] if entry["request_id"] == retained_context.request_id)
        self.assertEqual(effect["registration_id"], retained_context.registration_id)
        self.assertEqual(effect["phase"], "completed")
        self.assertTrue(self.pump.status["closed"])
        self.assertIsNone(self.pump.status["failure"])
        self.assertEqual(self.pump.status["registration_ids"], ())
        self.assertEqual(self.pump.status["request_ids"], ())
        self.assertEqual(self.pump.status["pending_acknowledgements"], ())
        self.assertEqual(self.pump.status["pending_commands"], 0)
        self.assertIsNone(self.pump.status["pending_native_command"])
        self.assertFalse(self.pump.status["recovery_required"])
        # Both actual Lua return and the retained Core ledger must use the same original committed snapshot.
        # 实际Lua返回与保留的Core账本必须使用同一个原始已提交快照。
        self.assertEqual({"lua": done["value"]["effects"], "ledger": effect["effects"]},
            {"lua": "committed", "ledger": "committed"}, (mode, result_kind, encoding_observations))

    def test_sync_invalid_completion_keeps_returned_effect_snapshot(self):
        """Verify one synchronous invalid-JSON callback retains its returned effects; return nothing.
        验证一个同步非法JSON回调保留返回时副作用；无返回值。
        """
        self._exercise_invalid_completion_effect_snapshot("sync", "invalid")

    def test_sync_oversized_completion_keeps_returned_effect_snapshot(self):
        """Verify one synchronous oversized callback retains its returned effects; return nothing.
        验证一个同步超限回调保留返回时副作用；无返回值。
        """
        self._exercise_invalid_completion_effect_snapshot("sync", "oversized")

    def test_async_invalid_completion_keeps_returned_effect_snapshot(self):
        """Verify one asynchronous invalid-JSON callback retains its returned effects; return nothing.
        验证一个异步非法JSON回调保留返回时副作用；无返回值。
        """
        self._exercise_invalid_completion_effect_snapshot("async", "invalid")

    def test_async_oversized_completion_keeps_returned_effect_snapshot(self):
        """Verify one asynchronous oversized callback retains its returned effects; return nothing.
        验证一个异步超限回调保留返回时副作用；无返回值。
        """
        self._exercise_invalid_completion_effect_snapshot("async", "oversized")

    def test_bounded_handlers_leave_queued_requests_cancellable_without_execution(self):
        """
        SDK handler capacity limits take size so a second queued callback can cancel before Python executes it.
        SDK 处理器容量限制取得批次数，使第二个排队回调能在 Python 执行前取消。
        """
        entered = threading.Event()
        release = threading.Event()
        calls = []

        def handler(arguments, context):
            """
            Hold the only SDK handler slot until the test explicitly releases it.
            保持唯一 SDK 处理器名额，直到测试显式释放。
            """
            calls.append(arguments)
            entered.set()
            self.assertTrue(release.wait(5))
            context.report_effects("committed")
            return arguments

        self.pump.register([self.capability(handler)], timeout=5)
        pool_id = self.callback_pool()
        first = self.submit(pool_id, "first")
        try:
            self.assertTrue(entered.wait(5))
            second = self.submit(pool_id, "second")
            self.wait_for(lambda: self.command({"type":"operation_status", "operation_id":second})["phase"] == "waiting_for_host")
            self.assertEqual(len(self.pump.status["request_ids"]), 1)
            self.command({"type":"operation_cancel", "operation_id":second})
            self.assertEqual(self.terminal(second)["phase"], "cancelled")
        finally:
            release.set()
        self.assertEqual(self.terminal(first)["phase"], "succeeded")
        self.assertEqual(calls, ["first"])

    def test_acknowledgement_failure_retains_result_without_replaying_handler(self):
        """
        Explicit completion delivery retry recovers capacity without executing an external mutation twice.
        显式完成交付重试恢复容量，不执行两次外部变更。
        """
        calls = []
        failed = threading.Event()
        actual_request = self.transport._request_encoded

        def request(encoded):
            """
            Fail exactly one completion before native dispatch, preserving all other actual core calls.
            在原生分发前精确失败一次完成，同时保留其余实际核心调用。
            """
            command = json.loads(encoded)["command"]
            if command["type"] == "runtime" and command["operation"]["type"] == "host_request_complete" and not failed.is_set():
                failed.set()
                raise EmbeddedTransportError("luaskills_ffi_embedded_request_v1", 4)
            return actual_request(encoded)

        def handler(arguments, context):
            """
            Record one actual host mutation and retain its committed evidence for retrying acknowledgement only.
            记录一次实际宿主变更，并保留其已提交证据，仅供重试确认。
            """
            calls.append(arguments)
            context.report_effects("committed")
            return None

        self.pump.register([self.capability(handler)], timeout=5)
        with patch.object(self.transport, "_request_encoded", side_effect=request):
            operation = self.submit(self.callback_pool(), "once")
            self.assertTrue(failed.wait(5))
            self.wait_for(lambda: bool(self.pump.status["pending_acknowledgements"]))
            self.pump.retry_acknowledgements(timeout=5)
        self.pump.close(timeout=5)
        done = self.terminal(operation)
        self.assertTrue(any(effect["effects"] == "committed" for effect in done["host_effects"]))
        self.assertEqual(calls, ["once"])
        self.assertEqual(self.pump.status["pending_acknowledgements"], ())

    def test_duplicate_owner_and_failed_startup_do_not_leak_transport_claims(self):
        """
        Refuse duplicate consumers and release startup-only ownership after a missing runtime error.
        拒绝重复消费者，并在运行时缺失错误后释放仅启动期所有权。
        """
        with self.assertRaisesRegex(RuntimeError, "already has"):
            EmbeddedCallbackPump(self.transport, self.runtime_id, self.pump_config)
        self.pump.close(timeout=5)
        with self.assertRaises(EmbeddedRuntimeError) as error:
            EmbeddedCallbackPump(self.transport, "missing-runtime", self.pump_config)
        self.assertEqual(error.exception.code, "not_found")
        self.assertFalse(self.transport._callback_pumps)

    def test_lost_completion_receipt_reconciles_exact_core_evidence_without_resending(self):
        """
        Reconcile a lost native success receipt without sending the completion mutation a second time.
        对账丢失的原生成功回执，不再次发送完成变更。
        """
        self._exercise_lost_completion_receipt("luaskills_ffi_embedded_request_v1", 6)

    def test_result_release_rejection_does_not_rewrite_completed_host_result(self):
        """
        A result-release InvalidArgument follows dispatch and cannot authorize replacing the actual callback result.
        结果释放 InvalidArgument 发生在分发后，不能授权替换实际回调结果。
        """
        self._exercise_lost_completion_receipt("luaskills_ffi_embedded_result_free_v1", 1)

    def _exercise_lost_completion_receipt(self, function_name, status):
        """
        Recover a lost success receipt from the exact core effect record without replaying handler or completion mutation.
        从精确核心副作用记录恢复丢失的成功回执，不重放处理器或完成变更。
        """
        failed = threading.Event()
        mutations = []
        completions = []
        actual_request = self.transport._request_encoded

        def request(encoded):
            """
            Drop only the first successful completion receipt after the actual native mutation and buffer release.
            仅在实际原生变更及缓冲释放后丢弃首次成功完成回执。
            """
            command = json.loads(encoded)["command"]
            completion = command["type"] == "runtime" and command["operation"]["type"] == "host_request_complete"
            result = actual_request(encoded)
            if completion:
                completions.append(command["operation"]["request_id"])
                if not failed.is_set():
                    failed.set()
                    raise EmbeddedTransportError(function_name, status)
            return result

        def handler(arguments, context):
            """
            Mutate once and publish committed evidence before any transport acknowledgement is attempted.
            变更一次，并在尝试任何传输确认前发布已提交证据。
            """
            mutations.append(arguments)
            context.report_effects("committed")
            return None

        self.pump.register([self.capability(handler)], timeout=5)
        with patch.object(self.transport, "_request_encoded", side_effect=request):
            operation = self.submit(self.callback_pool(), "one-mutation")
            self.assertTrue(failed.wait(5))
            done = self.terminal(operation)
            self.wait_for(lambda: bool(self.pump.status["pending_acknowledgements"]))
            self.pump.retry_acknowledgements(timeout=5)
        self.pump.close(timeout=5)
        self.assertEqual(mutations, ["one-mutation"])
        self.assertEqual(len(completions), 1)
        self.assertTrue(any(effect["request_id"] == completions[0] and effect["phase"] == "completed"
            for effect in done["host_effects"]))
        self.assertEqual(self.pump.status["pending_acknowledgements"], ())

    def test_cancelled_observers_keep_bounded_control_command_ownership(self):
        """
        Cancelled asyncio observers cannot release admission for unregister tasks still waiting on a real handler.
        已取消 asyncio 观察者不能释放仍等待实际处理器的注销任务入场。
        """
        entered = threading.Event()
        release = threading.Event()

        def handler(arguments, context):
            """
            Keep one handler active while several callers stop observing their exact unregister operations.
            多个调用方停止观察其精确注销操作期间，保持一个处理器活动。
            """
            entered.set()
            self.assertTrue(release.wait(5))
            context.report_effects("committed")
            return None

        registration, = self.pump.register([self.capability(handler)], timeout=5)
        operation = self.submit(self.callback_pool(), None)

        async def caller():
            """
            Fill the real pending-command budget, cancel observers, then prove new admission is still refused.
            填满实际待完成命令预算、取消观察者，随后证明仍拒绝新入场。
            """
            waiting = [asyncio.create_task(self.pump.unregister_async(registration))
                for _ in range(self.pump_config.max_pending_commands)]
            while self.pump.status["pending_commands"] != self.pump_config.max_pending_commands:
                await asyncio.sleep(0)
            for observer in waiting:
                observer.cancel()
            await asyncio.gather(*waiting, return_exceptions=True)
            with self.assertRaises(EmbeddedRuntimeError) as error:
                await self.pump.unregister_async(registration)
            self.assertEqual(error.exception.code, "capacity_exceeded")

        try:
            self.assertTrue(entered.wait(5))
            asyncio.run(caller())
            self.assertEqual(self.pump.status["pending_commands"], self.pump_config.max_pending_commands)
        finally:
            release.set()
        self.terminal(operation)
        self.wait_for(lambda: self.pump.status["pending_commands"] == 0)
        self.assertFalse(self.pump._command_futures)

    def test_mismatched_completion_evidence_keeps_the_original_request_owned(self):
        """
        Reject another request's completed status during recovery and preserve the actual unfinished acknowledgement.
        恢复时拒绝其他请求的已完成状态，并保留实际未完成确认。
        """
        original_request = self.transport._request_encoded
        failed = threading.Event()
        corrupt = threading.Event()
        corrupt.set()
        calls = []

        def request(encoded):
            """
            Reject one completion before entry, then substitute wrong status identity only during failed recovery.
            在入场前拒绝一次完成，然后仅在失败恢复期间替换错误状态身份。
            Return unchanged native results for every other command.
            其他命令均返回未经更改的原生结果。
            """
            command = json.loads(encoded)["command"]
            if command["type"] == "runtime":
                kind = command["operation"]["type"]
                if kind == "host_request_complete" and not failed.is_set():
                    failed.set()
                    raise EmbeddedTransportError("luaskills_ffi_embedded_request_v1", EmbeddedNativeStatus.CAPACITY_EXCEEDED)
                result = original_request(encoded)
                if kind == "host_request_status" and failed.is_set() and corrupt.is_set():
                    result = dict(result, request_id="another-request", phase="completed")
                return result
            return original_request(encoded)

        def handler(arguments, context):
            """
            Commit arguments once through context and return null; retries may only acknowledge this result.
            通过 context 提交 arguments 一次并返回空值；重试只能确认此结果。
            """
            calls.append(arguments)
            context.report_effects("committed")
            return None

        self.pump.register([self.capability(handler)], 5)
        pool = self.callback_pool()
        with patch.object(self.transport, "_request_encoded", side_effect=request):
            operation = self.submit(pool, "identity-proof")
            self.assertTrue(failed.wait(5))
            self.wait_for(lambda: self.pump.recovery_required)
            retained = self.pump.status["request_ids"]
            try:
                with self.assertRaisesRegex(RuntimeError, "mismatched identity"):
                    self.pump.retry_acknowledgements(5)
                self.assertEqual(self.pump.status["request_ids"], retained)
                self.assertTrue(self.pump.recovery_required)
            finally:
                corrupt.clear()
                self.pump.retry_acknowledgements(5)
            self.pump.close(5)
        done = self.terminal(operation)
        self.assertEqual(calls, ["identity-proof"])
        self.assertTrue(any(effect["request_id"] in retained and effect["effects"] == "committed"
                            for effect in done["host_effects"]))

    def test_rejected_registration_does_not_leave_an_uncertain_mutation(self):
        """
        Keep proven business rejection separate from lost delivery and allow the valid handler to drain normally.
        区分已证明业务拒绝与丢失交付，并允许有效处理器正常排空。
        """
        capability = self.capability(lambda arguments, context: None)
        with self.assertRaises(EmbeddedRuntimeError):
            self.pump.register([], 5)
        identity = self.pump.register([capability], 5)
        with self.assertRaises(EmbeddedRuntimeError):
            self.pump.register([capability], 5)
        self.assertEqual(self.pump.status["registration_ids"], identity)
        self.assertNotEqual(self.pump.status["pending_native_command"], "capabilities_register")
        self.assertFalse(self.pump.recovery_required)
        self.assertFalse(self.pump.status["closing"])

    def test_missing_copied_receipt_preserves_owner_until_original_evidence_recovers(self):
        """
        Refuse replay when copied registration evidence is unavailable, then recover only the restored original bytes.
        复制注册证据不可用时拒绝重放，然后仅从恢复的原始字节继续。
        """
        with PumpReleaseFault(self.transport, "capabilities_register") as fault:
            with self.assertRaises(EmbeddedResultReleaseError) as caught:
                self.pump.register([self.capability(lambda arguments, context: None)], 5)
            original_bytes = caught.exception.response_bytes
            try:
                # Corrupt the test adapter's retained evidence without changing the already executed native mutation.
                # 损坏测试适配器的保留证据，不改变已执行原生变更。
                caught.exception._response_bytes = None
                with self.assertRaisesRegex(RuntimeError, "no copied embedded response"):
                    self.pump.retry_acknowledgements(5)
                self.assertTrue(self.pump.recovery_required)
                self.assertEqual(self.pump.status["pending_native_command"], fault.kind)
                self.assertEqual(len(fault.successes), 1)
                self.assertFalse(self.transport._results)
                with self.assertRaises(TimeoutError):
                    self.pump.close(0.01)
            finally:
                # Restore exact captured test evidence solely to prove recovery and release real fixture resources.
                # 仅为证明恢复及释放真实夹具资源，恢复测试捕获的精确原始证据。
                caught.exception._response_bytes = original_bytes
                self.pump.retry_acknowledgements(5)
                self.pump.close(5)
            self.assertEqual(len(fault.successes), 1)

    def test_register_release_failure_recovers_original_handler_ownership(self):
        """
        Recover successful registration from copied bytes without registering again or dropping its handler owner.
        从复制字节恢复成功注册，不再次注册或丢弃其处理器所有者。
        """
        with PumpReleaseFault(self.transport, "capabilities_register") as fault:
            with self.assertRaises(EmbeddedResultReleaseError):
                self.pump.register([self.capability(lambda arguments, context: None)], 5)
            self.assertTrue(self.pump.recovery_required)
            self.assertEqual(self.pump.status["registration_ids"], ())
            self.assertEqual(self.pump.status["pending_native_command"], fault.kind)
            self.assertTrue(self.transport._results)
            self.pump.retry_acknowledgements(5)
            self.pump.close(5)
            self.assertEqual(len(fault.successes), 1)
            self.assertFalse(self.transport._results)
            self.assertFalse(self.pump.recovery_required)

    def test_take_release_failure_retains_batch_and_executes_handler_once(self):
        """
        Keep a delivered native request batch until copied receipt recovery, then execute its handler once.
        保留已交付原生请求批次直到复制回执恢复，然后执行处理器一次。
        """
        calls = []

        def handler(arguments, context):
            """
            Record arguments once and publish committed effects through context before returning null.
            记录 arguments 一次，并在返回空值前通过 context 发布已提交副作用。
            """
            calls.append(arguments)
            context.report_effects("committed")
            return None

        self.pump.register([self.capability(handler)], 5)
        pool = self.callback_pool()
        with PumpReleaseFault(self.transport, "host_requests_take") as fault:
            operation = self.submit(pool, "delivered-once")
            self.assertTrue(fault.failed.wait(5))
            self.wait_for(lambda: self.pump.recovery_required)
            self.assertEqual(calls, [])
            self.assertEqual(self.pump.status["request_ids"], ())
            self.assertTrue(self.transport._results)
            self.pump.retry_acknowledgements(5)
            self.pump.close(5)
            done = self.terminal(operation)
            self.assertEqual(calls, ["delivered-once"])
            self.assertEqual(len(fault.successes), 1)
            request = fault.successes[0][0]
            self.assertTrue(any(effect["request_id"] == request["request_id"]
                and effect["registration_id"] == request["registration_id"] and effect["effects"] == "committed"
                for effect in done["host_effects"]))
            self.assertFalse(self.pump.recovery_required)

    def test_unregister_release_failure_never_repeats_native_retirement(self):
        """
        Preserve a successful retirement receipt until explicit recovery and dispatch unregister exactly once.
        保留成功退役回执直到显式恢复，并精确分发注销一次。
        """
        identities = self.pump.register([self.capability(lambda arguments, context: None)], 5)
        with PumpReleaseFault(self.transport, "capability_unregister") as fault:
            with self.assertRaises(EmbeddedResultReleaseError):
                self.pump.unregister(identities[0], 5)
            self.assertTrue(self.pump.recovery_required)
            with self.assertRaises(TimeoutError):
                self.pump.close(0.01)
            self.assertEqual(len(fault.successes), 1)
            self.pump.retry_acknowledgements(5)
            self.pump.close(5)
            self.assertEqual(len(fault.successes), 1)
            self.assertFalse(self.pump.recovery_required)

    def test_forget_release_failure_recovers_removal_without_querying_missing_registration(self):
        """
        Recover a removed registration from its retained null receipt instead of polling missing native metadata.
        从保留空回执恢复已移除注册，不轮询缺失原生元数据。
        """
        identities = self.pump.register([self.capability(lambda arguments, context: None)], 5)
        with PumpReleaseFault(self.transport, "capability_forget") as fault:
            self.pump.request_close()
            self.assertTrue(fault.failed.wait(5))
            self.wait_for(lambda: self.pump.recovery_required)
            self.assertEqual(self.pump.status["registration_ids"], identities)
            with self.assertRaises(TimeoutError):
                self.pump.close(0.01)
            self.pump.retry_acknowledgements(5)
            self.pump.close(5)
            self.assertEqual(len(fault.successes), 1)
            self.assertEqual(self.pump.status["registration_ids"], ())
            self.assertFalse(self.transport._results)

    def test_recovery_has_one_reserved_attempt_when_unregister_commands_are_full(self):
        """
        Recover a failed completion with every ordinary command occupied, sharing one reserved recovery attempt.
        在每个普通命令槽都被占用时恢复失败完成，共享一个预留恢复尝试。
        """
        entered = threading.Event()
        release = threading.Event()
        recovering = threading.Event()
        resume = threading.Event()
        self.addCleanup(release.set)
        self.addCleanup(resume.set)
        calls = []

        def handler(arguments, context):
            """
            Hold arguments until release and report one committed mutation through context before returning.
            保持 arguments 直到 release，并在返回前通过 context 报告一次已提交变更。
            """
            calls.append(arguments)
            entered.set()
            self.assertTrue(release.wait(5))
            context.report_effects("committed")
            return None

        original_release = self.transport.release_results

        def release_results():
            """
            Hold real buffer recovery until resume to expose concurrent observer admission; return after release.
            保持真实缓冲恢复直到 resume 以暴露并发观察者入场；释放后返回。
            """
            recovering.set()
            self.assertTrue(resume.wait(5))
            original_release()

        identity = self.pump.register([self.capability(handler)], 5)[0]
        pool = self.callback_pool()
        with PumpReleaseFault(self.transport, "host_request_complete") as fault:
            self.submit(pool, "full-command-budget")
            self.assertTrue(entered.wait(5))
            waiters = [self.pump._submit(self.pump._unregister(identity), drain=True)
                       for _ in range(self.pump_config.max_pending_commands)]
            self.wait_for(lambda: self.pump.status["pending_commands"] == len(waiters))
            release.set()
            self.assertTrue(fault.failed.wait(5))
            self.wait_for(lambda: self.pump.recovery_required)
            with patch.object(self.transport, "release_results", side_effect=release_results):
                first = self.pump._submit(self.pump._retry_acknowledgements(), drain=True, recovery=True)
                self.assertTrue(recovering.wait(5))
                second = self.pump._submit(self.pump._retry_acknowledgements(), drain=True, recovery=True)
                self.assertIs(first, second)
                self.assertEqual(self.pump.status["pending_commands"], len(waiters) + 1)
                resume.set()
                first.result(5)
            for waiter in waiters:
                waiter.result(5)
            self.pump.close(5)
            self.assertEqual(calls, ["full-command-budget"])
            self.assertEqual(len(fault.successes), 1)
            self.assertEqual(self.pump.status["pending_commands"], 0)

    def test_callback_cannot_wait_for_its_own_pump_to_drain(self):
        """
        Reject self-drain from a handler before it can create a cross-thread dependency deadlock.
        在处理器可能创建跨线程依赖死锁前拒绝等待自身排空。
        """
        def handler(arguments, context):
            """
            Attempt an explicitly forbidden self-drain and let the pump return its structured error.
            尝试显式禁止的自身排空，并让事件泵返回结构化错误。
            """
            self.pump.close(timeout=1)

        self.pump.register([self.capability(handler)], timeout=5)
        done = self.terminal(self.submit(self.callback_pool(), None))
        self.assertEqual(done["value"]["error"]["code"], "unsupported", done)
        self.assertIsNone(self.pump.status["failure"])


if __name__ == "__main__":
    unittest.main()
