from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Make the source package importable when tests run from one checkout.
# 从检出目录运行测试时让源码包可导入。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from luaskills.client import RuntimeLeaseClient
from luaskills.types import Authority


class RecordingClient:
    """
    Minimal client double that records runtime-lease calls.
    记录运行时租约调用的最小客户端替身。
    """

    def __init__(self) -> None:
        """
        Initialize one fake engine id and empty call list.
        初始化一个假的引擎标识和空调用列表。
        """

        self.engine_id = 77
        self.calls: list[tuple[str, dict[str, object]]] = []

    def _call(self, function_name: str, payload: dict[str, object]) -> dict[str, object]:
        """
        Record one SDK call and return one object-shaped result.
        记录一次 SDK 调用并返回对象形状结果。
        """

        self.calls.append((function_name, payload))
        return {"ok": True}


class RuntimeLeaseActionTests(unittest.TestCase):
    """
    Unit tests for runtime-lease action dispatch.
    运行时租约动作分发单元测试。
    """

    def test_call_raw_uses_system_runtime_lease_endpoint(self) -> None:
        """
        Verify authority-bound raw calls use dedicated system endpoints.
        校验绑定权限的原始调用使用专用 system 入口。
        """

        client = RecordingClient()
        leases = RuntimeLeaseClient(client, authority=Authority.SYSTEM)

        result = leases.call_raw("status", {"lease_id": "lease-1"})

        self.assertEqual(result["ok"], True)
        function_name, payload = client.calls[0]
        self.assertEqual(function_name, "luaskills_ffi_system_runtime_lease_status_json")
        self.assertEqual(payload["engine_id"], 77)
        self.assertEqual(payload["authority"], "system")
        self.assertEqual(payload["lease_id"], "lease-1")

    def test_call_raw_rejects_unsupported_action(self) -> None:
        """
        Verify unsupported actions fail before native FFI dispatch.
        校验不支持的动作会在原生 FFI 分发前失败。
        """

        client = RecordingClient()
        leases = RuntimeLeaseClient(client)

        with self.assertRaisesRegex(ValueError, "unsupported runtime lease action"):
            leases.call_raw("destroy", {})
        self.assertEqual(client.calls, [])

    def test_system_create_sends_required_package_descriptor(self) -> None:
        """
        Verify System create matches the strict Rust request shape.
        校验 System create 与严格 Rust 请求结构一致。
        """

        client = RecordingClient()
        leases = RuntimeLeaseClient(client, authority=Authority.SYSTEM)
        leases.create(
            "system-session",
            system_package={"id": "debug", "root": "C:/plugins/debug", "dependencies_file": "dependencies.json"},
        )
        function_name, payload = client.calls[0]
        self.assertEqual(function_name, "luaskills_ffi_system_runtime_lease_create_json")
        self.assertEqual(payload["system_package"], {
            "id": "debug",
            "root": "C:/plugins/debug",
            "dependencies_file": "dependencies.json",
        })

    def test_system_create_rejects_public_roots_and_missing_package(self) -> None:
        """
        Verify System create rejects fields absent from the strict Rust request.
        校验 System create 拒绝严格 Rust 请求中不存在的字段。
        """

        client = RecordingClient()
        leases = RuntimeLeaseClient(client, authority=Authority.SYSTEM)
        with self.assertRaisesRegex(ValueError, "requires system_package"):
            leases.create("system-session")
        with self.assertRaisesRegex(ValueError, "does not accept lua_roots"):
            leases.create("system-session", lua_roots=["lua"], system_package={})
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
