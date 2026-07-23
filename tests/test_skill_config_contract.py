"""
Core-generated package-configuration contract drift tests.
核心生成的技能包配置契约漂移测试。
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from luaskills.config_contract import (
    SKILL_CONFIG_CONTRACT_VERSION,
    SKILL_CONFIG_ERROR_CODES,
    SKILL_CONFIG_MAXIMUM_EVENT_POLL_LIMIT,
    SKILL_CONFIG_MAXIMUM_SAFE_INTEGER,
    SKILL_CONFIG_STORE_SCOPES,
    SKILL_PACKAGE_CONFIG_DESCRIBE_MODES,
    SKILL_PACKAGE_CONFIG_FORMATS,
    SKILL_PACKAGE_CONFIG_STATES,
    SKILL_PACKAGE_CONFIG_TYPES,
)


class SkillConfigContractTests(unittest.TestCase):
    """
    Verify public Python constants match the checked-in core-generated contract.
    验证 Python 公共常量与检入的核心生成契约一致。
    """

    def test_public_constants_match_contract(self) -> None:
        """
        Reject any unchecked drift in types, states, formats, or numeric limits.
        拒绝类型、状态、格式或数值上限中未经检查的漂移。
        """

        # Repository-local canonical contract copied from the matching core release.
        # 从匹配核心版本复制的仓库本地规范契约。
        contract_path = (
            Path(__file__).resolve().parents[1]
            / "contracts"
            / "skill-config"
            / "v1"
            / "contract.json"
        )
        # Parsed contract document used as the source of truth.
        # 作为事实源使用的已解析契约文档。
        contract = json.loads(contract_path.read_text(encoding="utf-8"))

        self.assertEqual(SKILL_CONFIG_CONTRACT_VERSION, contract["contract_version"])
        self.assertEqual(list(SKILL_CONFIG_ERROR_CODES), contract["errors"])
        self.assertEqual(list(SKILL_PACKAGE_CONFIG_TYPES), contract["declaration"]["types"])
        self.assertEqual(list(SKILL_PACKAGE_CONFIG_FORMATS), contract["declaration"]["formats"])
        self.assertEqual(list(SKILL_PACKAGE_CONFIG_STATES), contract["declaration"]["states"])
        self.assertEqual(
            list(SKILL_PACKAGE_CONFIG_DESCRIBE_MODES),
            contract["declaration"]["describe_modes"],
        )
        self.assertEqual(
            list(SKILL_CONFIG_STORE_SCOPES),
            contract["declaration"]["store_scopes"],
        )
        self.assertEqual(
            SKILL_CONFIG_MAXIMUM_SAFE_INTEGER,
            contract["limits"]["maximum_safe_integer"],
        )
        self.assertEqual(
            SKILL_CONFIG_MAXIMUM_EVENT_POLL_LIMIT,
            contract["limits"]["maximum_event_poll_limit"],
        )

    def test_generated_module_is_current(self) -> None:
        """
        Run the deterministic generator in check mode to reject stale source.
        以检查模式运行确定性生成器以拒绝过期源码。
        """

        # Generator path belongs to this repository and performs no writes in check mode.
        # 生成器路径属于当前仓库且在检查模式下不执行写入。
        generator = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "generate_skill_config_contract.py"
        )
        subprocess.run(
            [sys.executable, str(generator), "--check"],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()
