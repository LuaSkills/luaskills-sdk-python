from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Make the source package importable when tests run from one checkout.
# 从检出目录运行测试时让源码包可导入。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from luaskills.client import SystemSkillManagementClient
from luaskills.types import Authority


class RecordingClient:
    """
    Minimal client double that records system management calls.
    记录 system 管理调用的最小客户端替身。
    """

    def __init__(self) -> None:
        """
        Initialize one fake engine id and empty call list.
        初始化一个假的引擎标识和空调用列表。
        """

        self.engine_id = 123
        self.calls: list[tuple[str, dict[str, object]]] = []

    def _call(self, function_name: str, payload: dict[str, object]) -> object:
        """
        Record one SDK call and return a shape expected by the requested helper.
        记录一次 SDK 调用，并返回请求辅助方法期望的形状。
        """

        self.calls.append((function_name, payload))
        if function_name == "luaskills_ffi_list_entries_json":
            return [{"id": "entry.demo"}]
        return {}


class SystemManagementRawCallBoundaryTests(unittest.TestCase):
    """
    Unit tests for the system management raw FFI call boundary.
    system 管理 raw FFI 调用边界的单元测试。
    """

    def test_public_raw_call_helpers_are_not_exposed(self) -> None:
        """
        Verify arbitrary authority-bound FFI dispatch is not a public API.
        校验任意绑定 authority 的 FFI 分发不是公开 API。
        """

        system = SystemSkillManagementClient(RecordingClient(), Authority.SYSTEM)

        self.assertFalse(hasattr(system, "call"))
        self.assertFalse(hasattr(system, "call_value"))

    def test_typed_helpers_still_inject_authority(self) -> None:
        """
        Verify typed system helpers continue to dispatch through the private helper.
        校验类型化 system 辅助方法仍通过私有 helper 分发。
        """

        client = RecordingClient()
        system = SystemSkillManagementClient(client, Authority.DELEGATED_TOOL)

        self.assertEqual(system.list_entries(), [{"id": "entry.demo"}])
        function_name, payload = client.calls[0]
        self.assertEqual(function_name, "luaskills_ffi_list_entries_json")
        self.assertEqual(payload["engine_id"], 123)
        self.assertEqual(payload["authority"], "delegated_tool")


if __name__ == "__main__":
    unittest.main()
