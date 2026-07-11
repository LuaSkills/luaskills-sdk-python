"""
Runtime archive validation tests.
运行时归档校验测试。
"""

from __future__ import annotations

import tarfile
import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

# Make the source package importable when tests run from one checkout.
# 从检出目录运行测试时让源码包可导入。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from luaskills.runtime_assets import extract_archive, validate_archive_member_path


class RuntimeArchiveValidationTests(unittest.TestCase):
    """
    Verify runtime archive extraction rejects unsafe members before writing them.
    校验运行时归档解压会在写入前拒绝不安全成员。
    """

    def test_extract_archive_rejects_zip_traversal(self) -> None:
        """
        Reject a zip member that would escape the extraction destination.
        拒绝会逃逸解压目标目录的 zip 成员。
        """

        with TemporaryDirectory() as temporary_text:
            temporary_root = Path(temporary_text)
            archive_path = temporary_root / "unsafe.zip"
            destination = temporary_root / "extract"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../evil.txt", "bad")

            with self.assertRaisesRegex(ValueError, "archive member escapes extraction directory"):
                extract_archive(archive_path, destination)

    def test_extract_archive_rejects_tar_symlink_escape(self) -> None:
        """
        Reject a tar symlink whose target resolves outside the destination.
        拒绝目标解析到解压目录外部的 tar 符号链接。
        """

        with TemporaryDirectory() as temporary_text:
            temporary_root = Path(temporary_text)
            archive_path = temporary_root / "unsafe.tar.gz"
            destination = temporary_root / "extract"
            with tarfile.open(archive_path, "w:gz") as archive:
                link_info = tarfile.TarInfo("safe/link")
                link_info.type = tarfile.SYMTYPE
                link_info.linkname = "../../evil.txt"
                archive.addfile(link_info)

            with self.assertRaisesRegex(ValueError, "archive member escapes extraction directory"):
                extract_archive(archive_path, destination)

    def test_extract_archive_rejects_tar_special_member(self) -> None:
        """
        Reject a tar member that is neither a regular file, directory, nor link.
        拒绝非常规文件、目录或链接的 tar 成员。
        """

        with TemporaryDirectory() as temporary_text:
            temporary_root = Path(temporary_text)
            archive_path = temporary_root / "unsafe.tar.gz"
            destination = temporary_root / "extract"
            with tarfile.open(archive_path, "w:gz") as archive:
                fifo_info = tarfile.TarInfo("pipe")
                fifo_info.type = tarfile.FIFOTYPE
                archive.addfile(fifo_info)

            with self.assertRaisesRegex(ValueError, "unsupported tar member type"):
                extract_archive(archive_path, destination)

    def test_validate_archive_member_path_rejects_windows_absolute_path(self) -> None:
        """
        Reject Windows absolute paths even when tests run on non-Windows hosts.
        即使测试运行在非 Windows 宿主上也拒绝 Windows 绝对路径。
        """

        with TemporaryDirectory() as temporary_text:
            with self.assertRaisesRegex(ValueError, "unsafe archive member path"):
                validate_archive_member_path(Path(temporary_text), r"C:\outside.txt")


if __name__ == "__main__":
    unittest.main()
