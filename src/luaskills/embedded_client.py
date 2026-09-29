"""
Typed embedded handles over retained command receipts; native state remains authoritative.
基于保留命令回执的嵌入式类型句柄；原生状态始终保持权威。
"""

from __future__ import annotations

import asyncio
import math
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar

from . import embedded_contract as wire
from .embedded_driver import EmbeddedCommand, EmbeddedCommandDriver
from .embedded_transport import EmbeddedResultReleaseError


# The type describes a projection of a delivered response, never a second native operation.
# 此类型描述已交付响应的投影，绝不表示第二次原生操作。
T = TypeVar("T")
# Match OperationPhase::is_terminal in the core; cleaning and cancellation intent are not terminal.
# 对应核心 OperationPhase::is_terminal；清理和取消意图均不属于终态。
_TERMINAL_PHASES: frozenset[wire.OutputOperationPhase] = frozenset({"succeeded", "failed", "cancelled"})
# One SDK polling default; callers may select a positive finite interval explicitly.
# 唯一 SDK 轮询默认值；调用方可显式选择有限正间隔。
_POLL_INTERVAL = 0.01


class EmbeddedPending(Generic[T]):
    """
    A typed view of an owned command receipt, supporting both synchronous and asynchronous observation.
    拥有型命令回执的类型视图，同时支持同步及异步观察。
    Keep the receipt until explicitly forgotten; projection never replays the original command.
    在显式遗忘前保留回执；投影绝不重放原始命令。
    """

    def __init__(self, receipt: EmbeddedCommand, project: Callable[[Any], T]) -> None:
        """
        Bind receipt and its pure result projection; return without waiting or issuing native work.
        绑定 receipt 及其纯结果投影 project；返回时不等待，也不发起原生工作。
        """
        # The underlying driver strongly retains the authoritative delivery evidence.
        # 底层驱动器强引用保留权威交付证据。
        self._receipt = receipt
        # This local projection creates handles only after observing actual successful delivery.
        # 此本地投影仅在观察到实际成功交付后创建句柄。
        self._project = project

    @property
    def receipt(self) -> EmbeddedCommand:
        """
        Return the exact receipt for diagnostics and recovery after observer cancellation.
        返回精确回执，用于诊断及观察者取消后的恢复。
        """
        return self._receipt

    def result(self, timeout: float | None = None) -> T:
        """
        Observe for timeout seconds and return the typed delivery; timeout never cancels native work.
        在 timeout 秒内观察并返回类型化交付；超时绝不取消原生工作。
        """
        return self._project(self._receipt.result(timeout))

    async def result_async(self) -> T:
        """
        Return the typed delivery without blocking the caller loop; cancellation preserves the receipt.
        不阻塞调用方循环地返回类型化交付；取消保留原回执。
        """
        return self._project(await self._receipt.result_async())

    def delivered_result(self) -> T:
        """
        Recover a completed copied response after result-buffer release failure; perform no retry or free.
        在结果缓冲释放失败后恢复已完成的复制响应；不执行重试或释放。
        Return the same projection, or raise TimeoutError, the delivered business error, or missing evidence.
        返回相同投影，或抛出 TimeoutError、已交付业务错误或证据缺失错误。
        """
        try:
            # Zero waiting prevents recovery from silently starting a new blocking observation.
            # 零等待防止恢复悄悄开始新的阻塞观察。
            value = self._receipt.result(0)
        except EmbeddedResultReleaseError as error:
            value = error.delivered_result()
        return self._project(value)

    def forget(self) -> None:
        """
        Release only a completed SDK receipt quota; core resources and operations remain unchanged.
        仅释放已完成的 SDK 回执配额；核心资源及操作保持不变。
        """
        self._receipt.forget()


