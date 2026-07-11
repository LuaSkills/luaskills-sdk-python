from __future__ import annotations

import sys
import threading
import unittest
from pathlib import Path

# Make the source package importable when tests run from one checkout.
# 从检出目录运行测试时让源码包可导入。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from luaskills.client import LuaSkillsClient


class RecordingFfi:
    """
    Minimal FFI double that records JSON calls.
    记录 JSON 调用的最小 FFI 替身。
    """

    def __init__(self) -> None:
        """
        Initialize an empty call list.
        初始化空调用列表。
        """

        self.calls: list[tuple[str, dict[str, object]]] = []

    def call_json(self, function_name: str, payload: dict[str, object]) -> dict[str, object]:
        """
        Record one JSON FFI call and return an acknowledgement payload.
        记录一次 JSON FFI 调用并返回确认载荷。
        """

        self.calls.append((function_name, payload))
        return {"ok": True}


def make_client(engine_id: int = 42) -> tuple[LuaSkillsClient, RecordingFfi]:
    """
    Build one LuaSkillsClient instance without creating a native engine.
    构造一个不会创建原生引擎的 LuaSkillsClient 实例。
    """

    client = LuaSkillsClient.__new__(LuaSkillsClient)
    ffi = RecordingFfi()
    client.ffi = ffi
    client._engine_id = engine_id
    client._lifecycle_condition = threading.Condition()
    client._active_calls = 0
    client._closing = False
    client._closed = False
    return client, ffi


class ClientLifecycleBoundaryTests(unittest.TestCase):
    """
    Unit tests for Python client lifecycle boundaries.
    Python 客户端生命周期边界的单元测试。
    """

    def test_engine_state_properties_are_read_only(self) -> None:
        """
        Verify external callers cannot rewrite lifecycle state through public attributes.
        校验外部调用方不能通过公开属性改写生命周期状态。
        """

        client, _ = make_client()

        self.assertEqual(client.engine_id, 42)
        self.assertFalse(client.closed)
        with self.assertRaises(AttributeError):
            client.engine_id = 7  # type: ignore[misc]
        with self.assertRaises(AttributeError):
            client.closed = True  # type: ignore[misc]

    def test_call_rejects_closed_engine_before_dispatch(self) -> None:
        """
        Verify closed clients never reach FFI dispatch.
        校验已关闭客户端不会进入 FFI 分发。
        """

        client, ffi = make_client()
        client._closed = True

        with self.assertRaisesRegex(RuntimeError, "LuaSkills engine 42 is already closed"):
            client._call("luaskills_ffi_unsupported_test_json", {})
        self.assertEqual(ffi.calls, [])

    def test_call_rejects_closing_engine_before_dispatch(self) -> None:
        """
        Verify close-in-progress clients block new calls before FFI dispatch.
        校验关闭中的客户端会在 FFI 分发前阻止新调用。
        """

        client, ffi = make_client()
        client._closing = True

        with self.assertRaisesRegex(RuntimeError, "LuaSkills engine 42 is closing"):
            client._call("luaskills_ffi_unsupported_test_json", {})
        self.assertEqual(ffi.calls, [])

    def test_close_waits_for_active_calls(self) -> None:
        """
        Verify close waits until active FFI reservations are released.
        校验关闭流程会等待活跃 FFI 占用释放。
        """

        client, ffi = make_client()
        client._begin_call()
        started = threading.Event()
        finished = threading.Event()
        result: list[dict[str, object] | None] = []

        def close_client() -> None:
            """
            Close the client from a background thread.
            从后台线程关闭客户端。
            """

            started.set()
            result.append(client.close())
            finished.set()

        thread = threading.Thread(target=close_client)
        thread.start()
        self.assertTrue(started.wait(1))
        self.assertFalse(finished.wait(0.05))
        self.assertEqual(ffi.calls, [])

        client._end_call()

        self.assertTrue(finished.wait(1))
        thread.join(1)
        self.assertEqual(result, [{"ok": True}])
        self.assertTrue(client.closed)
        self.assertEqual(ffi.calls, [("luaskills_ffi_engine_free_json", {"engine_id": 42})])


if __name__ == "__main__":
    unittest.main()
