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

from luaskills.runtime_assets import host_options_from_runtime_manifest


class RuntimeManifestHostOptionsTests(unittest.TestCase):
    """
    Verify runtime manifest host option paths remain scoped to runtime_root.
    校验运行时清单宿主选项路径保持在 runtime_root 范围内。
    """

    def test_host_options_from_runtime_manifest_sanitizes_root_paths(self) -> None:
        """
        Accept and normalize root-scoped manifest host option paths.
        接受并归一化 root 范围内的 manifest 宿主选项路径。
        """

        with TemporaryDirectory() as temporary_text:
            runtime_root = Path(temporary_text)
            manifest = {
                "runtime_root": str(runtime_root),
                "host_options_patch": {
                    "sqlite_library_path": "libs/sqlite.dll",
                    "lancedb_library_path": str(runtime_root / "libs" / "lancedb.dll"),
                    "space_controller": {
                        "executable_path": "bin/vldb-controller.exe",
                    },
                },
            }

            options = host_options_from_runtime_manifest(manifest)
            self.assertEqual(options["sqlite_library_path"], str((runtime_root / "libs" / "sqlite.dll").resolve()).replace("\\", "/"))
            self.assertEqual(options["space_controller"]["executable_path"], str((runtime_root / "bin" / "vldb-controller.exe").resolve()).replace("\\", "/"))

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
