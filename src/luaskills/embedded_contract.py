"""
Generated embedded wire shapes; run scripts/generate_embedded_contract.py to update.
生成的嵌入式线形状；运行 scripts/generate_embedded_contract.py 更新。
Types describe JSON shape; core validation owns bounds, authorization and lifecycle semantics.
类型描述 JSON 形状；核心校验负责边界、授权及生命周期语义。
"""

from __future__ import annotations

from enum import IntEnum
from typing import Dict, List, Literal, TypeAlias, TypedDict, Union

# Recursive JSON values preserve exact integers within native bounds and explicit null separately from absence.
# 递归 JSON 值保留原生边界内的精确整数，并将显式空值与缺失分开。
JsonValue: TypeAlias = Union[None, bool, int, float, str, List["JsonValue"], Dict[str, "JsonValue"]]

# Generated contract metadata: EMBEDDED_PROTOCOL_VERSION.
# 生成的契约元数据：EMBEDDED_PROTOCOL_VERSION。
EMBEDDED_PROTOCOL_VERSION = 1

# Generated contract metadata: EMBEDDED_CONTRACT_VERSION.
# 生成的契约元数据：EMBEDDED_CONTRACT_VERSION。
EMBEDDED_CONTRACT_VERSION = 1

# Generated contract metadata: EMBEDDED_CORE_VERSION.
# 生成的契约元数据：EMBEDDED_CORE_VERSION。
EMBEDDED_CORE_VERSION = '0.5.9'

# Generated contract metadata: EMBEDDED_CONTRACT_SHA256.
# 生成的契约元数据：EMBEDDED_CONTRACT_SHA256。
EMBEDDED_CONTRACT_SHA256 = '3db021e06afb4aee8ac00100db2a5ba20e29cb68cb43d5461a1770b9fd2e2b86'

# Generated contract metadata: EMBEDDED_DESCRIPTION_VERSION.
# 生成的契约元数据：EMBEDDED_DESCRIPTION_VERSION。
EMBEDDED_DESCRIPTION_VERSION = 1

# Generated contract metadata: EMBEDDED_DESCRIPTION_MAX_BYTES.
# 生成的契约元数据：EMBEDDED_DESCRIPTION_MAX_BYTES。
EMBEDDED_DESCRIPTION_MAX_BYTES = 16384

# Generated contract metadata: EMBEDDED_REQUIRED_CAPABILITIES.
# 生成的契约元数据：EMBEDDED_REQUIRED_CAPABILITIES。
EMBEDDED_REQUIRED_CAPABILITIES = ('bounded_transports_v1', 'plugin_budgets_v1', 'shared_pools_v1', 'dedicated_pools_v1', 'fixed_sessions_v1', 'host_request_queue_v1', 'in_memory_effect_evidence_v1', 'strict_json_v1')

# Generated contract metadata: EMBEDDED_ROOT_COMMANDS.
# 生成的契约元数据：EMBEDDED_ROOT_COMMANDS。
EMBEDDED_ROOT_COMMANDS = ('describe', 'runtime_reserve', 'runtime_initialize', 'runtime_status', 'runtime_close', 'runtime_free', 'runtime')

# Generated contract metadata: EMBEDDED_RUNTIME_COMMANDS.
# 生成的契约元数据：EMBEDDED_RUNTIME_COMMANDS。
EMBEDDED_RUNTIME_COMMANDS = ('plugin_register', 'plugin_status', 'plugin_close', 'plugin_forget', 'pool_register', 'pool_status', 'pool_close', 'pool_forget', 'pool_revoke_permission', 'call_submit', 'session_open', 'session_submit', 'session_status', 'session_close', 'session_forget', 'operation_status', 'operation_wait', 'operation_cancel', 'operation_forget', 'capabilities_register', 'capabilities_list', 'capability_status', 'capability_unregister', 'capability_forget', 'host_requests_take', 'host_request_status', 'host_request_complete')


class EmbeddedNativeStatus(IntEnum):
    """
    Exact native transport return codes from the Rust contract.
    来自 Rust 契约的精确原生传输返回码。
    """
    # Native status ok.
    # 原生状态 ok。
    OK = 0
    # Native status invalid_argument.
    # 原生状态 invalid_argument。
    INVALID_ARGUMENT = 1
    # Native status not_found.
    # 原生状态 not_found。
    NOT_FOUND = 2
    # Native status busy.
    # 原生状态 busy。
    BUSY = 3
    # Native status capacity_exceeded.
    # 原生状态 capacity_exceeded。
    CAPACITY_EXCEEDED = 4
    # Native status closed.
    # 原生状态 closed。
    CLOSED = 5
    # Native status internal.
    # 原生状态 internal。
    INTERNAL = 6
    # Native status unsupported.
    # 原生状态 unsupported。
    UNSUPPORTED = 7


class InputCapabilityDescriptor(TypedDict, total=True):
    """
    Wire fields for InputCapabilityDescriptor; native validation enforces semantic constraints.
    InputCapabilityDescriptor 的线字段；原生校验负责语义约束。
    Immutable capability declaration shared by Rust, generated contracts and SDKs.
    Rust、生成契约与 SDK 共享的不可变能力声明。
    """
    # English description of the host capability for tool consumers.
    # 面向工具消费者的宿主能力英文描述。
    # Exact wire member description; required independently of nullability.
    # 精确线成员 description；必需与是否可为空值相互独立。
    description: str
    # Declared mutation category.
    # 声明的变更类别。
    # Exact wire member effects; required independently of nullability.
    # 精确线成员 effects；必需与是否可为空值相互独立。
    effects: 'InputCapabilityEffects'
    # Explicit native or queued dispatch protocol.
    # 显式原生或队列分发协议。
    # Exact wire member execution; required independently of nullability.
    # 精确线成员 execution；必需与是否可为空值相互独立。
    execution: 'InputCapabilityExecution'
    # Explicit host deduplication contract.
    # 显式宿主去重契约。
    # Exact wire member idempotency; required independently of nullability.
    # 精确线成员 idempotency；必需与是否可为空值相互独立。
    idempotency: 'InputCapabilityIdempotency'
    # Offline input value contract.
    # 离线输入值契约。
    # Exact wire member input_schema; required independently of nullability.
    # 精确线成员 input_schema；必需与是否可为空值相互独立。
    input_schema: JsonValue
    # Per-capability budget capped by the original operation deadline.
    # 受原始操作截止时间约束的单能力预算。
    # Exact wire member max_call_ms; required independently of nullability.
    # 精确线成员 max_call_ms；必需与是否可为空值相互独立。
    max_call_ms: int
    # Maximum in-flight handlers, including cancelled handlers that have not stopped.
    # 在途处理器上限，包含已取消但尚未停止的处理器。
    # Exact wire member max_concurrent; required independently of nullability.
    # 精确线成员 max_concurrent；必需与是否可为空值相互独立。
    max_concurrent: int
    # Maximum serialized input bytes within the parent value limit.
    # 父级值上限内的最大序列化输入字节数。
    # Exact wire member max_input_bytes; required independently of nullability.
    # 精确线成员 max_input_bytes；必需与是否可为空值相互独立。
    max_input_bytes: int
    # Maximum serialized output bytes within the parent value limit.
    # 父级值上限内的最大序列化输出字节数。
    # Exact wire member max_output_bytes; required independently of nullability.
    # 精确线成员 max_output_bytes；必需与是否可为空值相互独立。
    max_output_bytes: int
    # Exact namespaced name; discovery exposes only authorized declarations.
    # 精确命名空间名称；发现操作仅暴露已授权声明。
    # Exact wire member name; required independently of nullability.
    # 精确线成员 name；必需与是否可为空值相互独立。
    name: str
    # Offline output value contract.
    # 离线输出值契约。
    # Exact wire member output_schema; required independently of nullability.
    # 精确线成员 output_schema；必需与是否可为空值相互独立。
    output_schema: JsonValue
    # Every listed grant must still exist at each admission boundary.
    # 每个入场边界仍必须拥有列出的全部授权。
    # Exact wire member permissions; required independently of nullability.
    # 精确线成员 permissions；必需与是否可为空值相互独立。
    permissions: List[str]
    # Required trusted invocation scope.
    # 必需的可信调用作用域。
    # Exact wire member scope; required independently of nullability.
    # 精确线成员 scope；必需与是否可为空值相互独立。
    scope: 'InputCapabilityScope'
    # Semantic interface version, independent from the core library version.
    # 语义接口版本，独立于核心库版本。
    # Exact wire member version; required independently of nullability.
    # 精确线成员 version；必需与是否可为空值相互独立。
    version: str


# Exact wire shape of InputCapabilityEffects, derived from the packaged core schema.
# 从包内核心 Schema 派生的 InputCapabilityEffects 精确线形状。
InputCapabilityEffects: TypeAlias = Literal['read_only', 'mutating']


# Exact wire shape of InputCapabilityExecution, derived from the packaged core schema.
# 从包内核心 Schema 派生的 InputCapabilityExecution 精确线形状。
InputCapabilityExecution: TypeAlias = Literal['native', 'queued']


# Exact wire shape of InputCapabilityIdempotency, derived from the packaged core schema.
# 从包内核心 Schema 派生的 InputCapabilityIdempotency 精确线形状。
InputCapabilityIdempotency: TypeAlias = Literal['none', 'host_request']


# Exact wire shape of InputCapabilityScope, derived from the packaged core schema.
# 从包内核心 Schema 派生的 InputCapabilityScope 精确线形状。
InputCapabilityScope: TypeAlias = Literal['invocation', 'session']


class InputCommandRuntime(TypedDict, total=True):
    """
    Wire fields for InputCommandRuntime; native validation enforces semantic constraints.
    InputCommandRuntime 的线字段；原生校验负责语义约束。
    Execute one typed operation on an exact initialized runtime.
    在精确已初始化运行时上执行一个类型化操作。
    """
    # Typed core operation with no legacy command aliases.
    # 不含旧命令别名的类型化核心操作。
    # Exact wire member operation; required independently of nullability.
    # 精确线成员 operation；必需与是否可为空值相互独立。
    operation: 'InputRuntimeCommand'
    # Exact transport-local runtime identity.
    # 精确传输局部运行时身份。
    # Exact wire member runtime_id; required independently of nullability.
    # 精确线成员 runtime_id；必需与是否可为空值相互独立。
    runtime_id: str
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['runtime']


class InputCommandDescribe(TypedDict, total=True):
    """
    Wire fields for InputCommandDescribe; native validation enforces semantic constraints.
    InputCommandDescribe 的线字段；原生校验负责语义约束。
    Inspect effective transport limits and implemented protocol commands.
    查看有效传输限制与已实现协议命令。
    """
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['describe']


class InputCommandRuntimeReserve(TypedDict, total=True):
    """
    Wire fields for InputCommandRuntimeReserve; native validation enforces semantic constraints.
    InputCommandRuntimeReserve 的线字段；原生校验负责语义约束。
    Allocate a bounded metadata-only runtime identity before construction can begin.
    在构造能够开始前分配有界且仅含元数据的运行时身份。
    """
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['runtime_reserve']


class InputCommandRuntimeInitialize(TypedDict, total=True):
    """
    Wire fields for InputCommandRuntimeInitialize; native validation enforces semantic constraints.
    InputCommandRuntimeInitialize 的线字段；原生校验负责语义约束。
    Attempt construction exactly once; the existing identity retains the actual outcome for query.
    精确尝试构造一次；已有身份保留实际结果供查询。
    """
    # Explicit core engine options, using the existing engine option contract.
    # 显式核心引擎选项，使用现有引擎选项契约。
    # Exact wire member engine_options; required independently of nullability.
    # 精确线成员 engine_options；必需与是否可为空值相互独立。
    engine_options: 'InputLuaEngineOptions'
    # Explicit formal runtime budgets validated before worker construction.
    # 工作线程构造前校验的显式正式运行时预算。
    # Exact wire member runtime_config; required independently of nullability.
    # 精确线成员 runtime_config；必需与是否可为空值相互独立。
    runtime_config: 'InputEmbeddedRuntimeConfig'
    # Exact identity returned by runtime_reserve in this transport.
    # 此传输中 runtime_reserve 返回的精确身份。
    # Exact wire member runtime_id; required independently of nullability.
    # 精确线成员 runtime_id；必需与是否可为空值相互独立。
    runtime_id: str
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['runtime_initialize']


class InputCommandRuntimeStatus(TypedDict, total=True):
    """
    Wire fields for InputCommandRuntimeStatus; native validation enforces semantic constraints.
    InputCommandRuntimeStatus 的线字段；原生校验负责语义约束。
    Read construction outcome and actual worker closure evidence.
    读取构造结果与实际工作线程关闭证据。
    """
    # Exact retained runtime identity in this transport.
    # 此传输中保留的精确运行时身份。
    # Exact wire member runtime_id; required independently of nullability.
    # 精确线成员 runtime_id；必需与是否可为空值相互独立。
    runtime_id: str
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['runtime_status']


class InputCommandRuntimeClose(TypedDict, total=True):
    """
    Wire fields for InputCommandRuntimeClose; native validation enforces semantic constraints.
    InputCommandRuntimeClose 的线字段；原生校验负责语义约束。
    Close existing admission, including a construction attempt that is still running.
    关闭已有入场，包含仍在运行的构造尝试。
    """
    # Exact retained runtime identity in this transport.
    # 此传输中保留的精确运行时身份。
    # Exact wire member runtime_id; required independently of nullability.
    # 精确线成员 runtime_id；必需与是否可为空值相互独立。
    runtime_id: str
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['runtime_close']


class InputCommandRuntimeFree(TypedDict, total=True):
    """
    Wire fields for InputCommandRuntimeFree; native validation enforces semantic constraints.
    InputCommandRuntimeFree 的线字段；原生校验负责语义约束。
    Remove an explicitly closed and fully drained runtime registration.
    移除显式关闭且完全排空的运行时注册。
    """
    # Exact retained runtime identity in this transport.
    # 此传输中保留的精确运行时身份。
    # Exact wire member runtime_id; required independently of nullability.
    # 精确线成员 runtime_id；必需与是否可为空值相互独立。
    runtime_id: str
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['runtime_free']


# Exact wire shape of InputCommand, derived from the packaged core schema.
# 从包内核心 Schema 派生的 InputCommand 精确线形状。
InputCommand: TypeAlias = Union['InputCommandRuntime', 'InputCommandDescribe', 'InputCommandRuntimeReserve', 'InputCommandRuntimeInitialize', 'InputCommandRuntimeStatus', 'InputCommandRuntimeClose', 'InputCommandRuntimeFree']


# Exact wire shape of InputEffectState, derived from the packaged core schema.
# 从包内核心 Schema 派生的 InputEffectState 精确线形状。
InputEffectState: TypeAlias = Literal['not_started', 'not_applicable', 'committed', 'rolled_back', 'unknown']


class InputEmbeddedCall(TypedDict, total=True):
    """
    Wire fields for InputEmbeddedCall; native validation enforces semantic constraints.
    InputEmbeddedCall 的线字段；原生校验负责语义约束。
    Owned structured request admitted under one original deadline.
    在单个原始截止时间下接纳的拥有所有权的结构化请求。
    """
    # Application value whose encoded size is checked before admission.
    # 入场前检查编码大小的应用值。
    # Exact wire member arguments; required independently of nullability.
    # 精确线成员 arguments；必需与是否可为空值相互独立。
    arguments: JsonValue
    # Trusted host context retained and charged with the queued request.
    # 与排队请求一并保留和计费的可信宿主上下文。
    # Exact wire member context; required independently of nullability.
    # 精确线成员 context；必需与是否可为空值相互独立。
    context: 'InputLuaInvocationContext'
    # Exact declared module export, never an evaluated code fragment.
    # 精确声明的模块导出，绝不是求值代码片段。
    # Exact wire member export; required independently of nullability.
    # 精确线成员 export；必需与是否可为空值相互独立。
    export: str
    # Exact immutable pool identity returned by this runtime.
    # 此运行时返回的精确不可变池身份。
    # Exact wire member pool_id; required independently of nullability.
    # 精确线成员 pool_id；必需与是否可为空值相互独立。
    pool_id: str


class InputEmbeddedError(TypedDict, total=True):
    """
    Wire fields for InputEmbeddedError; native validation enforces semantic constraints.
    InputEmbeddedError 的线字段；原生校验负责语义约束。
    Structured error; `code` is stable and `message` is an English diagnostic.
    结构化错误；`code` 稳定，`message` 为英文诊断信息。
    """
    # Stable classification consumed by SDKs instead of parsing text.
    # 供 SDK 使用的稳定分类，避免解析文案。
    # Exact wire member code; required independently of nullability.
    # 精确线成员 code；必需与是否可为空值相互独立。
    code: 'InputEmbeddedErrorCode'
    # Human-readable detail without credentials or plugin input dumps.
    # 不含凭据或插件输入转储的可读详情。
    # Exact wire member message; required independently of nullability.
    # 精确线成员 message；必需与是否可为空值相互独立。
    message: str


# Exact wire shape of InputEmbeddedErrorCode, derived from the packaged core schema.
# 从包内核心 Schema 派生的 InputEmbeddedErrorCode 精确线形状。
InputEmbeddedErrorCode: TypeAlias = Literal['invalid_argument', 'not_found', 'stale_generation', 'capacity_exceeded', 'busy', 'already_completed', 'closed', 'cancelled', 'deadline_exceeded', 'permission_denied', 'unsupported', 'execution_failed', 'cleanup_failed', 'internal']


