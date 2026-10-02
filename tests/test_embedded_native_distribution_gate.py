"""
Prove missing and mismatched native candidates fail before package installation, without optional native skips.
证明缺失及不匹配原生候选在包安装前失败，不使用可选原生跳过。
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


# The executable gate is selected explicitly from this test's repository, independent of the working directory.
# 从此测试的仓库显式选择可执行门禁，不依赖工作目录。
GATE = Path(__file__).resolve().parents[1] / "scripts/verify_embedded_native_distribution.py"


class NativeDistributionGateTests(unittest.TestCase):
    """
    Verify fail-closed CLI behavior using temporary candidate files and no SDK or native test doubles.
    使用临时候选文件验证命令行失败关闭行为，不模拟 SDK 或原生调用。
    """

    def run_gate(self, root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        """
        Run the gate with missing artifact paths under root plus arguments; return captured process evidence.
        在 root 下使用缺失产物路径及 arguments 运行门禁；返回捕获的进程证据。
        """
        return subprocess.run([sys.executable, "-X", "utf8", str(GATE),
            "--wheel", str(root / "missing.whl"), "--sdist", str(root / "missing.tar.gz"),
            *arguments], cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=10)

    def test_library_and_frozen_identity_are_required(self) -> None:
        """
        Omit native arguments and require argparse failure rather than an offline-only success; return nothing.
        省略原生参数并要求 argparse 失败而非仅离线成功；无返回值。
        """
        with tempfile.TemporaryDirectory() as temporary:
            # A missing native declaration cannot inherit LUASKILLS_LIB or select an artifact automatically.
            # 缺失原生声明不能继承 LUASKILLS_LIB 或自动选择产物。
            result = self.run_gate(Path(temporary))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--library", result.stderr)
            self.assertIn("--library-sha256", result.stderr)
            self.assertIn("--description", result.stderr)

    def test_missing_library_fails_before_reading_artifacts(self) -> None:
        """
        Select a nonexistent library and require its explicit failure before missing wheel validation; return nothing.
        选择不存在的库并要求其在缺失 wheel 校验前显式失败；无返回值。
        """
        with tempfile.TemporaryDirectory() as temporary:
            # Both artifacts deliberately do not exist, exposing verification order through the exact error.
            # 两个产物刻意不存在，通过精确错误显示校验顺序。
            root = Path(temporary)
            result = self.run_gate(root, "--library", str(root / "missing.dll"),
                "--library-sha256", "0" * 64, "--description", str(root / "description.json"))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("required native candidate library is missing", result.stderr)
            self.assertNotIn("missing.whl", result.stderr)

    def test_wrong_library_digest_fails_before_loading_or_installation(self) -> None:
        """
        Select regular fake candidate files with a wrong digest and require identity failure; return nothing.
        选择普通伪候选文件及错误摘要并要求身份失败；无返回值。
        """
        with tempfile.TemporaryDirectory() as temporary:
            # Bytes are deliberately not loadable; digest rejection must happen before any native loader call.
            # 字节刻意不可加载；摘要拒绝必须先于任何原生加载器调用。
            root = Path(temporary)
            library = root / "candidate.dll"
            description = root / "description.json"
            library.write_bytes(b"not a native library")
            description.write_text("{}", encoding="utf-8")
            result = self.run_gate(root, "--library", str(library), "--library-sha256", "0" * 64,
                "--description", str(description))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("native candidate library SHA-256 mismatch", result.stderr)
            self.assertNotIn("missing.whl", result.stderr)


if __name__ == "__main__":
    unittest.main()
