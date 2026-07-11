from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Make the source package importable when tests run from one checkout.
# 从检出目录运行测试时让源码包可导入。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from luaskills.client import SystemSkillManagementClient
from luaskills.types import Authority, RuntimeSkillRoot


class RecordingClient:
    """
    Minimal client double that records private URL-manifest calls.
    记录私有 URL manifest 调用的最小客户端替身。
    """

    def __init__(self) -> None:
        """
        Initialize one fake engine id and empty call list.
        初始化一个假的引擎标识和空调用列表。
        """

        self.engine_id = 42
        self.calls: list[tuple[str, dict[str, object]]] = []

    def _call(self, function_name: str, payload: dict[str, object]) -> dict[str, object]:
        """
        Record one SDK call and return one object-shaped result.
        记录一次 SDK 调用并返回对象形状结果。
        """

        self.calls.append((function_name, payload))
        return {"status": "ok", "skill_id": payload["skill_id"]}


class PrivateUrlManifestTests(unittest.TestCase):
    """
    Unit tests for host-private URL-manifest SDK payload construction.
    宿主私有 URL manifest SDK 载荷构造单元测试。
    """

    def test_install_private_url_manifest_uses_system_private_endpoint(self) -> None:
        """
        Verify install payload keys match the native Rust request contract.
        校验安装载荷字段匹配原生 Rust 请求契约。
        """

        client = RecordingClient()
        system = SystemSkillManagementClient(client, Authority.DELEGATED_TOOL)
        target_root = RuntimeSkillRoot("ROOT", "runtime/skills")

        result = system.install_private_url_manifest(
            [RuntimeSkillRoot("ROOT", "runtime/skills")],
            "private.demo",
            "https://example.test/skill.json",
            target_root=target_root,
        )

        self.assertEqual(result["status"], "ok")
        function_name, payload = client.calls[0]
        self.assertEqual(function_name, "luaskills_ffi_system_private_install_skill_from_url_manifest_json")
        self.assertEqual(payload["engine_id"], 42)
        self.assertEqual(payload["skill_id"], "private.demo")
        self.assertEqual(payload["manifest_url"], "https://example.test/skill.json")
        self.assertEqual(payload["authority"], "system")
        self.assertEqual(payload["target_root"], {"name": "ROOT", "skills_dir": "runtime/skills"})
        self.assertEqual(payload["skill_roots"], [{"name": "ROOT", "skills_dir": "runtime/skills"}])

    def test_update_private_url_manifest_uses_null_target_root(self) -> None:
        """
        Verify update sends null target_root when no explicit root is provided.
        校验未提供显式 root 时更新载荷发送 null target_root。
        """

        client = RecordingClient()
        system = SystemSkillManagementClient(client, Authority.SYSTEM)

        system.update_private_url_manifest(
            [{"name": "ROOT", "skills_dir": "runtime/skills"}],
            "private.demo",
            "https://example.test/skill.json",
        )

        function_name, payload = client.calls[0]
        self.assertEqual(function_name, "luaskills_ffi_system_private_update_skill_from_url_manifest_json")
        self.assertIsNone(payload["target_root"])
        self.assertEqual(payload["authority"], "system")

    def test_private_url_manifest_rejects_relative_manifest_url_before_ffi(self) -> None:
        """
        Verify the dedicated private manifest helper rejects relative URLs before FFI dispatch.
        校验专用私有 manifest 辅助入口会在 FFI 分发前拒绝相对 URL。
        """

        client = RecordingClient()
        system = SystemSkillManagementClient(client, Authority.SYSTEM)

        with self.assertRaisesRegex(ValueError, "manifest_url must be an absolute HTTP or HTTPS URL"):
            system.install_private_url_manifest(
                [{"name": "ROOT", "skills_dir": "runtime/skills"}],
                "private.demo",
                "/private/skill.json",
            )
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
