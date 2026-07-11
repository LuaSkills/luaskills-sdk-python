from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Make the source package importable when tests run from one checkout.
# 从检出目录运行测试时让源码包可导入。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from luaskills.types import SkillInstallSourceType


class SkillInstallSourceTypeTests(unittest.TestCase):
    """
    Unit tests for managed skill install source protocol values.
    受管理 skill 安装来源协议值的单元测试。
    """

    def test_source_type_values_match_rust_protocol(self) -> None:
        """
        Verify SDK enum values match Rust SkillInstallSourceType JSON values.
        校验 SDK 枚举值匹配 Rust SkillInstallSourceType JSON 值。
        """

        self.assertEqual(SkillInstallSourceType.GITHUB.value, "github")
        self.assertEqual(SkillInstallSourceType.OFFICIAL_HUB.value, "official_hub")
        self.assertEqual(SkillInstallSourceType.URL.value, "url")
        self.assertEqual(SkillInstallSourceType.PRIVATE_URL_MANIFEST.value, "private_url_manifest")


if __name__ == "__main__":
    unittest.main()
