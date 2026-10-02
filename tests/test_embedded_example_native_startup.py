"""
Reject real pump/scope thread startup and prove the example preserves the error while releasing native ownership.
拒绝真实泵及作用域线程启动，证明示例保留错误并释放原生所有权。
"""

from __future__ import annotations

import os
import asyncio
import json
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch

from luaskills import EmbeddedCallbackPump, EmbeddedCommandDriver, EmbeddedTransport
from luaskills.examples import embedded_runtime as example


@unittest.skipUnless(os.environ.get("LUASKILLS_LIB"), "requires an explicit matching native library")
class EmbeddedExampleNativeStartupTests(unittest.TestCase):
    """
    Exercise actual native allocation and drainage after injected Python infrastructure startup failures.
    注入 Python 基础设施启动失败后执行真实原生分配及排空。
    """

    def assert_startup_drains(self, name: str, asynchronous: bool, *, late: bool = False) -> None:
        """
        Refuse Thread.start for name in asynchronous or sync example mode; require original error and native free.
        在 asynchronous 或同步示例模式拒绝 name 的 Thread.start；要求原始错误及原生释放。
        Return nothing; successful native transport free proves its runtime slots and workers are no longer live.
        无返回值；原生传输成功释放证明其运行时槽及线程已不再活动。
        late starts the actual thread before interruption and delays the pump's real worker entry.
        late 在中断前启动实际线程，并延迟事件泵真实线程入口。
        """
        # Record real transports without replacing their native implementation or lifecycle behavior.
        # 记录真实传输，不替换其原生实现或生命周期行为。
        transports: list[EmbeddedTransport] = []
        startup_error = RuntimeError("injected " + name + " thread startup refusal")
        original_start = threading.Thread.start
        # Retain real pumps to inspect public close status and actual thread joins after the example returns.
        # 保留真实泵以在示例返回后检查公开关闭状态及实际线程汇合。
        pumps: list[EmbeddedCallbackPump] = []

        class RecordingTransport(EmbeddedTransport):
            """
            Preserve native transport construction and record each completed allocation for post-error assertions.
            保留原生传输构造并记录每次已完成分配，用于错误后断言。
            """

            def __init__(self, *arguments, **keywords):
                """
                Forward arguments/keywords to the actual transport and append this allocated owner; return nothing.
                将 arguments/keywords 转发至实际传输并追加此已分配所有者；无返回值。
                """
                super().__init__(*arguments, **keywords)
                transports.append(self)

        class DelayedPump(EmbeddedCallbackPump):
            """
            Retain the actual pump, including interrupted constructors, and expose the late-start worker boundary.
            保留实际事件泵，包含中断构造器，并暴露迟到启动线程边界。
            """

            def __init__(self, *arguments, **keywords):
                """
                Record this pump before forwarding arguments/keywords to its actual constructor; return nothing.
                将 arguments/keywords 转发至实际构造器前记录此事件泵；无返回值。
                """
                pumps.append(self)
                super().__init__(*arguments, **keywords)

            def _thread_main(self):
                """
                Delay entry only for late startup, then run the original pump worker and its real cleanup.
                仅迟到启动时延迟入口，再运行原事件泵线程及其真实清理。
                """
                if late:
                    time.sleep(0.05)
                super()._thread_main()

        def refuse_start(thread: threading.Thread) -> None:
            """
            Reject the selected thread by name; start every other real worker with the original implementation.
            按名称拒绝选定 thread；使用原实现启动全部其它真实工作线程。
            """
            if thread.name == name:
                if late:
                    original_start(thread)
                raise startup_error
            original_start(thread)

        with patch.object(example, "EmbeddedTransport", RecordingTransport), patch.object(
            threading.Thread, "start", refuse_start,
        ), patch.object(example, "EmbeddedCallbackPump", DelayedPump):
            with self.assertRaises(RuntimeError) as failure:
                example._run(Path(os.environ["LUASKILLS_LIB"]), None, asynchronous=asynchronous)
        self.assertIs(failure.exception, startup_error)
        self.assertEqual(len(transports), 1)
        for transport in transports:
            self.assertIsNone(transport._transport_id)
            self.assertEqual(transport._callback_pumps, {})
            self.assertEqual(transport._runtime_scopes, {})
            self.assertIsNone(transport._command_driver)
            self.assertEqual(transport._active_calls, 0)
            self.assertEqual(transport._results, {})
        if late:
            for pump in pumps:
                self.assertTrue(pump.status["closed"])
                self.assertIsNone(pump.status["failure"])
                self.assertFalse(pump._thread.is_alive())

    def test_sync_pump_startup_failure_drains_runtime(self) -> None:
        """
        Fail synchronous pump construction after real runtime readiness and require actual release; return nothing.
        真实运行时就绪后使同步泵构造失败并要求实际释放；无返回值。
        """
        self.assert_startup_drains("luaskills-callback-pump", False)

    def test_sync_scope_startup_failure_drains_pump_and_runtime(self) -> None:
        """
        Fail synchronous scope construction with a live pump and require ordered actual release; return nothing.
        活动泵存在时使同步作用域构造失败并要求有序实际释放；无返回值。
        """
        self.assert_startup_drains("luaskills-runtime-scope", False)

    def test_async_pump_startup_failure_drains_runtime(self) -> None:
        """
        Fail asyncio pump construction after real runtime readiness and require actual release; return nothing.
        真实运行时就绪后使 asyncio 泵构造失败并要求实际释放；无返回值。
        """
        self.assert_startup_drains("luaskills-callback-pump", True)

    def test_async_scope_startup_failure_drains_pump_and_runtime(self) -> None:
        """
        Fail asyncio scope construction with a live pump and require ordered actual release; return nothing.
        活动泵存在时使 asyncio 作用域构造失败并要求有序实际释放；无返回值。
        """
        self.assert_startup_drains("luaskills-runtime-scope", True)

    def test_sync_late_pump_startup_failure_joins_before_runtime_release(self) -> None:
        """
        Interrupt a truly started sync pump with delayed worker entry; require its actual closure before release.
        中断真实启动且线程入口延迟的同步泵；要求释放前实际关闭。
        """
        self.assert_startup_drains("luaskills-callback-pump", False, late=True)

    def test_async_late_pump_startup_failure_joins_before_runtime_release(self) -> None:
        """
        Interrupt a truly started asyncio pump with delayed worker entry; require its actual closure before release.
        中断真实启动且线程入口延迟的 asyncio 泵；要求释放前实际关闭。
        """
        self.assert_startup_drains("luaskills-callback-pump", True, late=True)

    def test_sync_late_scope_startup_failure_keeps_original_cleanup_order(self) -> None:
        """
        Interrupt an actually started sync scope; require constructor claim recovery then actual pump/runtime release.
        中断实际启动的同步作用域；要求构造器声明恢复后实际泵及运行时释放。
        """
        self.assert_startup_drains("luaskills-runtime-scope", False, late=True)

    def test_async_late_scope_startup_failure_keeps_original_cleanup_order(self) -> None:
        """
        Interrupt an actually started asyncio scope; require constructor claim recovery then actual pump/runtime release.
        中断实际启动的 asyncio 作用域；要求构造器声明恢复后实际泵及运行时释放。
        """
        self.assert_startup_drains("luaskills-runtime-scope", True, late=True)

    def assert_reserve_recovery(self, *, unknown_delivery: bool) -> None:
        """
        Cancel the first reserve observer while its actual native command runs; require one reserve and full release.
        实际原生命令运行时取消首个预留观察者；要求仅一次预留及完整释放。
        Return nothing; the original cancellation must survive late native receipt delivery and cleanup.
        无返回值；迟到原生回执交付及清理后必须保留原取消。
        unknown_delivery drops the actual reserve response and requires retained ownership instead of guessed cleanup.
        unknown_delivery 丢弃实际预留响应，并要求保留所有权而非猜测清理。
        """
        # Record actual native allocations and drivers; only the observation timing is fault-injected.
        # 记录实际原生分配及驱动器；仅向观察时序注入故障。
        transports: list[EmbeddedTransport] = []
        drivers: list[EmbeddedCommandDriver] = []
        reserve_commands: list[bytes] = []
        # These identities are test-only evidence from the real native return, intentionally hidden from the SDK observer.
        # 这些身份仅为来自真实原生返回的测试证据，刻意对 SDK 观察者隐藏。
        native_reservations: list[str] = []
        native_commands: list[str] = []
        delivery_error = RuntimeError("injected unknown native reserve delivery")
        original_take_async = example.take_async

        class DelayedTransport(EmbeddedTransport):
            """
            Preserve real native calls and delay only the exact reserve command for cancellation overlap.
            保留真实原生调用，仅延迟精确预留命令以与取消重叠。
            """

            def __init__(self, *arguments, **keywords):
                """
                Forward arguments/keywords to actual allocation and record its owner; return nothing.
                将 arguments/keywords 转发至实际分配并记录所有者；无返回值。
                """
                super().__init__(*arguments, **keywords)
                transports.append(self)

            def _request_encoded(self, encoded):
                """
                Delay encoded's authoritative runtime_reserve frame, then return the actual native delivery.
                延迟 encoded 的权威 runtime_reserve 帧，再返回实际原生交付。
                """
                # The generated request envelope is authoritative; no alternative field path is probed.
                # 生成请求信封保持权威；不探测替代字段路径。
                command_type = json.loads(encoded)["command"]["type"]
                native_commands.append(command_type)
                if command_type == "runtime_reserve":
                    reserve_commands.append(encoded)
                    time.sleep(0.05)
                # The native allocation is real and happens exactly once before an optional lost-delivery fault.
                # 原生分配真实发生，且在可选丢失交付故障前恰好执行一次。
                result = super()._request_encoded(encoded)
                if command_type == "runtime_reserve":
                    native_reservations.append(result["runtime_id"])
                    if unknown_delivery:
                        raise delivery_error
                return result

        class RecordingDriver(EmbeddedCommandDriver):
            """
            Retain the actual bounded driver for checking post-cancellation receipt cleanup.
            保留实际有界驱动器，供检查取消后的回执清理。
            """

            def __init__(self, *arguments, **keywords):
                """
                Forward arguments/keywords to real driver construction and record it; return nothing.
                将 arguments/keywords 转发至真实驱动器构造并记录；无返回值。
                """
                super().__init__(*arguments, **keywords)
                drivers.append(self)

        async def cancel_first_observer(pending):
            """
            Schedule the caller task's cancellation, then observe pending with the actual SDK async implementation.
            安排调用方任务取消，再使用实际 SDK 异步实现观察 pending。
            """
            # This example's first async observation is the only runtime reservation receipt.
            # 此示例首个异步观察是唯一运行时预留回执。
            caller = asyncio.current_task()
            assert caller is not None
            asyncio.get_running_loop().call_soon(caller.cancel)
            return await original_take_async(pending)

        with patch.object(example, "EmbeddedTransport", DelayedTransport), patch.object(
            example, "EmbeddedCommandDriver", RecordingDriver,
        ), patch.object(example, "take_async", cancel_first_observer):
            with self.assertRaises(asyncio.CancelledError):
                example._run(Path(os.environ["LUASKILLS_LIB"]), None, asynchronous=True)
        self.assertEqual(len(reserve_commands), 1)
        self.assertEqual(len(transports), 1)
        self.assertEqual(len(drivers), 1)
        if unknown_delivery:
            try:
                self.assertNotIn("runtime_free", native_commands)
                for transport in transports:
                    self.assertIsNotNone(transport._transport_id)
                for driver in drivers:
                    self.assertEqual(len(driver.commands), 1)
                    for receipt in driver.commands:
                        with self.assertRaises(RuntimeError) as failure:
                            receipt.result(0)
                        self.assertIs(failure.exception, delivery_error)
            finally:
                # Only the test has the withheld successful identity; explicit cleanup uses that evidence after assertion.
                # 仅测试拥有被隐藏的成功身份；断言后显式清理使用该证据。
                for transport in transports:
                    for runtime_id in native_reservations:
                        self.assertTrue(transport.request({"type": "runtime_status", "runtime_id": runtime_id})["closed"])
                        transport.request({"type": "runtime_free", "runtime_id": runtime_id})
                    transport.free()
            return
        for transport in transports:
            self.assertIsNone(transport._transport_id)
            self.assertEqual(transport._callback_pumps, {})
            self.assertEqual(transport._runtime_scopes, {})
            self.assertIsNone(transport._command_driver)
        for driver in drivers:
            self.assertEqual(driver.commands, ())

    def test_async_reserve_cancellation_recovers_same_native_receipt(self) -> None:
        """
        Cancel reserve observation and require cleanup from its one actual delivered identity; return nothing.
        取消预留观察并要求按唯一实际已交付身份清理；无返回值。
        """
        self.assert_reserve_recovery(unknown_delivery=False)

    def test_unknown_reserve_delivery_retains_receipt_and_native_ownership(self) -> None:
        """
        Withhold the actual reserve response and require recoverable ownership without guessed runtime release.
        隐藏实际预留响应并要求可恢复所有权，不猜测释放运行时。
        Return only after assertions and test-owned cleanup; the example must retain its unknown receipt.
        断言及测试拥有的清理完成后返回；示例必须保留未知回执。
        """
        self.assert_reserve_recovery(unknown_delivery=True)


if __name__ == "__main__":
    unittest.main()