class InputEmbeddedPluginConfig(TypedDict, total=True):
    """
    Wire fields for InputEmbeddedPluginConfig; native validation enforces semantic constraints.
    InputEmbeddedPluginConfig 的线字段；原生校验负责语义约束。
    Immutable host-approved aggregate budgets across every generation and execution domain of one plugin.
    一个插件的全部代次与执行域共享的不可变宿主批准聚合预算。
    """
    # Maximum retained operations, including completed results not explicitly forgotten.
    # 保留操作的数量上限，包含尚未显式遗忘的已完成结果。
    # Exact wire member max_operations; required independently of nullability.
    # 精确线成员 max_operations；必需与是否可为空值相互独立。
    max_operations: int
    # Maximum exact serialized queued request bytes across this plugin.
    # 此插件全部排队请求精确序列化字节数上限。
    # Exact wire member max_queued_bytes; required independently of nullability.
    # 精确线成员 max_queued_bytes；必需与是否可为空值相互独立。
    max_queued_bytes: int
    # Maximum accepted queued calls across all domains and sessions.
    # 全部域和会话已接纳排队调用的合计上限。
    # Exact wire member max_queued_calls; required independently of nullability.
    # 精确线成员 max_queued_calls；必需与是否可为空值相互独立。
    max_queued_calls: int
    # Maximum retained pool identities, including closed generations awaiting explicit removal.
    # 保留池身份的数量上限，包含等待显式移除的已关闭代次。
    # Exact wire member max_registered_pools; required independently of nullability.
    # 精确线成员 max_registered_pools；必需与是否可为空值相互独立。
    max_registered_pools: int
    # Maximum actual resident VMs plus other domains' unused dedicated reservations.
    # 实际常驻 VM 与其他域未使用专用预留的合计上限。
    # Exact wire member max_resident_vms; required independently of nullability.
    # 精确线成员 max_resident_vms；必需与是否可为空值相互独立。
    max_resident_vms: int
    # Maximum dispatched operations, retained through initialization, host waiting and cleanup.
    # 已分发操作上限，计费覆盖初始化、宿主等待及清理。
    # Exact wire member max_running_calls; required independently of nullability.
    # 精确线成员 max_running_calls；必需与是否可为空值相互独立。
    max_running_calls: int
    # Maximum retained sessions, including closed session records.
    # 保留会话的数量上限，包含已关闭会话记录。
    # Exact wire member max_sessions; required independently of nullability.
    # 精确线成员 max_sessions；必需与是否可为空值相互独立。
    max_sessions: int


class InputEmbeddedRuntimeConfig(TypedDict, total=True):
    """
    Wire fields for InputEmbeddedRuntimeConfig; native validation enforces semantic constraints.
    InputEmbeddedRuntimeConfig 的线字段；原生校验负责语义约束。
    Explicit parent budgets; hosts resolve defaults once before construction.
    显式父级预算；宿主在构造前一次性解析默认值。
    """
    # Maximum serialized effect metadata bytes retained by one operation.
    # 单次操作保留的副作用元数据序列化字节上限。
    # Exact wire member max_effect_bytes_per_operation; required independently of nullability.
    # 精确线成员 max_effect_bytes_per_operation；必需与是否可为空值相互独立。
    max_effect_bytes_per_operation: int
    # Maximum host effect records retained by one operation, including completed callbacks.
    # 单次操作保留的宿主副作用记录上限，包含已完成回调。
    # Exact wire member max_effect_records_per_operation; required independently of nullability.
    # 精确线成员 max_effect_records_per_operation；必需与是否可为空值相互独立。
    max_effect_records_per_operation: int
    # Maximum request bytes and reserved application output bytes, including dispatched calls.
    # 请求字节与预留应用输出字节上限，包含已分发调用。
    # Fixed protocol error metadata is separately bounded by the retained request count.
    # 固定协议错误元数据由保留请求数量独立约束。
    # Exact wire member max_host_request_bytes; required independently of nullability.
    # 精确线成员 max_host_request_bytes；必需与是否可为空值相互独立。
    max_host_request_bytes: int
    # Maximum pending host requests across all plugin instances.
    # 所有插件实例待完成宿主请求的数量上限。
    # Exact wire member max_host_requests; required independently of nullability.
    # 精确线成员 max_host_requests；必需与是否可为空值相互独立。
    max_host_requests: int
    # Maximum operation records retained, including unfinished operations.
    # 操作记录保留数量上限，包含未完成操作。
    # Exact wire member max_operations; required independently of nullability.
    # 精确线成员 max_operations；必需与是否可为空值相互独立。
    max_operations: int
    # Maximum serialized bytes retained by queued requests.
    # 排队请求保留的序列化字节数上限。
    # Exact wire member max_queued_bytes; required independently of nullability.
    # 精确线成员 max_queued_bytes；必需与是否可为空值相互独立。
    max_queued_bytes: int
    # Maximum accepted requests waiting for an execution slot.
    # 等待执行许可的已接纳请求数量上限。
    # Exact wire member max_queued_calls; required independently of nullability.
    # 精确线成员 max_queued_calls；必需与是否可为空值相互独立。
    max_queued_calls: int
    # Maximum retained capability registrations, including draining or unforgotten retired entries.
    # 能力注册保留上限，包含正在排空或尚未遗忘的已退役条目。
    # Exact wire member max_registered_capabilities; required independently of nullability.
    # 精确线成员 max_registered_capabilities；必需与是否可为空值相互独立。
    max_registered_capabilities: int
    # Maximum retained plugin registrations, including closed entries awaiting explicit removal.
    # 保留插件注册的数量上限，包含等待显式移除的已关闭条目。
    # Exact wire member max_registered_plugins; required independently of nullability.
    # 精确线成员 max_registered_plugins；必需与是否可为空值相互独立。
    max_registered_plugins: int
    # Maximum concurrently registered pool declarations, including draining generations.
    # 同时注册的池声明数量上限，包含正在排空的代次。
    # Exact wire member max_registered_pools; required independently of nullability.
    # 精确线成员 max_registered_pools；必需与是否可为空值相互独立。
    max_registered_pools: int
    # Maximum resident VMs, including creation and pending teardown.
    # 最大常驻 VM 数，包含创建中与等待清理的实例。
    # Exact wire member max_resident_vms; required independently of nullability.
    # 精确线成员 max_resident_vms；必需与是否可为空值相互独立。
    max_resident_vms: int
    # Maximum concurrent calls, including calls waiting for host results.
    # 最大并发调用数，包含等待宿主结果的调用。
    # Exact wire member max_running_calls; required independently of nullability.
    # 精确线成员 max_running_calls；必需与是否可为空值相互独立。
    max_running_calls: int
    # Maximum retained session identities, including closed sessions awaiting explicit removal.
    # 保留会话身份的数量上限，包含等待显式移除的已关闭会话。
    # Exact wire member max_sessions; required independently of nullability.
    # 精确线成员 max_sessions；必需与是否可为空值相互独立。
    max_sessions: int
    # Maximum serialized application value bytes; fixed protocol error metadata is separate.
    # 应用值的最大序列化字节数；固定协议错误元数据独立计算。
    # Exact wire member max_value_bytes; required independently of nullability.
    # 精确线成员 max_value_bytes；必需与是否可为空值相互独立。
    max_value_bytes: int


# Exact wire shape of InputExecutionBackend, derived from the packaged core schema.
# 从包内核心 Schema 派生的 InputExecutionBackend 精确线形状。
InputExecutionBackend: TypeAlias = Literal['in_process', 'worker_process']


class InputHostCompletionShape89b6ef9bf484(TypedDict, total=True):
    """
    Wire fields for InputHostCompletionShape89b6ef9bf484; native validation enforces semantic constraints.
    InputHostCompletionShape89b6ef9bf484 的线字段；原生校验负责语义约束。
    Exactly the success shape; ok must be true and value remains required even when null.
    精确成功形状；ok 必须为真，value 即使为空值也必须存在。
    """
    # Actual host effect evidence.
    # 实际宿主副作用证据。
    # Exact wire member effects; required independently of nullability.
    # 精确线成员 effects；必需与是否可为空值相互独立。
    effects: 'InputEffectState'
    # Explicit success discriminator.
    # 显式成功判别。
    # Exact wire member ok; required independently of nullability.
    # 精确线成员 ok；必需与是否可为空值相互独立。
    ok: bool
    # Actual application result.
    # 实际应用结果。
    # Exact wire member value; required independently of nullability.
    # 精确线成员 value；必需与是否可为空值相互独立。
    value: JsonValue


class InputHostCompletionShapeb9f2ee658336(TypedDict, total=True):
    """
    Wire fields for InputHostCompletionShapeb9f2ee658336; native validation enforces semantic constraints.
    InputHostCompletionShapeb9f2ee658336 的线字段；原生校验负责语义约束。
    Exactly the failure shape; ok must be false.
    精确失败形状；ok 必须为假。
    """
    # Actual host effect evidence, even if a commit preceded the error.
    # 实际宿主副作用证据，即使错误前已发生提交。
    # Exact wire member effects; required independently of nullability.
    # 精确线成员 effects；必需与是否可为空值相互独立。
    effects: 'InputEffectState'
    # Actual structured host error.
    # 实际结构化宿主错误。
    # Exact wire member error; required independently of nullability.
    # 精确线成员 error；必需与是否可为空值相互独立。
    error: 'InputEmbeddedError'
    # Explicit failure discriminator.
    # 显式失败判别。
    # Exact wire member ok; required independently of nullability.
    # 精确线成员 ok；必需与是否可为空值相互独立。
    ok: bool


# Exact wire shape of InputHostCompletion, derived from the packaged core schema.
# 从包内核心 Schema 派生的 InputHostCompletion 精确线形状。
InputHostCompletion: TypeAlias = Union['InputHostCompletionShape89b6ef9bf484', 'InputHostCompletionShapeb9f2ee658336']


# Exact wire shape of InputInstanceReuse, derived from the packaged core schema.
# 从包内核心 Schema 派生的 InputInstanceReuse 精确线形状。
InputInstanceReuse: TypeAlias = Literal['single_call', 'reusable', 'session']


class InputLuaEngineOptions(TypedDict, total=True):
    """
    Wire fields for InputLuaEngineOptions; native validation enforces semantic constraints.
    InputLuaEngineOptions 的线字段；原生校验负责语义约束。
    Construction options used by the host to create one LuaSkills runtime engine.
    宿主创建单个 LuaSkills 运行时引擎时使用的构造选项。
    """
    # Host-owned runtime paths and external library locations.
    # 宿主拥有的运行时路径与外部动态库位置配置。
    # Exact wire member host_options; required independently of nullability.
    # 精确线成员 host_options；必需与是否可为空值相互独立。
    host_options: 'InputLuaRuntimeHostOptions'
    # Pool sizing configuration for reusable Lua virtual machines.
    # 可复用 Lua 虚拟机池的容量配置。
    # Exact wire member pool_config; required independently of nullability.
    # 精确线成员 pool_config；必需与是否可为空值相互独立。
    pool_config: 'InputLuaVmPoolConfig'


class _InputLuaInvocationContextRequired(TypedDict, total=True):
    """
    Wire fields for _InputLuaInvocationContextRequired; native validation enforces semantic constraints.
    _InputLuaInvocationContextRequired 的线字段；原生校验负责语义约束。
    Host-injected invocation context delivered alongside one skill or runlua call.
    宿主在单次 skill 或 runlua 调用时一并注入的调用上下文。
    """
    # Host-resolved client budget object injected into `vulcan.context.client_budget`.
    # 宿主解析后的客户端预算对象，将被注入到 `vulcan.context.client_budget`。
    # Exact wire member client_budget; required independently of nullability.
    # 精确线成员 client_budget；必需与是否可为空值相互独立。
    client_budget: JsonValue
    # Host-resolved tool configuration object injected into `vulcan.context.tool_config`.
    # 宿主解析后的工具配置对象，将被注入到 `vulcan.context.tool_config`。
    # Exact wire member tool_config; required independently of nullability.
    # 精确线成员 tool_config；必需与是否可为空值相互独立。
    tool_config: JsonValue


class InputLuaInvocationContext(_InputLuaInvocationContextRequired, total=False):
    """
    Wire fields for InputLuaInvocationContext; native validation enforces semantic constraints.
    InputLuaInvocationContext 的线字段；原生校验负责语义约束。
    Host-injected invocation context delivered alongside one skill or runlua call.
    宿主在单次 skill 或 runlua 调用时一并注入的调用上下文。
    """
    # Optional transport/request metadata preserved for Lua consumption.
    # 供 Lua 消费的可选传输层/请求层元数据。
    # Exact wire member request_context; omittable independently of nullability.
    # 精确线成员 request_context；可省略与是否可为空值相互独立。
    request_context: Union['InputRuntimeRequestContext', None]


class _InputLuaRuntimeCapabilityOptionsRequired(TypedDict, total=True):
    """
    Wire fields for _InputLuaRuntimeCapabilityOptionsRequired; native validation enforces semantic constraints.
    _InputLuaRuntimeCapabilityOptionsRequired 的线字段；原生校验负责语义约束。
    Host-controlled toggles for optional Lua-exposed runtime bridges.
    宿主控制的可选 Lua 暴露运行时桥接开关集合。
    """
    # Whether luaexec and runtime sessions replace Lua's global `io` table with managed IO.
    # luaexec 与持久运行时会话是否使用托管 IO 替换 Lua 全局 `io` 表。
    # Exact wire member enable_managed_io_compat; required independently of nullability.
    # 精确线成员 enable_managed_io_compat；必需与是否可为空值相互独立。
    enable_managed_io_compat: bool


class InputLuaRuntimeCapabilityOptions(_InputLuaRuntimeCapabilityOptionsRequired, total=False):
    """
    Wire fields for InputLuaRuntimeCapabilityOptions; native validation enforces semantic constraints.
    InputLuaRuntimeCapabilityOptions 的线字段；原生校验负责语义约束。
    Host-controlled toggles for optional Lua-exposed runtime bridges.
    宿主控制的可选 Lua 暴露运行时桥接开关集合。
    """
    # Whether `vulcan.runtime.skills.*` management bridges are exposed to Lua.
    # 是否将 `vulcan.runtime.skills.*` 管理桥接暴露给 Lua。
    # Exact wire member enable_skill_management_bridge; omittable independently of nullability.
    # 精确线成员 enable_skill_management_bridge；可省略与是否可为空值相互独立。
    enable_skill_management_bridge: bool


# Exact wire shape of InputLuaRuntimeDatabaseCallbackMode, derived from the packaged core schema.
# 从包内核心 Schema 派生的 InputLuaRuntimeDatabaseCallbackMode 精确线形状。
InputLuaRuntimeDatabaseCallbackMode: TypeAlias = Literal['standard', 'json']


# Exact wire shape of InputLuaRuntimeDatabaseProviderMode, derived from the packaged core schema.
# 从包内核心 Schema 派生的 InputLuaRuntimeDatabaseProviderMode 精确线形状。
InputLuaRuntimeDatabaseProviderMode: TypeAlias = Literal['dynamic_library', 'host_callback', 'space_controller']


class _InputLuaRuntimeHostOptionsRequired(TypedDict, total=True):
    """
    Wire fields for _InputLuaRuntimeHostOptionsRequired; native validation enforces semantic constraints.
    _InputLuaRuntimeHostOptionsRequired 的线字段；原生校验负责语义约束。
    Host-provided filesystem and runtime paths consumed by the LuaSkills library.
    宿主提供给 LuaSkills 库消费的文件系统与运行时路径集合。
    """
    # Whether the runtime is allowed to perform network downloads while installing dependencies.
    # 运行时在安装依赖时是否允许执行网络下载。
    # Exact wire member allow_network_download; required independently of nullability.
    # 精确线成员 allow_network_download；必需与是否可为空值相互独立。
    allow_network_download: bool
    # Host-reserved public entry names that LuaSkills canonical name generation must never occupy directly.
    # 宿主保留的公开入口名称集合，LuaSkills 在生成 canonical 名称时必须直接避开这些名称。
    # Exact wire member reserved_entry_names; required independently of nullability.
    # 精确线成员 reserved_entry_names；必需与是否可为空值相互独立。
    reserved_entry_names: List[str]


