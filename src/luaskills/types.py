"""
Shared Python SDK types for LuaSkills JSON FFI integration.
LuaSkills JSON FFI 集成使用的 Python SDK 共享类型。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Literal, TypeAlias, TypedDict

from .config_contract import (
    SkillConfigStoreScope,
    SkillPackageConfigFormat,
    SkillPackageConfigItemState,
    SkillPackageConfigType,
)

JsonValue: TypeAlias = Any

# ManagedRuntimeKind identifies the host-selected managed interpreter family.
# ManagedRuntimeKind 标识宿主选择的受管解释器类型。
ManagedRuntimeKind: TypeAlias = Literal["python", "node"]



# Typed scalar accepted by package configuration writes.
# 技能包配置写入接受的类型化标量。
SkillConfigValue: TypeAlias = str | int | float | bool

class SkillPackageConfigConstraints(TypedDict, total=False):
    """
    Type-specific package configuration constraints.
    类型专属技能包配置约束。
    """

    minimum: int | float
    maximum: int | float
    min_length: int
    max_length: int


class SkillPackageConfigEnumOption(TypedDict):
    """
    One declared package configuration enumeration option.
    单个已声明技能包配置枚举选项。
    """

    value: str
    label: str
    description: str


class _SkillPackageConfigDeclarationRequired(TypedDict):
    """
    Required package configuration declaration fields.
    技能包配置声明必填字段。
    """

    key: str
    type: SkillPackageConfigType
    required: bool
    sensitive: bool
    description: str
    constraints: SkillPackageConfigConstraints
    options: list[SkillPackageConfigEnumOption]
    advanced: bool
    restart_required: bool
    deprecated: bool


class SkillPackageConfigDeclaration(_SkillPackageConfigDeclarationRequired, total=False):
    """
    Complete manifest-level package configuration declaration.
    完整清单级技能包配置声明。
    """

    default: SkillConfigValue
    title: str
    group: str
    order: int
    placeholder: str
    example: SkillConfigValue
    format: SkillPackageConfigFormat
    deprecation_message: str


class SkillPackageConfigValidationError(TypedDict):
    """
    Structured value-safe item validation failure.
    结构化且不泄漏值的配置项校验失败。
    """

    code: str
    message: str


class _SkillPackageConfigItemDescriptorRequired(_SkillPackageConfigDeclarationRequired):
    """
    Required runtime item descriptor fields.
    运行时配置项描述必填字段。
    """

    state: SkillPackageConfigItemState
    satisfied: bool


class SkillPackageConfigItemDescriptor(
    _SkillPackageConfigItemDescriptorRequired,
    total=False,
):
    """
    Runtime descriptor for one declared package configuration item.
    单个已声明技能包配置项的运行时描述。
    """

    default: SkillConfigValue
    title: str
    group: str
    order: int
    placeholder: str
    example: SkillConfigValue
    format: SkillPackageConfigFormat
    deprecation_message: str
    validation_error: SkillPackageConfigValidationError
    value: str


class SkillPackageConfigIssue(TypedDict):
    """
    One key-owned static configuration issue.
    单个配置键所属的静态配置问题。
    """

    key: str
    code: str
    message: str


class SkillPackageConfigBusinessIssue(TypedDict, total=False):
    """
    One optional-key cross-field business issue.
    单个可选键跨字段业务问题。
    """

    key: str
    code: str
    message: str


class SkillPackageConfigStatus(TypedDict):
    """
    Completeness and validity status of one effective package.
    单个有效技能包的完整性与合法性状态。
    """

    skill_id: str
    complete: bool
    revision: str
    store_scope: SkillConfigStoreScope
    missing: list[SkillPackageConfigIssue]
    invalid: list[SkillPackageConfigIssue]
    business_issues: list[SkillPackageConfigBusinessIssue]
    orphaned: list[str]
    orphaned_count: int


class SkillPackageConfigDescriptor(TypedDict):
    """
    Effective package configuration descriptor.
    有效技能包配置描述。
    """

    skill_id: str
    skill_version: str
    complete: bool
    revision: str
    store_scope: SkillConfigStoreScope
    missing_count: int
    invalid_count: int
    business_issue_count: int
    orphaned_count: int
    orphaned: list[str]
    items: list[SkillPackageConfigItemDescriptor]


class SkillConfigEventError(TypedDict):
    """
    Structured watcher or reload failure.
    结构化监听或重载失败。
    """

    code: str
    message: str


class InstalledSkillPackageConfigDescriptor(TypedDict, total=False):
    """
    Physical installed package declaration descriptor.
    物理已安装技能包声明描述。
    """

    skill_id: str
    root_name: str
    absolute_path: str
    enabled: bool
    shadowed: bool
    effective: bool
    manifest_valid: bool
    manifest_issue: SkillConfigEventError
    skill_version: str
    config: list[SkillPackageConfigDeclaration]


class SkillConfigEntry(TypedDict):
    """
    One raw persisted package configuration record.
    单条原始持久化技能包配置记录。
    """

    store_scope: SkillConfigStoreScope
    skill_id: str
    key: str
    value: str


class _SkillConfigGetResultRequired(TypedDict):
    """
    Required fields of one package configuration lookup result.
    单个技能包配置查询结果的必填字段。
    """

    found: bool
    skill_id: str
    key: str


class SkillConfigGetResult(_SkillConfigGetResultRequired, total=False):
    """
    One package configuration lookup result with an optional found value.
    单个技能包配置查询结果，可选包含已找到的值。
    """

    value: str


class SkillConfigWriteResult(TypedDict):
    """
    Result of one atomic package configuration write.
    单次原子技能包配置写入结果。
    """

    revision: str
    changed: bool
    values: dict[str, str]
    changed_keys: list[str]


class SkillConfigDeleteResult(TypedDict):
    """
    Result of one compare-and-swap deletion.
    单次比较并交换删除结果。
    """

    revision: str
    deleted: bool
    key: str


class SkillConfigEvent(TypedDict, total=False):
    """
    One ordered package configuration event.
    单个有序技能包配置事件。
    """

    sequence: str
    type: Literal["skill_config_changed", "skill_config_reload_failed"]
    store_scope: SkillConfigStoreScope
    skill_id: str
    revision: str
    changed_keys: list[str]
    source: Literal["local_write", "external_reload"]
    restart_required_keys: list[str]
    complete: bool
    error: SkillConfigEventError


class SkillConfigEventBatch(TypedDict):
    """
    Ordered package configuration event batch.
    有序技能包配置事件批次。
    """

    events: list[SkillConfigEvent]
    next_sequence: str


class SkillConfigStoreRefresh(TypedDict):
    """
    Result of one explicit store refresh.
    单次显式存储刷新结果。
    """

    store_scope: SkillConfigStoreScope
    revision: str
    changed: bool


class LuaRuntimeManagedRuntimeConfig(TypedDict):
    """
    Host-selected managed Python/Node Worker and persistent-session resource policy.
    宿主选择的受管 Python/Node Worker 与持久会话资源策略。
    """

    # WorkerPoolMaxSizePerEnvironment is the maximum live Worker count for one exact pool key.
    # WorkerPoolMaxSizePerEnvironment 是单个精确池键的最大活动 Worker 数量。
    worker_pool_max_size_per_environment: int
    # WorkerIdleTtlSecs is the idle lifetime before one unused Worker may be retired.
    # WorkerIdleTtlSecs 是未使用 Worker 可被回收前的空闲秒数。
    worker_idle_ttl_secs: int
    # PersistentSessionLimitPerEngine bounds launching and live sessions owned by one engine.
    # PersistentSessionLimitPerEngine 限制单个引擎拥有的启动中与活动会话数量。
    persistent_session_limit_per_engine: int
    # PersistentSessionDefaultBufferLimitBytesPerStream is the omitted session.open stream limit.
    # PersistentSessionDefaultBufferLimitBytesPerStream 是 session.open 省略时的每流缓冲上限。
    persistent_session_default_buffer_limit_bytes_per_stream: int
    # InvokeDefaultTimeoutMs is the omitted invoke timeout; None means unlimited.
    # InvokeDefaultTimeoutMs 是 invoke 省略时的超时；None 表示无限制。
    invoke_default_timeout_ms: int | None


class ManagedRuntimeInstallDescriptor(TypedDict):
    """
    Validated host-visible managed runtime installation returned by LuaSkills.
    LuaSkills 返回的已校验宿主可见受管运行时安装。
    """

    # Runtime is the exact managed interpreter family.
    # Runtime 是精确的受管解释器类型。
    runtime: ManagedRuntimeKind
    # Version is the exact semantic runtime version.
    # Version 是精确的语义化运行时版本。
    version: str
    # Platform is the normalized LuaSkills platform key.
    # Platform 是规范化的 LuaSkills 平台键。
    platform: str
    # InstallRoot is the canonical installation directory.
    # InstallRoot 是规范安装目录。
    install_root: str
    # Executable is the canonical interpreter executable path.
    # Executable 是规范解释器可执行文件路径。
    executable: str
    # ManifestHash is the SHA-256 digest of runtime-manifest.json.
    # ManifestHash 是 runtime-manifest.json 的 SHA-256 摘要。
    manifest_hash: str
    # ExecutableHash is the SHA-256 digest of the interpreter executable.
    # ExecutableHash 是解释器可执行文件的 SHA-256 摘要。
    executable_hash: str


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
