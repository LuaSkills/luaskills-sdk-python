"""
Shared Python SDK types for LuaSkills JSON FFI integration.
LuaSkills JSON FFI 集成使用的 Python SDK 共享类型。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Literal, TypeAlias, TypedDict

JsonValue: TypeAlias = Any


class RuntimeChangeSetLine(TypedDict):
    """
    One canonical change-set line record.
    单条 canonical change_set 行记录。
    """

    line: int
    content: str


class RuntimeChangeSetHunk(TypedDict):
    """
    One canonical change-set modify hunk.
    单个 canonical change_set modify hunk。
    """

    before: str
    delete: list[RuntimeChangeSetLine]
    insert: list[RuntimeChangeSetLine]
    after: str


class RuntimeChangeSetDiagnostic(TypedDict):
    """
    One canonical change-set diagnostic record.
    单条 canonical change_set 诊断记录。
    """

    level: str
    message: str


class RuntimeChangeSetFile(TypedDict, total=False):
    """
    One canonical change-set file record.
    单个 canonical change_set 文件记录。
    """

    change: Literal["create", "modify", "delete", "rename"]
    path: str
    old_path: str
    new_path: str
    content: str
    hunks: list[RuntimeChangeSetHunk]
    patch: str | None


class RuntimeChangeSetPayload(TypedDict, total=False):
    """
    Canonical `change_set` payload consumed by IDE-aware hosts.
    IDE 感知宿主消费的 canonical `change_set` 载荷。
    """

    mode: Literal["preview", "applied"]
    summary: str | None
    files: list[RuntimeChangeSetFile]
    diagnostics: list[RuntimeChangeSetDiagnostic]


class RuntimeHostResult(TypedDict):
    """
    Structured host-side result returned alongside tool text content.
    与工具文本结果一并返回的结构化宿主侧结果。
    """

    kind: str
    payload: JsonValue


class RuntimeChangeSetHostResult(TypedDict):
    """
    Runtime host-result envelope specialized for canonical `change_set`.
    专用于 canonical `change_set` 的运行时宿主结果包络。
    """

    kind: Literal["change_set"]
    payload: RuntimeChangeSetPayload


class Authority(str, Enum):
    """
    Host-injected authority used by query and system management entrypoints.
    查询与 system 管理入口使用的宿主注入权限。
    """

    SYSTEM = "system"
    DELEGATED_TOOL = "delegated_tool"


class SkillInstallSourceType(str, Enum):
    """
    Supported managed skill source type.
    支持的受管 skill 来源类型。
    """

    # GitHub Release backed managed skill source.
    # 基于 GitHub Release 的受管理 skill 来源。
    GITHUB = "github"
    # Official LuaSkills Hub managed skill source.
    # 官方 LuaSkills Hub 的受管理 skill 来源。
    OFFICIAL_HUB = "official_hub"
    # Remote source descriptor URL source.
    # 远程 source 描述文件 URL 来源。
    URL = "url"
    # Host-private URL manifest source.
    # 宿主私有 URL manifest 来源。
    PRIVATE_URL_MANIFEST = "private_url_manifest"


@dataclass(frozen=True)
class RuntimeSkillRoot:
    """
    Named runtime skill root used by the formal ROOT, PROJECT, USER chain.
    正式 ROOT、PROJECT、USER 链使用的命名运行时 skill 根。
    """

    name: str
    skills_dir: str

    def to_json(self) -> dict[str, str]:
        """
        Convert this root descriptor into one JSON FFI payload object.
        将当前 root 描述转换为 JSON FFI 载荷对象。
        """

        return asdict(self)


@dataclass(frozen=True)
class LuaInvocationContext:
    """
    Invocation context injected into call_skill and run_lua.
    注入 call_skill 与 run_lua 的调用上下文。
    """

    request_context: JsonValue | None = None
    client_budget: JsonValue | None = None
    tool_config: JsonValue | None = None

    def to_json(self) -> dict[str, JsonValue]:
        """
        Convert this invocation context into one JSON FFI payload object.
        将当前调用上下文转换为 JSON FFI 载荷对象。
        """

        return {
            "request_context": self.request_context,
            "client_budget": self.client_budget or {},
            "tool_config": self.tool_config or {},
        }


def roots_to_json(skill_roots: list[RuntimeSkillRoot | dict[str, str]]) -> list[dict[str, str]]:
    """
    Convert mixed runtime-root values into JSON objects.
    将混合 runtime root 值转换为 JSON 对象。
    """

    return [root.to_json() if isinstance(root, RuntimeSkillRoot) else root for root in skill_roots]


def authority_value(authority: Authority | str) -> str:
    """
    Return the raw JSON authority value.
    返回原始 JSON 权限值。
    """

    return authority.value if isinstance(authority, Authority) else authority