class InputLuaRuntimeHostOptions(_InputLuaRuntimeHostOptionsRequired, total=False):
    """
    Wire fields for InputLuaRuntimeHostOptions; native validation enforces semantic constraints.
    InputLuaRuntimeHostOptions 的线字段；原生校验负责语义约束。
    Host-provided filesystem and runtime paths consumed by the LuaSkills library.
    宿主提供给 LuaSkills 库消费的文件系统与运行时路径集合。
    """
    # Host-provided transient cache policy consumed by `vulcan.cache`.
    # 由宿主提供并供 `vulcan.cache` 消费的临时缓存策略。
    # Exact wire member cache_config; omittable independently of nullability.
    # 精确线成员 cache_config；可省略与是否可为空值相互独立。
    cache_config: Union['InputToolCacheConfig', None]
    # Host-controlled optional runtime capability toggles.
    # 由宿主控制的可选运行时能力开关集合。
    # Exact wire member capabilities; omittable independently of nullability.
    # 精确线成员 capabilities；可省略与是否可为空值相互独立。
    capabilities: 'InputLuaRuntimeCapabilityOptions'
    # Fixed sibling directory name used under one skill-root parent to store skill databases.
    # 在单个技能根父目录下存放技能数据库时使用的固定兄弟目录名称。
    # Exact wire member database_dir_name; omittable independently of nullability.
    # 精确线成员 database_dir_name；可省略与是否可为空值相互独立。
    database_dir_name: str
    # Optional default text encoding label used by managed IO and process APIs.
    # 托管 IO 与进程 API 使用的可选默认文本编码标签。
    # Exact wire member default_text_encoding; omittable independently of nullability.
    # 精确线成员 default_text_encoding；可省略与是否可为空值相互独立。
    default_text_encoding: Union[str, None]
    # Fixed sibling directory name used under one skill-root parent to store dependencies.
    # 在单个技能根父目录下存放依赖时使用的固定兄弟目录名称。
    # Exact wire member dependency_dir_name; omittable independently of nullability.
    # 精确线成员 dependency_dir_name；可省略与是否可为空值相互独立。
    dependency_dir_name: str
    # Host-managed cache directory used for downloaded archives and remote manifests.
    # 宿主管理的下载缓存目录，用于归档文件和远程清单缓存。
    # Exact wire member download_cache_root; omittable independently of nullability.
    # 精确线成员 download_cache_root；可省略与是否可为空值相互独立。
    download_cache_root: Union[str, None]
    # Whether trusted system operations may install from private URL manifests.
    # 可信 system 操作是否允许从私有 URL manifest 安装。
    # Exact wire member enable_private_url_skill_install; omittable independently of nullability.
    # 精确线成员 enable_private_url_skill_install；可省略与是否可为空值相互独立。
    enable_private_url_skill_install: bool
    # Optional GitHub API base URL override used to resolve release metadata.
    # 可选的 GitHub API 基址覆盖，用于解析 release 元数据。
    # Exact wire member github_api_base_url; omittable independently of nullability.
    # 精确线成员 github_api_base_url；可省略与是否可为空值相互独立。
    github_api_base_url: Union[str, None]
    # Optional GitHub site base URL override used to rewrite browser download URLs.
    # 可选的 GitHub 站点基址覆盖，用于重写浏览器下载地址。
    # Exact wire member github_base_url; omittable independently of nullability.
    # 精确线成员 github_base_url；可省略与是否可为空值相互独立。
    github_base_url: Union[str, None]
    # Host-managed root directory used only to probe host-provided FFI/native dependencies.
    # 仅用于探测宿主提供 FFI/原生依赖的宿主管理根目录。
    # Exact wire member host_provided_ffi_root; omittable independently of nullability.
    # 精确线成员 host_provided_ffi_root；可省略与是否可为空值相互独立。
    host_provided_ffi_root: Union[str, None]
    # Host-managed root directory used only to probe host-provided Lua package dependencies.
    # 仅用于探测宿主提供 Lua 包依赖的宿主管理根目录。
    # Exact wire member host_provided_lua_root; omittable independently of nullability.
    # 精确线成员 host_provided_lua_root；可省略与是否可为空值相互独立。
    host_provided_lua_root: Union[str, None]
    # Host-managed root directory used only to probe host-provided tool dependencies.
    # 仅用于探测宿主提供工具依赖的宿主管理根目录。
    # Exact wire member host_provided_tool_root; omittable independently of nullability.
    # 精确线成员 host_provided_tool_root；可省略与是否可为空值相互独立。
    host_provided_tool_root: Union[str, None]
    # Host-forced skill identifiers that must be skipped before dependency or database setup.
    # 宿主强制跳过的技能标识符列表，会在依赖或数据库初始化前生效。
    # Exact wire member ignored_skill_ids; omittable independently of nullability.
    # 精确线成员 ignored_skill_ids；可省略与是否可为空值相互独立。
    ignored_skill_ids: List[str]
    # LanceDB callback transport mode selected by the host when provider mode is `host_callback`.
    # 当 provider 模式为 `host_callback` 时，宿主为 LanceDB 选择的回调传输模式。
    # Exact wire member lancedb_callback_mode; omittable independently of nullability.
    # 精确线成员 lancedb_callback_mode；可省略与是否可为空值相互独立。
    lancedb_callback_mode: 'InputLuaRuntimeDatabaseCallbackMode'
    # Explicit LanceDB dynamic-library path owned by the host.
    # 由宿主显式提供的 LanceDB 动态库路径。
    # Exact wire member lancedb_library_path; omittable independently of nullability.
    # 精确线成员 lancedb_library_path；可省略与是否可为空值相互独立。
    lancedb_library_path: Union[str, None]
    # LanceDB database provider mode selected by the host.
    # 宿主为 LanceDB 数据库选择的 provider 模式。
    # Exact wire member lancedb_provider_mode; omittable independently of nullability.
    # 精确线成员 lancedb_provider_mode；可省略与是否可为空值相互独立。
    lancedb_provider_mode: 'InputLuaRuntimeDatabaseProviderMode'
    # Optional lua_packages root used to build `package.path` and `package.cpath`.
    # 用于拼接 `package.path` 与 `package.cpath` 的可选 lua_packages 根目录。
    # Exact wire member lua_packages_dir; omittable independently of nullability.
    # 精确线成员 lua_packages_dir；可省略与是否可为空值相互独立。
    lua_packages_dir: Union[str, None]
    # Host-selected managed Python/Node worker and persistent-session resource policy.
    # 宿主选择的受管 Python/Node Worker 与持久会话资源策略。
    # Exact wire member managed_runtime_config; omittable independently of nullability.
    # 精确线成员 managed_runtime_config；可省略与是否可为空值相互独立。
    managed_runtime_config: 'InputLuaRuntimeManagedRuntimeConfig'
    # Optional host-configured read-only root containing managed Python and Node distributions.
    # 可选的宿主配置只读根目录，包含受管 Python 与 Node 发行包。
    # Exact wire member managed_runtime_distribution_root; omittable independently of nullability.
    # 精确线成员 managed_runtime_distribution_root；可省略与是否可为空值相互独立。
    managed_runtime_distribution_root: Union[str, None]
    # Optional host-configured writable root containing reusable managed environments.
    # 可选的宿主配置可写根目录，包含可复用受管环境。
    # Exact wire member managed_runtime_environment_root; omittable independently of nullability.
    # 精确线成员 managed_runtime_environment_root；可省略与是否可为空值相互独立。
    managed_runtime_environment_root: Union[str, None]
    # Optional official LuaSkills Hub base URL used by managed Hub installs.
    # 受管 Hub 安装使用的可选官方 LuaSkills Hub 基址。
    # Exact wire member official_skill_hub_base_url; omittable independently of nullability.
    # 精确线成员 official_skill_hub_base_url；可省略与是否可为空值相互独立。
    official_skill_hub_base_url: Union[str, None]
    # Host-controlled URL prefixes allowed for private skill manifests.
    # 宿主管控的私有技能 manifest 允许 URL 前缀。
    # Exact wire member private_skill_source_allowlist; omittable independently of nullability.
    # 精确线成员 private_skill_source_allowlist；可省略与是否可为空值相互独立。
    private_skill_source_allowlist: List[str]
    # Optional host-managed resources directory exposed to Lua as `vulcan.runtime.resources_dir`.
    # 以 `vulcan.runtime.resources_dir` 形式暴露给 Lua 的可选宿主管理资源目录。
    # Exact wire member resources_dir; omittable independently of nullability.
    # 精确线成员 resources_dir；可省略与是否可为空值相互独立。
    resources_dir: Union[str, None]
    # Optional dedicated pool configuration for isolated `vulcan.runtime.lua.exec` VMs.
    # 供隔离 `vulcan.runtime.lua.exec` 虚拟机使用的可选独立池配置。
    # Exact wire member runlua_pool_config; omittable independently of nullability.
    # 精确线成员 runlua_pool_config；可省略与是否可为空值相互独立。
    runlua_pool_config: Union['InputLuaRuntimeRunLuaPoolConfig', None]
    # Optional canonical LuaSkills runtime root used to derive the fixed runtime layout.
    # 用于推导固定运行时布局的可选规范 LuaSkills 运行时根目录。
    # Exact wire member runtime_root; omittable independently of nullability.
    # 精确线成员 runtime_root；可省略与是否可为空值相互独立。
    runtime_root: Union[str, None]
    # Optional cross-process configuration lock timeout in milliseconds.
    # 可选的配置跨进程锁超时毫秒数。
    # Exact wire member skill_config_lock_timeout_ms; omittable independently of nullability.
    # 精确线成员 skill_config_lock_timeout_ms；可省略与是否可为空值相互独立。
    skill_config_lock_timeout_ms: Union[int, None]
    # Explicit user-level root containing normal and system skill configuration stores.
    # 包含普通技能与系统技能配置存储的显式用户级根目录。
    # Exact wire member skill_config_root; omittable independently of nullability.
    # 精确线成员 skill_config_root；可省略与是否可为空值相互独立。
    skill_config_root: Union[str, None]
    # Optional configuration file watcher debounce interval in milliseconds.
    # 可选的配置文件监听防抖毫秒数。
    # Exact wire member skill_config_watch_debounce_ms; omittable independently of nullability.
    # 精确线成员 skill_config_watch_debounce_ms；可省略与是否可为空值相互独立。
    skill_config_watch_debounce_ms: Union[int, None]
    # Shared controller client options used when one database backend selects `space_controller`.
    # 当数据库后端选择 `space_controller` 时所使用的共享控制器客户端选项。
    # Exact wire member space_controller; omittable independently of nullability.
    # 精确线成员 space_controller；可省略与是否可为空值相互独立。
    space_controller: 'InputLuaRuntimeSpaceControllerOptions'
    # SQLite callback transport mode selected by the host when provider mode is `host_callback`.
    # 当 provider 模式为 `host_callback` 时，宿主为 SQLite 选择的回调传输模式。
    # Exact wire member sqlite_callback_mode; omittable independently of nullability.
    # 精确线成员 sqlite_callback_mode；可省略与是否可为空值相互独立。
    sqlite_callback_mode: 'InputLuaRuntimeDatabaseCallbackMode'
    # Explicit SQLite dynamic-library path owned by the host.
    # 由宿主显式提供的 SQLite 动态库路径。
    # Exact wire member sqlite_library_path; omittable independently of nullability.
    # 精确线成员 sqlite_library_path；可省略与是否可为空值相互独立。
    sqlite_library_path: Union[str, None]
    # SQLite database provider mode selected by the host.
    # 宿主为 SQLite 数据库选择的 provider 模式。
    # Exact wire member sqlite_provider_mode; omittable independently of nullability.
    # 精确线成员 sqlite_provider_mode；可省略与是否可为空值相互独立。
    sqlite_provider_mode: 'InputLuaRuntimeDatabaseProviderMode'
    # Fixed sibling directory name used under one skill-root parent to store skill state.
    # 在单个技能根父目录下存放技能状态时使用的固定兄弟目录名称。
    # Exact wire member state_dir_name; omittable independently of nullability.
    # 精确线成员 state_dir_name；可省略与是否可为空值相互独立。
    state_dir_name: str
    # Optional fixed host-owned system Lua library directory used by `system_lua_lib` leases.
    # 供 `system_lua_lib` 租约使用的可选固定宿主系统 Lua 库目录。
    # Exact wire member system_lua_lib_dir; omittable independently of nullability.
    # 精确线成员 system_lua_lib_dir；可省略与是否可为空值相互独立。
    system_lua_lib_dir: Union[str, None]
    # Host-managed temporary directory used by luaexec spill files and similar transient artifacts.
    # 宿主管理的临时目录，供 luaexec 请求文件等短生命周期产物使用。
    # Exact wire member temp_dir; omittable independently of nullability.
    # 精确线成员 temp_dir；可省略与是否可为空值相互独立。
    temp_dir: Union[str, None]


class _InputLuaRuntimeManagedRuntimeConfigRequired(TypedDict, total=True):
    """
    Wire fields for _InputLuaRuntimeManagedRuntimeConfigRequired; native validation enforces semantic constraints.
    _InputLuaRuntimeManagedRuntimeConfigRequired 的线字段；原生校验负责语义约束。
    Host-selected resource policy for managed Python and Node workers and persistent sessions.
    宿主为受管 Python 与 Node Worker 及持久会话选择的资源策略。
    """
    # Default retained byte limit for each persistent-session stdout or stderr stream.
    # 每个持久会话 stdout 或 stderr 流默认保留的字节上限。
    # Exact wire member persistent_session_default_buffer_limit_bytes_per_stream; required independently of nullability.
    # 精确线成员 persistent_session_default_buffer_limit_bytes_per_stream；必需与是否可为空值相互独立。
    persistent_session_default_buffer_limit_bytes_per_stream: int
    # Maximum launching or live persistent sessions retained by one engine.
    # 单个引擎允许保留的启动中或活动持久会话最大数量。
    # Exact wire member persistent_session_limit_per_engine; required independently of nullability.
    # 精确线成员 persistent_session_limit_per_engine；必需与是否可为空值相互独立。
    persistent_session_limit_per_engine: int
    # Idle seconds after which an unused worker may be retired.
    # 未使用 Worker 可被回收前的空闲秒数。
    # Exact wire member worker_idle_ttl_secs; required independently of nullability.
    # 精确线成员 worker_idle_ttl_secs；必需与是否可为空值相互独立。
    worker_idle_ttl_secs: int
    # Maximum live workers for one exact environment and package-owner pool key.
    # 单个精确环境与包所有者池键允许的最大活动 Worker 数量。
    # Exact wire member worker_pool_max_size_per_environment; required independently of nullability.
    # 精确线成员 worker_pool_max_size_per_environment；必需与是否可为空值相互独立。
    worker_pool_max_size_per_environment: int


class InputLuaRuntimeManagedRuntimeConfig(_InputLuaRuntimeManagedRuntimeConfigRequired, total=False):
    """
    Wire fields for InputLuaRuntimeManagedRuntimeConfig; native validation enforces semantic constraints.
    InputLuaRuntimeManagedRuntimeConfig 的线字段；原生校验负责语义约束。
    Host-selected resource policy for managed Python and Node workers and persistent sessions.
    宿主为受管 Python 与 Node Worker 及持久会话选择的资源策略。
    """
    # Default positive invoke timeout in milliseconds; absent means unlimited.
    # 默认正数 invoke 超时毫秒数；缺失表示无限制。
    # Exact wire member invoke_default_timeout_ms; omittable independently of nullability.
    # 精确线成员 invoke_default_timeout_ms；可省略与是否可为空值相互独立。
    invoke_default_timeout_ms: Union[int, None]


class InputLuaRuntimeRunLuaPoolConfig(TypedDict, total=True):
    """
    Wire fields for InputLuaRuntimeRunLuaPoolConfig; native validation enforces semantic constraints.
    InputLuaRuntimeRunLuaPoolConfig 的线字段；原生校验负责语义约束。
    Host-provided pool configuration for isolated runlua VMs.
    宿主提供的隔离 runlua 虚拟机池配置。
    """
    # Idle TTL in seconds before one excess isolated runlua VM may be retired.
    # 多余隔离 runlua 虚拟机在空闲多少秒后允许回收。
    # Exact wire member idle_ttl_secs; required independently of nullability.
    # 精确线成员 idle_ttl_secs；必需与是否可为空值相互独立。
    idle_ttl_secs: int
    # Maximum number of isolated runlua VMs allowed in the pool.
    # 隔离 runlua 虚拟机池允许存在的最大数量。
    # Exact wire member max_size; required independently of nullability.
    # 精确线成员 max_size；必需与是否可为空值相互独立。
    max_size: int
    # Minimum number of isolated runlua VMs kept warm.
    # 隔离 runlua 虚拟机需要常驻保温的最小数量。
    # Exact wire member min_size; required independently of nullability.
    # 精确线成员 min_size；必需与是否可为空值相互独立。
    min_size: int


class _InputLuaRuntimeSpaceControllerOptionsRequired(TypedDict, total=True):
    """
    Wire fields for _InputLuaRuntimeSpaceControllerOptionsRequired; native validation enforces semantic constraints.
    _InputLuaRuntimeSpaceControllerOptionsRequired 的线字段；原生校验负责语义约束。
    Host-provided controller client options used when one database backend chooses `space_controller`.
    当数据库后端选择 `space_controller` 时使用的宿主侧控制器客户端选项。
    """
    # Whether the runtime may auto-spawn the controller when the endpoint is unavailable.
    # 当控制器端点不可用时，运行时是否允许自动唤起控制器。
    # Exact wire member auto_spawn; required independently of nullability.
    # 精确线成员 auto_spawn；必需与是否可为空值相互独立。
    auto_spawn: bool
    # Transport connect timeout in seconds used by the controller client proxy.
    # 控制器客户端代理使用的传输连接超时秒数。
    # Exact wire member connect_timeout_secs; required independently of nullability.
    # 精确线成员 connect_timeout_secs；必需与是否可为空值相互独立。
    connect_timeout_secs: int
    # Default lease TTL in seconds passed to one auto-spawned controller.
    # 传递给自动唤起控制器的默认租约 TTL 秒数。
    # Exact wire member default_lease_ttl_secs; required independently of nullability.
    # 精确线成员 default_lease_ttl_secs；必需与是否可为空值相互独立。
    default_lease_ttl_secs: int
    # Idle timeout in seconds passed to one auto-spawned controller.
    # 传递给自动唤起控制器的空闲超时秒数。
    # Exact wire member idle_timeout_secs; required independently of nullability.
    # 精确线成员 idle_timeout_secs；必需与是否可为空值相互独立。
    idle_timeout_secs: int
    # Lease renew interval in seconds used by the background controller client task.
    # 后台控制器客户端任务使用的租约续约间隔秒数。
    # Exact wire member lease_renew_interval_secs; required independently of nullability.
    # 精确线成员 lease_renew_interval_secs；必需与是否可为空值相互独立。
    lease_renew_interval_secs: int
    # Minimum uptime in seconds passed to one auto-spawned controller.
    # 传递给自动唤起控制器的最小存活秒数。
    # Exact wire member minimum_uptime_secs; required independently of nullability.
    # 精确线成员 minimum_uptime_secs；必需与是否可为空值相互独立。
    minimum_uptime_secs: int
    # Process mode used when auto-spawning one controller process.
    # 自动唤起控制器进程时使用的进程模式。
    # Exact wire member process_mode; required independently of nullability.
    # 精确线成员 process_mode；必需与是否可为空值相互独立。
    process_mode: 'InputLuaRuntimeSpaceControllerProcessMode'
    # Startup retry interval in milliseconds used while polling one spawned controller.
    # 轮询已唤起控制器时使用的启动重试间隔毫秒数。
    # Exact wire member startup_retry_interval_ms; required independently of nullability.
    # 精确线成员 startup_retry_interval_ms；必需与是否可为空值相互独立。
    startup_retry_interval_ms: int
    # Startup timeout in seconds used while waiting for one spawned controller to become ready.
    # 等待已唤起控制器就绪时使用的启动超时秒数。
    # Exact wire member startup_timeout_secs; required independently of nullability.
    # 精确线成员 startup_timeout_secs；必需与是否可为空值相互独立。
    startup_timeout_secs: int


class InputLuaRuntimeSpaceControllerOptions(_InputLuaRuntimeSpaceControllerOptionsRequired, total=False):
    """
    Wire fields for InputLuaRuntimeSpaceControllerOptions; native validation enforces semantic constraints.
    InputLuaRuntimeSpaceControllerOptions 的线字段；原生校验负责语义约束。
    Host-provided controller client options used when one database backend chooses `space_controller`.
    当数据库后端选择 `space_controller` 时使用的宿主侧控制器客户端选项。
    """
    # Optional explicit controller endpoint; when omitted the shared default endpoint is used.
    # 可选的显式控制器端点；缺失时使用共享默认端点。
    # Exact wire member endpoint; omittable independently of nullability.
    # 精确线成员 endpoint；可省略与是否可为空值相互独立。
    endpoint: Union[str, None]
    # Optional local executable path copied and managed by the host.
    # 由宿主复制并管理的可选本地可执行文件路径。
    # Exact wire member executable_path; omittable independently of nullability.
    # 精确线成员 executable_path；可省略与是否可为空值相互独立。
    executable_path: Union[str, None]


# Exact wire shape of InputLuaRuntimeSpaceControllerProcessMode, derived from the packaged core schema.
# 从包内核心 Schema 派生的 InputLuaRuntimeSpaceControllerProcessMode 精确线形状。
InputLuaRuntimeSpaceControllerProcessMode: TypeAlias = Literal['service', 'managed']