class EmbeddedClient:
    """
    Typed command facade borrowing an explicit driver; it does not create or close transports or pumps.
    借用显式驱动器的类型化命令入口；不创建或关闭传输及事件泵。
    """

    def __init__(self, driver: EmbeddedCommandDriver) -> None:
        """
        Bind driver for every child handle; construction submits no native request.
        为全部子句柄绑定 driver；构造不提交原生请求。
        """
        # All handles share this driver and therefore its bounded admission and native library lifetime.
        # 全部句柄共享此驱动器及其有界入场和原生库寿命。
        self._driver = driver

    def _submit(self, command: wire.InputCommand, project: Callable[[Any], T]) -> EmbeddedPending[T]:
        """
        Submit exact generated command fields and return a retained typed projection using project.
        提交精确生成的 command 字段，并返回使用 project 的保留类型投影。
        """
        return EmbeddedPending(self._driver.submit(command), project)

    def describe(self) -> EmbeddedPending[wire.OutputTransportDescription]:
        """
        Return a pending native protocol and command description; do not infer library compatibility.
        返回待完成的原生协议和命令描述；不推断动态库兼容性。
        """
        return self._submit({"type": "describe"}, lambda value: value)

    def reserve(self) -> EmbeddedPending[EmbeddedRuntime]:
        """
        Reserve one native runtime slot and return its recoverable handle receipt, without initialization.
        预留一个原生运行时槽并返回可恢复的句柄回执，不执行初始化。
        """
        return self._submit({"type": "runtime_reserve"}, lambda value: self.runtime(value["runtime_id"]))

    def runtime(self, runtime_id: str) -> EmbeddedRuntime:
        """
        Bind a known exact runtime_id without probing; subsequent native commands validate its ownership.
        绑定已知精确 runtime_id，不进行探测；后续原生命令校验其归属。
        """
        return EmbeddedRuntime(self, runtime_id)


