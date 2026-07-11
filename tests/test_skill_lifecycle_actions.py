from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Make the source package importable when tests run from one checkout.
# 从检出目录运行测试时让源码包可导入。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from luaskills.client import SkillManagementClient, SystemSkillManagementClient
from luaskills.types import Authority, SkillInstallSourceType


class RecordingClient:
    """
    Minimal client double that records skill lifecycle calls.
    记录 skill 生命周期调用的最小客户端替身。
    """

    def __init__(self) -> None:
        """
        Initialize one fake engine id and empty call list.
        初始化一个假的引擎标识和空调用列表。
        """

        self.engine_id = 99
        self.calls: list[tuple[str, dict[str, object]]] = []

    def _call(self, function_name: str, payload: dict[str, object]) -> dict[str, object]:
        """
        Record one SDK call and return one object-shaped result.
        记录一次 SDK 调用并返回对象形状结果。
        """

        self.calls.append((function_name, payload))
        return {"status": "ok"}


class SkillLifecycleActionTests(unittest.TestCase):
    """
    Unit tests for typed skill lifecycle FFI action dispatch.
    类型化 skill 生命周期 FFI 动作分发的单元测试。
    """

    def test_public_disable_uses_public_endpoint_without_authority(self) -> None:
        """
        Verify ordinary lifecycle calls use public FFI names and omit authority.
        校验普通生命周期调用使用 public FFI 函数名且不注入 authority。
        """

        client = RecordingClient()
        management = SkillManagementClient(client, system_plane=False)

        result = management.disable([{"name": "ROOT", "skills_dir": "runtime/skills"}], "demo.skill", "manual")

        self.assertEqual(result["status"], "ok")
        function_name, payload = client.calls[0]
        self.assertEqual(function_name, "luaskills_ffi_disable_skill_json")
        self.assertEqual(payload["engine_id"], 99)
        self.assertEqual(payload["skill_id"], "demo.skill")
        self.assertEqual(payload["reason"], "manual")
        self.assertNotIn("authority", payload)

    def test_system_update_uses_system_endpoint_and_authority(self) -> None:
        """
        Verify system lifecycle calls use system FFI names and injected authority.
        校验 system 生命周期调用使用 system FFI 函数名并注入 authority。
        """

        client = RecordingClient()
        management = SystemSkillManagementClient(client, Authority.DELEGATED_TOOL)

        management.update(
            [{"name": "ROOT", "skills_dir": "runtime/skills"}],
            {"source_type": SkillInstallSourceType.GITHUB, "source": "LuaSkills/demo-skill"},
        )

        function_name, payload = client.calls[0]
        self.assertEqual(function_name, "luaskills_ffi_system_update_skill_json")
        self.assertEqual(payload["engine_id"], 99)
        self.assertEqual(payload["authority"], "delegated_tool")
        self.assertEqual(payload["target_root"], None)
        self.assertEqual(payload["request"], {"source_type": "github", "source": "LuaSkills/demo-skill"})

    def test_install_rejects_legacy_source_shape_before_ffi(self) -> None:
        """
        Verify legacy type/url request keys fail before native FFI dispatch.
        校验旧版 type/url 请求键会在原生 FFI 分发前失败。
        """

        client = RecordingClient()
        management = SkillManagementClient(client, system_plane=False)

        with self.assertRaisesRegex(ValueError, "unsupported keys"):
            management.install(
                [{"name": "ROOT", "skills_dir": "runtime/skills"}],
                {"type": "github", "url": "https://example.test/skill.git"},
            )
        self.assertEqual(client.calls, [])

    def test_private_manifest_install_rejects_non_http_source_before_ffi(self) -> None:
        """
        Verify private URL-manifest managed install rejects non-HTTP source locators.
        校验私有 URL manifest 受管安装会拒绝非 HTTP 来源定位值。
        """

        client = RecordingClient()
        management = SystemSkillManagementClient(client, Authority.SYSTEM)

        with self.assertRaisesRegex(ValueError, "source must use|absolute HTTP"):
            management.install(
                [{"name": "ROOT", "skills_dir": "runtime/skills"}],
                {
                    "skill_id": "private.demo",
                    "source_type": SkillInstallSourceType.PRIVATE_URL_MANIFEST,
                    "source": "file:///tmp/private.json",
                },
            )
        self.assertEqual(client.calls, [])

    def test_function_name_rejects_unsupported_action(self) -> None:
        """
        Verify unsupported lifecycle actions fail before native FFI dispatch.
        校验不支持的生命周期动作会在原生 FFI 分发前失败。
        """

        client = RecordingClient()
        management = SkillManagementClient(client, system_plane=False)

        with self.assertRaisesRegex(ValueError, "unsupported skill lifecycle action"):
            management._function_name("delete_skill")
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
