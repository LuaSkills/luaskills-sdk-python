"""
Exercise the owned Python callback pump with actual Lua and the newly built native core.
使用实际 Lua 及新构建原生核心验证拥有型 Python 回调事件泵。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
import unittest
from unittest.mock import patch

from luaskills import EmbeddedRuntimeError, EmbeddedTransportError
from luaskills.embedded_callbacks import HOST_CALLBACK_RUNTIME, HostCapability
from luaskills.embedded_pump import CallbackPumpConfig, EmbeddedCallbackPump
from test_embedded_native_e2e import EmbeddedNativeFixture


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

    def test_sync_callback_receives_trusted_identity_and_preserves_null(self):
        """
        Invoke a synchronous handler off the pump loop and preserve explicit host commit and successful null.
        在事件泵循环外调用同步处理器，并保留显式宿主提交及成功空值。
        """
        def handler(arguments, context):
            """
            Check authenticated identity separately from arguments, then report an actual test commit.
            独立于参数检查已认证身份，随后报告实际测试提交。
            """
            self.assertEqual(context.caller["plugin_id"], self.plugin_id)
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
