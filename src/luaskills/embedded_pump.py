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
from typing import Any, Coroutine, Iterable

from .embedded_callbacks import HOST_CALLBACK_RUNTIME, HostCallbackContext, HostCapability
from .embedded_contract import EmbeddedNativeStatus
from .embedded_transport import EMBEDDED_CONTROL_WORKERS, EmbeddedRuntimeError, EmbeddedTransport, EmbeddedTransportError


@dataclass(frozen=True, kw_only=True)
class CallbackPumpConfig:
    """
    Explicit bounds for active handlers, submitted control commands and polling cadence.
    活动处理器、已提交控制命令及轮询节奏的显式边界。
    """

    # Combined synchronous and asynchronous handlers, including pending acknowledgements.
    # 同步与异步处理器合计，包含待确认结果。
    max_concurrent_handlers: int
    # SDK commands accepted but not yet fully returned to their owned futures.
    # SDK 已接纳但尚未完整返回到其拥有 future 的命令。
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

    # Exact immutable registration owner, held throughout execution and acknowledgement.
    # 精确不可变注册所有者，在执行与确认全过程持有。
    registration: _Registration
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
        self._command_futures: set[Future] = set()
        self._closing = False
        self._accepting_commands = True
        self._failure: str | None = None
        self._registration_ids: tuple[str, ...] = ()
        self._request_ids: tuple[str, ...] = ()
        self._pending_ack_ids: tuple[str, ...] = ()
        # These maps are mutated only on the owned loop; thread readers receive immutable snapshots.
        # 这些映射仅在拥有循环上修改；线程读取方取得不可变快照。
        self._registrations: dict[str, _Registration] = {}
        self._requests: dict[str, _Request] = {}
        # Requests from an unexpected external registration remain acknowledged or explicitly retained, never lost.
        # 来自意外外部注册的请求保持已确认或显式保留，绝不丢失。
        self._unowned: dict[str, dict[str, Any]] = {}
        self._tasks: set[asyncio.Task] = set()
        # Futures survive cancellation or closure of any caller-owned asyncio loop.
        # Future 跨越任意调用方 asyncio 循环的取消或关闭而存活。
        self._ready: Future[None] = Future()
        self._closed: Future[None] = Future()
        # The transport prevents a second pump or premature transport free for this exact runtime.
        # 传输阻止此精确运行时的第二个泵或过早传输释放。
        self._transport._claim_callback_pump(runtime_id, self)
        # An owned non-daemon thread keeps live callbacks and library references reachable until real drainage.
        # 拥有型非守护线程在实际排空前保持活动回调及动态库引用可达。
        self._thread = threading.Thread(target=self._thread_main, name="luaskills-callback-pump", daemon=False)
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
        Return SDK ownership diagnostics without inventing native operation or registration terminal states.
        返回 SDK 所有权诊断，不编造原生操作或注册终态。
        """
        with self._lock:
            return {"runtime_id":self._runtime_id, "closing":self._closing,
                "closed":self._closed.done() and self._closed.exception() is None,
                "registration_ids":self._registration_ids, "request_ids":self._request_ids,
                "pending_acknowledgements":self._pending_ack_ids, "pending_commands":self._pending_commands,
                "failure":self._failure}

    def _publish(self) -> None:
        """
        Copy current owned-loop identities into a short-lock diagnostic snapshot.
        将当前拥有循环身份复制到短锁诊断快照。
        """
        with self._lock:
            self._registration_ids = tuple(self._registrations)
            self._request_ids = tuple(self._requests) + tuple(self._unowned)
            self._pending_ack_ids = tuple(key for key, record in self._requests.items() if record.outcome is not None) + tuple(self._unowned)

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
        if not self._registrations and not self._requests and not self._unowned and not self._tasks:
            self._transport._release_callback_pump(self._runtime_id, self)
        if failure is not None:
            self._closed.set_exception(failure)
            if not self._ready.done():
                self._ready.set_exception(failure)
        else:
            self._closed.set_result(None)


    async def _native(self, operation: dict[str, Any]) -> Any:
        """
        Run one short native command off the owned event loop; long operation waits are never issued by this pump.
        在拥有循环之外运行一个短原生命令；此泵绝不发出长操作等待。
        """
        return await self._loop.run_in_executor(self._native_executor, self._transport.request,
            {"type":"runtime", "runtime_id":self._runtime_id, "operation":operation})

    async def _run(self) -> None:
        """
        Validate the runtime, then deliver only available handler capacity and continuously observe cancellation.
        校验运行时，随后仅按可用处理器容量投递，并持续观察取消。
        """
        # Read the known runtime before advertising a ready pump.
        # 在公布事件泵已就绪前读取已知运行时。
        initial = await self._loop.run_in_executor(self._native_executor, self._transport.request,
            {"type":"runtime_status", "runtime_id":self._runtime_id})
        if initial["initialization"] != "ready" or initial["closing"]:
            raise RuntimeError("callback pump requires an initialized open runtime")
        self._ready.set_result(None)
        while True:
            try:
                if self.status["closing"]:
                    async with self._publication:
                        for record in tuple(self._registrations.values()):
                            await self._retire(record)
                else:
                    async with self._publication:
                        # Pending acknowledgements keep their handler slots until accepted by the core.
                        # 待确认结果在核心接受前仍占用处理器名额。
                        available = self._config.max_concurrent_handlers - len(self._requests) - len(self._unowned)
                        if available:
                            batch = await self._native({"type":"host_requests_take", "limit":available})
                            for request in batch:
                                self._dispatch(request)
                for record in tuple(self._requests.values()):
                    async with record.native_lock:
                        if record.outcome is None:
                            current = await self._native({"type":"host_request_status", "request_id":record.context.request_id})
                            if current["cancellation"] is not None:
                                record.context._observe_cancellation(current["cancellation"])
                for record in tuple(self._registrations.values()):
                    if record.retiring:
                        current = await self._native({"type":"capability_status", "registration_id":record.registration_id})
                        if current["drained"] and not any(active.registration is record for active in self._requests.values()):
                            await self._native({"type":"capability_forget", "registration_id":record.registration_id})
                            del self._registrations[record.registration_id]
                            record.drained.set()
                self._publish()
                if not self._registrations and not self._requests and not self._unowned and not self._tasks:
                    with self._lock:
                        if self._closing and self._pending_commands == 0:
                            self._accepting_commands = False
                            return
            except Exception as error:
                self._record_failure(error)
            # Wakeups are advisory; authoritative maps and core status are re-read each iteration.
            # 唤醒仅供通知；每轮重新读取权威映射与核心状态。
            try:
                await asyncio.wait_for(self._wake.wait(), self._config.poll_interval_ms / 1000)
            except asyncio.TimeoutError:
                pass
            self._wake.clear()

    def _dispatch(self, request: dict[str, Any]) -> None:
        """
        Retain every delivered identity before any await so a later batch item can never be lost after earlier failure.
        在任何等待前保留每个已交付身份，使后续批次项不会因前项失败而丢失。
        """
        # Route only immutable registration identity, never a replaceable capability name.
        # 仅路由不可变注册身份，绝不路由可被替换的能力名称。
        registration = self._registrations.get(request["registration_id"])
        if registration is None:
            self._unowned[request["request_id"]] = {
                "ok":False, "error":{"code":"internal", "message":"Python callback registration owner is absent"},
                "effects":"not_started",
            }
            self._record_failure(RuntimeError("delivered callback has no exact Python registration owner"))
            task = self._loop.create_task(self._reject_unowned(request["request_id"]))
        else:
            # Context comes from authenticated metadata, never from application arguments.
            # 上下文来自已认证元数据，绝不来自应用参数。
            context = HostCallbackContext(request, registration.capability.descriptor["effects"], self._loop)
            record = _Request(registration, context, request["arguments"])
            self._requests[context.request_id] = record
            task = self._loop.create_task(self._handle(record))
        self._tasks.add(task)
        task.add_done_callback(self._handler_returned)
        self._publish()


    async def _handle(self, record: _Request) -> None:
        """
        Execute one retained handler, preserve explicit effects on exceptions, and acknowledge only actual return.
        执行一个保留处理器，在异常时保留显式副作用，并仅在真实返回后确认。
        """
        # Context variables also mark copied synchronous worker contexts for future reentry guards.
        # 上下文变量也标记复制后的同步工作线程上下文，供重入防护使用。
        token = HOST_CALLBACK_RUNTIME.set(self._runtime_id)
        try:
            try:
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
                record.outcome = {"ok":True, "value":value, "effects":record.context.effects}
            except BaseException as error:
                # Catch handler failures, including explicit cancellation, without exposing business arguments or secrets.
                # 捕获处理器失败，包含显式取消，不暴露业务参数或秘密。
                failure = {"code":error.code, "message":error.message} if isinstance(error, EmbeddedRuntimeError) else {
                    "code":"execution_failed", "message":f"Python host callback raised {type(error).__name__}"}
                record.outcome = {"ok":False, "error":failure, "effects":record.context.effects}
            try:
                record.encoded_completion = self._encode_completion(record)
            except (TypeError, ValueError, OverflowError, UnicodeError, RecursionError):
                record.outcome = {"ok":False, "error":{"code":"execution_failed",
                    "message":"Python host callback produced an invalid or oversized result"}, "effects":record.context.effects}
                record.encoded_completion = self._encode_completion(record)
            self._publish()
            await self._acknowledge(record)
        finally:
            HOST_CALLBACK_RUNTIME.reset(token)
            self._wake.set()

    async def _acknowledge(self, record: _Request) -> None:
        """
        Serialize completion and retain ownership on uncertain failure; reject results refused before native dispatch.
        串行化完成并在不确定失败时保留所有权；拒绝在原生分发前被拒绝的结果。
        """
        async with record.native_lock:
            if self._requests.get(record.context.request_id) is not record:
                return
            try:
                try:
                    await self._loop.run_in_executor(self._native_executor, self._transport._request_encoded, record.encoded_completion)
                except EmbeddedTransportError as error:
                    # Only request entrypoint InvalidArgument proves that this exact frame was rejected before dispatch.
                    # 仅请求入口的 InvalidArgument 能证明此精确帧在分发前被拒绝。
                    # Result-release failures may follow a successful mutation and must never rewrite that completion.
                    # 结果释放失败可能发生在变更成功后，绝不能改写该完成结果。
                    if error.function_name != "luaskills_ffi_embedded_request_v1" or error.status != EmbeddedNativeStatus.INVALID_ARGUMENT:
                        raise
                    record.outcome = {"ok":False, "error":{"code":"execution_failed",
                        "message":"Python host callback result was rejected by the native parser"},
                        "effects":record.outcome["effects"]}
                    record.encoded_completion = self._encode_completion(record)
                    # A bounded rejection acknowledgement preserves actual effects without executing the handler again.
                    # 有界拒绝确认保留实际副作用，不再次执行处理器。
                    await self._loop.run_in_executor(self._native_executor, self._transport._request_encoded, record.encoded_completion)
            except Exception as error:
                self._record_failure(error)
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
        Publish one core batch and install its exact Python owners before the pump can take those requests.
        发布一个核心批次，并在事件泵能够取得请求前安装精确 Python 所有者。
        """
        async with self._publication:
            result = await self._native({"type":"capabilities_register", "descriptors":[item.descriptor for item in capabilities]})
            identities = tuple(result["registration_ids"])
            if len(identities) != len(capabilities):
                raise RuntimeError("core returned an inconsistent capability registration batch")
            for identity, capability in zip(identities, capabilities):
                self._registrations[identity] = _Registration(capability, identity, False, asyncio.Event())
            self._publish()
        self._wake.set()
        return identities

    async def _retire(self, record: _Registration) -> None:
        """
        Request exact core unregister once, preserving Python closure ownership through later drainage.
        精确请求核心注销一次，并跨后续排空保留 Python 闭包所有权。
        """
        async with record.native_lock:
            if not record.retiring:
                await self._native({"type":"capability_unregister", "registration_id":record.registration_id})
                record.retiring = True

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

    def _submit(self, action: Coroutine[Any, Any, Any], *, drain: bool = False) -> Future:
        """
        Bound submitted SDK commands; their actual owned-loop tasks survive caller observation cancellation.
        限制已提交 SDK 命令；其实际拥有循环任务跨调用方观察取消存活。
        """
        with self._lock:
            if not self._accepting_commands or (self._closing and not drain):
                action.close()
                raise EmbeddedRuntimeError("closed", "Python callback pump is closing")
            if self._pending_commands >= self._config.max_pending_commands:
                action.close()
                raise EmbeddedRuntimeError("capacity_exceeded", "Python callback command capacity is exhausted")
            self._pending_commands += 1
        try:
            future = asyncio.run_coroutine_threadsafe(action, self._loop)
        except BaseException:
            action.close()
            with self._lock:
                self._pending_commands -= 1
            raise
        with self._lock:
            self._command_futures.add(future)
        future.add_done_callback(self._command_returned)
        return future

    def _command_returned(self, future: Future) -> None:
        """
        Release command admission after the actual owned task returned and wake the drainage service.
        实际拥有任务返回后释放命令入场，并唤醒排空服务。
        """
        with self._lock:
            self._pending_commands -= 1
            self._command_futures.discard(future)
        self._loop.call_soon_threadsafe(self._wake.set)

    def _handler_returned(self, task: asyncio.Task) -> None:
        """
        Observe actual handler task return and retain unexpected faults instead of silently dropping task exceptions.
        观察实际处理器任务返回，并保留意外故障，而非静默丢弃任务异常。
        """
        self._tasks.discard(task)
        if task.cancelled():
            self._record_failure(RuntimeError("owned callback task was unexpectedly cancelled"))
        elif task.exception() is not None:
            self._record_failure(task.exception())
        self._wake.set()

    async def _reject_unowned(self, request_id: str) -> None:
        """
        Acknowledge a request with no Python owner as not executed while retaining failed acknowledgements explicitly.
        将没有 Python 所有者的请求确认为未执行，同时显式保留失败确认。
        """
        try:
            await self._native({"type":"host_request_complete", "request_id":request_id, "outcome":self._unowned[request_id]})
        except Exception as error:
            self._record_failure(error)
            return
        del self._unowned[request_id]
        self._publish()

    async def _retry_acknowledgements(self) -> None:
        """
        Reconcile exact completion evidence before explicitly retrying delivery; never invoke a handler again.
        显式重试交付前核对精确完成证据；绝不再次调用处理器。
        """
        for record in tuple(self._requests.values()):
            if record.outcome is None:
                continue
            async with record.native_lock:
                if self._requests.get(record.context.request_id) is not record:
                    continue
                try:
                    status = await self._native({"type":"host_request_status", "request_id":record.context.request_id})
                    completed = status["phase"] == "completed"
                    if status["phase"] == "completing":
                        continue
                except EmbeddedRuntimeError as error:
                    if error.code not in ("not_found", "already_completed"):
                        raise
                    # A consumed record has a bounded tombstone, then expires; neither error alone proves completion.
                    # 已消费记录先保留有界墓碑再过期；两个错误本身均不能证明完成。
                    # Verify the exact original operation effect for both broker-defined absent-record classifications.
                    # 对代理定义的两种记录缺失分类，均校验精确原始操作副作用。
                    operation = await self._native({"type":"operation_status", "operation_id":record.context.caller["operation_id"]})
                    completed = any(effect["request_id"] == record.context.request_id
                        and effect["registration_id"] == record.context.registration_id
                        and effect["phase"] == "completed" for effect in operation["host_effects"])
                    if not completed:
                        raise EmbeddedRuntimeError("not_found", "callback completion evidence is unavailable; native completion cannot be inferred") from error
                if completed:
                    del self._requests[record.context.request_id]
                    self._publish()
                    continue
                if record.encoded_completion is None:
                    record.encoded_completion = self._encode_completion(record)
            await self._acknowledge(record)
        for request_id in tuple(self._unowned):
            await self._reject_unowned(request_id)
        self._wake.set()


    def retry_acknowledgements(self, timeout: float | None = None) -> None:
        """
        Retry only failed acknowledgement delivery; status continues to expose any remaining unresolved identities.
        仅重试失败确认交付；状态继续暴露剩余未解决身份。
        """
        self._check_wait()
        self._wait(self._submit(self._retry_acknowledgements(), drain=True), timeout)

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
    def _wait(future: Future, timeout: float | None) -> Any:
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
    async def _observe(future: Future) -> Any:
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
    def _observe_returned(observer: asyncio.Future) -> None:
        """
        Retrieve delayed exceptions for cancelled observers while leaving normal await result semantics intact.
        为已取消观察者取回延迟异常，同时保持正常等待结果语义。
        """
        if not observer.cancelled():
            observer.exception()