class EmbeddedRuntime:
    """
    Exact runtime-slot handle; initialization, closure request, actual closure and release remain distinct.
    精确运行时槽句柄；初始化、关闭请求、实际关闭及释放保持独立。
    """

    def __init__(self, client: EmbeddedClient, runtime_id: str) -> None:
        """
        Bind client and known runtime_id; return a handle without claiming the runtime is initialized.
        绑定 client 和已知 runtime_id；返回句柄，不声称运行时已经初始化。
        """
        # Retain the exact client namespace; IDs from another transport are never substituted.
        # 保留精确客户端命名空间；绝不替换来自其他传输的身份。
        self._client = client
        # Immutable through the public API; the core remains the authority for existence and state.
        # 通过公共接口不可变；存在性和状态仍以核心为权威。
        self._runtime_id = runtime_id

    @property
    def runtime_id(self) -> str:
        """
        Return the exact native FFI slot identity, distinct from the core's internal runtime namespace.
        返回精确原生 FFI 槽身份，与核心内部运行时命名空间不同。
        """
        return self._runtime_id

    def _submit(self, operation: wire.InputRuntimeCommand, project: Callable[[Any], T]) -> EmbeddedPending[T]:
        """
        Bind operation to this runtime and return a retained typed result using project.
        将 operation 绑定到此运行时，并返回使用 project 的保留类型结果。
        """
        return self._client._submit({"type": "runtime", "runtime_id": self.runtime_id, "operation": operation}, project)

    def initialize(self, engine_options: wire.InputLuaEngineOptions, runtime_config: wire.InputEmbeddedRuntimeConfig, persistence: wire.InputRuntimePersistenceConfig | None = None) -> EmbeddedPending[wire.OutputRuntimeReceipt]:
        """
        Start the one-shot native construction using explicit engine_options and runtime_config budgets.
        使用显式 engine_options 和 runtime_config 预算开始原生单次构造。
        Optional persistence selects an explicit host path and storage budgets; None selects memory-only mode.
        可选 persistence 选择显式宿主路径与存储预算；None 选择纯内存模式。
        Return an attempt receipt, not a success claim; always query status for ready, failed or faulted.
        返回尝试回执，不代表初始化成功；始终查询状态区分 ready、failed 或 faulted。
        After interruption retain this identity and query status instead of reinitializing.
        中断后保留此身份并查询状态，不重新初始化。
        """
        return self._client._submit({"type": "runtime_initialize", "runtime_id": self.runtime_id,
                                    "engine_options": engine_options, "runtime_config": runtime_config, "persistence": persistence}, lambda value: value)

    def status(self) -> EmbeddedPending[wire.OutputRuntimeSnapshot]:
        """
        Return actual initialization, closure and resource evidence from the native slot.
        返回来自原生槽的实际初始化、关闭及资源证据。
        """
        return self._client._submit({"type": "runtime_status", "runtime_id": self.runtime_id}, lambda value: value)

    def storage_status(self) -> EmbeddedPending[wire.OutputOperationJournalWorkerStatus]:
        """
        Return actual writer ownership on the control lane; memory-only runtimes report unsupported.
        在控制通道返回实际写入者所有权；纯内存运行时报告不支持。
        """
        return self._submit({"type": "storage_status"}, lambda value: value)

    def recover_storage(self) -> EmbeddedPending[bool]:
        """
        Reopen and validate the same failed database on the work lane; return whether recovery was needed.
        在工作通道重新打开并校验同一故障数据库；返回是否需要恢复。
        This never retries a checkpoint or executes a plugin; inspect operation failure and request retry separately.
        此操作绝不重试检查点或执行插件；需另行检查操作故障并请求重试。
        """
        return self._submit({"type": "storage_recover"}, lambda value: value)

    def recover_storage_worker(self) -> EmbeddedPending[bool]:
        """
        Rebuild one failed, actually exited writer on the work lane; return False for a healthy running writer.
        在工作通道重建一个已失败且实际退出的写入者；健康运行写入者返回 False。
        Old receipts and budgets remain owned; storage recovery and original checkpoint retry are separate actions.
        旧回执及预算继续被拥有；存储恢复及原检查点重试是独立操作。
        Explicit writer closure and unproven or poisoned ownership remain errors rather than implicit reopening.
        显式写入者关闭及未证实或中毒所有权保持错误，不能隐式重新打开。
        """
        return self._submit({"type": "storage_worker_recover"}, lambda value: value)

    def history_get(self, history_runtime_id: str, operation_id: str) -> EmbeddedPending[wire.OutputJournalOperation | None]:
        """
        Read one original history_runtime_id/operation_id on the work lane; absence is not proof of no execution.
        在工作通道读取一个原始 history_runtime_id/operation_id；不存在不证明从未执行。
        """
        return self._submit({"type": "history_get", "history_runtime_id": history_runtime_id, "operation_id": operation_id}, lambda value: value)

    def history_next(self, after: wire.InputHistoryCursor | None = None) -> EmbeddedPending[wire.OutputJournalOperation | None]:
        """
        Read the row after the exact original cursor, or the first row for None; return None at enumeration end.
        读取精确原始游标之后的记录，None 表示首条；枚举结束返回 None。
        Concurrent changes are not a multi-call snapshot and historical identities never become live handles.
        并发变更不构成跨调用快照，历史身份绝不成为活动句柄。
        """
        return self._submit({"type": "history_next", "after": after}, lambda value: value)

    def history_reconcile(self, history_runtime_id: str, operation_id: str, expected_revision: int,
                          resolution: wire.InputOperationReconciliation) -> EmbeddedPending[int]:
        """
        Attach final trusted-host resolution to exact original history; return its durable successor revision.
        为精确原历史附加最终可信宿主 resolution；返回其持久后继修订。
        The host must authorize the resolver, verify every effect and prove all original owners stopped.
        宿主必须授权对账者、核验全部副作用并证明所有原所有者已停止。
        Retain expected_revision and all resolution fields for exact retries; live retained operations are rejected.
        精确重试须保留 expected_revision 及全部 resolution 字段；仍保留的活动操作被拒绝。
        """
        return self._submit({"type": "history_reconcile", "history_runtime_id": history_runtime_id, "operation_id": operation_id, "expected_revision": expected_revision, "resolution": resolution}, lambda value: value)

    def history_forget(self, history_runtime_id: str, operation_id: str, expected_revision: int) -> EmbeddedPending[None]:
        """
        Remove fully resolved history at expected_revision; first forget any retained live operation.
        按 expected_revision 移除已完全解决的历史；需先遗忘仍保留的活动操作。
        Return the native deletion receipt; stale revisions and unresolved effects retain the original record.
        返回原生删除回执；过期修订及未决副作用保留原始记录。
        """
        return self._submit({"type": "history_forget", "history_runtime_id": history_runtime_id, "operation_id": operation_id, "expected_revision": expected_revision}, lambda value: value)

    def request_close(self) -> EmbeddedPending[wire.OutputRuntimeReceipt]:
        """
        Permanently stop native admission; return acknowledgement, not proof that workers have exited.
        永久停止原生入场；返回确认，不代表工作线程已经退出。
        """
        return self._client._submit({"type": "runtime_close", "runtime_id": self.runtime_id}, lambda value: value)

    def free(self) -> EmbeddedPending[wire.OutputRuntimeReceipt]:
        """
        Request removal of this exact slot; the core rejects premature release while resources are live.
        请求移除此精确槽；资源仍存活时由核心拒绝过早释放。
        """
        self._client._driver._transport._check_unmanaged_runtime(self.runtime_id)
        return self._client._submit({"type": "runtime_free", "runtime_id": self.runtime_id}, lambda value: value)

    def register_plugin(self, plugin_id: str, config: wire.InputEmbeddedPluginConfig) -> EmbeddedPending[EmbeddedPlugin]:
        """
        Register plugin_id with explicit aggregate config budgets and return its acknowledged handle.
        使用显式聚合 config 预算注册 plugin_id，并返回已确认句柄。
        """
        return self._submit({"type": "plugin_register", "plugin_id": plugin_id, "config": config}, lambda _: self.plugin(plugin_id))

    def register_capacity(self, plugin_id: str, config: wire.InputEmbeddedCapacityConfig) -> EmbeddedPending[EmbeddedCapacity]:
        """
        Register complete config for exact plugin_id and return its acknowledged capacity handle.
        为精确 plugin_id 注册完整 config，并返回已确认容量句柄。
        Receipt observation never repeats registration or changes the immutable capacity owner.
        回执观测绝不重复注册，也不改变不可变容量所有者。
        """
        return self._submit({"type": "capacity_register", "plugin_id": plugin_id, "config": config},
                            lambda value: self.capacity(value["capacity_id"]))

    def capacity(self, capacity_id: str) -> EmbeddedCapacity:
        """
        Bind exact capacity_id to this runtime without probing or inferring ownership; return its handle.
        将精确 capacity_id 绑定到此运行时，不探测或推断归属；返回其句柄。
        """
        return EmbeddedCapacity(self, capacity_id)

    def register_pool(self, definition: wire.InputModuleDefinition, policy: wire.InputPluginPoolConfig,
                      permissions: list[str], execution_revision: str) -> EmbeddedPending[EmbeddedPool]:
        """
        Register immutable definition with explicit policy, granted permissions and execution_revision.
        使用显式 policy、授权 permissions 和 execution_revision 注册不可变 definition。
        Return the actual pool handle only after the native registration acknowledgement.
        仅在原生注册确认后返回实际池句柄。
        """
        return self._submit({"type": "pool_register", "definition": definition, "policy": policy,
                             "permissions": permissions, "execution_revision": execution_revision},
                            lambda value: self.pool(value["pool_id"]))

    def plugin(self, plugin_id: str) -> EmbeddedPlugin:
        """
        Bind known plugin_id to this runtime; native status remains the authority for its existence.
        将已知 plugin_id 绑定到此运行时；存在性仍以原生状态为权威。
        """
        return EmbeddedPlugin(self, plugin_id)

    def pool(self, pool_id: str) -> EmbeddedPool:
        """
        Bind known pool_id to this runtime without guessing its plugin, generation or policy.
        将已知 pool_id 绑定到此运行时，不猜测其插件、代次或策略。
        """
        return EmbeddedPool(self, pool_id)

    def session(self, session_id: str) -> EmbeddedSession:
        """
        Bind known session_id to this runtime without assuming initialization or readiness.
        将已知 session_id 绑定到此运行时，不假定初始化或就绪状态。
        """
        return EmbeddedSession(self, session_id)

    def list_operations(self, pool_id: str | None, after_operation_id: str | None, limit: int) -> EmbeddedPending[wire.OutputOperationPage]:
        """
        Discover up to limit retained operations for optional pool_id after a retained after_operation_id cursor.
        在保留的 after_operation_id 游标后，为可选 pool_id 发现至多 limit 个保留操作。
        Return a typed publication-ordered page; restart after forgetting the cursor and query outcomes by exact ID.
        返回按发布顺序排列的类型化页面；遗忘游标后重新开始，并按精确身份查询结果。
        """
        return self._submit({"type": "operation_list", "pool_id": pool_id,
                             "after_operation_id": after_operation_id, "limit": limit}, lambda value: value)

    def operation(self, operation_id: str) -> EmbeddedOperation:
        """
        Bind known operation_id to this runtime so cancellation and terminal evidence remain queryable.
        将已知 operation_id 绑定到此运行时，使取消及终态证据保持可查询。
        """
        return EmbeddedOperation(self, operation_id)


