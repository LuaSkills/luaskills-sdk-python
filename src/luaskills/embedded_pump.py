"""
Owned Python callback event pump with bounded workers and explicit registration drainage.
拥有型 Python 回调事件泵，包含有界工作线程与显式注册排空。
"""

from __future__ import annotations

import asyncio
import contextvars
import inspect
import sys
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Iterable, TypeVar, cast, get_args

from .embedded_callbacks import HOST_CALLBACK_RUNTIME, HostCallbackContext, HostCapability
from .embedded_contract import EmbeddedNativeStatus, OutputHostRequestPhase
from .embedded_pump_delivery import PumpDelivery
from .embedded_transport import EMBEDDED_CONTROL_WORKERS, EmbeddedResultReleaseError, EmbeddedRuntimeError, EmbeddedTransport, EmbeddedTransportError


# Owned command futures preserve their result type across synchronous and asynchronous observers.
# 拥有型命令 future 跨同步及异步观察者保留结果类型。
_Result = TypeVar("_Result")

# Query identity fields and host phases come from the exact commands and generated response contract.
# 查询身份字段及宿主阶段来自精确命令与生成响应契约。
_QUERY_IDENTITIES = {"host_request_status": "request_id", "operation_status": "operation_id",
                     "capability_status": "registration_id"}
_HOST_REQUEST_PHASES = frozenset(get_args(OutputHostRequestPhase))


@dataclass(frozen=True, kw_only=True)
class CallbackPumpConfig:
    """
    Explicit bounds for active handlers, submitted control commands and polling cadence.
    活动处理器、已提交控制命令及轮询节奏的显式边界。
    """

    # Combined synchronous and asynchronous handlers, including pending acknowledgements.
    # 同步与异步处理器合计，包含待确认结果。
    max_concurrent_handlers: int
    # Ordinary SDK commands not yet returned; one separate shared recovery attempt is reserved.
    # 尚未返回的普通 SDK 命令；另外预留一个共享恢复尝试。
    max_pending_commands: int
    # Core cancellation and request queue polling interval in milliseconds.
    # 核心取消及请求队列轮询间隔毫秒数。
    poll_interval_ms: int

    def __post_init__(self) -> None:
        """
        Reject implicit unlimited or non-integral configuration before creating threads.
        在线程创建前拒绝隐式无限或非整数配置。
        """
        for value in (self.max_concurrent_handlers, self.max_pending_commands, self.poll_interval_ms):
            if type(value) is not int or not 0 < value <= sys.maxsize:
                raise ValueError(f"callback pump limits must be positive integers no greater than {sys.maxsize}")


@dataclass
class _Registration:
    """
    Retain an exact language handler until the core registration and actual SDK tasks have both drained.
    保留精确语言处理器，直到核心注册及实际 SDK 任务均已排空。
    """

    # Frozen Python handler declaration and exact core registration identity.
    # 冻结 Python 处理器声明及精确核心注册身份。
    capability: HostCapability
    registration_id: str
    # Explicit unregister intent, independent of actual core drainage.
    # 显式注销意图，独立于实际核心排空。
    retiring: bool
    # Owned-loop completion notification after the core metadata has been forgotten.
    # 核心元数据已遗忘后的拥有循环完成通知。
    drained: asyncio.Event
    # Serialize native retirement for callers racing the service's close path.
    # 为与服务关闭路径竞争的调用方串行化原生退役。
    native_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass
