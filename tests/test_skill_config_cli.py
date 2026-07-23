"""
Skill package configuration CLI contract tests.
技能包配置 CLI 契约测试。
"""

from __future__ import annotations

import unittest

from luaskills.cli import (
    build_parser,
    normalize_global_args,
    parse_skill_config_value,
    parse_skill_config_values,
)


class SkillConfigCliTests(unittest.TestCase):
    """
    Verify CLI configuration inputs preserve typed batch and explicit-root semantics.
    验证 CLI 配置输入保持类型化批次与显式根目录语义。
    """

    def test_global_config_root_is_accepted_after_subcommand(self) -> None:
        """
        Keep the explicit configuration root usable in the customary trailing position.
        保持显式配置根目录可在常用的命令尾部位置使用。
        """

        # ParsedArgs represents one user command after global-option normalization.
        # ParsedArgs 表示经过全局选项规范化后的用户命令。
        parsed_args = build_parser().parse_args(
            normalize_global_args(
                [
                    "config",
                    "describe",
                    "demo-skill",
                    "--skill-config-root",
                    "D:/user-config",
                ]
            )
        )
        self.assertEqual(parsed_args.skill_config_root, "D:/user-config")
        self.assertEqual(parsed_args.action, "describe")
        self.assertEqual(parsed_args.values, ["demo-skill"])

    def test_config_values_are_parsed_as_json_scalars_and_batches(self) -> None:
        """
        Preserve JSON number, boolean, and string types without accepting nested values.
        保持 JSON 数字、布尔与字符串类型，同时拒绝嵌套值。
        """

        self.assertEqual(parse_skill_config_value("3"), 3)
        self.assertEqual(parse_skill_config_value("true"), True)
        self.assertEqual(parse_skill_config_value('"safe"'), "safe")
        self.assertEqual(
            parse_skill_config_values('{"retry_count":3,"enabled":true}'),
            {"retry_count": 3, "enabled": True},
        )
        with self.assertRaises(TypeError):
            parse_skill_config_value("null")
        with self.assertRaises(TypeError):
            parse_skill_config_values('{"nested":{"value":1}}')


if __name__ == "__main__":
    unittest.main()
