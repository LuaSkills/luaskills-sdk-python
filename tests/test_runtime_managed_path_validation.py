"""
Managed runtime path validation tests.
受管运行时路径校验测试。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

# Make the source package importable when tests run from one checkout.
# 从检出目录运行测试时让源码包可导入。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from luaskills.runtime_assets import resolve_managed_runtime_child_path, resolve_managed_runtime_installed_path


class ManagedRuntimePathValidationTests(unittest.TestCase):
    """
    Verify managed runtime plan paths cannot escape the runtime root.
    校验受管运行时计划路径不能逃逸 runtime root。
    """

    def test_resolve_managed_runtime_installed_path_accepts_relative_child(self) -> None:
        """
        Accept a generated relative installed path under the runtime root.
        接受 runtime root 下生成的相对安装路径。
        """

        with TemporaryDirectory() as temporary_text:
            runtime_root = Path(temporary_text)
            plan = {"installed_paths": {"uv": "dependencies/runtimes/python/uv-test"}}
            resolved = resolve_managed_runtime_installed_path(runtime_root, plan, "uv")
            self.assertEqual(resolved, (runtime_root / "dependencies/runtimes/python/uv-test").resolve())

    def test_resolve_managed_runtime_installed_path_rejects_traversal(self) -> None:
        """
        Reject an installed path that escapes with parent directory traversal.
        拒绝通过父目录遍历逃逸的安装路径。
        """

        with TemporaryDirectory() as temporary_text:
            plan = {"installed_paths": {"uv": "../outside"}}
            with self.assertRaisesRegex(ValueError, "escapes its root|relative path"):
                resolve_managed_runtime_installed_path(Path(temporary_text), plan, "uv")

    def test_resolve_managed_runtime_installed_path_rejects_windows_absolute_path(self) -> None:
        """
        Reject Windows absolute paths regardless of the current host platform.
        无论当前宿主平台如何都拒绝 Windows 绝对路径。
        """

        with TemporaryDirectory() as temporary_text:
            plan = {"installed_paths": {"uv": r"C:\outside"}}
            with self.assertRaisesRegex(ValueError, "relative path inside"):
                resolve_managed_runtime_installed_path(Path(temporary_text), plan, "uv")

    def test_resolve_managed_runtime_installed_path_rejects_normalized_traversal(self) -> None:
        """
        Reject parent traversal segments even when the normalized path would stay inside.
        即使归一化后仍在内部，也拒绝父目录遍历片段。
        """

        with TemporaryDirectory() as temporary_text:
            plan = {"installed_paths": {"uv": "dependencies/../uv"}}
            with self.assertRaisesRegex(ValueError, "relative path inside"):
                resolve_managed_runtime_installed_path(Path(temporary_text), plan, "uv")

    def test_resolve_managed_runtime_child_path_rejects_executable_escape(self) -> None:
        """
        Reject executable paths that escape a managed runtime directory.
        拒绝逃逸受管运行时目录的可执行文件路径。
        """

        with TemporaryDirectory() as temporary_text:
            runtime_directory = Path(temporary_text) / "runtime"
            runtime_directory.mkdir()
            with self.assertRaisesRegex(ValueError, "escapes its root|relative path"):
                resolve_managed_runtime_child_path(runtime_directory, "../uv.exe", "managed uv executable")


if __name__ == "__main__":
    unittest.main()
