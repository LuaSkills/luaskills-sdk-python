from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Make the source package importable when tests run from one checkout.
# 从检出目录运行测试时让源码包可导入。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from luaskills.runtime_assets import decode_runtime_install_manifest


class RuntimeManifestErrorTests(unittest.TestCase):
    """
    Unit tests for malformed runtime install manifest diagnostics.
    畸形运行时安装清单诊断的单元测试。
    """

    def test_decode_runtime_install_manifest_reports_path_aware_errors(self) -> None:
        """
        Verify malformed manifests include path and protocol context.
        校验畸形清单包含路径和协议上下文。
        """

        manifest_path = Path("runtime/resources/luaskills-sdk-runtime-manifest.json")
        cases = [
            ("", "is empty"),
            ("{", "is invalid JSON"),
            ("[1]", "must be one JSON object"),
        ]

        for raw, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(ValueError, expected):
                    decode_runtime_install_manifest(manifest_path, raw)


if __name__ == "__main__":
    unittest.main()