class InputLuaVmPoolConfig(TypedDict, total=True):
    """
    Wire fields for InputLuaVmPoolConfig; native validation enforces semantic constraints.
    InputLuaVmPoolConfig 的线字段；原生校验负责语义约束。
    Pool sizing configuration for Lua virtual machines.
    Lua 虚拟机池的容量配置。
    """
    # Idle TTL in seconds before an excess VM can be retired.
    # 多余虚拟机在空闲多少秒后允许回收。
    # Exact wire member idle_ttl_secs; required independently of nullability.
    # 精确线成员 idle_ttl_secs；必需与是否可为空值相互独立。
    idle_ttl_secs: int
    # Maximum number of VMs allowed in the pool.
    # 池内允许存在的最大虚拟机数量。
    # Exact wire member max_size; required independently of nullability.
    # 精确线成员 max_size；必需与是否可为空值相互独立。
    max_size: int
    # Minimum number of VMs that should stay warm.
    # 需要常驻保温的最小虚拟机数量。
    # Exact wire member min_size; required independently of nullability.
    # 精确线成员 min_size；必需与是否可为空值相互独立。
    min_size: int


class _InputModuleDefinitionRequired(TypedDict, total=True):
    """
    Wire fields for _InputModuleDefinitionRequired; native validation enforces semantic constraints.
    _InputModuleDefinitionRequired 的线字段；原生校验负责语义约束。
    Immutable source and trusted path declaration supplied during module activation.
    模块激活时提供的不可变源码与可信路径声明。
    """
    # Package-relative dependency manifest, validated by the existing package loader.
    # 由既有包加载器校验的包相对依赖清单。
    # Exact wire member dependencies_file; required independently of nullability.
    # 精确线成员 dependencies_file；必需与是否可为空值相互独立。
    dependencies_file: str
    # Exact public exports and value contracts validated before invocation.
    # 调用前校验的精确公开导出及值契约。
    # Exact wire member exports; required independently of nullability.
    # 精确线成员 exports；必需与是否可为空值相互独立。
    exports: List['InputModuleExport']
    # Host-assigned immutable code and dependency generation.
    # 宿主分配的不可变代码与依赖代次。
    # Exact wire member generation; required independently of nullability.
    # 精确线成员 generation；必需与是否可为空值相互独立。
    generation: str
    # Trusted mount metadata; must be a JSON object.
    # 可信挂载元数据，必须为 JSON 对象。
    # Exact wire member mounts; required independently of nullability.
    # 精确线成员 mounts；必需与是否可为空值相互独立。
    mounts: JsonValue
    # Absolute plugin root inside the configured System trust root.
    # 位于已配置 System 信任根内的绝对插件根目录。
    # Exact wire member package_root; required independently of nullability.
    # 精确线成员 package_root；必需与是否可为空值相互独立。
    package_root: str
    # Host-assigned stable plugin identity.
    # 宿主分配的稳定插件身份。
    # Exact wire member plugin_id; required independently of nullability.
    # 精确线成员 plugin_id；必需与是否可为空值相互独立。
    plugin_id: str
    # Host-authenticated security partition used for instance matching.
    # 用于实例匹配且由宿主认证的安全分区。
    # Exact wire member security_partition; required independently of nullability.
    # 精确线成员 security_partition；必需与是否可为空值相互独立。
    security_partition: str
    # Source evaluated once; it must return a table of declared functions.
    # 仅求值一次的源码；必须返回已声明函数的表。
    # Exact wire member source; required independently of nullability.
    # 精确线成员 source；必需与是否可为空值相互独立。
    source: str


class InputModuleDefinition(_InputModuleDefinitionRequired, total=False):
    """
    Wire fields for InputModuleDefinition; native validation enforces semantic constraints.
    InputModuleDefinition 的线字段；原生校验负责语义约束。
    Immutable source and trusted path declaration supplied during module activation.
    模块激活时提供的不可变源码与可信路径声明。
    """
    # Logical working directory; absent selects the existing package-root rule.
    # 逻辑工作目录；省略时使用既有包根目录规则。
    # Exact wire member cwd; omittable independently of nullability.
    # 精确线成员 cwd；可省略与是否可为空值相互独立。
    cwd: Union[str, None]
    # Explicitly authorized workspace root, absent for package-only execution.
    # 显式授权的工作区根目录；仅在包内执行时省略。
    # Exact wire member workspace_root; omittable independently of nullability.
    # 精确线成员 workspace_root；可省略与是否可为空值相互独立。
    workspace_root: Union[str, None]


class InputModuleExport(TypedDict, total=True):
    """
    Wire fields for InputModuleExport; native validation enforces semantic constraints.
    InputModuleExport 的线字段；原生校验负责语义约束。
    One named export with explicit input and output schemas.
    具有显式输入及输出 Schema 的单个具名导出。
    """
    # Offline Draft 2020-12 schema for structured invocation arguments.
    # 结构化调用参数的离线 Draft 2020-12 Schema。
    # Exact wire member input_schema; required independently of nullability.
    # 精确线成员 input_schema；必需与是否可为空值相互独立。
    input_schema: JsonValue
    # Exact Lua table key captured when the module is loaded.
    # 模块加载时捕获的精确 Lua 表键。
    # Exact wire member name; required independently of nullability.
    # 精确线成员 name；必需与是否可为空值相互独立。
    name: str
    # Offline Draft 2020-12 schema for structured return values.
    # 结构化返回值的离线 Draft 2020-12 Schema。
    # Exact wire member output_schema; required independently of nullability.
    # 精确线成员 output_schema；必需与是否可为空值相互独立。
    output_schema: JsonValue


class _InputPluginPoolConfigRequired(TypedDict, total=True):
    """
    Wire fields for _InputPluginPoolConfigRequired; native validation enforces semantic constraints.
    _InputPluginPoolConfigRequired 的线字段；原生校验负责语义约束。
    Immutable capacity policy for one host-assigned plugin execution group.
    单个宿主分配的插件执行分组的不可变容量策略。
    """
    # Requested execution backend, validated before activation.
    # 激活前校验的所请求执行后端。
    # Exact wire member backend; required independently of nullability.
    # 精确线成员 backend；必需与是否可为空值相互独立。
    backend: 'InputExecutionBackend'
    # Shared or dedicated ownership of resident capacity.
    # 常驻容量的公共或专用归属。
    # Exact wire member kind; required independently of nullability.
    # 精确线成员 kind；必需与是否可为空值相互独立。
    kind: 'InputPoolKind'
    # Maximum pending calls in this group.
    # 当前分组等待调用的数量上限。
    # Exact wire member max_queued_calls; required independently of nullability.
    # 精确线成员 max_queued_calls；必需与是否可为空值相互独立。
    max_queued_calls: int
    # Maximum resident instances in this exact immutable execution domain.
    # 此精确不可变执行域的最大常驻实例数。
    # Exact wire member max_resident_vms; required independently of nullability.
    # 精确线成员 max_resident_vms；必需与是否可为空值相互独立。
    max_resident_vms: int
    # Maximum simultaneously executing calls in this group.
    # 当前分组同时执行的调用数上限。
    # Exact wire member max_running_calls; required independently of nullability.
    # 精确线成员 max_running_calls；必需与是否可为空值相互独立。
    max_running_calls: int
    # Non-lendable reservation; only dedicated groups may reserve capacity.
    # 不可出借的预留；仅专用分组可以预留容量。
    # Exact wire member min_resident_vms; required independently of nullability.
    # 精确线成员 min_resident_vms；必需与是否可为空值相互独立。
    min_resident_vms: int
    # Module state lifetime; legacy stateless calls select single-call mode.
    # 模块状态寿命；旧无状态调用选择单次模式。
    # Exact wire member reuse; required independently of nullability.
    # 精确线成员 reuse；必需与是否可为空值相互独立。
    reuse: 'InputInstanceReuse'
    # Whether all calls in this group require FIFO serialization.
    # 当前分组的全部调用是否要求先进先出的串行执行。
    # Exact wire member serial; required independently of nullability.
    # 精确线成员 serial；必需与是否可为空值相互独立。
    serial: bool


class InputPluginPoolConfig(_InputPluginPoolConfigRequired, total=False):
    """
    Wire fields for InputPluginPoolConfig; native validation enforces semantic constraints.
    InputPluginPoolConfig 的线字段；原生校验负责语义约束。
    Immutable capacity policy for one host-assigned plugin execution group.
    单个宿主分配的插件执行分组的不可变容量策略。
    """
    # Idle retirement threshold; absent explicitly disables idle retirement.
    # 空闲退役阈值；省略明确表示关闭空闲退役。
    # Exact wire member idle_ttl_ms; omittable independently of nullability.
    # 精确线成员 idle_ttl_ms；可省略与是否可为空值相互独立。
    idle_ttl_ms: Union[int, None]
    # Maximum successful uses before retirement; absent disables this limit.
    # 退役前成功使用次数上限；省略表示关闭此上限。
    # Exact wire member max_uses; omittable independently of nullability.
    # 精确线成员 max_uses；可省略与是否可为空值相互独立。
    max_uses: Union[int, None]


# Exact wire shape of InputPoolKind, derived from the packaged core schema.
# 从包内核心 Schema 派生的 InputPoolKind 精确线形状。
InputPoolKind: TypeAlias = Literal['shared', 'dedicated']


class InputRuntimeClientInfo(TypedDict, total=False):
    """
    Wire fields for InputRuntimeClientInfo; native validation enforces semantic constraints.
    InputRuntimeClientInfo 的线字段；原生校验负责语义约束。
    Generic host-side client identity information passed into the LuaSkills runtime.
    传入 LuaSkills 运行时的通用宿主客户端身份信息。
    """
    # Stable host-defined client kind, such as `mcp`, `ide`, or `desktop`.
    # 宿主定义的稳定客户端类型，例如 `mcp`、`ide` 或 `desktop`。
    # Exact wire member kind; omittable independently of nullability.
    # 精确线成员 kind；可省略与是否可为空值相互独立。
    kind: Union[str, None]
    # Human-readable client name reported by the host.
    # 由宿主上报的人类可读客户端名称。
    # Exact wire member name; omittable independently of nullability.
    # 精确线成员 name；可省略与是否可为空值相互独立。
    name: Union[str, None]
    # Optional client version string.
    # 可选的客户端版本字符串。
    # Exact wire member version; omittable independently of nullability.
    # 精确线成员 version；可省略与是否可为空值相互独立。
    version: Union[str, None]