class EmbeddedPlugin:
    """
    A plugin registration handle whose aggregate budgets cover all generations in one runtime.
    插件注册句柄，其聚合预算覆盖一个运行时中的全部代次。
    """

    def __init__(self, runtime: EmbeddedRuntime, plugin_id: str) -> None:
        """
        Bind exact runtime and plugin_id; return without creating or validating native registration.
        绑定精确 runtime 和 plugin_id；返回时不创建或校验原生注册。
        """
        # Retain the runtime namespace that owns this registration.
        # 保留拥有此注册的运行时命名空间。
        self._runtime = runtime
        # Known plugin identity; all native commands use exactly this value.
        # 已知插件身份；全部原生命令精确使用此值。
        self._plugin_id = plugin_id

    @property
    def plugin_id(self) -> str:
        """
        Return the exact plugin identity without exposing a mutable routing field.
        返回精确插件身份，不暴露可修改的路由字段。
        """
        return self._plugin_id

    def status(self) -> EmbeddedPending[wire.OutputEmbeddedPluginSnapshot]:
        """
        Return live native aggregate usage across this plugin's pools, sessions and operations.
        返回此插件全部池、会话及操作的实时原生聚合用量。
        """
        return self._runtime._submit({"type": "plugin_status", "plugin_id": self.plugin_id}, lambda value: value)

    def request_close(self) -> EmbeddedPending[None]:
        """
        Close plugin admission and request drainage; return acknowledgement rather than release proof.
        关闭插件入场并请求排空；返回确认，不代表释放证据。
        """
        return self._runtime._submit({"type": "plugin_close", "plugin_id": self.plugin_id}, lambda value: value)

    def forget(self) -> EmbeddedPending[None]:
        """
        Request removal of a drained native plugin record; native busy errors retain its ownership.
        请求移除已排空的原生插件记录；原生忙碌错误保留其所有权。
        """
        return self._runtime._submit({"type": "plugin_forget", "plugin_id": self.plugin_id}, lambda value: value)


