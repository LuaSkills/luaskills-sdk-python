"""
Package-configuration discovery and validation client tests.
技能包配置发现与校验客户端测试。
"""

from __future__ import annotations

import unittest
from typing import Any

from luaskills.client import SkillConfigClient


class RecordingClient:
    """
    Minimal parent client that records JSON FFI calls made by SkillConfigClient.
    记录 SkillConfigClient 所发 JSON FFI 调用的最小父客户端。
    """

    def __init__(self) -> None:
        """
        Initialize a stable engine id and an empty call log.
        初始化稳定引擎 ID 与空调用日志。
        """

        # Stable fake native engine handle.
        # 稳定的假原生引擎句柄。
        self.engine_id = 77
        # Ordered JSON FFI calls emitted by the namespace under test.
        # 被测命名空间发出的有序 JSON FFI 调用。
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _call(self, function_name: str, payload: dict[str, Any]) -> Any:
        """
        Record one JSON FFI call and return a deterministic matching result.
        记录一次 JSON FFI 调用并返回确定的对应结果。
        """

        self.calls.append((function_name, payload))
        if function_name.endswith("_describe_json"):
            return [
                {
                    "skill_id": "demo-skill",
                    "skill_version": "1.0.0",
                    "complete": False,
                    "orphaned_count": 0,
                    "items": [],
                }
            ]
        return {
            "skill_id": "demo-skill",
            "complete": False,
            "missing": [],
            "invalid": [],
            "orphaned_count": 0,
        }


class SkillPackageConfigClientTests(unittest.TestCase):
    """
    Verify package-configuration methods preserve the public JSON FFI contract.
    验证技能包配置方法保持公共 JSON FFI 契约。
    """

    def test_describe_and_validate_payloads(self) -> None:
        """
        Verify optional value disclosure is explicit and validation targets one package.
        验证可选值披露必须显式启用，且校验只针对单个技能包。
        """

        # Recording parent client used by the child configuration namespace.
        # 子配置命名空间使用的记录型父客户端。
        parent = RecordingClient()
        # Package-configuration namespace under test.
        # 被测的技能包配置命名空间。
        config = SkillConfigClient(parent)  # type: ignore[arg-type]

        descriptors = config.describe("demo-skill", include_values=True)
        self.assertEqual(descriptors[0]["skill_id"], "demo-skill")
        self.assertEqual(
            parent.calls[0],
            (
                "luaskills_ffi_skill_config_describe_json",
                {
                    "engine_id": 77,
                    "skill_id": "demo-skill",
                    "include_values": True,
                    "mode": "effective",
                    "root_name": None,
                },
            ),
        )

        status = config.validate("demo-skill")
        self.assertFalse(status["complete"])
        self.assertEqual(
            parent.calls[1],
            (
                "luaskills_ffi_skill_config_validate_json",
                {
                    "engine_id": 77,
                    "skill_id": "demo-skill",
                },
            ),
        )

    def test_mutation_event_and_numeric_contracts(self) -> None:
        """
        Verify batch/CAS payloads and reject integers outside the shared exact range.
        验证批量/CAS 载荷并拒绝超出共享精确范围的整数。
        """

        # Recording parent client used by the configuration namespace.
        # 配置命名空间使用的记录型父客户端。
        parent = RecordingClient()
        # Package-configuration namespace under test.
        # 被测的技能包配置命名空间。
        config = SkillConfigClient(parent)  # type: ignore[arg-type]

        config.set(
            "demo-skill",
            {"retry_count": 3, "enabled": True},
            expected_revision="7",
        )
        self.assertEqual(
            parent.calls[0],
            (
                "luaskills_ffi_skill_config_set_json",
                {
                    "engine_id": 77,
                    "skill_id": "demo-skill",
                    "values": {"retry_count": 3, "enabled": True},
                    "expected_revision": "7",
                },
            ),
        )
        config.delete("demo-skill", "retry_count", expected_revision="8")
        self.assertEqual(
            parent.calls[1],
            (
                "luaskills_ffi_skill_config_delete_json",
                {
                    "engine_id": 77,
                    "skill_id": "demo-skill",
                    "key": "retry_count",
                    "expected_revision": "8",
                },
            ),
        )
        config.refresh("skills")
        config.poll_events("12", limit=25)
        self.assertEqual(
            parent.calls[3],
            (
                "luaskills_ffi_skill_config_events_poll_json",
                {
                    "engine_id": 77,
                    "after_sequence": "12",
                    "limit": 25,
                },
            ),
        )
        config.set("demo-skill", "large_float", 1e20)
        self.assertEqual(
            parent.calls[4],
            (
                "luaskills_ffi_skill_config_set_json",
                {
                    "engine_id": 77,
                    "skill_id": "demo-skill",
                    "values": {"large_float": 1e20},
                    "expected_revision": None,
                },
            ),
        )
        with self.assertRaises(ValueError):
            config.set("demo-skill", "retry_count", 9_007_199_254_740_992)
        with self.assertRaises(ValueError):
            config.poll_events(limit=0)


if __name__ == "__main__":
    unittest.main()
