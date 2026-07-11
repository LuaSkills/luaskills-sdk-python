"""
Runtime checksum validation tests.
运行时校验和校验测试。
"""

from __future__ import annotations

import base64
import hashlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

# Make the source package importable when tests run from one checkout.
# 从检出目录运行测试时让源码包可导入。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from luaskills.runtime_assets import verify_named_sha256, verify_sha256, verify_sha512_integrity


class RuntimeChecksumValidationTests(unittest.TestCase):
    """
    Verify runtime asset checksum helpers reject malformed checksum protocols.
    校验运行时资产校验和辅助函数会拒绝畸形校验协议。
    """

    def test_verify_sha256_rejects_empty_sidecar(self) -> None:
        """
        Reject an empty SHA-256 sidecar with a stable ValueError.
        使用稳定的 ValueError 拒绝空 SHA-256 旁路文件。
        """

        with TemporaryDirectory() as temporary_text:
            file_path = write_sample_file(Path(temporary_text))
            with self.assertRaisesRegex(ValueError, "invalid SHA-256 sidecar"):
                verify_sha256(file_path, "")

    def test_verify_sha256_rejects_malformed_digest(self) -> None:
        """
        Reject a SHA-256 sidecar whose first token is not a full hex digest.
        拒绝首个 token 不是完整十六进制摘要的 SHA-256 旁路文件。
        """

        with TemporaryDirectory() as temporary_text:
            file_path = write_sample_file(Path(temporary_text))
            with self.assertRaisesRegex(ValueError, "invalid SHA-256 digest"):
                verify_sha256(file_path, "abc sample.bin")

    def test_verify_named_sha256_requires_exact_asset_entry(self) -> None:
        """
        Require a named SHA-256 manifest entry to match the exact asset name.
        要求命名 SHA-256 清单条目精确匹配资产名。
        """

        with TemporaryDirectory() as temporary_text:
            file_path = write_sample_file(Path(temporary_text))
            digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "was not found"):
                verify_named_sha256(file_path, f"{digest} other.bin\n", "sample.bin")

    def test_verify_named_sha256_accepts_exact_valid_entry(self) -> None:
        """
        Accept a named SHA-256 manifest entry with the exact asset name.
        接受资产名精确匹配的命名 SHA-256 清单条目。
        """

        with TemporaryDirectory() as temporary_text:
            file_path = write_sample_file(Path(temporary_text))
            digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
            verify_named_sha256(file_path, f"{digest} sample.bin\n", "sample.bin")

    def test_verify_sha512_integrity_validates_prefix_and_base64(self) -> None:
        """
        Reject malformed npm integrity strings before comparing file bytes.
        比较文件字节前拒绝畸形 npm integrity 字符串。
        """

        with TemporaryDirectory() as temporary_text:
            file_path = write_sample_file(Path(temporary_text))
            with self.assertRaisesRegex(ValueError, "invalid SHA-512 integrity"):
                verify_sha512_integrity(file_path, "sha256-not-sha512")
            with self.assertRaisesRegex(ValueError, "invalid SHA-512 integrity"):
                verify_sha512_integrity(file_path, "sha512-not-base64!")

    def test_verify_sha512_integrity_accepts_matching_digest(self) -> None:
        """
        Accept a SHA-512 integrity string that matches the downloaded file.
        接受与已下载文件匹配的 SHA-512 integrity 字符串。
        """

        with TemporaryDirectory() as temporary_text:
            file_path = write_sample_file(Path(temporary_text))
            digest = base64.b64encode(hashlib.sha512(file_path.read_bytes()).digest()).decode("ascii")
            verify_sha512_integrity(file_path, f"sha512-{digest}")


def write_sample_file(directory: Path) -> Path:
    """
    Write one deterministic sample file and return its path.
    写入一个确定性的样例文件并返回路径。
    """

    file_path = directory / "sample.bin"
    file_path.write_bytes(b"luaskills checksum sample")
    return file_path


if __name__ == "__main__":
    unittest.main()