class EmbeddedCapacity:
    """
    Immutable capacity identity shared by isolated member modules within one native plugin.
    一个原生插件内由隔离成员模块共享的不可变容量身份。
    Closure and forgetting remain distinct; the core owns physical and scheduling guarantees.
    关闭与遗忘保持区分；核心拥有物理及调度保证。
    """

    def __init__(self, runtime: EmbeddedRuntime, capacity_id: str) -> None:
        """
        Bind runtime and exact capacity_id; return without registering or probing native state.
        绑定 runtime 及精确 capacity_id；返回时不注册或探测原生状态。
        """
        # Every member and control request remains in this original runtime namespace.
        # 每个成员及控制请求保持在此原始运行时命名空间内。
        self._runtime = runtime
        # The identity never switches to another capacity on failure or plugin update.
        # 失败或插件更新时，身份绝不切换到另一容量。
        self._capacity_id = capacity_id

    @property
    def capacity_id(self) -> str:
        """
        Return the original native capacity identity, independent of command receipt identity.
        返回原生容量身份，独立于命令回执身份。
        """
        return self._capacity_id

    def status(self) -> EmbeddedPending[wire.OutputEmbeddedCapacitySnapshot]:
        """
        Return live native physical, queued and cleanup ownership on the reserved control lane.
        在预留控制通道返回实时原生物理、排队及清理归属。
        """
        return self._runtime._submit({"type": "capacity_status", "capacity_id": self.capacity_id}, lambda value: value)

    def policy(self) -> EmbeddedPending[wire.OutputEmbeddedCapacityPolicySnapshot]:
        """
        Return the atomic native revision, current policy and convergence on the reserved control lane.
        在预留控制通道返回原子原生修订、当前策略及收敛状态。
        """
        return self._runtime._submit({"type": "capacity_policy", "capacity_id": self.capacity_id}, lambda value: value)

    def revise(self, expected_revision: str, config: wire.InputEmbeddedCapacityConfig) -> EmbeddedPending[str]:
        """
        Compare expected_revision and replace complete config; return the retained committed-token receipt.
        比较 expected_revision 并替换完整 config；返回保留的已提交令牌回执。
        Native conflicts, execution pressure and closure remain explicit; never refresh or retry the token automatically.
        原生冲突、执行压力及关闭保持显式；绝不自动刷新或重试令牌。
        """
        return self._runtime._submit({"type": "capacity_revise", "capacity_id": self.capacity_id,
                                     "expected_revision": expected_revision, "config": config}, lambda value: value)

    def request_close(self) -> EmbeddedPending[None]:
        """
        Permanently close capacity admission and request member drainage; return acknowledgement only.
        永久关闭容量入场并请求成员排空；仅返回确认。
        """
        return self._runtime._submit({"type": "capacity_close", "capacity_id": self.capacity_id}, lambda value: value)

    def forget(self) -> EmbeddedPending[None]:
        """
        Request exact capacity removal; return acknowledgement only after the core proves release eligible.
        请求精确容量移除；仅在核心证明符合释放条件后返回确认。
        Members must be forgotten first; a busy response never switches or recreates the capacity.
        必须先遗忘成员；忙碌响应绝不切换或重建容量。
        """
        return self._runtime._submit({"type": "capacity_forget", "capacity_id": self.capacity_id}, lambda value: value)

    def register_pool(self, definition: wire.InputModuleDefinition, policy: wire.InputPluginPoolConfig,
                      permissions: list[str], execution_revision: str) -> EmbeddedPending[EmbeddedPool]:
        """
        Register definition with policy, permissions and execution_revision in this exact capacity.
        使用 policy、permissions 及 execution_revision 在此精确容量中注册 definition。
        Return the acknowledged member handle; native validation rejects foreign plugins and conflicting budgets.
        返回已确认成员句柄；原生校验拒绝外来插件及冲突预算。
        """
        return self._runtime._submit({"type": "pool_register", "capacity_id": self.capacity_id,
                                     "definition": definition, "policy": policy, "permissions": permissions,
                                     "execution_revision": execution_revision},
                                    lambda value: self._runtime.pool(value["pool_id"]))


