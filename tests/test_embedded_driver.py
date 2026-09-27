"""
Exercise native command receipt ownership, independent control capacity and actual DLL recovery.
验证原生命令回执所有权、独立控制容量及实际 DLL 恢复。
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import threading
import unittest
from dataclasses import replace
from unittest.mock import patch

from luaskills import (
    EmbeddedCommandDriver, EmbeddedDriverConfig, EmbeddedNativeStatus,
    EmbeddedResultReleaseError, EmbeddedRuntimeError, EmbeddedTransport,
)
from luaskills.embedded_callbacks import HOST_CALLBACK_RUNTIME
from test_embedded_native_e2e import EmbeddedNativeFixture
from test_embedded_transport import NativeLibrary, config


class EmbeddedDriverTests(unittest.TestCase):
    """
    Use the real transport binding with deterministic native boundaries to inspect driver races and receipts.
    使用真实传输绑定及确定性原生边界，检查驱动器竞态和回执。
    """

    def setUp(self) -> None:
        """
        Create one bounded driver and controllable native library, with cleanup that first releases test gates.
        创建一个有界驱动器及可控原生库，清理时先释放测试门。
        Return nothing and retain every native/driver owner until actual cleanup completes.
        无返回值，并保留每个原生／驱动器所有者直到实际清理完成。
        """
        # Cleanup order must unblock a worker before joining it, even when an assertion fails.
        # 即使断言失败，清理顺序也必须先解除工作线程阻塞再汇合。
        self.native = NativeLibrary()
        self.loader = patch("luaskills.embedded_transport.ctypes.CDLL", return_value=self.native)
        self.loader.start()
        self.addCleanup(self.loader.stop)
        self.transport = EmbeddedTransport(config(), library_path=Path(__file__))
        self.driver = EmbeddedCommandDriver(self.transport, EmbeddedDriverConfig(work_threads=1, max_work_commands=2, max_control_commands=2))
        self.gate = threading.Event()
        self.entered = threading.Event()
        self.addCleanup(self._cleanup)

    def _cleanup(self) -> None:
        """
        Unblock test/native gates, join real workers and release all retained buffers before native free.
        解除测试／原生门阻塞，汇合实际工作线程，并在原生释放前释放全部保留缓冲。
        Return nothing; leaked ownership or failed real shutdown must fail the test.
        无返回值；泄漏所有权或实际关闭失败必须使测试失败。
        """
        self.gate.set()
        self.native.proceed.set()
        self.driver.close(timeout=5)
        self.native.release_status = 0
        self.transport.release_results()
        self.transport.close()
        self.transport.free()
        self.assertFalse(self.native.allocations)

    def _delay_work(self) -> None:
        """
        Delay only ordinary work at the real transport boundary, leaving describe control fully executable.
        仅在真实传输边界延迟普通工作，使 describe 控制保持完全可执行。
        Return nothing and retain the exact original request implementation for eventual execution.
        无返回值，并保留精确原始请求实现以最终执行。
        """
        # Frozen command routing is inspected from bytes actually sent by the driver.
        # 从驱动器实际发送的字节检查冻结命令路由。
        original = self.transport._request_encoded

        def request(encoded: bytes):
            """
            Wait only for test runtime_reserve requests, then return the actual transport result.
            仅等待测试 runtime_reserve 请求，然后返回实际传输结果。
            """
            if json.loads(encoded)["command"]["type"] == "runtime_reserve":
                self.entered.set()
                self.assertTrue(self.gate.wait(5), "test did not release the work command")
            return original(encoded)

        self.transport._request_encoded = request

    def test_work_receipts_cannot_exhaust_control_capacity(self) -> None:
        """
        Fill running/queued work slots while control still executes, then require explicit completed receipt forget.
        填满运行／排队工作槽，同时控制仍可执行，然后要求显式遗忘已完成回执。
        Return nothing; both work and control quotas must survive observer timeouts unchanged.
        无返回值；工作及控制配额均须在观察超时后保持不变。
        """
        self._delay_work()
        first = self.driver.submit({"type": "runtime_reserve"})
        self.assertTrue(self.entered.wait(2))
        second = self.driver.submit({"type": "runtime_reserve"})
        with self.assertRaises(EmbeddedRuntimeError) as full:
            self.driver.submit({"type": "runtime_reserve"})
        self.assertEqual(full.exception.code, "capacity_exceeded")
        with self.assertRaises(TimeoutError):
            first.result(0.01)
        with self.assertRaisesRegex(RuntimeError, "still running or queued"):
            first.forget()
        control = self.driver.submit({"type": "describe"})
        self.assertIsNone(control.result(2))
        control.forget()
        self.gate.set()
        first.result(2)
        second.result(2)
        with self.assertRaises(EmbeddedRuntimeError):
            self.driver.submit({"type": "runtime_reserve"})
        first.forget()
        third = self.driver.submit({"type": "runtime_reserve"})
        third.result(2)
        self.assertNotEqual(first.command_id, third.command_id)

    def test_cancelled_caller_loop_retains_command_and_close_ownership(self) -> None:
        """
        Cancel receipt and close observers, close their loop, and still recover one native result without replay.
        取消回执及关闭观察者，关闭其循环，仍可恢复一个原生结果且不重放。
        Return nothing; early free must remain blocked until the real worker returns.
        无返回值；提前释放必须保持被阻止，直到实际工作线程返回。
        """
        self._delay_work()
        command = self.driver.submit({"type": "runtime_reserve"})
        self.assertTrue(self.entered.wait(2))

        async def caller() -> None:
            """
            Cancel only local observer tasks; their underlying native command and closer must remain active.
            仅取消局部观察任务；其底层原生命令和关闭线程必须保持活动。
            """
            observer = asyncio.create_task(command.result_async())
            await asyncio.sleep(0)
            observer.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await observer
            closer = asyncio.create_task(self.driver.close_async())
            await asyncio.sleep(0)
            closer.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await closer

        asyncio.run(caller())
        self.assertIn(command, self.driver.commands)
        self.assertFalse(command.done)
        with self.assertRaises(TimeoutError):
            self.driver.close(timeout=0.01)
        with self.assertRaisesRegex(RuntimeError, "owns active calls or results"):
            self.transport.free()
        self.gate.set()
        self.driver.close(timeout=2)
        self.assertFalse(self.driver._closer.is_alive())
        self.assertIsNone(command.result())
        self.assertEqual(len(self.native.received), 1)
        command.forget()
        self.assertFalse(self.driver.commands)

    def test_frozen_requests_and_late_error_receipts_are_recoverable(self) -> None:
        """
        Mutate caller-owned mappings after submission and verify queued bytes and retained errors remain exact.
        提交后修改调用方拥有的映射，验证排队字节及保留错误保持精确。
        Return nothing; discarded observers cannot discard the command's business failure.
        无返回值；被丢弃的观察者不能丢弃命令业务失败。
        """
        self._delay_work()
        source = {"type": "runtime_reserve"}
        command = self.driver.submit(source)
        self.assertTrue(self.entered.wait(2))
        source["type"] = "runtime_free"
        diagnostic = command.request
        diagnostic["type"] = "describe"
        self.native.reply = b'{"protocol_version":1,"status":"error","error":{"code":"closed","message":"closed fixture"}}'
        self.gate.set()
        with self.assertRaises(EmbeddedRuntimeError) as error:
            command.result(2)
        self.assertEqual(error.exception.code, "closed")
        self.assertEqual(command.request, {"type": "runtime_reserve"})
        self.assertEqual(self.native.received[0]["command"], command.request)
        self.assertIn(command, self.driver.commands)

    def test_rejected_executor_submission_keeps_a_nonexecuting_receipt(self) -> None:
        """
        Model executor rejection after SDK publication and retain exact failure without allowing later native execution.
        模拟 SDK 发布后的执行器拒绝，保留精确失败且不允许稍后原生执行。
        Return nothing; retained errors remain discoverable even though submit raised.
        无返回值；即使 submit 抛出，保留错误仍可发现。
        """
        with patch.object(self.driver._work, "submit", side_effect=RuntimeError("executor rejected")):
            with self.assertRaisesRegex(RuntimeError, "executor rejected"):
                self.driver.submit({"type": "runtime_reserve"})
        self.assertEqual(len(self.driver.commands), 1)
        receipt, = self.driver.commands
        with self.assertRaisesRegex(RuntimeError, "executor rejected"):
            receipt.result()
        self.driver._execute(receipt)
        self.assertFalse(self.native.received)
        receipt.forget()

    def test_success_observers_cannot_mutate_retained_delivery_evidence(self) -> None:
        """
        Return independent JSON values to synchronous and asynchronous observers of the same retained receipt.
        向同一保留回执的同步及异步观察者返回独立 JSON 值。
        Return nothing; caller edits must not change later recovered identities or nested application values.
        无返回值；调用方修改不得改变稍后恢复的身份或嵌套应用值。
        """
        self.native.reply = b'{"protocol_version":1,"status":"ok","result":{"runtime_id":"native-id","nested":[{"value":1}]}}'
        receipt = self.driver.submit({"type": "runtime_reserve"})
        first = receipt.result(2)
        first["runtime_id"] = "changed-id"
        first["nested"][0]["value"] = 42
        second = asyncio.run(receipt.result_async())
        self.assertEqual(second, {"runtime_id": "native-id", "nested": [{"value": 1}]})
        second["nested"].clear()
        self.assertEqual(receipt.result()["nested"], [{"value": 1}])

    def test_duplicate_drivers_nested_callbacks_and_blocking_wait_are_rejected(self) -> None:
        """
        Reject duplicate driver owners, unsupported host reentry and native blocking waits before dispatch.
        在分发前拒绝重复驱动器所有者、不支持的宿主重入及原生阻塞等待。
        Return nothing; rejected requests must not create retained commands or native calls.
        无返回值；拒绝请求不得创建保留命令或原生调用。
        """
        with self.assertRaisesRegex(RuntimeError, "already has a command driver"):
            EmbeddedCommandDriver(self.transport, self.driver._config)
        with self.assertRaises(EmbeddedRuntimeError):
            self.driver.submit({"type": "runtime", "runtime_id": "fixture", "operation": {"type": "operation_wait", "operation_id": "op", "wait_ms": 1}})
        token = HOST_CALLBACK_RUNTIME.set("fixture")
        try:
            with self.assertRaises(EmbeddedRuntimeError):
                self.driver.submit({"type": "describe"})
        finally:
            HOST_CALLBACK_RUNTIME.reset(token)
        self.assertFalse(self.driver.commands)
        self.assertFalse(self.native.received)

    def test_driver_and_callback_pump_reservations_share_native_capacity(self) -> None:
        """
        Account for existing and newly added callback owners together with actual driver executor slots.
        将既有和新增回调所有者与实际驱动器执行器槽共同计数。
        Return nothing; rejected claims must not mutate ownership, and limits remain read-only.
        无返回值；拒绝的声明不得改变所有权，且限制保持只读。
        """
        self.driver.close()
        first_owner = object()
        second_owner = object()
        self.transport._claim_callback_pump("first", first_owner)
        self.addCleanup(self.transport._release_callback_pump, "first", first_owner)
        self.driver = EmbeddedCommandDriver(self.transport, EmbeddedDriverConfig(work_threads=2, max_work_commands=2, max_control_commands=2))
        with self.assertRaises(EmbeddedRuntimeError) as failure:
            self.transport._claim_callback_pump("second", second_owner)
        self.assertEqual(failure.exception.code, "capacity_exceeded")
        self.assertNotIn("second", self.transport._callback_pumps)
        with self.assertRaises(AttributeError):
            self.transport.config = config()
        self.driver.close()
        self.transport._claim_callback_pump("second", second_owner)
        self.transport._release_callback_pump("second", second_owner)

    def test_closer_start_failure_and_late_interruption_release_the_claim_once(self) -> None:
        """
        Fail coordinator startup before and after real thread creation, proving exactly one safe cleanup owner.
        在实际线程创建前后使协调线程启动失败，证明恰有一个安全清理所有者。
        Return nothing; no constructor failure may leave a live closer or duplicate native ownership release.
        无返回值；构造失败不得留下活动关闭线程或重复释放原生所有权。
        """
        self.driver.close()
        original_start = threading.Thread.start
        for started in (False, True):
            with self.subTest(started=started):
                threads = []

                def start(thread: threading.Thread) -> None:
                    """
                    Optionally create the real owned closer before injecting a caller-side startup interruption.
                    可选地创建实际拥有型关闭线程，然后注入调用方启动中断。
                    """
                    if started:
                        original_start(thread)
                        threads.append(thread)
                        raise KeyboardInterrupt("startup interrupted after thread creation")
                    raise RuntimeError("thread creation failed")

                with patch.object(self.transport, "_release_command_driver", wraps=self.transport._release_command_driver) as released:
                    with patch.object(threading.Thread, "start", new=start):
                        with self.assertRaises(KeyboardInterrupt if started else RuntimeError):
                            EmbeddedCommandDriver(self.transport, self.driver._config)
                    for thread in threads:
                        thread.join(2)
                        self.assertFalse(thread.is_alive())
                    self.assertEqual(released.call_count, 1)
                self.assertIsNone(self.transport._command_driver)
                self.assertFalse(self.native.received)

    def test_release_failure_retains_success_business_error_and_invalid_bytes(self) -> None:
        """
        Preserve exact copied delivery independently of native-buffer recovery, including null and business errors.
        独立于原生缓冲恢复保留精确复制交付，包含空值及业务错误。
        Return nothing; failed cleanup never replaces delivery evidence with an assumption of rejection.
        无返回值；清理失败绝不以拒绝假设替换交付证据。
        """
        for response in (
            b'{"protocol_version":1,"status":"ok","result":{"runtime_id":"owned-runtime"}}',
            b'{"protocol_version":1,"status":"ok","result":null}',
            b'{"protocol_version":1,"status":"error","error":{"code":"closed","message":"closed"}}',
            b"\xff",
        ):
            with self.subTest(response=response):
                self.native.reply = response
                self.native.release_status = EmbeddedNativeStatus.INTERNAL
                receipt = self.driver.submit({"type": "runtime_reserve"})
                with self.assertRaises(EmbeddedResultReleaseError) as failure:
                    receipt.result(2)
                self.assertEqual(failure.exception.response_bytes, response)
                self.native.release_status = 0
                self.transport.release_results()
                if response == b"\xff":
                    with self.assertRaises(UnicodeDecodeError):
                        failure.exception.delivered_result()
                elif json.loads(response)["status"] == "error":
                    with self.assertRaises(EmbeddedRuntimeError) as business:
                        failure.exception.delivered_result()
                    self.assertEqual(business.exception.code, "closed")
                else:
                    self.assertEqual(failure.exception.delivered_result(), json.loads(response)["result"])
                receipt.forget()


class EmbeddedDriverReservationTests(unittest.TestCase):
    """
    Isolate result-count and aggregate-byte admission before any driver thread or native request starts.
    在任何驱动器线程或原生请求开始前，隔离验证结果数量及聚合字节入场。
    """

    def test_count_and_worst_case_bytes_both_cover_control_workers(self) -> None:
        """
        Reject insufficient count and insufficient bytes independently while leaving a transport releasable.
        分别拒绝数量不足及字节不足，同时保持传输可释放。
        Return nothing; failed claims cannot leak executors or native request ownership.
        无返回值；失败声明不得泄漏执行器或原生请求所有权。
        """
        for budgets in (replace(config(), max_result_buffers=1), replace(config(), max_result_bytes=config().max_response_bytes)):
            with self.subTest(budgets=budgets):
                native = NativeLibrary()
                with patch("luaskills.embedded_transport.ctypes.CDLL", return_value=native):
                    transport = EmbeddedTransport(budgets, library_path=Path(__file__))
                try:
                    with self.assertRaises(EmbeddedRuntimeError) as failure:
                        EmbeddedCommandDriver(transport, EmbeddedDriverConfig(work_threads=1, max_work_commands=1, max_control_commands=1))
                    self.assertEqual(failure.exception.code, "capacity_exceeded")
                    self.assertIsNone(transport._command_driver)
                    self.assertFalse(native.received)
                finally:
                    transport.close()
                    transport.free()


@unittest.skipUnless(os.environ.get("LUASKILLS_LIB"), "requires the matching actual core library")
class EmbeddedDriverNativeTests(EmbeddedNativeFixture, unittest.TestCase):
    """
    Verify the owned command driver against actual Lua execution and post-mutation result-release failure.
    针对实际 Lua 执行及变更后的结果释放失败验证拥有型命令驱动器。
    """

    def setUp(self) -> None:
        """
        Start the established native runtime fixture and retain a separate bounded command driver until cleanup.
        启动既有原生运行时夹具，并保留独立有界命令驱动器直到清理。
        Return nothing; driver threads drain before fixture runtime and transport cleanup.
        无返回值；驱动器线程先于夹具运行时和传输清理排空。
        """
        super().setUp()
        self.driver = EmbeddedCommandDriver(self.transport, EmbeddedDriverConfig(work_threads=1, max_work_commands=4, max_control_commands=4))
        self.addCleanup(self.driver.close, 5)

    def test_real_lua_receipt_survives_cancelled_loop_and_late_return(self) -> None:
        """
        Admit real Lua once, delay its SDK receipt and recover the exact operation after cancelling its loop observer.
        实际接纳 Lua 一次，延迟其 SDK 回执，并在取消循环观察者后恢复精确操作。
        Return nothing; driver observer cancellation must not cancel or replay core execution.
        无返回值；驱动器观察者取消不得取消或重放核心执行。
        """
        pool_id = self.pool("local count = 0; return {call=function(a) count=count+1; return {count=count,value=a} end}")
        entered = threading.Event()
        proceed = threading.Event()
        self.addCleanup(proceed.set)
        original = self.transport._request_encoded

        def request(encoded: bytes):
            """
            Delay only the actual admitted call receipt, retaining its true core operation identity.
            仅延迟实际已接纳调用的回执，保留其真实核心操作身份。
            """
            result = original(encoded)
            frame = json.loads(encoded)["command"]
            if frame["type"] == "runtime" and frame["operation"]["type"] == "call_submit":
                entered.set()
                self.assertTrue(proceed.wait(5))
            return result

        self.transport._request_encoded = request
        receipt = self.driver.submit({"type": "runtime", "runtime_id": self.runtime_id, "operation": {
            "type": "call_submit", "timeout_ms": 10000, "call": {"pool_id": pool_id, "export": "call", "arguments": "真实值",
            "context": {"request_context": None, "client_budget": None, "tool_config": None}},
        }})
        self.assertTrue(entered.wait(2))

        async def observer() -> None:
            """
            Cancel a waiting caller without allowing its event loop to own the native receipt.
            取消等待调用方，不允许其事件循环拥有原生回执。
            """
            waiting = asyncio.create_task(receipt.result_async())
            await asyncio.sleep(0)
            waiting.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await waiting

        asyncio.run(observer())
        proceed.set()
        operation_id = receipt.result(2)["operation_id"]
        outcome = self.terminal(operation_id)
        self.assertEqual(outcome["value"], {"count": 1, "value": "真实值"})
        self.assertEqual(self.driver.commands, (receipt,))
        receipt.forget()

    def test_real_mutation_identity_survives_failed_buffer_release(self) -> None:
        """
        Preserve an actual core operation identity when its receipt release fails, then recover without resubmission.
        当实际核心操作回执释放失败时保留其身份，然后无需重新提交即可恢复。
        Return nothing; the recovered identity must query the original successful Lua operation.
        无返回值；恢复身份必须可查询原始成功 Lua 操作。
        """
        pool_id = self.pool("return {call=function(a) return a end}")
        original_free = self.transport._result_free
        self.transport._result_free = lambda identity, result: EmbeddedNativeStatus.INTERNAL
        try:
            receipt = self.driver.submit({"type": "runtime", "runtime_id": self.runtime_id, "operation": {
                "type": "call_submit", "timeout_ms": 10000, "call": {"pool_id": pool_id, "export": "call", "arguments": "receipt-evidence",
                "context": {"request_context": None, "client_budget": None, "tool_config": None}},
            }})
            with self.assertRaises(EmbeddedResultReleaseError) as failure:
                receipt.result(2)
        finally:
            self.transport._result_free = original_free
        self.transport.release_results()
        operation_id = failure.exception.delivered_result()["operation_id"]
        self.assertEqual(self.terminal(operation_id)["value"], "receipt-evidence")
        self.assertEqual(self.driver.commands, (receipt,))
        receipt.forget()


if __name__ == "__main__":
    unittest.main()
