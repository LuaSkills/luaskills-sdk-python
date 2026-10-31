"""
Runtime manifest host option path validation tests.
运行时清单宿主选项路径校验测试。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

# Make the source package importable when tests run from one checkout.
# 从检出目录运行测试时让源码包可导入。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from luaskills.runtime_assets import host_options_from_runtime_manifest, build_runtime_install_manifest
from luaskills import default_host_options


class RuntimeManifestHostOptionsTests(unittest.TestCase):
    """Verify host-only manifests and explicit rejection of retired database settings.
    验证仅由宿主管理的清单，并显式拒绝退役数据库设置。
    """

    def test_host_callback_installs_no_database(self) -> None:
        """Verify the actual manifest contains only core/Lua assets and rejects retired database configuration.
        验证实际清单仅包含核心及 Lua 资产，并拒绝退役数据库配置。
        """
        with TemporaryDirectory() as temporary_text:
            # Pin the fixture package version to keep this test entirely offline.
            # 固定夹具包版本，使此测试完全离线。
            manifest = build_runtime_install_manifest(runtime_root=temporary_text, database="host-callback", lua_runtime_version="v0.1.6")
            self.assertEqual({asset["role"] for asset in manifest["assets"]}, {"lua_runtime", "luaskills_ffi"})
            self.assertEqual(manifest["host_options_patch"], {"sqlite_callback_mode": "json"})
            self.assertEqual(default_host_options(temporary_text)["host_mode"], "console")
            for preset in ("vldb-controller", "vldb-direct"):
                with self.assertRaises(ValueError):
                    build_runtime_install_manifest(runtime_root=temporary_text, database=preset, lua_runtime_version="v0.1.6")
            for key in ("sqlite_library_path", "sqlite_provider_mode", "lancedb_library_path", "lancedb_provider_mode", "lancedb_callback_mode", "space_controller"):
                with self.assertRaisesRegex(ValueError, key):
                    host_options_from_runtime_manifest({"runtime_root": temporary_text, "host_options_patch": {key: None}})

    def test_host_options_from_runtime_manifest_sanitizes_root_paths(self) -> None:
        """Accept only current host registration settings and preserve desktop mode.
        接受当前宿主注册设置，并保留桌面模式。
        """
        with TemporaryDirectory() as temporary_text:
            manifest = {"runtime_root": temporary_text, "host_options_patch": {"host_mode": "desktop", "sqlite_callback_mode": "json"}}
            self.assertEqual(host_options_from_runtime_manifest(manifest), manifest["host_options_patch"])

    def test_host_options_from_runtime_manifest_rejects_escaping_path(self) -> None:
        """
        Reject host option paths that escape the runtime root.
        拒绝逃逸 runtime root 的宿主选项路径。
        """

        with TemporaryDirectory() as temporary_text:
            manifest = {
                "runtime_root": temporary_text,
                "host_options_patch": {
                    "sqlite_library_path": "../outside.dll",
                },
            }
            with self.assertRaisesRegex(ValueError, "sqlite_library_path"):
                host_options_from_runtime_manifest(manifest)

    def test_host_options_from_runtime_manifest_rejects_invalid_space_controller(self) -> None:
        """
        Reject malformed nested space controller options.
        拒绝畸形的嵌套 space controller 选项。
        """

        with TemporaryDirectory() as temporary_text:
            manifest = {
                "runtime_root": temporary_text,
                "host_options_patch": {
                    "space_controller": "not-an-object",
                },
            }
            with self.assertRaisesRegex(ValueError, "space_controller"):
                host_options_from_runtime_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