class EmbeddedPool:
    """
    One immutable native execution-domain handle, independent of later plugin generation updates.
    一个不可变原生执行域句柄，独立于后续插件代次更新。
    """

    def __init__(self, runtime: EmbeddedRuntime, pool_id: str) -> None:
        """
        Bind exact runtime and pool_id; construction performs no registration or availability probe.
        绑定精确 runtime 和 pool_id；构造不注册，也不探测可用性。
        """
        # Preserve the exact runtime ownership namespace.
        # 保留精确运行时所有权命名空间。
        self._runtime = runtime
        # This identity never switches to a newer generation by name.
        # 此身份绝不按名称切换到较新代次。
        self._pool_id = pool_id

    @property
    def pool_id(self) -> str:
        """
        Return the native pool identity used by every call and lifecycle command.
        返回每个调用及生命周期命令使用的原生池身份。
        """
        return self._pool_id

    def status(self) -> EmbeddedPending[wire.OutputPoolUsage]:
        """
        Return live native VM accounting, including creating and retiring residents.
        返回实时原生 VM 计费，包含创建中及退役中的常驻实例。
        """
        return self._runtime._submit({"type": "pool_status", "pool_id": self.pool_id}, lambda value: value)

    def request_close(self) -> EmbeddedPending[None]:
        """
        Request permanent pool drainage; the acknowledgement does not imply actual VM destruction.
        请求永久排空池；确认不代表 VM 已实际销毁。
        """
        return self._runtime._submit({"type": "pool_close", "pool_id": self.pool_id}, lambda value: value)

    def forget(self) -> EmbeddedPending[None]:
        """
        Remove this pool record only when native lifecycle checks permit; return the retained receipt.
        仅在原生生命周期校验允许时移除此池记录；返回保留回执。
        """
        return self._runtime._submit({"type": "pool_forget", "pool_id": self.pool_id}, lambda value: value)

    def revoke_permission(self, permission: str) -> EmbeddedPending[bool]:
        """
        Revoke exact permission from this pool and return whether the native grant changed.
        从此池撤销精确 permission，并返回原生授权是否发生变化。
        """
        return self._runtime._submit({"type": "pool_revoke_permission", "pool_id": self.pool_id,
                                      "permission": permission}, lambda value: value)

    def submit(self, export: str, arguments: wire.JsonValue, context: wire.InputLuaInvocationContext,
               timeout_ms: int) -> EmbeddedPending[EmbeddedOperation]:
        """
        Submit export and arguments with explicit trusted context and the native execution timeout_ms.
        使用显式可信 context 和原生执行 timeout_ms 提交 export 及 arguments。
        Return an operation admission receipt; observing it does not wait for Lua completion.
        返回操作入场回执；观察该回执不等待 Lua 执行完成。
        """
        return self._runtime._submit({"type": "call_submit", "timeout_ms": timeout_ms, "call": {
            "pool_id": self.pool_id, "export": export, "arguments": arguments, "context": context}},
            lambda value: self._runtime.operation(value["operation_id"]))

    def prewarm_instance(self, context: wire.InputLuaInvocationContext,
                         timeout_ms: int) -> EmbeddedPending[EmbeddedOperation]:
        """
        Initialize one additional VM in this exact reusable pool without invoking a business export.
        在此精确可复用池初始化一个额外 VM，不调用业务导出。
        context supplies trusted host metadata; timeout_ms is the original native execution budget.
        context 提供可信宿主元数据；timeout_ms 为原始原生执行预算。
        Return a retained admission receipt; its operation reports instance_id after successful initialization.
        返回保留入场回执；所得操作在初始化成功后报告 instance_id。
        """
        return self._runtime._submit({"type": "instance_prewarm", "timeout_ms": timeout_ms, "request": {
            "pool_id": self.pool_id, "context": context}},
            lambda value: self._runtime.operation(value["operation_id"]))

    def open_session(self, timeout_ms: int) -> EmbeddedPending[EmbeddedSessionOpen]:
        """
        Reserve a fixed session with initialization timeout_ms; return both independently queryable handles.
        以初始化 timeout_ms 预留固定会话；返回两个可独立查询的句柄。
        """
        return self._runtime._submit({"type": "session_open", "pool_id": self.pool_id, "timeout_ms": timeout_ms},
            lambda value: EmbeddedSessionOpen(self._runtime.session(value["session_id"]),
                                              self._runtime.operation(value["operation_id"])))


