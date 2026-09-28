"""
Own one known runtime's shutdown without owning its shared transport or command driver.
拥有一个已知运行时的关闭过程，不拥有其共享传输或命令驱动器。
"""

from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import Future
from types import TracebackType
from typing import Any, Literal, cast, get_args

from .embedded_client import EmbeddedRuntime, _POLL_INTERVAL, _validate_interval
from .embedded_driver import EmbeddedCommandDriver
from .embedded_contract import EmbeddedNativeStatus, OutputInitializationPhase
from .embedded_pump import EmbeddedCallbackPump
from .embedded_transport import EmbeddedResultReleaseError, EmbeddedRuntimeError, EmbeddedTransportError


# Checkpoints advance only after an acknowledged native transition, never after observer timeout.
# 检查点仅在原生转换得到确认后推进，绝不因观察超时推进。
_Phase = Literal["open", "closing_runtime", "draining_callbacks", "draining_runtime", "releasing_runtime", "released", "closed"]

# Initialization vocabulary comes from the generated native contract rather than a second lifecycle schema.
# 初始化词汇来自生成的原生契约，不创建第二份生命周期 Schema。
_INITIALIZATION_PHASES = frozenset(get_args(OutputInitializationPhase))


class EmbeddedRuntimeScope:
    """
    Adopt a known runtime and optional existing callback pump for ordered, independently owned shutdown.
    接管已知运行时及可选现有回调泵，执行有序且独立拥有的关闭。
    Context exit requests closure; cancellation and timeouts leave the coordinator and native ownership alive.
    上下文退出请求关闭；取消及超时保持协调器和原生所有权存活。
    """

    def __init__(self, runtime: EmbeddedRuntime, *, pump: EmbeddedCallbackPump | None = None,
                 poll_interval: float = _POLL_INTERVAL) -> None:
        """
        Adopt exact runtime and pump, reserving one native control slot before starting its coordinator.
        接管精确 runtime 和 pump，在启动协调器前预留一个原生控制槽。
        poll_interval controls closed-state polling; return without closing or initializing native resources.
        poll_interval 控制关闭状态轮询；返回时不关闭或初始化原生资源。
        """
        EmbeddedCommandDriver._check_wait()
        _validate_interval(poll_interval, positive=True)
        # The concrete typed-handle chain uniquely identifies the transport that owns this runtime.
        # 具体类型句柄链唯一确定拥有此运行时的传输。
        self._runtime = runtime
        self._transport = runtime._client._driver._transport
        # A supplied pump must be the exact native namespace owner, never merely share a textual ID.
        # 所提供泵必须是精确原生命名空间所有者，不能仅共享文本身份。
        if pump is not None and (pump._transport is not self._transport or pump._runtime_id != runtime.runtime_id):
            raise ValueError("callback pump does not belong to this exact runtime transport")
        self._pump = pump
        self._poll_interval = poll_interval
        # Only local diagnostics and attempt publication use this lock; native calls never hold it.
        # 仅本地诊断及尝试发布使用此锁；原生调用绝不持有它。
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._aborted = False
        # A scope may be entered once; nested or concurrent contexts must not close each other's runtime.
        # 一个作用域只能进入一次；嵌套或并发上下文不得互相关闭运行时。
        self._entered = False
        self._phase: _Phase = "open"
        self._attempt: Future[None] | None = None
        # Each published attempt records explicit recovery intent separately from ordinary close observation.
        # 每个已发布尝试分别记录显式恢复意图与普通关闭观察。
        self._attempt_retry = False
        self._failure: BaseException | None = None
        # A delivered result-release failure permits exact buffer recovery, not mutation replay.
        # 已交付结果的释放失败允许精确缓冲恢复，不允许变更重放。
        self._release_failure = False
        # Missing or invalid copied delivery evidence forbids replaying the last lifecycle mutation.
        # 复制交付证据缺失或无效时，禁止重放最后的生命周期变更。
        self._uncertain_delivery = False
        self._retryable = False
        # Caller and a late-starting aborted thread share one exact claim-release checkpoint.
        # 调用方与迟到启动的中止线程共享一个精确声明释放检查点。
        self._claim_released = False
        # Strong transport ownership bounds the coordinator count and blocks premature DLL release.
        # 强传输所有权限制协调器数量，并阻止过早动态库释放。
        self._thread = threading.Thread(target=self._run, name="luaskills-runtime-scope", daemon=False)
        self._transport._claim_runtime_scope(runtime.runtime_id, self, pump)
        try:
            self._thread.start()
        except BaseException:
            # No native command is admitted before request_close; failed startup can safely return the claim.
            # request_close 前不接纳原生命令；启动失败可安全归还声明。
            with self._lock:
                self._aborted = True
            self._wake.set()
            self._release_claim_once()
            if self._thread.ident is not None:
                self._thread.join()
            raise

    @property
    def runtime(self) -> EmbeddedRuntime:
        """
        Return the adopted handle for normal commands; the scope exclusively owns final slot release.
        返回接管句柄用于普通命令；最终槽释放由作用域独占拥有。
        """
        return self._runtime

    @property
    def status(self) -> dict[str, Any]:
        """
        Return local shutdown checkpoints and callback diagnostics without issuing a native query.
        返回本地关闭检查点及回调诊断，不发起原生查询。
        closed proves slot removal and claim release; close observers additionally join the coordinator.
        closed 证明槽移除及声明释放；关闭观察者另外汇合协调器。
        """
        with self._lock:
            # This fresh snapshot cannot mutate lifecycle state or retained error evidence.
            # 此新快照不能修改生命周期状态及保留错误证据。
            snapshot = {"runtime_id": self.runtime.runtime_id, "phase": self._phase,
                        "closing": self._attempt is not None, "closed": self._phase == "closed",
                        "failure": None if self._failure is None else str(self._failure),
                        "retryable": self._retryable}
        snapshot["callbacks"] = None if self._pump is None else self._pump.status
        return snapshot

    def _set_phase(self, phase: _Phase) -> None:
        """
        Publish acknowledged phase under the diagnostics lock; return without native execution.
        在诊断锁内发布已确认 phase；返回时不执行原生工作。
        """
        with self._lock:
            self._phase = phase

    def _release_claim_once(self) -> None:
        """
        Return the exact ownership claim once across startup interruption and a late aborted coordinator.
        在启动中断及迟到中止协调器之间恰好归还一次精确所有权声明。
        Return nothing; the local checkpoint prevents duplicate release without masking foreign ownership.
        无返回值；本地检查点阻止重复释放，不掩盖其他所有权。
        """
        with self._lock:
            if not self._claim_released:
                self._transport._release_runtime_scope(self.runtime.runtime_id, self)
                self._claim_released = True

    def _validate_control(self, command_type: str, value: Any) -> dict[str, Any]:
        """
        Validate command_type's copied slot identity and consumed lifecycle fields; return the original object.
        校验 command_type 的已复制槽身份及消费的生命周期字段；返回原对象。
        Invalid value cannot advance a checkpoint or authorize replay of a lifecycle mutation.
        无效 value 不能推进检查点，也不能授权重放生命周期变更。
        """
        if type(value) is not dict or value.get("runtime_id") != self.runtime.runtime_id:
            raise RuntimeError("runtime scope control response changed its exact slot identity")
        if command_type == "runtime_status" and (type(value.get("closed")) is not bool
                or type(value.get("initialization")) is not str
                or value["initialization"] not in _INITIALIZATION_PHASES):
            raise RuntimeError("runtime scope control response has invalid lifecycle evidence")
        return cast(dict[str, Any], value)

    def _transition(self, command_type: str, following: _Phase) -> None:
        """
        Execute command_type once and publish following only when its successful delivery is proven.
        执行 command_type 一次，仅在成功交付得到证明后发布 following。
        A copied success survives result-release failure; the failure is still reported for explicit recovery.
        复制的成功结果跨越结果释放失败而保留；仍报告该失败用于显式恢复。
        """
        try:
            result = self._transport.request({"type": command_type, "runtime_id": self.runtime.runtime_id})
        except EmbeddedResultReleaseError as error:
            self._release_failure = True
            # Decode the exact copied response. Missing bytes or a business rejection cannot advance the checkpoint.
            # 解码精确复制响应；字节缺失或业务拒绝不能推进检查点。
            try:
                self._validate_control(command_type, error.delivered_result())
            except EmbeddedRuntimeError:
                raise error
            except BaseException:
                self._uncertain_delivery = True
                raise error
            self._set_phase(following)
            raise
        self._validate_control(command_type, result)
        self._set_phase(following)

    def _drain_callbacks(self, retry: bool) -> None:
        """
        Drain the exact pump or report current recovery needs; retry authorizes its retained delivery recovery.
        排空精确事件泵或报告当前恢复需求；retry 授权恢复其保留交付。
        Return only after its actual coordinator joins, without mistaking historical failure for pending recovery.
        仅在其实际协调器汇合后返回，不将历史失败误认为待恢复状态。
        """
        pump = self._pump
        if pump is None:
            return
        pump.request_close()
        if retry and pump.recovery_required and not pump._closed.done():
            try:
                pump.retry_acknowledgements()
            except EmbeddedRuntimeError as error:
                # Concurrent explicit recovery may finish closure before this observer enters; require actual proof.
                # 并发显式恢复可能在此观察者入场前完成关闭；必须取得实际证明。
                if error.code != "closed" or not pump._closed.done():
                    raise
        while not pump._closed.done():
            if pump.recovery_required:
                raise EmbeddedRuntimeError("busy", "callback pump requires explicit delivery recovery before runtime release")
            time.sleep(self._poll_interval)
        pump.close()

    def _drain(self, retry: bool = False) -> None:
        """
        Resume from the last proven checkpoint; return only after actual pump, core and slot release.
        从最后得到证明的检查点继续；仅在实际泵、核心及槽释放后返回。
        Buffer recovery is an explicit retry action and never resubmits an acknowledged mutation.
        缓冲恢复属于显式重试动作，绝不重新提交已确认变更。
        """
        if self._release_failure:
            self._transport.release_results()
            self._release_failure = False
        if self._phase == "closing_runtime":
            self._transition("runtime_close", "draining_runtime")
        if self._phase == "draining_runtime":
            # Finalizers can create new callbacks after business cancellation; retain the exact pump.
            # 业务取消后关闭函数仍可创建新回调；保留精确事件泵。
            if retry and self._pump is not None and self._pump.recovery_required:
                try:
                    self._pump.retry_acknowledgements()
                except EmbeddedResultReleaseError as error:
                    # The pump owns this failed buffer, so scope recovery must not claim its result journal.
                    # 失败缓冲由事件泵拥有，作用域恢复不得认领其结果日志。
                    raise EmbeddedRuntimeError("busy", "callback pump requires explicit delivery recovery before runtime release") from error
            while True:
                if self._pump is not None and self._pump.recovery_required:
                    raise EmbeddedRuntimeError("busy", "callback pump requires explicit delivery recovery before runtime release")
                # Queries use the scope's reserved slot even when driver receipt quotas are exhausted.
                # 即使驱动器回执配额耗尽，查询仍使用作用域预留槽。
                snapshot = self._transport.request({"type": "runtime_status", "runtime_id": self.runtime.runtime_id})
                snapshot = self._validate_control("runtime_status", snapshot)
                if snapshot["initialization"] == "faulted":
                    raise RuntimeError("faulted initialization prevents proving safe runtime release")
                if snapshot["closed"]:
                    break
                time.sleep(self._poll_interval)
            self._set_phase("draining_callbacks")
        if self._phase == "draining_callbacks":
            self._drain_callbacks(retry)
            self._set_phase("releasing_runtime")
        if self._phase == "releasing_runtime":
            while True:
                try:
                    self._transition("runtime_free", "released")
                    break
                except EmbeddedRuntimeError as error:
                    # The core's busy response proves release was rejected before mutation while leases remain.
                    # 核心 busy 响应证明租约仍在时释放在变更前被拒绝。
                    if error.code != "busy":
                        raise
                    time.sleep(self._poll_interval)
        if self._phase == "released":
            self._release_claim_once()
            self._set_phase("closed")

    def _run(self) -> None:
        """
        Own shutdown attempts independently of caller loops; retain the claim after any unproven failure.
        独立于调用方循环拥有关闭尝试；任何未获证明的失败后保留声明。
        Return after actual closure or failed startup; explicit result recovery reuses this same coordinator.
        在实际关闭或启动失败后返回；显式结果恢复复用同一协调器。
        """
        while True:
            self._wake.wait()
            self._wake.clear()
            with self._lock:
                # Publication precedes wake-up; only startup abort has no close-attempt future.
                # 发布先于唤醒；只有启动中止没有关闭尝试 future。
                aborted = self._aborted
                attempt = self._attempt
                retry = self._attempt_retry
            if aborted:
                self._release_claim_once()
                return
            assert attempt is not None
            try:
                self._drain(retry)
            except BaseException as error:
                # Pump recovery owns its own journals and buffers; a busy drainage observer can safely retry.
                # 泵恢复拥有自己的日志及缓冲；繁忙排空观察者可以安全重试。
                callback_recovery = (self._phase in ("draining_callbacks", "draining_runtime") and self._pump is not None
                    and ((isinstance(error, EmbeddedRuntimeError) and error.code == "busy")
                         or (not self._pump._closed.done() and self._pump.recovery_required)))
                with self._lock:
                    self._failure = error
                    self._release_failure = self._release_failure or (
                        self._phase != "draining_callbacks" and isinstance(error, EmbeddedResultReleaseError))
                    # Successful root mutations use pre-encoded receipts; queries are read-only and close is idempotent.
                    # 成功的根变更使用预编码回执；查询只读且关闭幂等。
                    # Capacity refusal on these controls cannot hide a successful slot removal.
                    # 这些控制的容量拒绝不能掩盖已经成功的槽移除。
                    capacity_rejected = (isinstance(error, EmbeddedTransportError)
                        and error.function_name == "luaskills_ffi_embedded_request_v1"
                        and error.status == EmbeddedNativeStatus.CAPACITY_EXCEEDED)
                    self._retryable = (self._release_failure and not self._uncertain_delivery) or capacity_rejected or callback_recovery
                    attempt.set_exception(error)
            else:
                with self._lock:
                    self._failure = None
                    self._retryable = False
                    attempt.set_result(None)
                return

    def _request(self, retry: bool) -> Future[None]:
        """
        Publish or observe one shutdown attempt; retry explicitly resumes buffers, callback recovery or root-control capacity rejection.
        发布或观察一次关闭尝试；retry 显式恢复缓冲、回调恢复或根控制容量拒绝。
        Return a strongly retained future; ordinary repeated close never retries an uncertain native command.
        返回强引用保留 future；普通重复关闭绝不重试不确定原生命令。
        """
        EmbeddedCommandDriver._check_wait()
        with self._lock:
            if self._attempt is None:
                self._attempt = Future()
                self._phase = "closing_runtime"
                self._wake.set()
            elif retry and self._attempt.done() and self._phase != "closed":
                if not self._retryable:
                    raise RuntimeError("runtime scope failure lacks evidence for a safe retry") from self._failure
                self._attempt = Future()
                self._failure = None
                self._attempt_retry = True
                self._retryable = False
                self._wake.set()
            return self._attempt

    def request_close(self) -> None:
        """
        Start owned shutdown and return without waiting for callbacks, native workers or VM destruction.
        启动拥有型关闭并返回，不等待回调、原生工作线程或 VM 销毁。
        """
        self._request(False)

    def close(self, timeout: float | None = None) -> None:
        """
        Observe owned closure for timeout seconds and join its thread; timeout does not stop cleanup.
        在 timeout 秒内观察拥有型关闭并汇合线程；超时不停止清理。
        Return after actual release; retained failures require diagnosis rather than implicit mutation replay.
        在实际释放后返回；保留失败需要诊断，而非隐式变更重放。
        """
        if timeout is not None:
            _validate_interval(timeout, positive=False)
        EmbeddedCommandDriver._wait(self._request(False), timeout)
        self._thread.join()

    async def close_async(self) -> None:
        """
        Await owned closure and thread join; cancelling this observer leaves cleanup active.
        等待拥有型关闭及线程汇合；取消此观察者保持清理活动。
        """
        await EmbeddedCommandDriver._observe(self._request(False))
        await asyncio.to_thread(self._thread.join)

    def retry_close(self, timeout: float | None = None) -> None:
        """
        Explicitly recover retained transport result buffers and continue from proven checkpoints within timeout.
        在 timeout 内显式恢复保留传输结果缓冲，并从已证明检查点继续。
        Shared transport recovery rejects active readers; it never repeats an acknowledged close or free.
        共享传输恢复拒绝活动读取者；绝不重复已确认关闭或释放。
        """
        if timeout is not None:
            _validate_interval(timeout, positive=False)
        EmbeddedCommandDriver._wait(self._request(True), timeout)
        self._thread.join()

    async def retry_close_async(self) -> None:
        """
        Observe explicit buffer recovery without caller-loop ownership; return after the coordinator joins.
        不把所有权交给调用方循环地观察显式缓冲恢复；在协调器汇合后返回。
        """
        await EmbeddedCommandDriver._observe(self._request(True))
        await asyncio.to_thread(self._thread.join)

    def __enter__(self) -> EmbeddedRuntimeScope:
        """
        Enter this open scope and return its owner; use runtime for initialization and normal commands.
        进入此开放作用域并返回其所有者；通过 runtime 初始化及执行普通命令。
        """
        EmbeddedCommandDriver._check_wait()
        with self._lock:
            if self._attempt is not None:
                raise RuntimeError("embedded runtime scope is already closing")
            if self._entered:
                raise RuntimeError("embedded runtime scope cannot be entered more than once")
            self._entered = True
        return self

    def __exit__(self, kind: type[BaseException] | None, error: BaseException | None,
                 traceback: TracebackType | None) -> None:
        """
        Close on normal or exceptional exit; kind, error and traceback are never suppressed.
        在正常或异常退出时关闭；绝不抑制 kind、error 和 traceback。
        """
        self.close()

    async def __aenter__(self) -> EmbeddedRuntimeScope:
        """
        Enter without blocking the caller loop; return the same explicit runtime owner.
        不阻塞调用方循环地进入；返回同一个显式运行时所有者。
        """
        return self.__enter__()

    async def __aexit__(self, kind: type[BaseException] | None, error: BaseException | None,
                        traceback: TracebackType | None) -> None:
        """
        Request cleanup even when the body failed; cancellation during exit never abandons the coordinator.
        即使代码体失败也请求清理；退出期间取消绝不放弃协调器。
        The body's kind, error and traceback remain unsuppressed after successful cleanup.
        成功清理后不抑制代码体的 kind、error 和 traceback。
        """
        await self.close_async()