class InputRuntimeCommandPluginRegister(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandPluginRegister; native validation enforces semantic constraints.
    InputRuntimeCommandPluginRegister 的线字段；原生校验负责语义约束。
    Register aggregate plugin budgets.
    注册插件聚合预算。
    """
    # Explicit aggregate plugin budgets.
    # 显式插件聚合预算。
    # Exact wire member config; required independently of nullability.
    # 精确线成员 config；必需与是否可为空值相互独立。
    config: 'InputEmbeddedPluginConfig'
    # Exact host-assigned plugin identity.
    # 精确宿主分配的插件身份。
    # Exact wire member plugin_id; required independently of nullability.
    # 精确线成员 plugin_id；必需与是否可为空值相互独立。
    plugin_id: str
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['plugin_register']


class InputRuntimeCommandPluginStatus(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandPluginStatus; native validation enforces semantic constraints.
    InputRuntimeCommandPluginStatus 的线字段；原生校验负责语义约束。
    Query live aggregate plugin ownership.
    查询实时插件聚合所有权。
    """
    # Exact host-assigned plugin identity.
    # 精确宿主分配的插件身份。
    # Exact wire member plugin_id; required independently of nullability.
    # 精确线成员 plugin_id；必需与是否可为空值相互独立。
    plugin_id: str
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['plugin_status']


class InputRuntimeCommandPluginClose(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandPluginClose; native validation enforces semantic constraints.
    InputRuntimeCommandPluginClose 的线字段；原生校验负责语义约束。
    Close one plugin's admission and pools.
    关闭一个插件的入场及池。
    """
    # Exact host-assigned plugin identity.
    # 精确宿主分配的插件身份。
    # Exact wire member plugin_id; required independently of nullability.
    # 精确线成员 plugin_id；必需与是否可为空值相互独立。
    plugin_id: str
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['plugin_close']


class InputRuntimeCommandPluginForget(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandPluginForget; native validation enforces semantic constraints.
    InputRuntimeCommandPluginForget 的线字段；原生校验负责语义约束。
    Forget only a fully released plugin registration.
    仅遗忘完全释放的插件注册。
    """
    # Exact host-assigned plugin identity.
    # 精确宿主分配的插件身份。
    # Exact wire member plugin_id; required independently of nullability.
    # 精确线成员 plugin_id；必需与是否可为空值相互独立。
    plugin_id: str
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['plugin_forget']


class InputRuntimeCommandPoolRegister(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandPoolRegister; native validation enforces semantic constraints.
    InputRuntimeCommandPoolRegister 的线字段；原生校验负责语义约束。
    Register immutable source and capability authority without executing Lua.
    注册不可变源码及能力权威，不执行 Lua。
    """
    # Immutable package and module declaration.
    # 不可变包与模块声明。
    # Exact wire member definition; required independently of nullability.
    # 精确线成员 definition；必需与是否可为空值相互独立。
    definition: 'InputModuleDefinition'
    # Immutable host initialization and configuration revision.
    # 不可变宿主初始化及配置修订。
    # Exact wire member execution_revision; required independently of nullability.
    # 精确线成员 execution_revision；必需与是否可为空值相互独立。
    execution_revision: str
    # Explicit host grants for this binding or discovery request.
    # 此绑定或发现请求的显式宿主授权。
    # Exact wire member permissions; required independently of nullability.
    # 精确线成员 permissions；必需与是否可为空值相互独立。
    permissions: List[str]
    # Explicit immutable VM pool policy.
    # 显式不可变 VM 池策略。
    # Exact wire member policy; required independently of nullability.
    # 精确线成员 policy；必需与是否可为空值相互独立。
    policy: 'InputPluginPoolConfig'
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['pool_register']


class InputRuntimeCommandPoolStatus(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandPoolStatus; native validation enforces semantic constraints.
    InputRuntimeCommandPoolStatus 的线字段；原生校验负责语义约束。
    Read actual resource accounting for an exact pool.
    读取精确池的实际资源计数。
    """
    # Exact immutable pool identity.
    # 精确不可变池身份。
    # Exact wire member pool_id; required independently of nullability.
    # 精确线成员 pool_id；必需与是否可为空值相互独立。
    pool_id: str
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['pool_status']


class InputRuntimeCommandPoolClose(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandPoolClose; native validation enforces semantic constraints.
    InputRuntimeCommandPoolClose 的线字段；原生校验负责语义约束。
    Close an exact pool and begin actual retirement.
    关闭精确池并开始实际退役。
    """
    # Exact immutable pool identity.
    # 精确不可变池身份。
    # Exact wire member pool_id; required independently of nullability.
    # 精确线成员 pool_id；必需与是否可为空值相互独立。
    pool_id: str
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['pool_close']


class InputRuntimeCommandPoolForget(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandPoolForget; native validation enforces semantic constraints.
    InputRuntimeCommandPoolForget 的线字段；原生校验负责语义约束。
    Forget only a pool whose ownership has drained.
    仅遗忘所有权已排空的池。
    """
    # Exact immutable pool identity.
    # 精确不可变池身份。
    # Exact wire member pool_id; required independently of nullability.
    # 精确线成员 pool_id；必需与是否可为空值相互独立。
    pool_id: str
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['pool_forget']


class InputRuntimeCommandPoolRevokePermission(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandPoolRevokePermission; native validation enforces semantic constraints.
    InputRuntimeCommandPoolRevokePermission 的线字段；原生校验负责语义约束。
    Revoke a grant on the existing live binding.
    撤销既有实时绑定上的授权。
    """
    # Exact live permission to revoke.
    # 需要撤销的精确实时权限。
    # Exact wire member permission; required independently of nullability.
    # 精确线成员 permission；必需与是否可为空值相互独立。
    permission: str
    # Exact immutable pool identity.
    # 精确不可变池身份。
    # Exact wire member pool_id; required independently of nullability.
    # 精确线成员 pool_id；必需与是否可为空值相互独立。
    pool_id: str
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['pool_revoke_permission']


class InputRuntimeCommandCallSubmit(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandCallSubmit; native validation enforces semantic constraints.
    InputRuntimeCommandCallSubmit 的线字段；原生校验负责语义约束。
    Admit an asynchronous ordinary invocation.
    接纳异步普通调用。
    """
    # Typed ordinary call bound to one exact pool.
    # 绑定一个精确池的类型化普通调用。
    # Exact wire member call; required independently of nullability.
    # 精确线成员 call；必需与是否可为空值相互独立。
    call: 'InputEmbeddedCall'
    # Original end-to-end execution budget in milliseconds.
    # 原始端到端执行预算毫秒数。
    # Exact wire member timeout_ms; required independently of nullability.
    # 精确线成员 timeout_ms；必需与是否可为空值相互独立。
    timeout_ms: int
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['call_submit']


class InputRuntimeCommandSessionOpen(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandSessionOpen; native validation enforces semantic constraints.
    InputRuntimeCommandSessionOpen 的线字段；原生校验负责语义约束。
    Reserve a fixed instance and submit initialization.
    预留固定实例并提交初始化。
    """
    # Exact immutable pool identity.
    # 精确不可变池身份。
    # Exact wire member pool_id; required independently of nullability.
    # 精确线成员 pool_id；必需与是否可为空值相互独立。
    pool_id: str
    # Original end-to-end execution budget in milliseconds.
    # 原始端到端执行预算毫秒数。
    # Exact wire member timeout_ms; required independently of nullability.
    # 精确线成员 timeout_ms；必需与是否可为空值相互独立。
    timeout_ms: int
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['session_open']


class InputRuntimeCommandSessionSubmit(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandSessionSubmit; native validation enforces semantic constraints.
    InputRuntimeCommandSessionSubmit 的线字段；原生校验负责语义约束。
    Submit work to an exact fixed session.
    向精确固定会话提交工作。
    """
    # Structured application arguments.
    # 结构化应用参数。
    # Exact wire member arguments; required independently of nullability.
    # 精确线成员 arguments；必需与是否可为空值相互独立。
    arguments: JsonValue
    # Trusted host invocation context.
    # 可信宿主调用上下文。
    # Exact wire member context; required independently of nullability.
    # 精确线成员 context；必需与是否可为空值相互独立。
    context: 'InputLuaInvocationContext'
    # Declared module export name.
    # 已声明模块导出名称。
    # Exact wire member export; required independently of nullability.
    # 精确线成员 export；必需与是否可为空值相互独立。
    export: str
    # Exact fixed-instance session identity.
    # 精确固定实例会话身份。
    # Exact wire member session_id; required independently of nullability.
    # 精确线成员 session_id；必需与是否可为空值相互独立。
    session_id: str
    # Original end-to-end execution budget in milliseconds.
    # 原始端到端执行预算毫秒数。
    # Exact wire member timeout_ms; required independently of nullability.
    # 精确线成员 timeout_ms；必需与是否可为空值相互独立。
    timeout_ms: int
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['session_submit']


class InputRuntimeCommandSessionStatus(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandSessionStatus; native validation enforces semantic constraints.
    InputRuntimeCommandSessionStatus 的线字段；原生校验负责语义约束。
    Read actual session ownership and closure.
    读取实际会话所有权及关闭状态。
    """
    # Exact fixed-instance session identity.
    # 精确固定实例会话身份。
    # Exact wire member session_id; required independently of nullability.
    # 精确线成员 session_id；必需与是否可为空值相互独立。
    session_id: str
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['session_status']


class InputRuntimeCommandSessionClose(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandSessionClose; native validation enforces semantic constraints.
    InputRuntimeCommandSessionClose 的线字段；原生校验负责语义约束。
    Close and cancel a fixed session without migrating its state.
    关闭并取消固定会话，不迁移其状态。
    """
    # Exact fixed-instance session identity.
    # 精确固定实例会话身份。
    # Exact wire member session_id; required independently of nullability.
    # 精确线成员 session_id；必需与是否可为空值相互独立。
    session_id: str
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['session_close']


class InputRuntimeCommandSessionForget(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandSessionForget; native validation enforces semantic constraints.
    InputRuntimeCommandSessionForget 的线字段；原生校验负责语义约束。
    Forget only a closed session with no live ownership.
    仅遗忘没有活动所有权的已关闭会话。
    """
    # Exact fixed-instance session identity.
    # 精确固定实例会话身份。
    # Exact wire member session_id; required independently of nullability.
    # 精确线成员 session_id；必需与是否可为空值相互独立。
    session_id: str
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['session_forget']


class InputRuntimeCommandOperationStatus(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandOperationStatus; native validation enforces semantic constraints.
    InputRuntimeCommandOperationStatus 的线字段；原生校验负责语义约束。
    Read current operation outcome and effect evidence.
    读取当前操作结果及副作用证据。
    """
    # Exact retained operation identity.
    # 精确保留操作身份。
    # Exact wire member operation_id; required independently of nullability.
    # 精确线成员 operation_id；必需与是否可为空值相互独立。
    operation_id: str
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['operation_status']


class InputRuntimeCommandOperationWait(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandOperationWait; native validation enforces semantic constraints.
    InputRuntimeCommandOperationWait 的线字段；原生校验负责语义约束。
    Wait for terminal state within an independent observer budget.
    在独立观察者预算内等待终态。
    """
    # Exact retained operation identity.
    # 精确保留操作身份。
    # Exact wire member operation_id; required independently of nullability.
    # 精确线成员 operation_id；必需与是否可为空值相互独立。
    operation_id: str
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['operation_wait']
    # Finite observer wait in milliseconds, independent of execution cancellation.
    # 有限观察者等待毫秒数，独立于执行取消。
    # Exact wire member wait_ms; required independently of nullability.
    # 精确线成员 wait_ms；必需与是否可为空值相互独立。
    wait_ms: int


class InputRuntimeCommandOperationCancel(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandOperationCancel; native validation enforces semantic constraints.
    InputRuntimeCommandOperationCancel 的线字段；原生校验负责语义约束。
    Request cooperative cancellation without declaring completion.
    请求协作取消，不宣称完成。
    """
    # Exact retained operation identity.
    # 精确保留操作身份。
    # Exact wire member operation_id; required independently of nullability.
    # 精确线成员 operation_id；必需与是否可为空值相互独立。
    operation_id: str
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['operation_cancel']


class InputRuntimeCommandOperationForget(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandOperationForget; native validation enforces semantic constraints.
    InputRuntimeCommandOperationForget 的线字段；原生校验负责语义约束。
    Forget retained terminal evidence explicitly.
    显式遗忘保留的终态证据。
    """
    # Exact retained operation identity.
    # 精确保留操作身份。
    # Exact wire member operation_id; required independently of nullability.
    # 精确线成员 operation_id；必需与是否可为空值相互独立。
    operation_id: str
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['operation_forget']


class InputRuntimeCommandCapabilitiesRegister(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandCapabilitiesRegister; native validation enforces semantic constraints.
    InputRuntimeCommandCapabilitiesRegister 的线字段；原生校验负责语义约束。
    Publish a queued capability batch atomically.
    原子发布队列能力批次。
    """
    # Batch of explicit queued capability declarations.
    # 显式队列能力声明批次。
    # Exact wire member descriptors; required independently of nullability.
    # 精确线成员 descriptors；必需与是否可为空值相互独立。
    descriptors: List['InputCapabilityDescriptor']
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['capabilities_register']


class InputRuntimeCommandCapabilitiesList(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandCapabilitiesList; native validation enforces semantic constraints.
    InputRuntimeCommandCapabilitiesList 的线字段；原生校验负责语义约束。
    List declarations authorized by explicit host grants.
    列出显式宿主授权允许的声明。
    """
    # Explicit host grants for this binding or discovery request.
    # 此绑定或发现请求的显式宿主授权。
    # Exact wire member permissions; required independently of nullability.
    # 精确线成员 permissions；必需与是否可为空值相互独立。
    permissions: List[str]
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['capabilities_list']


class InputRuntimeCommandCapabilityStatus(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandCapabilityStatus; native validation enforces semantic constraints.
    InputRuntimeCommandCapabilityStatus 的线字段；原生校验负责语义约束。
    Read actual callback registration lifetime.
    读取实际回调注册寿命。
    """
    # Exact capability registration identity.
    # 精确能力注册身份。
    # Exact wire member registration_id; required independently of nullability.
    # 精确线成员 registration_id；必需与是否可为空值相互独立。
    registration_id: str
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['capability_status']


class InputRuntimeCommandCapabilityUnregister(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandCapabilityUnregister; native validation enforces semantic constraints.
    InputRuntimeCommandCapabilityUnregister 的线字段；原生校验负责语义约束。
    Retire one exact registration without rerouting existing calls.
    退役一个精确注册，不重定向既有调用。
    """
    # Exact capability registration identity.
    # 精确能力注册身份。
    # Exact wire member registration_id; required independently of nullability.
    # 精确线成员 registration_id；必需与是否可为空值相互独立。
    registration_id: str
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['capability_unregister']


class InputRuntimeCommandCapabilityForget(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandCapabilityForget; native validation enforces semantic constraints.
    InputRuntimeCommandCapabilityForget 的线字段；原生校验负责语义约束。
    Forget only a drained registration.
    仅遗忘已排空注册。
    """
    # Exact capability registration identity.
    # 精确能力注册身份。
    # Exact wire member registration_id; required independently of nullability.
    # 精确线成员 registration_id；必需与是否可为空值相互独立。
    registration_id: str
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['capability_forget']


class InputRuntimeCommandHostRequestsTake(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandHostRequestsTake; native validation enforces semantic constraints.
    InputRuntimeCommandHostRequestsTake 的线字段；原生校验负责语义约束。
    Deliver one bounded callback batch with pre-dispatch encoding.
    通过分发前编码投递一个有界回调批次。
    """
    # Maximum host requests in this one bounded batch.
    # 此单个有界批次的宿主请求数量上限。
    # Exact wire member limit; required independently of nullability.
    # 精确线成员 limit；必需与是否可为空值相互独立。
    limit: int
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['host_requests_take']


class InputRuntimeCommandHostRequestStatus(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandHostRequestStatus; native validation enforces semantic constraints.
    InputRuntimeCommandHostRequestStatus 的线字段；原生校验负责语义约束。
    Read cancellation while retaining actual handler ownership.
    读取取消状态，同时保留实际处理器所有权。
    """
    # Exact host request identity to query or acknowledge.
    # 用于查询或确认的精确宿主请求身份。
    # Exact wire member request_id; required independently of nullability.
    # 精确线成员 request_id；必需与是否可为空值相互独立。
    request_id: str
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['host_request_status']


class InputRuntimeCommandHostRequestComplete(TypedDict, total=True):
    """
    Wire fields for InputRuntimeCommandHostRequestComplete; native validation enforces semantic constraints.
    InputRuntimeCommandHostRequestComplete 的线字段；原生校验负责语义约束。
    Acknowledge actual host completion and preserve effect evidence.
    确认实际宿主完成并保留副作用证据。
    """
    # Actual host result and effect evidence, including late completion.
    # 实际宿主结果与副作用证据，包含迟到完成。
    # Exact wire member outcome; required independently of nullability.
    # 精确线成员 outcome；必需与是否可为空值相互独立。
    outcome: 'InputHostCompletion'
    # Exact host request identity to query or acknowledge.
    # 用于查询或确认的精确宿主请求身份。
    # Exact wire member request_id; required independently of nullability.
    # 精确线成员 request_id；必需与是否可为空值相互独立。
    request_id: str
    # Exact wire member type; required independently of nullability.
    # 精确线成员 type；必需与是否可为空值相互独立。
    type: Literal['host_request_complete']


# Exact wire shape of InputRuntimeCommand, derived from the packaged core schema.
# 从包内核心 Schema 派生的 InputRuntimeCommand 精确线形状。
InputRuntimeCommand: TypeAlias = Union['InputRuntimeCommandPluginRegister', 'InputRuntimeCommandPluginStatus', 'InputRuntimeCommandPluginClose', 'InputRuntimeCommandPluginForget', 'InputRuntimeCommandPoolRegister', 'InputRuntimeCommandPoolStatus', 'InputRuntimeCommandPoolClose', 'InputRuntimeCommandPoolForget', 'InputRuntimeCommandPoolRevokePermission', 'InputRuntimeCommandCallSubmit', 'InputRuntimeCommandSessionOpen', 'InputRuntimeCommandSessionSubmit', 'InputRuntimeCommandSessionStatus', 'InputRuntimeCommandSessionClose', 'InputRuntimeCommandSessionForget', 'InputRuntimeCommandOperationStatus', 'InputRuntimeCommandOperationWait', 'InputRuntimeCommandOperationCancel', 'InputRuntimeCommandOperationForget', 'InputRuntimeCommandCapabilitiesRegister', 'InputRuntimeCommandCapabilitiesList', 'InputRuntimeCommandCapabilityStatus', 'InputRuntimeCommandCapabilityUnregister', 'InputRuntimeCommandCapabilityForget', 'InputRuntimeCommandHostRequestsTake', 'InputRuntimeCommandHostRequestStatus', 'InputRuntimeCommandHostRequestComplete']


class InputRuntimeRequestContext(TypedDict, total=False):
    """
    Wire fields for InputRuntimeRequestContext; native validation enforces semantic constraints.
    InputRuntimeRequestContext 的线字段；原生校验负责语义约束。
    Generic request-scoped context injected by the host into one runtime invocation.
    宿主在单次运行时调用中注入的通用请求级上下文。
    """
    # Optional host-provided raw client capabilities object.
    # 可选的宿主原始客户端能力对象。
    # Exact wire member client_capabilities; omittable independently of nullability.
    # 精确线成员 client_capabilities；可省略与是否可为空值相互独立。
    client_capabilities: JsonValue
    # Optional host-side client metadata.
    # 可选的宿主客户端元数据。
    # Exact wire member client_info; omittable independently of nullability.
    # 精确线成员 client_info；可省略与是否可为空值相互独立。
    client_info: Union['InputRuntimeClientInfo', None]
    # Optional host-defined client name for audit and cost attribution.
    # 可选的宿主客户端名称，用于审计和成本归因。
    # Exact wire member client_name; omittable independently of nullability.
    # 精确线成员 client_name；可省略与是否可为空值相互独立。
    client_name: Union[str, None]
    # Optional host-defined request identifier for audit and cost attribution.
    # 可选的宿主请求标识符，用于审计和成本归因。
    # Exact wire member request_id; omittable independently of nullability.
    # 精确线成员 request_id；可省略与是否可为空值相互独立。
    request_id: Union[str, None]
    # Optional host-defined session identifier.
    # 可选的宿主会话标识。
    # Exact wire member session_id; omittable independently of nullability.
    # 精确线成员 session_id；可省略与是否可为空值相互独立。
    session_id: Union[str, None]
    # Optional host-defined transport name for the current request.
    # 当前请求的可选宿主传输层名称。
    # Exact wire member transport_name; omittable independently of nullability.
    # 精确线成员 transport_name；可省略与是否可为空值相互独立。
    transport_name: Union[str, None]


class InputToolCacheConfig(TypedDict, total=True):
    """
    Wire fields for InputToolCacheConfig; native validation enforces semantic constraints.
    InputToolCacheConfig 的线字段；原生校验负责语义约束。
    Runtime configuration for the shared tool cache, controlling capacity and expiration behavior.
    共享工具缓存的运行时配置，控制容量与过期策略。
    """
    # Default TTL in seconds used when callers omit a TTL.
    # 默认 TTL（秒），调用方未传 TTL 时使用。
    # Exact wire member default_ttl_secs; required independently of nullability.
    # 精确线成员 default_ttl_secs；必需与是否可为空值相互独立。
    default_ttl_secs: int
    # Maximum number of entries; oldest entries are evicted when the cache exceeds this size.
    # 缓存最大条目数，超出后会按创建顺序淘汰最旧条目。
    # Exact wire member max_entries; required independently of nullability.
    # 精确线成员 max_entries；必需与是否可为空值相互独立。
    max_entries: int
    # Maximum TTL in seconds; requested TTL values are clamped to this ceiling.
    # 最大 TTL（秒），请求 TTL 会被限制在该范围内。
    # Exact wire member max_ttl_secs; required independently of nullability.
    # 精确线成员 max_ttl_secs；必需与是否可为空值相互独立。
    max_ttl_secs: int


class InputRequest(TypedDict, total=True):
    """
    Wire fields for InputRequest; native validation enforces semantic constraints.
    InputRequest 的线字段；原生校验负责语义约束。
    Strict versioned request; unknown fields and commands are explicit protocol errors.
    严格版本化请求；未知字段与命令是明确协议错误。
    """
    # One typed operation; no legacy envelope aliases are inferred.
    # 一个类型化操作；不推断旧信封别名。
    # Exact wire member command; required independently of nullability.
    # 精确线成员 command；必需与是否可为空值相互独立。
    command: 'InputCommand'
    # Explicit wire version, checked before dispatch.
    # 分发前检查的显式线协议版本。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int


class OutputCapabilityCaller(TypedDict, total=True):
    """
    Wire fields for OutputCapabilityCaller; native validation enforces semantic constraints.
    OutputCapabilityCaller 的线字段；原生校验负责语义约束。
    Host-authenticated caller data copied outside plugin-controlled arguments.
    在插件可控参数之外复制的宿主认证调用方数据。
    """
    # Immutable execution and initialization-configuration revision.
    # 不可变执行与初始化配置修订。
    # Exact wire member execution_revision; required independently of nullability.
    # 精确线成员 execution_revision；必需与是否可为空值相互独立。
    execution_revision: str
    # Exact operation whose original budget applies.
    # 适用原始预算的精确操作。
    # Exact wire member operation_id; required independently of nullability.
    # 精确线成员 operation_id；必需与是否可为空值相互独立。
    operation_id: str
    # Immutable package and dependency generation.
    # 不可变包与依赖代次。
    # Exact wire member package_generation; required independently of nullability.
    # 精确线成员 package_generation；必需与是否可为空值相互独立。
    package_generation: str
    # Exact activated plugin identity.
    # 精确激活的插件身份。
    # Exact wire member plugin_id; required independently of nullability.
    # 精确线成员 plugin_id；必需与是否可为空值相互独立。
    plugin_id: str
    # Runtime namespace that owns the registration and operation.
    # 拥有注册及操作的运行时命名空间。
    # Exact wire member runtime_id; required independently of nullability.
    # 精确线成员 runtime_id；必需与是否可为空值相互独立。
    runtime_id: str
    # Trusted user/workspace partition, never copied from a Lua argument.
    # 可信用户与工作区分区，绝不从 Lua 参数复制。
    # Exact wire member security_partition; required independently of nullability.
    # 精确线成员 security_partition；必需与是否可为空值相互独立。
    security_partition: str
    # Optional fixed session required by session-scoped capabilities.
    # 会话作用域能力要求的可选固定会话。
    # Exact wire member session_id; required independently of nullability.
    # 精确线成员 session_id；必需与是否可为空值相互独立。
    session_id: Union[str, None]
    # Explicit authorized workspace; absent means package-only context.
    # 显式授权工作区；省略表示仅包内上下文。
    # Exact wire member workspace_root; required independently of nullability.
    # 精确线成员 workspace_root；必需与是否可为空值相互独立。
    workspace_root: Union[str, None]


class OutputCapabilityDescriptor(TypedDict, total=True):
    """
    Wire fields for OutputCapabilityDescriptor; native validation enforces semantic constraints.
    OutputCapabilityDescriptor 的线字段；原生校验负责语义约束。
    Immutable capability declaration shared by Rust, generated contracts and SDKs.
    Rust、生成契约与 SDK 共享的不可变能力声明。
    """
    # English description of the host capability for tool consumers.
    # 面向工具消费者的宿主能力英文描述。
    # Exact wire member description; required independently of nullability.
    # 精确线成员 description；必需与是否可为空值相互独立。
    description: str
    # Declared mutation category.
    # 声明的变更类别。
    # Exact wire member effects; required independently of nullability.
    # 精确线成员 effects；必需与是否可为空值相互独立。
    effects: 'OutputCapabilityEffects'
    # Explicit native or queued dispatch protocol.
    # 显式原生或队列分发协议。
    # Exact wire member execution; required independently of nullability.
    # 精确线成员 execution；必需与是否可为空值相互独立。
    execution: 'OutputCapabilityExecution'
    # Explicit host deduplication contract.
    # 显式宿主去重契约。
    # Exact wire member idempotency; required independently of nullability.
    # 精确线成员 idempotency；必需与是否可为空值相互独立。
    idempotency: 'OutputCapabilityIdempotency'
    # Offline input value contract.
    # 离线输入值契约。
    # Exact wire member input_schema; required independently of nullability.
    # 精确线成员 input_schema；必需与是否可为空值相互独立。
    input_schema: JsonValue
    # Per-capability budget capped by the original operation deadline.
    # 受原始操作截止时间约束的单能力预算。
    # Exact wire member max_call_ms; required independently of nullability.
    # 精确线成员 max_call_ms；必需与是否可为空值相互独立。
    max_call_ms: int
    # Maximum in-flight handlers, including cancelled handlers that have not stopped.
    # 在途处理器上限，包含已取消但尚未停止的处理器。
    # Exact wire member max_concurrent; required independently of nullability.
    # 精确线成员 max_concurrent；必需与是否可为空值相互独立。
    max_concurrent: int
    # Maximum serialized input bytes within the parent value limit.
    # 父级值上限内的最大序列化输入字节数。
    # Exact wire member max_input_bytes; required independently of nullability.
    # 精确线成员 max_input_bytes；必需与是否可为空值相互独立。
    max_input_bytes: int
    # Maximum serialized output bytes within the parent value limit.
    # 父级值上限内的最大序列化输出字节数。
    # Exact wire member max_output_bytes; required independently of nullability.
    # 精确线成员 max_output_bytes；必需与是否可为空值相互独立。
    max_output_bytes: int
    # Exact namespaced name; discovery exposes only authorized declarations.
    # 精确命名空间名称；发现操作仅暴露已授权声明。
    # Exact wire member name; required independently of nullability.
    # 精确线成员 name；必需与是否可为空值相互独立。
    name: str
    # Offline output value contract.
    # 离线输出值契约。
    # Exact wire member output_schema; required independently of nullability.
    # 精确线成员 output_schema；必需与是否可为空值相互独立。
    output_schema: JsonValue
    # Every listed grant must still exist at each admission boundary.
    # 每个入场边界仍必须拥有列出的全部授权。
    # Exact wire member permissions; required independently of nullability.
    # 精确线成员 permissions；必需与是否可为空值相互独立。
    permissions: List[str]
    # Required trusted invocation scope.
    # 必需的可信调用作用域。
    # Exact wire member scope; required independently of nullability.
    # 精确线成员 scope；必需与是否可为空值相互独立。
    scope: 'OutputCapabilityScope'
    # Semantic interface version, independent from the core library version.
    # 语义接口版本，独立于核心库版本。
    # Exact wire member version; required independently of nullability.
    # 精确线成员 version；必需与是否可为空值相互独立。
    version: str


# Exact wire shape of OutputCapabilityEffects, derived from the packaged core schema.
# 从包内核心 Schema 派生的 OutputCapabilityEffects 精确线形状。
OutputCapabilityEffects: TypeAlias = Literal['read_only', 'mutating']


# Exact wire shape of OutputCapabilityExecution, derived from the packaged core schema.
# 从包内核心 Schema 派生的 OutputCapabilityExecution 精确线形状。
OutputCapabilityExecution: TypeAlias = Literal['native', 'queued']


# Exact wire shape of OutputCapabilityIdempotency, derived from the packaged core schema.
# 从包内核心 Schema 派生的 OutputCapabilityIdempotency 精确线形状。
OutputCapabilityIdempotency: TypeAlias = Literal['none', 'host_request']


class OutputCapabilityRegistrationStatus(TypedDict, total=True):
    """
    Wire fields for OutputCapabilityRegistrationStatus; native validation enforces semantic constraints.
    OutputCapabilityRegistrationStatus 的线字段；原生校验负责语义约束。
    Observable lifetime of an exact registration, including unregistration still draining calls.
    精确注册的可观察生命周期，包含注销后仍在排空的调用。
    """
    # Whether new calls may enter this specific registration.
    # 新调用是否可以进入此特定注册。
    # Exact wire member accepting; required independently of nullability.
    # 精确线成员 accepting；必需与是否可为空值相互独立。
    accepting: bool
    # True only after admission closed and all native callback references were released.
    # 仅在入场关闭且全部原生回调引用释放后为真。
    # Exact wire member drained; required independently of nullability.
    # 精确线成员 drained；必需与是否可为空值相互独立。
    drained: bool
    # Actually executing or dispatched handlers, including pending cancellation.
    # 实际执行或已分发的处理器，包含等待取消完成的处理器。
    # Exact wire member in_flight; required independently of nullability.
    # 精确线成员 in_flight；必需与是否可为空值相互独立。
    in_flight: int
    # Exact declared capability name.
    # 精确声明的能力名称。
    # Exact wire member name; required independently of nullability.
    # 精确线成员 name；必需与是否可为空值相互独立。
    name: str
    # Opaque identity, never a lossy language number.
    # 不透明身份，绝不使用有精度损失的语言数值。
    # Exact wire member registration_id; required independently of nullability.
    # 精确线成员 registration_id；必需与是否可为空值相互独立。
    registration_id: str


# Exact wire shape of OutputCapabilityScope, derived from the packaged core schema.
# 从包内核心 Schema 派生的 OutputCapabilityScope 精确线形状。
OutputCapabilityScope: TypeAlias = Literal['invocation', 'session']


# Exact wire shape of OutputEffectState, derived from the packaged core schema.
# 从包内核心 Schema 派生的 OutputEffectState 精确线形状。
OutputEffectState: TypeAlias = Literal['not_started', 'not_applicable', 'committed', 'rolled_back', 'unknown']


class OutputEmbeddedBuildIdentity(TypedDict, total=True):
    """
    Wire fields for OutputEmbeddedBuildIdentity; native validation enforces semantic constraints.
    OutputEmbeddedBuildIdentity 的线字段；原生校验负责语义约束。
    Selected package and compiler input identities; binary authentication remains the release artifact's job.
    选定包及编译器输入身份；二进制认证仍由发布产物负责。
    """
    # Sorted Cargo feature environment suffixes; they are not reverse-mapped into guessed feature names.
    # 排序后 Cargo 功能环境后缀；不反向映射为猜测功能名。
    # Exact wire member cargo_features; required independently of nullability.
    # 精确线成员 cargo_features；必需与是否可为空值相互独立。
    cargo_features: List[str]
    # Exact bundled embedded contract identity, independently checked by SDKs.
    # 精确包内嵌入式契约身份，由 SDK 独立检查。
    # Exact wire member contract_sha256; required independently of nullability.
    # 精确线成员 contract_sha256；必需与是否可为空值相互独立。
    contract_sha256: str
    # Cargo's debug-information setting, independent of optimization.
    # Cargo 调试信息设置，独立于优化。
    # Exact wire member debug_info; required independently of nullability.
    # 精确线成员 debug_info；必需与是否可为空值相互独立。
    debug_info: str
    # SHA-256 of the exact machine-readable selected-input report emitted by build.rs.
    # build.rs 输出的精确机器可读选定输入报告的 SHA-256。
    # Exact wire member inputs_sha256; required independently of nullability.
    # 精确线成员 inputs_sha256；必需与是否可为空值相互独立。
    inputs_sha256: str
    # Actual Cargo optimization setting, not an inferred profile label.
    # 实际 Cargo 优化设置，不推断配置名称。
    # Exact wire member opt_level; required independently of nullability.
    # 精确线成员 opt_level；必需与是否可为空值相互独立。
    opt_level: str
    # Bundled package lockfile identity; a consuming Rust workspace may resolve a different dependency graph.
    # 包内锁文件身份；消费它的 Rust 工作区可能解析出不同依赖图。
    # Exact wire member package_lock_sha256; required independently of nullability.
    # 精确线成员 package_lock_sha256；必需与是否可为空值相互独立。
    package_lock_sha256: str
    # Cargo's target pointer width, preserved as its exact textual value.
    # Cargo 目标指针位宽，保留其精确文本值。
    # Exact wire member pointer_width; required independently of nullability.
    # 精确线成员 pointer_width；必需与是否可为空值相互独立。
    pointer_width: str
    # The selected rustc executable's verbose version output.
    # 所选 rustc 可执行文件的详细版本输出。
    # Exact wire member rustc; required independently of nullability.
    # 精确线成员 rustc；必需与是否可为空值相互独立。
    rustc: str
    # SHA-256 of Cargo's exact encoded additional compiler flags.
    # Cargo 精确编码额外编译参数的 SHA-256。
    # Exact wire member rustflags_sha256; required independently of nullability.
    # 精确线成员 rustflags_sha256；必需与是否可为空值相互独立。
    rustflags_sha256: str
    # SHA-256 of sorted package-relative input paths and their exact content hashes.
    # 排序后包相对输入路径及其精确内容摘要的 SHA-256。
    # Exact wire member source_sha256; required independently of nullability.
    # 精确线成员 source_sha256；必需与是否可为空值相互独立。
    source_sha256: str
    # Cargo's target triple for this build.
    # 此构建的 Cargo 目标三元组。
    # Exact wire member target; required independently of nullability.
    # 精确线成员 target；必需与是否可为空值相互独立。
    target: str
    # Cargo's target architecture identity.
    # Cargo 目标架构身份。
    # Exact wire member target_arch; required independently of nullability.
    # 精确线成员 target_arch；必需与是否可为空值相互独立。
    target_arch: str
    # Cargo's target operating-system identity.
    # Cargo 目标操作系统身份。
    # Exact wire member target_os; required independently of nullability.
    # 精确线成员 target_os；必需与是否可为空值相互独立。
    target_os: str


class OutputEmbeddedError(TypedDict, total=True):
    """
    Wire fields for OutputEmbeddedError; native validation enforces semantic constraints.
    OutputEmbeddedError 的线字段；原生校验负责语义约束。
    Structured error; `code` is stable and `message` is an English diagnostic.
    结构化错误；`code` 稳定，`message` 为英文诊断信息。
    """
    # Stable classification consumed by SDKs instead of parsing text.
    # 供 SDK 使用的稳定分类，避免解析文案。
    # Exact wire member code; required independently of nullability.
    # 精确线成员 code；必需与是否可为空值相互独立。
    code: 'OutputEmbeddedErrorCode'
    # Human-readable detail without credentials or plugin input dumps.
    # 不含凭据或插件输入转储的可读详情。
    # Exact wire member message; required independently of nullability.
    # 精确线成员 message；必需与是否可为空值相互独立。
    message: str


# Exact wire shape of OutputEmbeddedErrorCode, derived from the packaged core schema.
# 从包内核心 Schema 派生的 OutputEmbeddedErrorCode 精确线形状。
OutputEmbeddedErrorCode: TypeAlias = Literal['invalid_argument', 'not_found', 'stale_generation', 'capacity_exceeded', 'busy', 'already_completed', 'closed', 'cancelled', 'deadline_exceeded', 'permission_denied', 'unsupported', 'execution_failed', 'cleanup_failed', 'internal']


class OutputEmbeddedPluginConfig(TypedDict, total=True):
    """
    Wire fields for OutputEmbeddedPluginConfig; native validation enforces semantic constraints.
    OutputEmbeddedPluginConfig 的线字段；原生校验负责语义约束。
    Immutable host-approved aggregate budgets across every generation and execution domain of one plugin.
    一个插件的全部代次与执行域共享的不可变宿主批准聚合预算。
    """
    # Maximum retained operations, including completed results not explicitly forgotten.
    # 保留操作的数量上限，包含尚未显式遗忘的已完成结果。
    # Exact wire member max_operations; required independently of nullability.
    # 精确线成员 max_operations；必需与是否可为空值相互独立。
    max_operations: int
    # Maximum exact serialized queued request bytes across this plugin.
    # 此插件全部排队请求精确序列化字节数上限。
    # Exact wire member max_queued_bytes; required independently of nullability.
    # 精确线成员 max_queued_bytes；必需与是否可为空值相互独立。
    max_queued_bytes: int
    # Maximum accepted queued calls across all domains and sessions.
    # 全部域和会话已接纳排队调用的合计上限。
    # Exact wire member max_queued_calls; required independently of nullability.
    # 精确线成员 max_queued_calls；必需与是否可为空值相互独立。
    max_queued_calls: int
    # Maximum retained pool identities, including closed generations awaiting explicit removal.
    # 保留池身份的数量上限，包含等待显式移除的已关闭代次。
    # Exact wire member max_registered_pools; required independently of nullability.
    # 精确线成员 max_registered_pools；必需与是否可为空值相互独立。
    max_registered_pools: int
    # Maximum actual resident VMs plus other domains' unused dedicated reservations.
    # 实际常驻 VM 与其他域未使用专用预留的合计上限。
    # Exact wire member max_resident_vms; required independently of nullability.
    # 精确线成员 max_resident_vms；必需与是否可为空值相互独立。
    max_resident_vms: int
    # Maximum dispatched operations, retained through initialization, host waiting and cleanup.
    # 已分发操作上限，计费覆盖初始化、宿主等待及清理。
    # Exact wire member max_running_calls; required independently of nullability.
    # 精确线成员 max_running_calls；必需与是否可为空值相互独立。
    max_running_calls: int
    # Maximum retained sessions, including closed session records.
    # 保留会话的数量上限，包含已关闭会话记录。
    # Exact wire member max_sessions; required independently of nullability.
    # 精确线成员 max_sessions；必需与是否可为空值相互独立。
    max_sessions: int


class OutputEmbeddedPluginSnapshot(TypedDict, total=True):
    """
    Wire fields for OutputEmbeddedPluginSnapshot; native validation enforces semantic constraints.
    OutputEmbeddedPluginSnapshot 的线字段；原生校验负责语义约束。
    Plugin-wide observation from exact immutable pool ownership, including draining generations.
    根据精确不可变池归属形成的插件级观测，包含正在排空的代次。
    """
    # Dispatched unfinished operations, including initialization and cleanup.
    # 已分发未完成操作，包含初始化与清理。
    # Exact wire member active_operations; required independently of nullability.
    # 精确线成员 active_operations；必需与是否可为空值相互独立。
    active_operations: int
    # Whether new pool and call admission is permanently closed.
    # 新池及新调用入场是否已永久关闭。
    # Exact wire member closing; required independently of nullability.
    # 精确线成员 closing；必需与是否可为空值相互独立。
    closing: bool
    # Actual residents plus all unused dedicated domain guarantees.
    # 实际常驻实例与全部未使用专用域保证的合计。
    # Exact wire member committed_resident_vms; required independently of nullability.
    # 精确线成员 committed_resident_vms；必需与是否可为空值相互独立。
    committed_resident_vms: int
    # Immutable effective aggregate policy.
    # 不可变有效聚合策略。
    # Exact wire member config; required independently of nullability.
    # 精确线成员 config；必需与是否可为空值相互独立。
    config: 'OutputEmbeddedPluginConfig'
    # Trusted host plugin identity used by module definitions and fair scheduling.
    # 模块定义与公平调度使用的可信宿主插件身份。
    # Exact wire member plugin_id; required independently of nullability.
    # 精确线成员 plugin_id；必需与是否可为空值相互独立。
    plugin_id: str
    # Exact serialized bytes still held by queued requests.
    # 排队请求仍持有的精确序列化字节数。
    # Exact wire member queued_bytes; required independently of nullability.
    # 精确线成员 queued_bytes；必需与是否可为空值相互独立。
    queued_bytes: int
    # Accepted queued calls across every domain and session.
    # 全部域和会话已接纳的排队调用。
    # Exact wire member queued_calls; required independently of nullability.
    # 精确线成员 queued_calls；必需与是否可为空值相互独立。
    queued_calls: int
    # Actual resident VM counters through confirmed destruction.
    # 持续记账到确认销毁的实际常驻 VM 计数。
    # Exact wire member resources; required independently of nullability.
    # 精确线成员 resources；必需与是否可为空值相互独立。
    resources: 'OutputPoolUsage'
    # Retained operations, including results whose callers dropped their handles.
    # 保留操作，包含调用方已丢弃句柄的结果。
    # Exact wire member retained_operations; required independently of nullability.
    # 精确线成员 retained_operations；必需与是否可为空值相互独立。
    retained_operations: int
    # Retained pools, including closed metadata not explicitly forgotten.
    # 保留池，包含尚未显式遗忘的已关闭元数据。
    # Exact wire member retained_pools; required independently of nullability.
    # 精确线成员 retained_pools；必需与是否可为空值相互独立。
    retained_pools: int
    # Retained fixed sessions, including closed records.
    # 保留固定会话，包含已关闭记录。
    # Exact wire member retained_sessions; required independently of nullability.
    # 精确线成员 retained_sessions；必需与是否可为空值相互独立。
    retained_sessions: int


class OutputEmbeddedRuntimeUsage(TypedDict, total=True):
    """
    Wire fields for OutputEmbeddedRuntimeUsage; native validation enforces semantic constraints.
    OutputEmbeddedRuntimeUsage 的线字段；原生校验负责语义约束。
    Live scheduler observations; queue bytes exclude already-dispatched request values.
    实时调度观测；队列字节不包含已分发的请求值。
    """
    # Nonqueued unfinished operations, including rejected requests awaiting terminal publication.
    # 不在队列中的未完成操作，包含等待终态发布的已拒绝请求。
    # Exact wire member active_operations; required independently of nullability.
    # 精确线成员 active_operations；必需与是否可为空值相互独立。
    active_operations: int
    # Operations whose execution returned and whose cleanup remains owned.
    # 执行已返回但仍拥有清理的操作。
    # Exact wire member cleaning_operations; required independently of nullability.
    # 精确线成员 cleaning_operations；必需与是否可为空值相互独立。
    cleaning_operations: int
    # Whether new admission has permanently closed.
    # 新入场是否已永久关闭。
    # Exact wire member closing; required independently of nullability.
    # 精确线成员 closing；必需与是否可为空值相互独立。
    closing: bool
    # Exact serialized queued request bytes.
    # 排队请求的精确序列化字节数。
    # Exact wire member queued_bytes; required independently of nullability.
    # 精确线成员 queued_bytes；必需与是否可为空值相互独立。
    queued_bytes: int
    # Requests waiting for actual resource admission.
    # 等待实际资源入场的请求。
    # Exact wire member queued_calls; required independently of nullability.
    # 精确线成员 queued_calls；必需与是否可为空值相互独立。
    queued_calls: int


# Exact wire shape of OutputEmbeddedSessionPhase, derived from the packaged core schema.
# 从包内核心 Schema 派生的 OutputEmbeddedSessionPhase 精确线形状。
OutputEmbeddedSessionPhase: TypeAlias = Literal['opening', 'ready', 'running', 'closing', 'closed']


class OutputEmbeddedSessionSnapshot(TypedDict, total=True):
    """
    Wire fields for OutputEmbeddedSessionSnapshot; native validation enforces semantic constraints.
    OutputEmbeddedSessionSnapshot 的线字段；原生校验负责语义约束。
    Bounded retained session observation with immutable pool ownership.
    具有不可变池归属的有界保留会话观测。
    """
    # Current operation, including initialization and cleanup; absent while idle.
    # 当前操作，包含初始化与清理；空闲时省略。
    # Exact wire member active_operation; required independently of nullability.
    # 精确线成员 active_operation；必需与是否可为空值相互独立。
    active_operation: Union[str, None]
    # First execution failure that made the session unusable.
    # 导致会话不可用的首次执行错误。
    # Exact wire member error; required independently of nullability.
    # 精确线成员 error；必需与是否可为空值相互独立。
    error: Union['OutputEmbeddedError', None]
    # Current lifecycle observation.
    # 当前生命周期观测。
    # Exact wire member phase; required independently of nullability.
    # 精确线成员 phase；必需与是否可为空值相互独立。
    phase: 'OutputEmbeddedSessionPhase'
    # Exact generation and security partition fixed at creation.
    # 创建时固定的精确代次与安全分区。
    # Exact wire member pool_id; required independently of nullability.
    # 精确线成员 pool_id；必需与是否可为空值相互独立。
    pool_id: str
    # Accepted calls waiting behind this session's current owner.
    # 此会话当前所有者之后等待的已接纳调用数。
    # Exact wire member queued_calls; required independently of nullability.
    # 精确线成员 queued_calls；必需与是否可为空值相互独立。
    queued_calls: int
    # Runtime-issued opaque identity, never reused after forgetting.
    # 运行时签发的不透明身份，遗忘后绝不复用。
    # Exact wire member session_id; required independently of nullability.
    # 精确线成员 session_id；必需与是否可为空值相互独立。
    session_id: str


# Exact wire shape of OutputErrorStatus, derived from the packaged core schema.
# 从包内核心 Schema 派生的 OutputErrorStatus 精确线形状。
OutputErrorStatus: TypeAlias = Literal['error']


# Exact wire shape of OutputExecutionBackend, derived from the packaged core schema.
# 从包内核心 Schema 派生的 OutputExecutionBackend 精确线形状。
OutputExecutionBackend: TypeAlias = Literal['in_process', 'worker_process']


# Exact wire shape of OutputHostEffectPhase, derived from the packaged core schema.
# 从包内核心 Schema 派生的 OutputHostEffectPhase 精确线形状。
OutputHostEffectPhase: TypeAlias = Literal['prepared', 'running', 'completed']


class OutputHostEffectRecord(TypedDict, total=True):
    """
    Wire fields for OutputHostEffectRecord; native validation enforces semantic constraints.
    OutputHostEffectRecord 的线字段；原生校验负责语义约束。
    Bounded evidence retained independently from values returned to Lua.
    独立于返回 Lua 的值保留的有界证据。
    """
    # Public capability name, excluding business arguments and credentials.
    # 公开能力名称，不包含业务参数与凭证。
    # Exact wire member capability_name; required independently of nullability.
    # 精确线成员 capability_name；必需与是否可为空值相互独立。
    capability_name: str
    # Interface version of the exact registration.
    # 精确注册的接口版本。
    # Exact wire member capability_version; required independently of nullability.
    # 精确线成员 capability_version；必需与是否可为空值相互独立。
    capability_version: str
    # Never-reused identity within the original operation.
    # 原始操作内绝不复用的身份。
    # Exact wire member effect_id; required independently of nullability.
    # 精确线成员 effect_id；必需与是否可为空值相互独立。
    effect_id: str
    # Trusted host evidence, independent from caller cancellation.
    # 可信宿主证据，独立于调用方取消。
    # Exact wire member effects; required independently of nullability.
    # 精确线成员 effects；必需与是否可为空值相互独立。
    effects: 'OutputEffectState'
    # Actual handler ownership lifecycle.
    # 真实处理器所有权生命周期。
    # Exact wire member phase; required independently of nullability.
    # 精确线成员 phase；必需与是否可为空值相互独立。
    phase: 'OutputHostEffectPhase'
    # Exact immutable registration identity.
    # 精确不可变注册身份。
    # Exact wire member registration_id; required independently of nullability.
    # 精确线成员 registration_id；必需与是否可为空值相互独立。
    registration_id: str
    # SDK request identity for queued execution.
    # 队列执行的 SDK 请求身份。
    # Exact wire member request_id; required independently of nullability.
    # 精确线成员 request_id；必需与是否可为空值相互独立。
    request_id: Union[str, None]


class OutputHostRequest(TypedDict, total=True):
    """
    Wire fields for OutputHostRequest; native validation enforces semantic constraints.
    OutputHostRequest 的线字段；原生校验负责语义约束。
    SDK request copied from an admitted, authenticated invocation.
    从已入场、已认证调用复制的 SDK 请求。
    """
    # Validated structured business arguments.
    # 已校验的结构化业务参数。
    # Exact wire member arguments; required independently of nullability.
    # 精确线成员 arguments；必需与是否可为空值相互独立。
    arguments: JsonValue
    # Trusted host identity, separate from business arguments.
    # 可信宿主身份，独立于业务参数。
    # Exact wire member caller; required independently of nullability.
    # 精确线成员 caller；必需与是否可为空值相互独立。
    caller: 'OutputCapabilityCaller'
    # Original operation effect record, absent only for untracked low-level calls.
    # 原始操作副作用记录，仅未跟踪低层调用省略。
    # Exact wire member effect_id; required independently of nullability.
    # 精确线成员 effect_id；必需与是否可为空值相互独立。
    effect_id: Union[str, None]
    # Declared capability name.
    # 声明的能力名称。
    # Exact wire member name; required independently of nullability.
    # 精确线成员 name；必需与是否可为空值相互独立。
    name: str
    # Exact registration, independent from later replacement by name.
    # 精确注册，独立于后续按名称替换。
    # Exact wire member registration_id; required independently of nullability.
    # 精确线成员 registration_id；必需与是否可为空值相互独立。
    registration_id: str
    # Advisory remaining duration; the core retains the original deadline.
    # 建议剩余时长；核心保留原始截止时间。
    # Exact wire member remaining_ms; required independently of nullability.
    # 精确线成员 remaining_ms；必需与是否可为空值相互独立。
    remaining_ms: int
    # Never-reused identity used for completion and host-side deduplication.
    # 用于完成与宿主侧去重、绝不复用的身份。
    # Exact wire member request_id; required independently of nullability.
    # 精确线成员 request_id；必需与是否可为空值相互独立。
    request_id: str
    # Declared semantic interface version.
    # 声明的语义接口版本。
    # Exact wire member version; required independently of nullability.
    # 精确线成员 version；必需与是否可为空值相互独立。
    version: str


# Exact wire shape of OutputHostRequestPhase, derived from the packaged core schema.
# 从包内核心 Schema 派生的 OutputHostRequestPhase 精确线形状。
OutputHostRequestPhase: TypeAlias = Literal['queued', 'dispatched', 'completing', 'completed']


class OutputHostRequestStatus(TypedDict, total=True):
    """
    Wire fields for OutputHostRequestStatus; native validation enforces semantic constraints.
    OutputHostRequestStatus 的线字段；原生校验负责语义约束。
    Live request status for SDK cancellation and orderly runtime shutdown.
    用于 SDK 取消与运行时有序关闭的实时请求状态。
    """
    # Cooperative cancellation reason, preserved until actual completion.
    # 协作取消原因，保留到真实完成。
    # Exact wire member cancellation; required independently of nullability.
    # 精确线成员 cancellation；必需与是否可为空值相互独立。
    cancellation: Union['OutputEmbeddedError', None]
    # Actual execution lifecycle.
    # 真实执行生命周期。
    # Exact wire member phase; required independently of nullability.
    # 精确线成员 phase；必需与是否可为空值相互独立。
    phase: 'OutputHostRequestPhase'
    # Exact request identity.
    # 精确请求身份。
    # Exact wire member request_id; required independently of nullability.
    # 精确线成员 request_id；必需与是否可为空值相互独立。
    request_id: str


# Exact wire shape of OutputInitializationPhase, derived from the packaged core schema.
# 从包内核心 Schema 派生的 OutputInitializationPhase 精确线形状。
OutputInitializationPhase: TypeAlias = Literal['reserved', 'initializing', 'ready', 'failed', 'faulted']


# Exact wire shape of OutputOperationPhase, derived from the packaged core schema.
# 从包内核心 Schema 派生的 OutputOperationPhase 精确线形状。
OutputOperationPhase: TypeAlias = Literal['queued', 'initializing', 'running', 'waiting_for_host', 'cleaning', 'succeeded', 'failed', 'cancelled']


class OutputOperationReceipt(TypedDict, total=True):
    """
    Wire fields for OutputOperationReceipt; native validation enforces semantic constraints.
    OutputOperationReceipt 的线字段；原生校验负责语义约束。
    Actual operation admission acknowledgement; it does not imply execution completion.
    实际操作入场确认；不代表执行完成。
    """
    # Retained queryable operation identity.
    # 保留且可查询的操作身份。
    # Exact wire member operation_id; required independently of nullability.
    # 精确线成员 operation_id；必需与是否可为空值相互独立。
    operation_id: str


class _OutputOperationSnapshotRequired(TypedDict, total=True):
    """
    Wire fields for _OutputOperationSnapshotRequired; native validation enforces semantic constraints.
    _OutputOperationSnapshotRequired 的线字段；原生校验负责语义约束。
    Bounded operation snapshot suitable for direct serialization to every SDK.
    适合直接序列化给各 SDK 的有界操作快照。
    """
    # Whether cooperative cancellation has been requested.
    # 是否已请求协作取消。
    # Exact wire member cancellation_requested; required independently of nullability.
    # 精确线成员 cancellation_requested；必需与是否可为空值相互独立。
    cancellation_requested: bool
    # Explicit effect status; successful execution does not automatically imply commit.
    # 显式副作用状态；执行成功不自动表示提交。
    # Exact wire member effects; required independently of nullability.
    # 精确线成员 effects；必需与是否可为空值相互独立。
    effects: 'OutputEffectState'
    # Exact host callback evidence retained even after Lua failure, cancellation or output rejection.
    # 即使 Lua 失败、取消或输出被拒绝也保留的精确宿主回调证据。
    # Exact wire member host_effects; required independently of nullability.
    # 精确线成员 host_effects；必需与是否可为空值相互独立。
    host_effects: List['OutputHostEffectRecord']
    # Opaque identifier, never a JavaScript floating-point integer.
    # 不透明标识符，绝不使用 JavaScript 浮点整数。
    # Exact wire member operation_id; required independently of nullability.
    # 精确线成员 operation_id；必需与是否可为空值相互独立。
    operation_id: str
    # Current execution phase, including still-running cancelled requests.
    # 当前执行阶段，包含已请求取消但仍在运行的请求。
    # Exact wire member phase; required independently of nullability.
    # 精确线成员 phase；必需与是否可为空值相互独立。
    phase: 'OutputOperationPhase'


class OutputOperationSnapshot(_OutputOperationSnapshotRequired, total=False):
    """
    Wire fields for OutputOperationSnapshot; native validation enforces semantic constraints.
    OutputOperationSnapshot 的线字段；原生校验负责语义约束。
    Bounded operation snapshot suitable for direct serialization to every SDK.
    适合直接序列化给各 SDK 的有界操作快照。
    """
    # Structured terminal error; absent while execution is still in progress.
    # 结构化终态错误；执行仍在进行时省略。
    # Exact wire member error; omittable independently of nullability.
    # 精确线成员 error；可省略与是否可为空值相互独立。
    error: Union['OutputEmbeddedError', None]
    # Successful value; absent before completion or on failure, distinct from JSON null.
    # 成功值；完成前或失败时省略，与 JSON 空值不同。
    # Exact wire member value; omittable independently of nullability.
    # 精确线成员 value；可省略与是否可为空值相互独立。
    value: JsonValue


class OutputPoolReceipt(TypedDict, total=True):
    """
    Wire fields for OutputPoolReceipt; native validation enforces semantic constraints.
    OutputPoolReceipt 的线字段；原生校验负责语义约束。
    Actual pool registration acknowledgement shared by capacity preparation and publication.
    容量准备及发布共享的实际池注册确认。
    """
    # Immutable core pool identity.
    # 不可变核心池身份。
    # Exact wire member pool_id; required independently of nullability.
    # 精确线成员 pool_id；必需与是否可为空值相互独立。
    pool_id: str


class OutputPoolUsage(TypedDict, total=True):
    """
    Wire fields for OutputPoolUsage; native validation enforces semantic constraints.
    OutputPoolUsage 的线字段；原生校验负责语义约束。
    Current counters for one governor or one execution group.
    单个治理器或执行分组的当前计数。
    """
    # Allocations that have not finished initialization.
    # 尚未完成初始化的分配。
    # Exact wire member creating; required independently of nullability.
    # 精确线成员 creating；必需与是否可为空值相互独立。
    creating: int
    # Initialized allocations that do not currently execute.
    # 已初始化且当前未执行的分配。
    # Exact wire member idle; required independently of nullability.
    # 精确线成员 idle；必需与是否可为空值相互独立。
    idle: int
    # All allocated slots, including creating and retiring instances.
    # 全部分配槽位，包含正在创建与退役的实例。
    # Exact wire member resident; required independently of nullability.
    # 精确线成员 resident；必需与是否可为空值相互独立。
    resident: int
    # Allocations retained until teardown has genuinely completed.
    # 保留到清理真正完成的分配。
    # Exact wire member retiring; required independently of nullability.
    # 精确线成员 retiring；必需与是否可为空值相互独立。
    retiring: int
    # Allocations holding a parent and group execution permit together.
    # 同时持有父级与分组执行许可的分配。
    # Exact wire member running; required independently of nullability.
    # 精确线成员 running；必需与是否可为空值相互独立。
    running: int


class OutputRegistrationReceipt(TypedDict, total=True):
    """
    Wire fields for OutputRegistrationReceipt; native validation enforces semantic constraints.
    OutputRegistrationReceipt 的线字段；原生校验负责语义约束。
    Exact identities from one atomic host capability publication.
    单次原子宿主能力发布的精确身份。
    """
    # Identities retain the descriptor batch's original order.
    # 身份保留描述符批次的原始顺序。
    # Exact wire member registration_ids; required independently of nullability.
    # 精确线成员 registration_ids；必需与是否可为空值相互独立。
    registration_ids: List[str]


class OutputRuntimeReceipt(TypedDict, total=True):
    """
    Wire fields for OutputRuntimeReceipt; native validation enforces semantic constraints.
    OutputRuntimeReceipt 的线字段；原生校验负责语义约束。
    Exact lifecycle identity returned before or after a runtime control mutation.
    在运行时控制变更前或后返回的精确生命周期身份。
    """
    # Immutable transport-local runtime identity.
    # 不可变传输局部运行时身份。
    # Exact wire member runtime_id; required independently of nullability.
    # 精确线成员 runtime_id；必需与是否可为空值相互独立。
    runtime_id: str


class OutputRuntimeSnapshot(TypedDict, total=True):
    """
    Wire fields for OutputRuntimeSnapshot; native validation enforces semantic constraints.
    OutputRuntimeSnapshot 的线字段；原生校验负责语义约束。
    Queryable construction and core closure evidence; no runtime implementation state is inferred by SDKs.
    可查询构造与核心关闭证据；SDK 不推断运行时实现状态。
    """
    # True only after native core workers have exited, or no core was ever created.
    # 仅当原生核心工作线程已退出或从未创建核心时为真。
    # Exact wire member closed; required independently of nullability.
    # 精确线成员 closed；必需与是否可为空值相互独立。
    closed: bool
    # Whether this slot has permanently closed admission.
    # 此槽是否已永久关闭入场。
    # Exact wire member closing; required independently of nullability.
    # 精确线成员 closing；必需与是否可为空值相互独立。
    closing: bool
    # Actual runtime namespace, present only after successful construction.
    # 实际运行时命名空间，仅在成功构造后存在。
    # Exact wire member core_runtime_id; required independently of nullability.
    # 精确线成员 core_runtime_id；必需与是否可为空值相互独立。
    core_runtime_id: Union[str, None]
    # Retained failure; a failed construction still owns its bounded registration until explicit release.
    # 保留失败；构造失败仍拥有其有界注册，直到显式释放。
    # Exact wire member error; required independently of nullability.
    # 精确线成员 error；必需与是否可为空值相互独立。
    error: Union['OutputEmbeddedError', None]
    # Actual one-shot construction state.
    # 实际单次构造状态。
    # Exact wire member initialization; required independently of nullability.
    # 精确线成员 initialization；必需与是否可为空值相互独立。
    initialization: 'OutputInitializationPhase'
    # Live resident and execution accounting directly from the core when available.
    # 可用时直接来自核心的实时常驻与执行计数。
    # Exact wire member resources; required independently of nullability.
    # 精确线成员 resources；必需与是否可为空值相互独立。
    resources: Union['OutputPoolUsage', None]
    # Exact FFI slot identity used by every control command.
    # 每个控制命令使用的精确 FFI 槽身份。
    # Exact wire member runtime_id; required independently of nullability.
    # 精确线成员 runtime_id；必需与是否可为空值相互独立。
    runtime_id: str
    # Live scheduler observations directly from the core when available.
    # 可用时直接来自核心的实时调度观测。
    # Exact wire member usage; required independently of nullability.
    # 精确线成员 usage；必需与是否可为空值相互独立。
    usage: Union['OutputEmbeddedRuntimeUsage', None]


class OutputSessionReceipt(TypedDict, total=True):
    """
    Wire fields for OutputSessionReceipt; native validation enforces semantic constraints.
    OutputSessionReceipt 的线字段；原生校验负责语义约束。
    Fixed-session reservation and its independently queryable initialization operation.
    固定会话预留及其可独立查询的初始化操作。
    """
    # Initialization operation whose actual outcome must be observed separately.
    # 必须单独观察实际结果的初始化操作。
    # Exact wire member operation_id; required independently of nullability.
    # 精确线成员 operation_id；必需与是否可为空值相互独立。
    operation_id: str
    # Immutable fixed-session identity.
    # 不可变固定会话身份。
    # Exact wire member session_id; required independently of nullability.
    # 精确线成员 session_id；必需与是否可为空值相互独立。
    session_id: str


# Exact wire shape of OutputSuccessStatus, derived from the packaged core schema.
# 从包内核心 Schema 派生的 OutputSuccessStatus 精确线形状。
OutputSuccessStatus: TypeAlias = Literal['ok']


class OutputTransportConfig(TypedDict, total=True):
    """
    Wire fields for OutputTransportConfig; native validation enforces semantic constraints.
    OutputTransportConfig 的线字段；原生校验负责语义约束。
    Validated native-sized transport configuration, copied once from the host declaration.
    从宿主声明一次性复制的已校验原生大小传输配置。
    """
    # Per-request byte limit.
    # 逐请求字节上限。
    # Exact wire member max_request_bytes; required independently of nullability.
    # 精确线成员 max_request_bytes；必需与是否可为空值相互独立。
    max_request_bytes: int
    # Per-response pre-dispatch reservation.
    # 逐响应分发前预留。
    # Exact wire member max_response_bytes; required independently of nullability.
    # 精确线成员 max_response_bytes；必需与是否可为空值相互独立。
    max_response_bytes: int
    # Maximum response owners, including pre-dispatch reservations.
    # 响应所有者数量上限，包含分发前预留。
    # Exact wire member max_result_buffers; required independently of nullability.
    # 精确线成员 max_result_buffers；必需与是否可为空值相互独立。
    max_result_buffers: int
    # Aggregate response allocation budget.
    # 聚合响应分配预算。
    # Exact wire member max_result_bytes; required independently of nullability.
    # 精确线成员 max_result_bytes；必需与是否可为空值相互独立。
    max_result_bytes: int
    # Maximum retained runtime identities.
    # 保留运行时身份数量上限。
    # Exact wire member max_runtimes; required independently of nullability.
    # 精确线成员 max_runtimes；必需与是否可为空值相互独立。
    max_runtimes: int


class OutputTransportDescription(TypedDict, total=True):
    """
    Wire fields for OutputTransportDescription; native validation enforces semantic constraints.
    OutputTransportDescription 的线字段；原生校验负责语义约束。
    Implemented transport description; every field comes from the running core's own authority.
    已实现传输描述；每个字段均来自运行核心自身权威。
    """
    # Version of the independent embedded ABI structures.
    # 独立嵌入式 ABI 结构版本。
    # Exact wire member abi_structure_version; required independently of nullability.
    # 精确线成员 abi_structure_version；必需与是否可为空值相互独立。
    abi_structure_version: int
    # Root commands implemented by the exhaustive dispatcher.
    # 穷尽分发器实现的根命令。
    # Exact wire member commands; required independently of nullability.
    # 精确线成员 commands；必需与是否可为空值相互独立。
    commands: List[str]
    # Cargo package version of this exact library build.
    # 此精确动态库构建的 Cargo 包版本。
    # Exact wire member core_version; required independently of nullability.
    # 精确线成员 core_version；必需与是否可为空值相互独立。
    core_version: str
    # Actual validated transport limits supplied at construction.
    # 构造时提供的实际已校验传输边界。
    # Exact wire member limits; required independently of nullability.
    # 精确线成员 limits；必需与是否可为空值相互独立。
    limits: 'OutputTransportConfig'
    # Version of the accepted embedded JSON protocol.
    # 接受的嵌入式 JSON 协议版本。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Runtime operations implemented by the exhaustive dispatcher.
    # 穷尽分发器实现的运行时操作。
    # Exact wire member runtime_commands; required independently of nullability.
    # 精确线成员 runtime_commands；必需与是否可为空值相互独立。
    runtime_commands: List[str]


class OutputCoreDescription(TypedDict, total=True):
    """
    Wire fields for OutputCoreDescription; native validation enforces semantic constraints.
    OutputCoreDescription 的线字段；原生校验负责语义约束。
    Immutable description of the exact linked core, usable without a transport or runtime.
    精确链接核心的不可变描述，无需传输或运行时即可使用。
    """
    # Exact independent embedded ABI structure version.
    # 精确独立嵌入式 ABI 结构版本。
    # Exact wire member abi_structure_version; required independently of nullability.
    # 精确线成员 abi_structure_version；必需与是否可为空值相互独立。
    abi_structure_version: int
    # Build input evidence; release manifests bind it to commits and signed artifact checksums separately.
    # 构建输入证据；发布清单另将其关联到提交及签名产物摘要。
    # Exact wire member build; required independently of nullability.
    # 精确线成员 build；必需与是否可为空值相互独立。
    build: 'OutputEmbeddedBuildIdentity'
    # Implemented semantic features; a name does not grant host permissions.
    # 已实现语义功能；名称不授予宿主权限。
    # Exact wire member capabilities; required independently of nullability.
    # 精确线成员 capabilities；必需与是否可为空值相互独立。
    capabilities: List[str]
    # Root command names shared with the exhaustive dispatcher.
    # 与穷尽分发器共享的根命令名称。
    # Exact wire member commands; required independently of nullability.
    # 精确线成员 commands；必需与是否可为空值相互独立。
    commands: List[str]
    # Cargo package version of this exact core.
    # 此精确核心的 Cargo 包版本。
    # Exact wire member core_version; required independently of nullability.
    # 精确线成员 core_version；必需与是否可为空值相互独立。
    core_version: str
    # Version of this independent descriptor format.
    # 此独立描述格式的版本。
    # Exact wire member description_version; required independently of nullability.
    # 精确线成员 description_version；必需与是否可为空值相互独立。
    description_version: int
    # Actually implemented execution backends, excluding reserved unsupported variants.
    # 实际已实现执行后端，不包含预留且不支持的取值。
    # Exact wire member execution_backends; required independently of nullability.
    # 精确线成员 execution_backends；必需与是否可为空值相互独立。
    execution_backends: List['OutputExecutionBackend']
    # Exact embedded JSON protocol version.
    # 精确嵌入式 JSON 协议版本。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Nested command names shared with the exhaustive dispatcher.
    # 与穷尽分发器共享的嵌套命令名称。
    # Exact wire member runtime_commands; required independently of nullability.
    # 精确线成员 runtime_commands；必需与是否可为空值相互独立。
    runtime_commands: List[str]


class OutputErrorResponse(TypedDict, total=True):
    """
    Wire fields for OutputErrorResponse; native validation enforces semantic constraints.
    OutputErrorResponse 的线字段；原生校验负责语义约束。
    Live structured failure envelope whose shape also drives SDK generation.
    同时驱动 SDK 生成的实际结构化失败信封。
    """
    # Borrowed core error retained until response encoding returns.
    # 保留到响应编码返回的借用核心错误。
    # Exact wire member error; required independently of nullability.
    # 精确线成员 error；必需与是否可为空值相互独立。
    error: 'OutputEmbeddedError'
    # Accepted embedded protocol version.
    # 接受的嵌入式协议版本。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Exact business-error discriminator.
    # 精确业务错误判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputErrorStatus'


class OutputRootDescribeResponse(TypedDict, total=True):
    """
    Wire fields for OutputRootDescribeResponse; native validation enforces semantic constraints.
    OutputRootDescribeResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: 'OutputTransportDescription'
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRootRuntimeCloseResponse(TypedDict, total=True):
    """
    Wire fields for OutputRootRuntimeCloseResponse; native validation enforces semantic constraints.
    OutputRootRuntimeCloseResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: 'OutputRuntimeReceipt'
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRootRuntimeFreeResponse(TypedDict, total=True):
    """
    Wire fields for OutputRootRuntimeFreeResponse; native validation enforces semantic constraints.
    OutputRootRuntimeFreeResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: 'OutputRuntimeReceipt'
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRootRuntimeInitializeResponse(TypedDict, total=True):
    """
    Wire fields for OutputRootRuntimeInitializeResponse; native validation enforces semantic constraints.
    OutputRootRuntimeInitializeResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: 'OutputRuntimeReceipt'
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRootRuntimeReserveResponse(TypedDict, total=True):
    """
    Wire fields for OutputRootRuntimeReserveResponse; native validation enforces semantic constraints.
    OutputRootRuntimeReserveResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: 'OutputRuntimeReceipt'
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRootRuntimeStatusResponse(TypedDict, total=True):
    """
    Wire fields for OutputRootRuntimeStatusResponse; native validation enforces semantic constraints.
    OutputRootRuntimeStatusResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: 'OutputRuntimeSnapshot'
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimeCallSubmitResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimeCallSubmitResponse; native validation enforces semantic constraints.
    OutputRuntimeCallSubmitResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: 'OutputOperationReceipt'
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimeCapabilitiesListResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimeCapabilitiesListResponse; native validation enforces semantic constraints.
    OutputRuntimeCapabilitiesListResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: List['OutputCapabilityDescriptor']
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimeCapabilitiesRegisterResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimeCapabilitiesRegisterResponse; native validation enforces semantic constraints.
    OutputRuntimeCapabilitiesRegisterResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: 'OutputRegistrationReceipt'
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimeCapabilityForgetResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimeCapabilityForgetResponse; native validation enforces semantic constraints.
    OutputRuntimeCapabilityForgetResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: None
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimeCapabilityStatusResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimeCapabilityStatusResponse; native validation enforces semantic constraints.
    OutputRuntimeCapabilityStatusResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: 'OutputCapabilityRegistrationStatus'
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimeCapabilityUnregisterResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimeCapabilityUnregisterResponse; native validation enforces semantic constraints.
    OutputRuntimeCapabilityUnregisterResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: None
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimeHostRequestCompleteResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimeHostRequestCompleteResponse; native validation enforces semantic constraints.
    OutputRuntimeHostRequestCompleteResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: None
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimeHostRequestStatusResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimeHostRequestStatusResponse; native validation enforces semantic constraints.
    OutputRuntimeHostRequestStatusResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: 'OutputHostRequestStatus'
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimeHostRequestsTakeResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimeHostRequestsTakeResponse; native validation enforces semantic constraints.
    OutputRuntimeHostRequestsTakeResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: List['OutputHostRequest']
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimeOperationCancelResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimeOperationCancelResponse; native validation enforces semantic constraints.
    OutputRuntimeOperationCancelResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: bool
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimeOperationForgetResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimeOperationForgetResponse; native validation enforces semantic constraints.
    OutputRuntimeOperationForgetResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: None
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimeOperationStatusResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimeOperationStatusResponse; native validation enforces semantic constraints.
    OutputRuntimeOperationStatusResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: 'OutputOperationSnapshot'
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimeOperationWaitResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimeOperationWaitResponse; native validation enforces semantic constraints.
    OutputRuntimeOperationWaitResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: 'OutputOperationSnapshot'
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimePluginCloseResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimePluginCloseResponse; native validation enforces semantic constraints.
    OutputRuntimePluginCloseResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: None
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimePluginForgetResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimePluginForgetResponse; native validation enforces semantic constraints.
    OutputRuntimePluginForgetResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: None
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimePluginRegisterResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimePluginRegisterResponse; native validation enforces semantic constraints.
    OutputRuntimePluginRegisterResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: None
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimePluginStatusResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimePluginStatusResponse; native validation enforces semantic constraints.
    OutputRuntimePluginStatusResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: 'OutputEmbeddedPluginSnapshot'
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimePoolCloseResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimePoolCloseResponse; native validation enforces semantic constraints.
    OutputRuntimePoolCloseResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: None
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimePoolForgetResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimePoolForgetResponse; native validation enforces semantic constraints.
    OutputRuntimePoolForgetResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: None
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimePoolRegisterResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimePoolRegisterResponse; native validation enforces semantic constraints.
    OutputRuntimePoolRegisterResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: 'OutputPoolReceipt'
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimePoolRevokePermissionResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimePoolRevokePermissionResponse; native validation enforces semantic constraints.
    OutputRuntimePoolRevokePermissionResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: bool
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimePoolStatusResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimePoolStatusResponse; native validation enforces semantic constraints.
    OutputRuntimePoolStatusResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: 'OutputPoolUsage'
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimeSessionCloseResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimeSessionCloseResponse; native validation enforces semantic constraints.
    OutputRuntimeSessionCloseResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: None
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimeSessionForgetResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimeSessionForgetResponse; native validation enforces semantic constraints.
    OutputRuntimeSessionForgetResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: None
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimeSessionOpenResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimeSessionOpenResponse; native validation enforces semantic constraints.
    OutputRuntimeSessionOpenResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: 'OutputSessionReceipt'
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimeSessionStatusResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimeSessionStatusResponse; native validation enforces semantic constraints.
    OutputRuntimeSessionStatusResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: 'OutputEmbeddedSessionSnapshot'
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


class OutputRuntimeSessionSubmitResponse(TypedDict, total=True):
    """
    Wire fields for OutputRuntimeSessionSubmitResponse; native validation enforces semantic constraints.
    OutputRuntimeSessionSubmitResponse 的线字段；原生校验负责语义约束。
    Borrowed success envelope avoids cloning application output during native response publication.
    借用成功信封，避免原生响应发布期间克隆应用输出。
    """
    # Single protocol version authority.
    # 唯一协议版本权威。
    # Exact wire member protocol_version; required independently of nullability.
    # 精确线成员 protocol_version；必需与是否可为空值相互独立。
    protocol_version: int
    # Borrowed result whose owner lives through serialization.
    # 借用结果，其所有者跨序列化存活。
    # Exact wire member result; required independently of nullability.
    # 精确线成员 result；必需与是否可为空值相互独立。
    result: 'OutputOperationReceipt'
    # Exact success discriminator.
    # 精确成功判别。
    # Exact wire member status; required independently of nullability.
    # 精确线成员 status；必需与是否可为空值相互独立。
    status: 'OutputSuccessStatus'


# Public generated type names; metadata remains directly importable by name.
# 公开生成类型名；元数据仍可按名称直接导入。
__all__ = ['JsonValue', 'EmbeddedNativeStatus', 'InputCapabilityDescriptor', 'InputCapabilityEffects', 'InputCapabilityExecution', 'InputCapabilityIdempotency', 'InputCapabilityScope', 'InputCommand', 'InputCommandDescribe', 'InputCommandRuntime', 'InputCommandRuntimeClose', 'InputCommandRuntimeFree', 'InputCommandRuntimeInitialize', 'InputCommandRuntimeReserve', 'InputCommandRuntimeStatus', 'InputEffectState', 'InputEmbeddedCall', 'InputEmbeddedError', 'InputEmbeddedErrorCode', 'InputEmbeddedPluginConfig', 'InputEmbeddedRuntimeConfig', 'InputExecutionBackend', 'InputHostCompletion', 'InputHostCompletionShape89b6ef9bf484', 'InputHostCompletionShapeb9f2ee658336', 'InputInstanceReuse', 'InputLuaEngineOptions', 'InputLuaInvocationContext', 'InputLuaRuntimeCapabilityOptions', 'InputLuaRuntimeDatabaseCallbackMode', 'InputLuaRuntimeDatabaseProviderMode', 'InputLuaRuntimeHostOptions', 'InputLuaRuntimeManagedRuntimeConfig', 'InputLuaRuntimeRunLuaPoolConfig', 'InputLuaRuntimeSpaceControllerOptions', 'InputLuaRuntimeSpaceControllerProcessMode', 'InputLuaVmPoolConfig', 'InputModuleDefinition', 'InputModuleExport', 'InputPluginPoolConfig', 'InputPoolKind', 'InputRequest', 'InputRuntimeClientInfo', 'InputRuntimeCommand', 'InputRuntimeCommandCallSubmit', 'InputRuntimeCommandCapabilitiesList', 'InputRuntimeCommandCapabilitiesRegister', 'InputRuntimeCommandCapabilityForget', 'InputRuntimeCommandCapabilityStatus', 'InputRuntimeCommandCapabilityUnregister', 'InputRuntimeCommandHostRequestComplete', 'InputRuntimeCommandHostRequestStatus', 'InputRuntimeCommandHostRequestsTake', 'InputRuntimeCommandOperationCancel', 'InputRuntimeCommandOperationForget', 'InputRuntimeCommandOperationStatus', 'InputRuntimeCommandOperationWait', 'InputRuntimeCommandPluginClose', 'InputRuntimeCommandPluginForget', 'InputRuntimeCommandPluginRegister', 'InputRuntimeCommandPluginStatus', 'InputRuntimeCommandPoolClose', 'InputRuntimeCommandPoolForget', 'InputRuntimeCommandPoolRegister', 'InputRuntimeCommandPoolRevokePermission', 'InputRuntimeCommandPoolStatus', 'InputRuntimeCommandSessionClose', 'InputRuntimeCommandSessionForget', 'InputRuntimeCommandSessionOpen', 'InputRuntimeCommandSessionStatus', 'InputRuntimeCommandSessionSubmit', 'InputRuntimeRequestContext', 'InputToolCacheConfig', 'OutputCapabilityCaller', 'OutputCapabilityDescriptor', 'OutputCapabilityEffects', 'OutputCapabilityExecution', 'OutputCapabilityIdempotency', 'OutputCapabilityRegistrationStatus', 'OutputCapabilityScope', 'OutputCoreDescription', 'OutputEffectState', 'OutputEmbeddedBuildIdentity', 'OutputEmbeddedError', 'OutputEmbeddedErrorCode', 'OutputEmbeddedPluginConfig', 'OutputEmbeddedPluginSnapshot', 'OutputEmbeddedRuntimeUsage', 'OutputEmbeddedSessionPhase', 'OutputEmbeddedSessionSnapshot', 'OutputErrorResponse', 'OutputErrorStatus', 'OutputExecutionBackend', 'OutputHostEffectPhase', 'OutputHostEffectRecord', 'OutputHostRequest', 'OutputHostRequestPhase', 'OutputHostRequestStatus', 'OutputInitializationPhase', 'OutputOperationPhase', 'OutputOperationReceipt', 'OutputOperationSnapshot', 'OutputPoolReceipt', 'OutputPoolUsage', 'OutputRegistrationReceipt', 'OutputRootDescribeResponse', 'OutputRootRuntimeCloseResponse', 'OutputRootRuntimeFreeResponse', 'OutputRootRuntimeInitializeResponse', 'OutputRootRuntimeReserveResponse', 'OutputRootRuntimeStatusResponse', 'OutputRuntimeCallSubmitResponse', 'OutputRuntimeCapabilitiesListResponse', 'OutputRuntimeCapabilitiesRegisterResponse', 'OutputRuntimeCapabilityForgetResponse', 'OutputRuntimeCapabilityStatusResponse', 'OutputRuntimeCapabilityUnregisterResponse', 'OutputRuntimeHostRequestCompleteResponse', 'OutputRuntimeHostRequestStatusResponse', 'OutputRuntimeHostRequestsTakeResponse', 'OutputRuntimeOperationCancelResponse', 'OutputRuntimeOperationForgetResponse', 'OutputRuntimeOperationStatusResponse', 'OutputRuntimeOperationWaitResponse', 'OutputRuntimePluginCloseResponse', 'OutputRuntimePluginForgetResponse', 'OutputRuntimePluginRegisterResponse', 'OutputRuntimePluginStatusResponse', 'OutputRuntimePoolCloseResponse', 'OutputRuntimePoolForgetResponse', 'OutputRuntimePoolRegisterResponse', 'OutputRuntimePoolRevokePermissionResponse', 'OutputRuntimePoolStatusResponse', 'OutputRuntimeReceipt', 'OutputRuntimeSessionCloseResponse', 'OutputRuntimeSessionForgetResponse', 'OutputRuntimeSessionOpenResponse', 'OutputRuntimeSessionStatusResponse', 'OutputRuntimeSessionSubmitResponse', 'OutputRuntimeSnapshot', 'OutputSessionReceipt', 'OutputSuccessStatus', 'OutputTransportConfig', 'OutputTransportDescription']