@dataclass(frozen=True)
class EmbeddedSessionOpen:
    """
    Exact paired identities delivered by session_open; admission alone does not mean initialization succeeded.
    session_open 交付的精确配对身份；入场本身不代表初始化成功。
    """

    # The fixed-session identity remains queryable even when initialization fails.
    # 即使初始化失败，固定会话身份仍可查询。
    session: EmbeddedSession
    # The original initialization operation retains success, failure and effect evidence.
    # 原始初始化操作保留成功、失败及副作用证据。
    initialization: EmbeddedOperation


class EmbeddedSession:
    """
    Exact fixed-session handle; every call remains bound to its original VM and runtime generation.
    精确固定会话句柄；每次调用始终绑定其原始 VM 及运行时代次。
    """

    def __init__(self, runtime: EmbeddedRuntime, session_id: str) -> None:
        """
        Bind exact runtime and session_id without inferring readiness or replaying initialization.
        绑定精确 runtime 和 session_id，不推断就绪状态，也不重放初始化。
        """
        # Retain native namespace ownership for this fixed session.
        # 为此固定会话保留原生命名空间所有权。
        self._runtime = runtime
        # Stable identity remains usable for status and closure after an operation fails.
        # 稳定身份在操作失败后仍可用于状态及关闭。
        self._session_id = session_id

    @property
    def session_id(self) -> str:
        """
        Return the exact session identity; no implicit lookup or replacement is performed.
        返回精确会话身份；不执行隐式查找或替换。
        """
        return self._session_id

    def status(self) -> EmbeddedPending[wire.OutputEmbeddedSessionSnapshot]:
        """
        Return actual initialization, active-operation and closure evidence for this native session.
        返回此原生会话的实际初始化、活动操作及关闭证据。
        """
        return self._runtime._submit({"type": "session_status", "session_id": self.session_id}, lambda value: value)

    def request_close(self) -> EmbeddedPending[None]:
        """
        Request native session closure; return acknowledgement without pretending outstanding work has stopped.
        请求原生会话关闭；返回确认，不假装未完成工作已经停止。
        """
        return self._runtime._submit({"type": "session_close", "session_id": self.session_id}, lambda value: value)

    def forget(self) -> EmbeddedPending[None]:
        """
        Remove this session record only after native release conditions are met; return the retained receipt.
        仅在满足原生释放条件后移除此会话记录；返回保留回执。
        """
        return self._runtime._submit({"type": "session_forget", "session_id": self.session_id}, lambda value: value)

    def submit(self, export: str, arguments: wire.JsonValue, context: wire.InputLuaInvocationContext,
               timeout_ms: int) -> EmbeddedPending[EmbeddedOperation]:
        """
        Admit export and arguments on this session using explicit context and native timeout_ms.
        使用显式 context 和原生 timeout_ms，在此会话接纳 export 和 arguments。
        Return the original operation receipt without substituting a shared-pool invocation.
        返回原始操作回执，不替换为公共池调用。
        """
        return self._runtime._submit({"type": "session_submit", "session_id": self.session_id,
            "export": export, "arguments": arguments, "context": context, "timeout_ms": timeout_ms},
            lambda value: self._runtime.operation(value["operation_id"]))