class _Request:
    """
    Retain one delivered handler and its completed outcome until the core accepts its acknowledgement.
    保留一个已交付处理器及其完成结果，直到核心接受确认。
    """

    # Exact registration owner through execution and acknowledgement; absent owners are explicitly rejected.
    # 执行与确认全过程的精确注册所有者；缺失所有者时显式拒绝。
    registration: _Registration | None
    # Trusted invocation context and original structured application arguments.
    # 可信调用上下文及原始结构化应用参数。
    context: HostCallbackContext
    arguments: Any
    # Present only after the actual handler has returned; pending native acknowledgement remains owned.
    # 仅实际处理器返回后存在；待原生确认仍保持拥有状态。
    outcome: dict[str, Any] | None = None
    # Frozen completion bytes cannot be changed by a host retaining an alias to its returned value.
    # 冻结完成字节不能被仍持有返回值别名的宿主修改。
    encoded_completion: bytes | None = None
    # Only an actual failed acknowledgement requires reconciliation; normal pending work is not a failure.
    # 仅实际失败的确认需要核对；正常挂起工作不属于故障。
    acknowledgement_failed: bool = False
    # Native status and completion cannot race each other's removal of the exact request.
    # 原生状态及完成不得相互竞争移除精确请求。
    native_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class EmbeddedCallbackPump:
    """
    Own a dedicated event loop for one runtime's queued Python callbacks; callers may use sync or async methods.
    为一个运行时的队列 Python 回调拥有独立事件循环；调用方可使用同步或异步方法。
    Register all queued handlers for this runtime through this pump and close it before freeing the transport.
    通过此事件泵注册此运行时的全部队列处理器，并在释放传输前关闭事件泵。
    """

    def __init__(self, transport: EmbeddedTransport, runtime_id: str, config: CallbackPumpConfig) -> None:
        """
        Start bounded SDK infrastructure for an already initialized exact native runtime; no callbacks run yet.
        为已初始化的精确原生运行时启动有界 SDK 基础设施；此时尚无回调运行。
        """
        # Native runtime and transport remain authoritative; this pump only owns Python handlers and calls.
        # 原生运行时及传输保持权威；此泵仅拥有 Python 处理器和调用。
        self._transport = transport
        self._runtime_id = runtime_id
        self._config = config
        # Short lock protects cross-thread SDK diagnostics and command admission only.
        # 短锁仅保护跨线程 SDK 诊断及命令入场。
        self._lock = threading.Lock()
        self._pending_commands = 0
        # Strongly retain actual cross-thread futures until their owned tasks return.
        # 强引用保留实际跨线程 future，直到其拥有任务返回。
        self._command_futures: set[Future[Any]] = set()
        self._closing = False
        self._accepting_commands = True
        self._failure: str | None = None
        self._registration_ids: tuple[str, ...] = ()
        self._request_ids: tuple[str, ...] = ()
        self._pending_ack_ids: tuple[str, ...] = ()
        # One mutation journal plus explicit release state bounds uncertain native control ownership.
        # 单条变更日志及显式释放状态限制不确定原生控制所有权。
        self._pending_native: PumpDelivery | None = None
        self._needs_release = False
        self._recovery_required = False
        self._pending_native_kind: str | None = None
        self._recovering = False
        # One extra recovery observer group cannot be starved by ordinary unregister waiters.
        # 一个额外恢复观察组不会被普通注销等待者饿死。
        self._recovery_future: Future[Any] | None = None
        # These maps are mutated only on the owned loop; thread readers receive immutable snapshots.
        # 这些映射仅在拥有循环上修改；线程读取方取得不可变快照。
        self._registrations: dict[str, _Registration] = {}
        self._requests: dict[str, _Request] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        # Futures survive cancellation or closure of any caller-owned asyncio loop.
        # Future 跨越任意调用方 asyncio 循环的取消或关闭而存活。
        self._ready: Future[None] = Future()
        self._closed: Future[None] = Future()
        # The transport prevents a second pump or premature transport free for this exact runtime.
        # 传输阻止此精确运行时的第二个泵或过早传输释放。
        # An owned non-daemon thread keeps live callbacks and library references reachable until real drainage.
        # 拥有型非守护线程在实际排空前保持活动回调及动态库引用可达。
        self._thread = threading.Thread(target=self._thread_main, name="luaskills-callback-pump", daemon=False)
        self._transport._claim_callback_pump(runtime_id, self)
        try:
            self._thread.start()
            self._ready.result()
        except BaseException:
            # If startup is already running, it must retain ownership until its own cleanup finishes.
            # 若启动已在进行，必须由其自身清理完成后才释放所有权。
            if self._thread.ident is None:
                self._transport._release_callback_pump(runtime_id, self)
            elif not self._closed.done():
                self.request_close()
            raise

    @property
    def status(self) -> dict[str, Any]:
        """
        Return retained identities and current recovery demand independently of historical failure text.
        独立于历史失败文本，返回保留身份及当前恢复需求。
        """
        with self._lock:
            return {"runtime_id": self._runtime_id, "closing": self._closing,
                "closed": self._closed.done() and self._closed.exception() is None,
                "registration_ids": self._registration_ids, "request_ids": self._request_ids,
                "pending_acknowledgements": self._pending_ack_ids, "pending_commands": self._pending_commands,
                "pending_native_command": self._pending_native_kind, "recovery_required": self._recovery_required,
                "failure": self._failure}

    def _publish(self) -> None:
        """
        Publish owned-loop identities and unresolved delivery state under a short diagnostic lock.
        在短诊断锁内发布拥有循环身份及未解决交付状态。
        """
        pending = self._pending_native
        with self._lock:
            self._registration_ids = tuple(self._registrations)
            self._request_ids = tuple(self._requests)
            self._pending_ack_ids = tuple(key for key, record in self._requests.items() if record.outcome is not None)
            self._pending_native_kind = None if pending is None else pending.kind
            self._recovery_required = self._needs_release or (pending is not None and pending.error is not None) or any(
                record.acknowledgement_failed for record in self._requests.values())

    def _record_failure(self, error: BaseException) -> None:
        """
        Retain the first infrastructure failure and stop admitting new callbacks while keeping drain control alive.
        保留首次基础设施失败，并停止接纳新回调，同时保持排空控制活动。
        """
        with self._lock:
            if self._failure is None:
                self._failure = f"{type(error).__name__}: {error}"
            self._closing = True

    def _thread_main(self) -> None:
        """
        Own the loop and bounded executors through real cleanup, including failures during infrastructure startup.
        跨实际清理拥有循环及有界执行器，包含基础设施启动期间的失败。
        """
        # Keep the failure until worker cleanup has completed, rather than declaring closure before executor joins.
        # 保留失败直到工作线程清理完成，而非在执行器汇合前宣称关闭。
        failure: BaseException | None = None
        try:
            with ThreadPoolExecutor(max_workers=EMBEDDED_CONTROL_WORKERS, thread_name_prefix="luaskills-control") as native_executor:
                with ThreadPoolExecutor(max_workers=self._config.max_concurrent_handlers, thread_name_prefix="luaskills-handler") as handler_executor:
                    self._native_executor = native_executor
                    self._handler_executor = handler_executor
                    self._loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(self._loop)
                    self._wake = asyncio.Event()
                    self._publication = asyncio.Lock()
                    # Serialize native frames and recovery on the one reserved control executor.
                    # 在唯一预留控制执行器上串行化原生帧及恢复。
                    self._io_lock = asyncio.Lock()
                    try:
                        self._loop.run_until_complete(self._run())
                    finally:
                        self._loop.run_until_complete(self._loop.shutdown_asyncgens())
                        self._loop.run_until_complete(self._loop.shutdown_default_executor())
                        self._loop.close()
        except BaseException as error:
            failure = error
            self._record_failure(error)
        with self._lock:
            self._accepting_commands = False
        # A startup failure owns no handlers; unexpected retained work remains fenced against transport free.
        # 启动失败不拥有处理器；意外保留工作继续通过屏障阻止传输释放。
        if not self._registrations and not self._requests and not self._tasks and not self._native_paused():
            self._transport._release_callback_pump(self._runtime_id, self)
        if failure is not None:
            self._closed.set_exception(failure)
            if not self._ready.done():
                self._ready.set_exception(failure)
        else:
            self._closed.set_result(None)


    @property
    def recovery_required(self) -> bool:
        """
        Return whether retained failed delivery needs explicit recovery, excluding normal in-flight work.
        返回保留的失败交付是否需要显式恢复，不包含正常在途工作。
        """
        with self._lock:
            return self._recovery_required

    def _native_paused(self) -> bool:
        """
        Check owned-loop evidence that prevents another native control mutation; return a local boolean.
        检查阻止下一次原生控制变更的拥有循环证据；返回本地布尔值。
        """
        return self._pending_native is not None or self._needs_release

    def _require_native_ready(self) -> None:
        """
        Reject native entry while a retained delivery or buffer release requires recovery; return nothing.
        保留交付或缓冲释放需要恢复时拒绝原生入场；无返回值。
        """
        if self._native_paused():
            raise EmbeddedRuntimeError("busy", "Python callback delivery requires explicit recovery")

    async def _mutate(self, operation: dict[str, Any], apply: Callable[[Any], None]) -> Any:
        """
        Retain operation and its apply callback before executing once; return only locally installed delivery.
        在单次执行前保留 operation 及其 apply 回调；仅返回已在本地安装的交付。
        Uncertain native outcomes remain fenced and cannot be retried as a fresh mutation.
        不确定原生结果继续受到屏障保护，不能作为新变更重试。
        """
        encoded = self._transport._encode_request({"type": "runtime", "runtime_id": self._runtime_id,
                                                  "operation": operation})
        async with self._io_lock:
            self._require_native_ready()
            delivery = PumpDelivery(operation["type"], encoded, apply)
            self._pending_native = delivery
            self._publish()
            try:
                await self._loop.run_in_executor(self._native_executor, delivery.capture, self._transport._request_encoded)
                if delivery.error is not None:
                    raise delivery.error
                value = delivery.result()
                apply(value)
            except BaseException as error:
                # Core registration and queue extraction reject business errors before publishing ownership.
                # 核心注册及队列提取在发布所有权前拒绝业务错误。
                if isinstance(error, EmbeddedRuntimeError) and delivery.error is error and delivery.kind in (
                    "capabilities_register", "host_requests_take"
                ):
                    self._pending_native = None
                    self._publish()
                    raise
                delivery.error = error
                self._needs_release = self._needs_release or isinstance(error, EmbeddedResultReleaseError)
                self._record_failure(error)
                self._publish()
                raise
            self._pending_native = None
            self._publish()
            return value

    def _install_registration(self, capabilities: tuple[HostCapability, ...], result: Any) -> None:
        """
        Validate the complete result before installing exact capabilities; retain all owners on invalid evidence.
        安装精确 capabilities 前验证完整 result；证据无效时保留全部所有者。
        Return nothing; publication makes every actual registration visible to close and recovery.
        无返回值；发布使每个实际注册对关闭及恢复可见。
        """
        if not isinstance(result, dict) or not isinstance(result.get("registration_ids"), list):
            raise RuntimeError("callback registration receipt lacks registration identities")
        identities = result["registration_ids"]
        if len(identities) != len(capabilities) or any(type(identity) is not str or not identity for identity in identities):
            raise RuntimeError("callback registration receipt has invalid identities")
        if len(set(identities)) != len(identities) or any(identity in self._registrations for identity in identities):
            raise RuntimeError("callback registration receipt repeats an owned identity")
        registrations = {identity: _Registration(capability, identity, False, asyncio.Event())
                         for identity, capability in zip(identities, capabilities)}
        self._registrations.update(registrations)
        self._publish()

    def _install_requests(self, batch: Any, limit: int) -> None:
        """
        Validate batch within its reserved limit before dispatch; return nothing and never replay owned requests.
        在分发前按预留 limit 验证 batch；无返回值，绝不重放已拥有请求。
        """
        if not isinstance(batch, list) or len(batch) > limit:
            raise RuntimeError("callback request delivery exceeds its reserved capacity")
        identities: set[str] = set()
        for request in batch:
            if (not isinstance(request, dict)
                or any(type(request.get(key)) is not str or not request[key] for key in ("request_id", "registration_id"))
                or not isinstance(request.get("caller"), dict)
                or type(request["caller"].get("operation_id")) is not str or not request["caller"]["operation_id"]
                or type(request.get("remaining_ms")) is not int or request["remaining_ms"] < 0
                or "arguments" not in request):
                raise RuntimeError("callback request delivery has invalid invocation evidence")
            identity = request["request_id"]
            if identity in identities or identity in self._requests:
                raise RuntimeError("callback request delivery repeats an owned identity")
            identities.add(identity)
        for request in batch:
            self._dispatch(request)

    def _finish_registration(self, record: _Registration, value: Any, *, forget: bool) -> None:
        """
        Apply null control value to this exact record; forget signals drainage only after native removal.
        将空控制 value 应用到此精确 record；forget 仅在原生移除后通知排空。
        Return nothing and reject evidence that does not match the retained registration owner.
        无返回值，拒绝与保留注册所有者不匹配的证据。
        """
        if value is not None or self._registrations.get(record.registration_id) is not record:
            raise RuntimeError("callback retirement receipt does not match its retained owner")
        if forget:
            del self._registrations[record.registration_id]
            record.drained.set()
        else:
            record.retiring = True
        self._publish()

    async def _forget_registration(self, record: _Registration) -> None:
        """
        Retain the exact drained record through native metadata removal; return after verified local removal.
        跨原生元数据移除保留精确已排空 record；本地移除得到验证后返回。
        """
        async with record.native_lock:
            await self._mutate({"type": "capability_forget", "registration_id": record.registration_id},
                               lambda value: self._finish_registration(record, value, forget=True))

    def _validate_query(self, operation: dict[str, Any], value: Any) -> dict[str, Any]:
        """
        Validate consumed lifecycle evidence in value against the exact query operation before releasing ownership.
        释放所有权前，按精确查询 operation 验证 value 中实际消费的生命周期证据。
        Return the checked snapshot; malformed or mismatched evidence cannot authorize completion or forgetting.
        返回已检查快照；畸形或错配证据不能授权完成或遗忘。
        """
        kind = operation["type"]
        identity = _QUERY_IDENTITIES[kind]
        if not isinstance(value, dict) or value.get(identity) != operation[identity]:
            raise RuntimeError("callback query receipt has a mismatched identity")
        if kind == "host_request_status":
            if type(value.get("phase")) is not str or value["phase"] not in _HOST_REQUEST_PHASES:
                raise RuntimeError("callback query receipt has an invalid request phase")
        elif kind == "capability_status":
            if type(value.get("drained")) is not bool:
                raise RuntimeError("callback query receipt has an invalid drainage flag")
        elif not isinstance(value.get("host_effects"), list):
            raise RuntimeError("callback query receipt lacks operation effect evidence")
        return value

    async def _native(self, operation: dict[str, Any]) -> Any:
        """
        Execute one read-only core query through the reserved frame; release failure pauses further native work.
        通过预留帧执行一个只读核心查询；释放失败暂停后续原生工作。
        Return decoded query data; mutating controls must use the retained mutation journal.
        返回解码查询数据；变更控制必须使用保留变更日志。
        """
        if operation["type"] not in _QUERY_IDENTITIES:
            raise RuntimeError("callback mutation requires the retained delivery path")
        encoded = self._transport._encode_request({"type": "runtime", "runtime_id": self._runtime_id, "operation": operation})
        async with self._io_lock:
            self._require_native_ready()
            try:
                value = await self._loop.run_in_executor(self._native_executor, self._transport._request_encoded, encoded)
                return self._validate_query(operation, value)
            except EmbeddedResultReleaseError as error:
                self._needs_release = True
                self._record_failure(error)
                self._publish()
                raise

    async def _run(self) -> None:
        """
        Own dispatch and drainage while pausing uncertain mutations until explicit delivery recovery.
        拥有分发及排空，同时暂停不确定变更，直到显式恢复交付。
        Ready confirms the exact initialized runtime; return only after all owned records and tasks drain.
        就绪确认精确已初始化运行时；仅在全部拥有记录及任务排空后返回。
        """
        initial = await self._loop.run_in_executor(self._native_executor, self._transport.request,
            {"type": "runtime_status", "runtime_id": self._runtime_id})
        if initial["runtime_id"] != self._runtime_id or initial["initialization"] != "ready" or initial["closing"]:
            raise RuntimeError("callback pump requires the exact initialized open runtime")
        self._ready.set_result(None)
        while True:
            try:
                if not self._native_paused() and not self._recovering:
                    if self.status["closing"]:
                        async with self._publication:
                            for registration in tuple(self._registrations.values()):
                                await self._retire(registration)
                    else:
                        async with self._publication:
                            available = self._config.max_concurrent_handlers - len(self._requests)
                            if available:
                                await self._mutate({"type": "host_requests_take", "limit": available},
                                    lambda batch: self._install_requests(batch, available))
                    for record in tuple(self._requests.values()):
                        if self._native_paused():
                            break
                        if record.outcome is None:
                            async with record.native_lock:
                                current = await self._native({"type": "host_request_status", "request_id": record.context.request_id})
                                if current["cancellation"] is not None:
                                    record.context._observe_cancellation(current["cancellation"])
                        elif not record.acknowledgement_failed:
                            await self._acknowledge(record)
                    for registration in tuple(self._registrations.values()):
                        if self._native_paused():
                            break
                        if registration.retiring:
                            current = await self._native({"type": "capability_status", "registration_id": registration.registration_id})
                            if current["drained"] and not any(active.registration is registration for active in self._requests.values()):
                                await self._forget_registration(registration)
                self._publish()
                if not self._native_paused() and not self._registrations and not self._requests and not self._tasks:
                    with self._lock:
                        if self._closing and self._pending_commands == 0:
                            self._accepting_commands = False
                            return
            except Exception as error:
                self._record_failure(error)
                self._publish()
            try:
                await asyncio.wait_for(self._wake.wait(), self._config.poll_interval_ms / 1000)
            except asyncio.TimeoutError:
                pass
            self._wake.clear()

    def _dispatch(self, request: dict[str, Any]) -> None:
        """
        Retain one validated request before scheduling its actual handler or a precise no-owner rejection.
        在调度实际处理器或精确无所有者拒绝前，保留一个已校验请求。
        Unknown registration ownership retains the original caller for later completion reconciliation.
        未知注册所有权保留原始调用方，用于后续完成核对。
        """
        registration = self._registrations.get(request["registration_id"])
        effects = "mutating" if registration is None else registration.capability.descriptor["effects"]
        context = HostCallbackContext(request, effects, self._loop)
        record = _Request(registration, context, request["arguments"])
        self._requests[context.request_id] = record
        if registration is None:
            self._record_failure(RuntimeError("delivered callback has no exact Python registration owner"))
        action = self._handle(record)
        try:
            task = self._loop.create_task(action)
        except BaseException:
            action.close()
            raise
        self._tasks.add(task)
        task.add_done_callback(self._handler_returned)
        self._publish()


    async def _handle(self, record: _Request) -> None:
        """
        Execute one retained handler and freeze its outcome; the service acknowledges only its actual return.
        执行一个保留处理器并冻结其结果；服务仅在其实际返回后确认。
        Missing registration owners are rejected without execution, while their trusted request remains retained.
        缺失注册所有者时拒绝执行，同时保留其可信请求。
        """
        token = HOST_CALLBACK_RUNTIME.set(self._runtime_id)
        try:
            try:
                if record.registration is None:
                    record.context.report_effects("not_started")
                    raise EmbeddedRuntimeError("internal", "Python callback registration owner is absent")
                capability = record.registration.capability
                if capability.mode == "async":
                    value = await capability.handler(record.arguments, record.context)
                else:
                    inherited = contextvars.copy_context()
                    value = await self._loop.run_in_executor(self._handler_executor,
                        inherited.run, capability.handler, record.arguments, record.context)
                    if inspect.isawaitable(value):
                        if inspect.iscoroutine(value):
                            value.close()
                        raise TypeError("sync callback must not return an awaitable")
                record.outcome = {"ok": True, "value": value, "effects": record.context.effects}
            except BaseException as error:
                # Handler failures preserve effects without exposing application arguments or secrets.
                # 处理器失败保留副作用，不暴露应用参数或秘密。
                failure = {"code": error.code, "message": error.message} if isinstance(error, EmbeddedRuntimeError) else {
                    "code": "execution_failed", "message": f"Python host callback raised {type(error).__name__}"}
                record.outcome = {"ok": False, "error": failure, "effects": record.context.effects}
            try:
                record.encoded_completion = self._encode_completion(record)
            except (TypeError, ValueError, OverflowError, UnicodeError, RecursionError):
                # Preserve the returned snapshot; a retained context alias may report different effects after return.
                # 保留返回时快照；保留的上下文别名可能在返回后报告不同副作用。
                record.outcome = {"ok": False, "error": {"code": "execution_failed",
                    "message": "Python host callback produced an invalid or oversized result"}, "effects": record.outcome["effects"]}
                record.encoded_completion = self._encode_completion(record)
        except BaseException as error:
            record.acknowledgement_failed = True
            self._record_failure(error)
        finally:
            self._publish()
            HOST_CALLBACK_RUNTIME.reset(token)
            self._wake.set()


    async def _acknowledge(self, record: _Request) -> None:
        """
        Serialize exact completion and retain failed ownership; return without replaying the handler.
        串行化精确完成并保留失败所有权；返回时不重放处理器。
        Parser rejection alone permits a bounded replacement result; release failures preserve the original.
        仅解析器拒绝允许有界替换结果；释放失败保留原结果。
        """
        async with record.native_lock:
            if self._requests.get(record.context.request_id) is not record:
                return
            async with self._io_lock:
                if self._native_paused():
                    return
                try:
                    if record.encoded_completion is None:
                        record.encoded_completion = self._encode_completion(record)
                    try:
                        value = await self._loop.run_in_executor(self._native_executor,
                            self._transport._request_encoded, record.encoded_completion)
                    except EmbeddedTransportError as error:
                        if error.function_name != "luaskills_ffi_embedded_request_v1" or error.status != EmbeddedNativeStatus.INVALID_ARGUMENT:
                            raise
                        assert record.outcome is not None
                        record.outcome = {"ok": False, "error": {"code": "execution_failed",
                            "message": "Python host callback result was rejected by the native parser"},
                            "effects": record.outcome["effects"]}
                        record.encoded_completion = self._encode_completion(record)
                        value = await self._loop.run_in_executor(self._native_executor,
                            self._transport._request_encoded, record.encoded_completion)
                    if value is not None:
                        raise RuntimeError("callback completion receipt must be null")
                except Exception as error:
                    record.acknowledgement_failed = True
                    self._needs_release = self._needs_release or isinstance(error, EmbeddedResultReleaseError)
                    self._record_failure(error)
                    self._publish()
                    return
                del self._requests[record.context.request_id]
                self._publish()


    def _encode_completion(self, record: _Request) -> bytes:
        """
        Freeze the exact completion frame before delivery, preserving original effects even when its value is rejected.
        在交付前冻结精确完成帧，即使结果值被拒绝也保留原始副作用。
        """
        return self._transport._encode_request({"type":"runtime", "runtime_id":self._runtime_id,
            "operation":{"type":"host_request_complete", "request_id":record.context.request_id, "outcome":record.outcome}})


    async def _register(self, capabilities: tuple[HostCapability, ...]) -> tuple[str, ...]:
        """
        Register a frozen batch while the journal retains its handlers until exact identities are installed.
        注册冻结批次，期间日志保留处理器，直到安装精确身份。
        Return confirmed identities; failed delivery leaves publication discoverable on the pump.
        返回已确认身份；失败交付将发布保留在可发现的事件泵中。
        """
        async with self._publication:
            result = await self._mutate({"type": "capabilities_register", "descriptors": [item.descriptor for item in capabilities]},
                lambda value: self._install_registration(capabilities, value))
        self._wake.set()
        return tuple(result["registration_ids"])

    async def _retire(self, record: _Registration) -> None:
        """
        Unregister an exact handler once and retain uncertain delivery instead of resubmitting on each tick.
        注销精确处理器一次，并保留不确定交付，不在每次轮询时重新提交。
        """
        async with record.native_lock:
            if not record.retiring:
                await self._mutate({"type": "capability_unregister", "registration_id": record.registration_id},
                    lambda value: self._finish_registration(record, value, forget=False))

    async def _unregister(self, registration_id: str) -> None:
        """
        Wait for actual core and SDK drainage for one owned registration, without rerouting same-name replacements.
        等待一个拥有注册的实际核心及 SDK 排空，不重定向同名替换。
        """
        record = self._registrations.get(registration_id)
        if record is None:
            raise EmbeddedRuntimeError("not_found", "Python callback registration is not owned by this pump")
        await self._retire(record)
        self._wake.set()
        await record.drained.wait()

    def _submit(self, action: Coroutine[Any, Any, _Result], *, drain: bool = False, recovery: bool = False) -> Future[_Result]:
        """
        Bound ordinary commands and reserve one shared recovery attempt; return an owned, cancellation-safe future.
        限制普通命令并预留一个共享恢复尝试；返回拥有型且不受观察取消影响的 future。
        Actual tasks retain admission until return, including unregister observers waiting for native drainage.
        实际任务直到返回才释放入场，包含等待原生排空的注销观察者。
        """
        with self._lock:
            if not self._accepting_commands or (self._closing and not drain):
                action.close()
                raise EmbeddedRuntimeError("closed", "Python callback pump is closing")
            if recovery and self._recovery_future is not None:
                action.close()
                return cast(Future[_Result], self._recovery_future)
            if not recovery and self._pending_commands >= self._config.max_pending_commands:
                action.close()
                raise EmbeddedRuntimeError("capacity_exceeded", "Python callback command capacity is exhausted")
            self._pending_commands += 1
            try:
                future = asyncio.run_coroutine_threadsafe(action, self._loop)
            except BaseException:
                action.close()
                self._pending_commands -= 1
                raise
            self._command_futures.add(future)
            if recovery:
                self._recovery_future = future
        # Attach outside the lock: an already completed future executes its callback synchronously.
        # 在锁外挂接：已完成 future 会同步执行其回调。
        future.add_done_callback(self._command_returned)
        return future


    def _command_returned(self, future: Future[Any]) -> None:
        """
        Release command admission after the actual owned task returned and wake the drainage service.
        实际拥有任务返回后释放命令入场，并唤醒排空服务。
        """
        with self._lock:
            self._pending_commands -= 1
            self._command_futures.discard(future)
            if self._recovery_future is future:
                self._recovery_future = None
        self._loop.call_soon_threadsafe(self._wake.set)

    def _handler_returned(self, task: asyncio.Task[None]) -> None:
        """
        Observe actual handler task return and retain unexpected faults instead of silently dropping task exceptions.
        观察实际处理器任务返回，并保留意外故障，而非静默丢弃任务异常。
        """
        self._tasks.discard(task)
        if task.cancelled():
            self._record_failure(RuntimeError("owned callback task was unexpectedly cancelled"))
        else:
            failure = task.exception()
            if failure is not None:
                self._record_failure(failure)
        self._wake.set()

    async def _retry_acknowledgements(self) -> None:
        """
        Recover original control delivery and failed acknowledgements without repeating handler execution.
        恢复原始控制交付及失败确认，不重复执行处理器。
        Return after reconciliation, or raise while retaining every unresolved identity and native buffer.
        核对后返回；否则抛错，同时保留全部未解决身份及原生缓冲。
        """
        self._recovering = True
        try:
            async with self._publication:
                async with self._io_lock:
                    if self._needs_release:
                        await self._loop.run_in_executor(self._native_executor, self._transport.release_results)
                        self._needs_release = False
                    delivery = self._pending_native
                    if delivery is not None:
                        try:
                            value = delivery.result()
                        except EmbeddedRuntimeError:
                            # These two core commands publish no ownership on a business rejection.
                            # 这两个核心命令在业务拒绝时不发布所有权。
                            if delivery.kind not in ("capabilities_register", "host_requests_take"):
                                raise
                        else:
                            delivery.apply(value)
                        self._pending_native = None
                    self._publish()
                for record in tuple(self._requests.values()):
                    if not record.acknowledgement_failed:
                        continue
                    async with record.native_lock:
                        if self._requests.get(record.context.request_id) is not record:
                            continue
                        try:
                            status = await self._native({"type": "host_request_status", "request_id": record.context.request_id})
                            completed = status["phase"] == "completed"
                            if status["phase"] == "completing":
                                continue
                        except EmbeddedRuntimeError as error:
                            if error.code not in ("not_found", "already_completed"):
                                raise
                            # Absence never proves completion; require the original caller's exact effect record.
                            # 缺失绝不证明完成；必须取得原调用方的精确副作用记录。
                            operation = await self._native({"type": "operation_status", "operation_id": record.context.caller["operation_id"]})
                            completed = any(effect["request_id"] == record.context.request_id
                                and effect["registration_id"] == record.context.registration_id
                                and effect["phase"] == "completed" for effect in operation["host_effects"])
                            if not completed:
                                raise EmbeddedRuntimeError("not_found",
                                    "callback completion evidence is unavailable; native completion cannot be inferred") from error
                        if completed:
                            del self._requests[record.context.request_id]
                            self._publish()
                            continue
                        if record.encoded_completion is None:
                            record.encoded_completion = self._encode_completion(record)
                    await self._acknowledge(record)
            if self.recovery_required:
                raise EmbeddedRuntimeError("busy", "Python callback recovery retains unresolved delivery")
        finally:
            self._recovering = False
            self._publish()
            self._wake.set()



    def retry_acknowledgements(self, timeout: float | None = None) -> None:
        """
        Explicitly recover retained control receipts, buffers and failed completions within observer timeout.
        在观察 timeout 内显式恢复保留控制回执、缓冲及失败完成。
        Return after recovery; concurrent observers share one reserved attempt without replaying handlers.
        恢复后返回；并发观察者共享一个预留尝试，不重放处理器。
        """
        self._check_wait()
        self._wait(self._submit(self._retry_acknowledgements(), drain=True, recovery=True), timeout)


    def _check_wait(self) -> None:
        """
        Reject blocking or self-draining operations from a callback that this same pump is responsible for finishing.
        拒绝此泵负责完成的回调发起阻塞或等待自身排空的操作。
        """
        if threading.current_thread() is self._thread or HOST_CALLBACK_RUNTIME.get() == self._runtime_id:
            raise EmbeddedRuntimeError("unsupported", "waiting for this callback pump from its own handler is forbidden")

    def register(self, capabilities: Iterable[HostCapability], timeout: float | None = None) -> tuple[str, ...]:
        """
        Register an atomic handler batch; observation timeout preserves the owned task and recoverable status identities.
        注册原子处理器批次；观察超时保留拥有任务及可从状态恢复的身份。
        """
        self._check_wait()
        return self._wait(self._submit(self._register(tuple(item.snapshot() for item in capabilities))), timeout)

    async def register_async(self, capabilities: Iterable[HostCapability]) -> tuple[str, ...]:
        """
        Await atomic registration from any caller loop without allowing its cancellation to abandon published handlers.
        从任意调用方循环等待原子注册，不允许其取消放弃已发布处理器。
        """
        self._check_wait()
        future = self._submit(self._register(tuple(item.snapshot() for item in capabilities)))
        return await self._observe(future)

    def unregister(self, registration_id: str, timeout: float | None = None) -> None:
        """
        Wait for an exact handler's actual drainage; timeout keeps both closure ownership and cleanup active.
        等待精确处理器实际排空；超时保持闭包所有权及清理活动。
        """
        self._check_wait()
        self._wait(self._submit(self._unregister(registration_id), drain=True), timeout)

    async def unregister_async(self, registration_id: str) -> None:
        """
        Await exact handler drainage while a cancelled caller leaves the owned unregister task running.
        等待精确处理器排空；调用方取消时拥有型注销任务继续运行。
        """
        self._check_wait()
        future = self._submit(self._unregister(registration_id), drain=True)
        await self._observe(future)

    def request_close(self) -> None:
        """
        Stop new SDK registrations and request retirement of every owned handler without pretending they have finished.
        停止新 SDK 注册，并请求全部拥有处理器退役，不假装它们已经结束。
        """
        with self._lock:
            self._closing = True
            wake = self._accepting_commands and self._ready.done()
        if wake:
            self._loop.call_soon_threadsafe(self._wake.set)

    def close(self, timeout: float | None = None) -> None:
        """
        Request closure and wait for actual callbacks, acknowledgements and threads; timeout preserves live ownership.
        请求关闭并等待实际回调、确认及线程；超时保留活动所有权。
        """
        self._check_wait()
        self.request_close()
        self._wait(self._closed, timeout)
        self._thread.join()

    async def close_async(self) -> None:
        """
        Await actual pump closure without binding its lifetime to the caller's event loop or cancellation.
        等待实际事件泵关闭，不将其寿命绑定到调用方事件循环或取消。
        """
        self._check_wait()
        self.request_close()
        await self._observe(self._closed)
        await asyncio.to_thread(self._thread.join)

    @staticmethod
    def _wait(future: Future[_Result], timeout: float | None) -> _Result:
        """
        Observe future for timeout seconds and expose built-in TimeoutError on every supported Python version.
        在 timeout 秒内观察 future，并在所有受支持 Python 版本暴露内置 TimeoutError。
        Return its actual result; timing out never cancels the future or releases its retained ownership.
        返回其实际结果；等待超时绝不取消 future 或释放其保留所有权。
        """
        try:
            return future.result(timeout)
        except FutureTimeoutError as error:
            # Python 3.10 has a distinct futures exception; 3.11 made it an alias of the built-in class.
            # Python 3.10 使用独立 futures 异常；3.11 才将其变为内置类的别名。
            raise TimeoutError("embedded callback pump wait timed out") from error

    @staticmethod
    async def _observe(future: Future[_Result]) -> _Result:
        """
        Await an owned cross-thread future without propagating cancellation or leaving later exceptions unobserved.
        等待拥有型跨线程 future，不传播取消，也不让后续异常无人观察。
        """
        # The underlying future remains rooted by the pump after an observer has stopped waiting.
        # 观察者停止等待后，底层 future 仍由事件泵保持根引用。
        observer = asyncio.wrap_future(future)
        observer.add_done_callback(EmbeddedCallbackPump._observe_returned)
        return await asyncio.shield(observer)

    @staticmethod
    def _observe_returned(observer: asyncio.Future[Any]) -> None:
        """
        Retrieve delayed exceptions for cancelled observers while leaving normal await result semantics intact.
        为已取消观察者取回延迟异常，同时保持正常等待结果语义。
        """
        if not observer.cancelled():
            observer.exception()
