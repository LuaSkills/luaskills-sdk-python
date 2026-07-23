"""
Real native package-configuration JSON FFI integration tests.
真实原生技能包配置 JSON FFI 集成测试。
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from luaskills import LuaSkillsClient


@unittest.skipUnless(os.environ.get("LUASKILLS_LIB"), "LUASKILLS_LIB is not configured")
class SkillConfigNativeIntegrationTests(unittest.TestCase):
    """
    Verify the Python SDK against the matching built LuaSkills dynamic library.
    使用匹配的已构建 LuaSkills 动态库验证 Python SDK。
    """

    def test_full_package_configuration_round_trip(self) -> None:
        """
        Cover declaration discovery, batch writes, CAS, routing, and ordered events.
        覆盖声明发现、批量写入、CAS、路由与有序事件。
        """

        # Temporary host root isolates all package and persistent state.
        # 临时宿主根目录隔离全部技能包与持久化状态。
        with tempfile.TemporaryDirectory(prefix="luaskills-config-e2e-") as directory:
            # Resolved root makes every host path absolute before crossing FFI.
            # 解析后的根目录使每个宿主路径在穿过 FFI 前均为绝对路径。
            host_root = Path(directory).resolve()
            # Runtime root satisfies unrelated fixed engine layout requirements.
            # 运行时根目录满足其他固定引擎布局要求。
            runtime_root = host_root / "runtime"
            # User-level configuration root is independent from package installation.
            # 用户级配置根目录独立于技能包安装。
            config_root = host_root / "config"
            # ROOT package directory verifies system-skill storage routing.
            # ROOT 技能包目录验证系统技能存储路由。
            root_skills = host_root / "root-skills"
            # USER package directory verifies ordinary storage routing.
            # USER 技能包目录验证普通存储路由。
            user_skills = host_root / "user-skills"
            self._write_config_skill(root_skills, "system-config-e2e")
            self._write_config_skill(user_skills, "user-config-e2e")

            # Client points explicitly at the just-built library and configuration root.
            # 客户端显式指向刚构建的动态库与配置根目录。
            with LuaSkillsClient(
                library_path=os.environ["LUASKILLS_LIB"],
                runtime_root=runtime_root,
                host_options={
                    "skill_config_root": str(config_root),
                    "skill_config_lock_timeout_ms": 5_000,
                    "skill_config_watch_debounce_ms": 20,
                },
            ) as client:
                client.load_from_roots(
                    [
                        {"name": "ROOT", "skills_dir": str(root_skills)},
                        {"name": "USER", "skills_dir": str(user_skills)},
                    ]
                )

                # Descriptor proves all common declaration types cross the native boundary.
                # 描述符证明所有常见声明类型均能穿过原生边界。
                descriptor = client.config.describe("user-config-e2e")[0]
                self.assertEqual(descriptor["skill_id"], "user-config-e2e")
                self.assertEqual(
                    [item["type"] for item in descriptor["items"]],
                    ["string", "integer", "float", "enum", "boolean"],
                )
                self.assertFalse(client.config.validate("user-config-e2e")["complete"])

                # One typed batch returns the revision used by subsequent CAS operations.
                # 单个类型化批次返回后续 CAS 操作使用的修订号。
                written = client.config.set(
                    "user-config-e2e",
                    {
                        "token": "secret",
                        "retries": 4,
                        "ratio": 0.5,
                        "mode": "fast",
                        "enabled": True,
                    },
                )
                self.assertTrue(written["changed"])
                self.assertEqual(
                    written["changed_keys"],
                    ["enabled", "mode", "ratio", "retries", "token"],
                )
                self.assertTrue(client.config.validate("user-config-e2e")["complete"])
                self.assertEqual(
                    client.config.get("user-config-e2e", "retries")["value"],
                    "4",
                )
                # Raw user records proving store-origin metadata reaches the SDK.
                # 证明存储来源元数据抵达 SDK 的原始用户记录。
                user_entries = client.config.list("user-config-e2e")
                self.assertEqual(len(user_entries), 5)
                self.assertTrue(
                    all(
                        entry["store_scope"] == "skills"
                        for entry in user_entries
                    )
                )

                # A stale CAS revision cannot overwrite committed state.
                # 过期 CAS 修订号不能覆盖已提交状态。
                with self.assertRaisesRegex(Exception, "CONFIG_REVISION_CONFLICT"):
                    client.config.set(
                        "user-config-e2e",
                        "retries",
                        5,
                        expected_revision="0",
                    )
                # One invalid member rejects the whole batch atomically.
                # 一个非法成员会原子拒绝整个批次。
                with self.assertRaisesRegex(Exception, "CONFIG_VALUE_OUT_OF_RANGE"):
                    client.config.set(
                        "user-config-e2e",
                        {"retries": 99, "enabled": False},
                        expected_revision=written["revision"],
                    )
                self.assertEqual(
                    client.config.get("user-config-e2e", "enabled")["value"],
                    "true",
                )

                # ROOT-owned values are persisted only in the dedicated system store.
                # ROOT 所属值仅持久化到专用系统存储。
                client.config.set(
                    "system-config-e2e",
                    {
                        "token": "system-secret",
                        "retries": 1,
                        "ratio": 1.0,
                        "mode": "safe",
                        "enabled": False,
                    },
                )
                system_document = json.loads(
                    (config_root / "system-skills" / "config.json").read_text(
                        encoding="utf-8"
                    )
                )
                normal_document = json.loads(
                    (config_root / "skills" / "config.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(
                    system_document["skills"]["system-config-e2e"]["token"],
                    "system-secret",
                )
                self.assertNotIn("system-config-e2e", normal_document["skills"])

                # Cursor pagination must expose subsequent local transactions without skipping.
                # 游标分页必须公开后续本地事务且不得跳过。
                first_page = client.config.poll_events(limit=1)
                self.assertEqual(len(first_page["events"]), 1)
                second_page = client.config.poll_events(
                    first_page["next_sequence"],
                    limit=10,
                )
                self.assertGreaterEqual(len(second_page["events"]), 1)

    @staticmethod
    def _write_config_skill(skills_root: Path, skill_id: str) -> None:
        """
        Create one valid package containing every common declaration type.
        创建一个包含所有常见声明类型的合法技能包。

        Args:
            skills_root: Physical root containing package directories.
            skill_id: Stable package identifier.
        Returns:
            None.

        参数：
            skills_root：包含技能包目录的物理根目录。
            skill_id：稳定技能包标识符。
        返回：
            无。
        """

        # Package directory owns its manifest and one inert Lua entry.
        # 技能包目录保存其清单与一个无副作用 Lua 入口。
        package_root = skills_root / skill_id
        (package_root / "runtime").mkdir(parents=True)
        (package_root / "skill.yaml").write_text(
            f"""name: {skill_id}
version: 1.0.0
enable: true
debug: false
config:
  - key: token
    type: string
    required: true
    sensitive: true
    description: Access token
    constraints:
      min_length: 1
      max_length: 128
  - key: retries
    type: integer
    default: 3
    description: Retry count
    constraints:
      minimum: 0
      maximum: 10
  - key: ratio
    type: float
    default: 0.25
    description: Sampling ratio
    constraints:
      minimum: 0.0
      maximum: 1.0
  - key: mode
    type: enum
    default: safe
    description: Execution mode
    options:
      - value: safe
        label: Safe
        description: Conservative mode
      - value: fast
        label: Fast
        description: Fast mode
  - key: enabled
    type: boolean
    default: false
    description: Feature switch
entries:
  - name: ping
    description: Return a stable response.
    lua_entry: runtime/main.lua
    lua_module: {skill_id}.main
""",
            encoding="utf-8",
        )
        (package_root / "runtime" / "main.lua").write_text(
            "return function() return 'ok' end\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