class EmbeddedOperation:
    """
    Query and control an admitted operation without equating observer cancellation with native completion.
    查询及控制已入场操作，不将观察者取消等同于原生完成。
    """

    def __init__(self, runtime: EmbeddedRuntime, operation_id: str) -> None:
        """
        Bind exact runtime and operation_id; return without waiting or modifying cancellation state.
        绑定精确 runtime 和 operation_id；返回时不等待，也不修改取消状态。
        """
        # Retain the native runtime namespace that owns the operation.
        # 保留拥有操作的原生运行时命名空间。
        self._runtime = runtime
        # The original operation identity is preserved across every observation attempt.
        # 每次观察尝试始终保留原始操作身份。
        self._operation_id = operation_id

    @property
    def operation_id(self) -> str:
        """
        Return the stable original identity used for status, cancellation and explicit forgetting.
        返回用于状态、取消及显式遗忘的稳定原始身份。
        """
        return self._operation_id

    def status(self) -> EmbeddedPending[wire.OutputOperationSnapshot]:
        """
        Return a pending native snapshot including complete effect evidence; errors do not imply no effects.
        返回包含完整副作用证据的待完成原生快照；错误不表示没有副作用。
        """
        return self._runtime._submit({"type": "operation_status", "operation_id": self.operation_id}, lambda value: value)

    def persistence_failure(self) -> EmbeddedPending[wire.OutputOperationPersistenceFailure | None]:
        """
        Return the original operation's retained checkpoint failure without waiting for disk or retrying it.
        返回原操作保留的检查点故障，不等待磁盘，也不重试它。
        """
        return self._runtime._submit({"type": "operation_persistence_failure", "operation_id": self.operation_id}, lambda value: value)

    def retry_checkpoint(self) -> EmbeddedPending[bool]:
        """
        Request one retained checkpoint retry, returning False if already pending; no failure reports busy.
        请求一次保留检查点重试，已在等待时返回 False；不存在故障则报告忙碌。
        This keeps the original execution and result; it never replays Lua or the host callback.
        此操作保留原执行及结果；绝不重放 Lua 或宿主回调。
        """
        return self._runtime._submit({"type": "operation_retry_checkpoint", "operation_id": self.operation_id}, lambda value: value)

    def cancel(self) -> EmbeddedPending[bool]:
        """
        Request cooperative cancellation and return whether intent changed; query actual terminal state separately.
        请求协作取消并返回意图是否变化；实际终态需要独立查询。
        """
        return self._runtime._submit({"type": "operation_cancel", "operation_id": self.operation_id}, lambda value: value)

    def forget(self) -> EmbeddedPending[None]:
        """
        Remove only a native terminal operation record; busy failures leave all evidence retained.
        仅移除原生终态操作记录；忙碌失败保留全部证据。
        """
        return self._runtime._submit({"type": "operation_forget", "operation_id": self.operation_id}, lambda value: value)

    def wait(self, timeout: float | None = None, *, poll_interval: float = _POLL_INTERVAL) -> wire.OutputOperationSnapshot:
        """
        Poll for at most timeout seconds using poll_interval; return any native terminal snapshot with effects.
        以 poll_interval 轮询，最长 timeout 秒；返回任意原生终态快照及副作用。
        Timeout raises without cancellation; an interrupted status receipt remains discoverable on the driver.
        超时抛出异常而不取消；中断的状态回执在驱动器上保持可发现。
        """
        _validate_interval(poll_interval, positive=True)
        if timeout is not None:
            _validate_interval(timeout, positive=False)
        # Use one monotonic observer deadline; the native operation keeps its original execution deadline.
        # 使用唯一单调观察截止时间；原生操作保留原始执行截止时间。
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            # Retain the active status receipt if an observation is interrupted or its delivery fails.
            # 观察中断或交付失败时保留活动状态回执。
            pending = self.status()
            snapshot = pending.result(None if deadline is None else max(0.0, deadline - time.monotonic()))
            pending.forget()
            if snapshot["phase"] in _TERMINAL_PHASES:
                return snapshot
            # Only successful read-only status receipts are consumed automatically; no mutation is retried.
            # 仅自动消费成功的只读状态回执；不重试任何变更。
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                raise TimeoutError("embedded operation observation timed out; execution remains queryable")
            time.sleep(poll_interval if remaining is None else min(poll_interval, remaining))

    async def wait_async(self, *, poll_interval: float = _POLL_INTERVAL) -> wire.OutputOperationSnapshot:
        """
        Poll with positive poll_interval without holding a native worker; return terminal snapshot with effects.
        以正 poll_interval 轮询且不占用原生等待线程；返回终态快照及副作用。
        Use asyncio.wait_for for an observer timeout; cancellation leaves the operation and receipts intact.
        使用 asyncio.wait_for 设置观察超时；取消保持操作及回执完整。
        """
        _validate_interval(poll_interval, positive=True)
        while True:
            # Each successful poll returns its SDK quota before sleeping, independently of core operation quota.
            # 每次成功轮询在休眠前归还 SDK 配额，独立于核心操作配额。
            pending = self.status()
            snapshot = await pending.result_async()
            pending.forget()
            if snapshot["phase"] in _TERMINAL_PHASES:
                return snapshot
            await asyncio.sleep(poll_interval)


def _validate_interval(value: float, *, positive: bool) -> None:
    """
    Validate value as finite platform-safe seconds; positive selects strict positivity instead of allowing zero.
    将 value 校验为有限且平台安全的秒数；positive 选择严格正数，而不是允许零值。
    Return normally only before any polling command has been submitted; reject booleans and overflow.
    仅在尚未提交任何轮询命令前正常返回；拒绝布尔值及溢出。
    """
    if (type(value) not in (int, float) or value < 0 or value > threading.TIMEOUT_MAX
            or not math.isfinite(value) or (positive and value == 0)):
        raise ValueError("observation intervals must be finite platform-safe seconds with the required sign")
