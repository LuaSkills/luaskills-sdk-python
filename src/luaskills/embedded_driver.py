"""
Bounded, owned asynchronous native commands with separately reserved lifecycle control capacity.
有界且拥有型的异步原生命令，单独预留生命周期控制容量。
"""

from __future__ import annotations

import asyncio
import copy
import json
import sys
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Any, Mapping, cast

from .embedded_callbacks import HOST_CALLBACK_RUNTIME
from .embedded_contract import EMBEDDED_ROOT_COMMANDS, EMBEDDED_RUNTIME_COMMANDS
from .embedded_transport import EMBEDDED_CONTROL_WORKERS, EmbeddedRuntimeError, EmbeddedTransport


# These short lifecycle queries/mutations get their own lane; new business commands use the work lane.
# 这些短生命周期查询／变更拥有独立通道；新增业务命令使用工作通道。
_ROOT_CONTROLS = frozenset({"describe", "runtime_status", "runtime_close", "runtime_free"})
_RUNTIME_CONTROLS = frozenset({
    "capacity_status", "capacity_close", "capacity_forget",
    "plugin_status", "plugin_close", "plugin_forget", "pool_status", "pool_close", "pool_forget",
    "pool_revoke_permission", "session_status", "session_close", "session_forget",
    "operation_status", "operation_list", "operation_cancel", "operation_forget", "capabilities_list",
    "capability_status", "capability_unregister", "capability_forget", "host_requests_take",
    "host_request_status", "host_request_complete",
    "operation_persistence_failure", "operation_retry_checkpoint", "storage_status",
})


@dataclass(frozen=True, kw_only=True)
class EmbeddedDriverConfig:
    """
    Bound worker concurrency and retained command receipts independently for work and lifecycle control.
    分别限制工作与生命周期控制的工作线程并发及保留命令回执。
    Completed commands still occupy their lane's quota until explicitly forgotten.
    已完成命令在显式遗忘前仍占用其通道配额。
    """

    # Concurrent native work requests; Lua execution itself remains governed by core budgets.
    # 并发原生工作请求；Lua 执行本身仍受核心预算治理。
    work_threads: int
    # Work commands retained across queued, running and completed phases.
    # 跨排队、运行及完成阶段保留的工作命令数。
    max_work_commands: int
    # Separately reserved short control commands, including their completed receipts.
    # 单独预留的短控制命令数，包含其已完成回执。
    max_control_commands: int

    def __post_init__(self) -> None:
        """
        Validate positive integral bounds and worker/retention relationships before allocating threads.
        分配线程前验证正整数边界及工作线程／保留数量关系。
        Return nothing; booleans, overflow and impossible budgets raise ValueError.
        无返回值；布尔值、溢出及不可能的预算抛出 ValueError。
        """
        for value in (self.work_threads, self.max_work_commands, self.max_control_commands):
            if type(value) is not int or not 0 < value <= sys.maxsize:
                raise ValueError("embedded driver budgets must be positive platform-sized integers")
        if self.work_threads > self.max_work_commands:
            raise ValueError("work_threads cannot exceed max_work_commands")


class EmbeddedCommand:
    """
    Retain one exact native command and its eventual result independently of every observing event loop.
    独立于每个观察事件循环，保留一个精确原生命令及其最终结果。
    This handle cancels neither native execution nor Lua operations when an observer times out or cancels.
    当观察者超时或取消时，此句柄既不取消原生执行，也不取消 Lua 操作。
    """

    def __init__(self, driver: EmbeddedCommandDriver, command_id: int, control: bool, encoded: bytes) -> None:
        """
        Bind driver-local command_id, lane and frozen encoded bytes before native submission.
        在原生提交前绑定驱动器局部 command_id、通道及冻结 encoded 字节。
        Return an owned receipt whose private future can only be completed by the native driver.
        返回其私有 future 只能由原生驱动器完成的拥有型回执。
        """
        # The driver retains this exact object until explicit forget; this is not a core runtime identity.
        # 驱动器保留此精确对象直到显式遗忘；这不是核心运行时身份。
        self._driver = driver
        self._command_id = command_id
        self._control = control
        self._encoded = encoded
        self._future: Future[Any] = Future()

    @property
    def command_id(self) -> int:
        """
        Return the immutable driver-local receipt identity for recovery after an observer is cancelled.
        返回不可变驱动器局部回执身份，供观察者取消后恢复。
        The integer is local Python metadata and is never serialized as a native authority.
        此整数为 Python 局部元数据，绝不序列化为原生权威。
        """
        return self._command_id

    @property
    def done(self) -> bool:
        """
        Return whether actual native execution, response decoding and result release have returned.
        返回实际原生执行、响应解码及结果释放是否已经返回。
        A true result may carry an explicit release error whose buffer is still owned by the transport.
        返回真仍可能包含显式释放错误，其缓冲仍由传输拥有。
        """
        return self._future.done()

    @property
    def request(self) -> dict[str, Any]:
        """
        Decode a fresh diagnostic copy of the frozen command, without exposing mutable queued bytes.
        解码冻结命令的新诊断副本，不暴露可变排队字节。
        Return the exact root command that this receipt submitted.
        返回此回执提交的精确根命令。
        """
        return cast(dict[str, Any], json.loads(self._encoded)["command"])

    def result(self, timeout: float | None = None) -> Any:
        """
        Observe the native receipt for timeout seconds, preserving its result and admission on timeout.
        在 timeout 秒内观察原生回执；超时时保留其结果及入场配额。
        Return the decoded result or raise the retained error; Lua terminal state requires operation queries.
        返回解码结果或抛出保留错误；Lua 终态需要操作查询。
        """
        self._driver._check_wait()
        # Application mutation must not rewrite the retained receipt observed by another caller.
        # 应用修改不得改写其他调用方观察到的保留回执。
        return copy.deepcopy(self._driver._wait(self._future, timeout))

    async def result_async(self) -> Any:
        """
        Await the receipt without blocking the caller loop or propagating observer cancellation into native work.
        等待回执，不阻塞调用方循环，也不将观察者取消传播到原生工作。
        Return the actual result; cancelled observers may later reattach using this handle or driver.commands.
        返回实际结果；已取消观察者可通过此句柄或 driver.commands 重新观察。
        """
        self._driver._check_wait()
        return copy.deepcopy(await self._driver._observe(self._future))

    def forget(self) -> None:
        """
        Release this completed receipt's driver quota without forgetting any core operation or runtime.
        释放此已完成回执的驱动器配额，不遗忘任何核心操作或运行时。
        Return nothing; running or foreign receipts cannot be forgotten.
        无返回值；运行中或外来回执不可遗忘。
        """
        self._driver._forget(self)


class EmbeddedCommandDriver:
    """
    Own bounded native commands and separate lifecycle workers until real executor shutdown completes.
    拥有有界原生命令及独立生命周期工作线程，直到实际执行器关闭完成。
    The caller still closes core runtimes and callback pumps explicitly; this driver owns only FFI work.
    调用方仍显式关闭核心运行时和回调泵；此驱动器仅拥有 FFI 工作。
    """

    def __init__(self, transport: EmbeddedTransport, config: EmbeddedDriverConfig) -> None:
        """
        Claim transport and create bounded work/control executors plus an owned shutdown coordinator.
        声明 transport 所有权，并创建有界工作／控制执行器及拥有型关闭协调线程。
        Return a live driver with no native commands executed and no implicit runtime construction.
        返回尚未执行原生命令且未隐式构造运行时的活动驱动器。
        """
        # The lock governs receipt publication and shutdown admission, never native request execution.
        # 锁治理回执发布及关闭入场，绝不治理原生请求执行。
        self._lock = threading.Lock()
        self._transport = transport
        self._config = config
        self._commands: dict[int, EmbeddedCommand] = {}
        self._next_id = 1
        self._closing = False
        self._closed: Future[None] = Future()
        # Prepare the closer before accepting commands so shutdown never depends on creating another thread.
        # 接纳命令前准备关闭线程，使关闭不依赖再次创建线程。
        self._close_requested = threading.Event()
        self._close_lock = threading.Lock()
        self._closer = threading.Thread(target=self._await_close, name="luaskills-command-close", daemon=False)
        # Two quotas and executors prevent retained work receipts or slow initialization from starving control.
        # 两套配额与执行器防止保留工作回执或缓慢初始化耗尽控制能力。
        self._work = ThreadPoolExecutor(max_workers=config.work_threads, thread_name_prefix="luaskills-command")
        self._control = ThreadPoolExecutor(max_workers=EMBEDDED_CONTROL_WORKERS, thread_name_prefix="luaskills-control")
        try:
            transport._claim_command_driver(self, config.work_threads + EMBEDDED_CONTROL_WORKERS)
        except BaseException:
            self._work.shutdown(wait=True)
            self._control.shutdown(wait=True)
            raise
        try:
            self._closer.start()
        except BaseException:
            # A start interruption may follow real thread creation; both cleanup paths share one completion owner.
            # 启动中断可能发生在实际线程创建后；两个清理路径共享一个完成所有者。
            self._closing = True
            self._close_requested.set()
            self._finish_close()
            raise


    @property
    def commands(self) -> tuple[EmbeddedCommand, ...]:
        """
        Return exact retained receipt objects in submission order, including errors and abandoned observers.
        按提交顺序返回精确保留回执对象，包含错误及已放弃的观察者。
        This snapshot is SDK ownership evidence, not an inferred native operation state.
        此快照是 SDK 所有权证据，不是推断的原生操作状态。
        """
        with self._lock:
            return tuple(self._commands.values())

    @staticmethod
    def _check_wait() -> None:
        """
        Reject nested driver work from a host callback until controlled dependency tracking is supported.
        在支持受控依赖追踪前，拒绝宿主回调中的嵌套驱动器工作。
        Return nothing; callbacks must not construct a cross-runtime wait cycle through this driver.
        无返回值；回调不得通过此驱动器构造跨运行时等待环。
        """
        if HOST_CALLBACK_RUNTIME.get() is not None:
            raise EmbeddedRuntimeError("unsupported", "nested embedded command driver calls from host callbacks are not supported")

    def submit(self, command: Mapping[str, Any]) -> EmbeddedCommand:
        """
        Freeze command and retain a bounded receipt before native admission; return without waiting for FFI.
        在原生入场前冻结 command 并保留有界回执；返回时不等待 FFI。
        Classify short controls into their reserved lane; blocking operation_wait is explicitly unsupported.
        将短控制命令归入预留通道；明确不支持阻塞 operation_wait。
        """
        self._check_wait()
        with self._lock:
            if self._closing:
                raise RuntimeError("embedded command driver is closing")
            # Routing uses the exact frozen bytes, so caller mutation cannot redirect a queued command's lane.
            # 路由使用精确冻结字节，调用方修改无法重定向排队命令的通道。
            encoded = self._transport._encode_request(command)
            frozen = json.loads(encoded)["command"]
            root_type = frozen.get("type")
            if root_type not in EMBEDDED_ROOT_COMMANDS:
                raise ValueError("unknown embedded root command")
            control = root_type in _ROOT_CONTROLS
            if root_type == "runtime":
                operation = frozen["operation"]
                kind = operation.get("type")
                if kind not in EMBEDDED_RUNTIME_COMMANDS:
                    raise ValueError("unknown embedded runtime command")
                if kind == "operation_wait":
                    raise EmbeddedRuntimeError("unsupported", "use operation_status polling without occupying a native command worker")
                control = kind in _RUNTIME_CONTROLS
            limit = self._config.max_control_commands if control else self._config.max_work_commands
            if sum(item._control == control for item in self._commands.values()) >= limit:
                raise EmbeddedRuntimeError("capacity_exceeded", "embedded command receipt quota is full; forget completed receipts explicitly")
            # Publish before executor submission; even an interrupted submit leaves a discoverable receipt.
            # 在提交执行器前发布；即使提交被中断，也留下可发现回执。
            receipt = EmbeddedCommand(self, self._next_id, control, encoded)
            self._next_id += 1
            self._commands[receipt.command_id] = receipt
            try:
                (self._control if control else self._work).submit(self._execute, receipt)
            except BaseException as error:
                # Execution takes this same lock before marking running, so a queued orphan cannot start later.
                # 执行在标记运行前取得此同一把锁，因此排队孤儿无法稍后开始。
                receipt._future.set_exception(error)
                raise
            return receipt

    def _execute(self, receipt: EmbeddedCommand) -> None:
        """
        Execute receipt's frozen native request once and publish its actual result or error to its owned future.
        执行 receipt 冻结的原生请求一次，并向其拥有 future 发布实际结果或错误。
        Return only after native result cleanup; retained receipt quota remains until explicit forget.
        仅在原生结果清理后返回；保留回执配额持续到显式遗忘。
        """
        with self._lock:
            if receipt._future.done():
                return
            receipt._future.set_running_or_notify_cancel()
        try:
            # No long-held SDK lock spans the C call, allowing lifecycle control to execute concurrently.
            # 不使用 SDK 长锁跨越 C 调用，使生命周期控制能够并发执行。
            result = self._transport._request_encoded(receipt._encoded)
        except BaseException as error:
            receipt._future.set_exception(error)
        else:
            receipt._future.set_result(result)

    def _forget(self, receipt: EmbeddedCommand) -> None:
        """
        Remove only this driver's exact completed receipt, preserving active workers and unrelated records.
        仅移除此驱动器的精确已完成回执，保留活动工作线程及无关记录。
        Return nothing; duplicate forget and unfinished receipts fail explicitly.
        无返回值；重复遗忘及未完成回执明确失败。
        """
        with self._lock:
            if self._commands.get(receipt.command_id) is not receipt:
                raise RuntimeError("embedded command receipt is not retained by this driver")
            if not receipt.done:
                raise RuntimeError("embedded command is still running or queued")
            del self._commands[receipt.command_id]

    def request_close(self) -> None:
        """
        Fence all command admission and wake the prestarted closer without cancelling accepted work.
        封闭全部命令入场并唤醒预先启动的关闭线程，不取消已接纳工作。
        Return immediately; native workers and transport ownership persist until actual shutdown.
        立即返回；原生工作线程及传输所有权保留到实际关闭。
        """
        self._check_wait()
        with self._lock:
            # Repeated calls republish the event even if a previous caller was interrupted after fencing admission.
            # 重复调用再次发布事件，即使先前调用方在封闭入场后被中断。
            self._closing = True
            self._close_requested.set()


    def _await_close(self) -> None:
        """
        Wait on the owned shutdown event independently of caller event loops, then join actual native workers.
        独立于调用方事件循环等待拥有型关闭事件，然后汇合实际原生工作线程。
        Return after the single completion owner has finished; this coordinator never issues native requests.
        在单个完成所有者结束后返回；此协调线程绝不发出原生请求。
        """
        self._close_requested.wait()
        self._finish_close()

    def _finish_close(self) -> None:
        """
        Join both real native executors once, release the exact transport claim and publish actual closure.
        只汇合一次两个实际原生执行器，释放精确传输所有权并发布实际关闭。
        Retain the claim if shutdown fails; constructor recovery and the closer cannot release twice.
        若关闭失败则保留所有权；构造恢复及关闭线程不能重复释放。
        """
        with self._close_lock:
            if self._closed.done():
                return
            try:
                self._work.shutdown(wait=True)
                self._control.shutdown(wait=True)
                self._transport._release_command_driver(self)
            except BaseException as error:
                self._closed.set_exception(error)
            else:
                self._closed.set_result(None)


    def close(self, timeout: float | None = None) -> None:
        """
        Request driver closure and observe actual executor drainage for timeout seconds.
        请求驱动器关闭，并在 timeout 秒内观察实际执行器排空。
        Return after joined workers; TimeoutError leaves the owned closer active and receipts queryable.
        在工作线程汇合后返回；TimeoutError 保持拥有型关闭线程活动且回执可查询。
        """
        self.request_close()
        self._wait(self._closed, timeout)
        self._closer.join()

    async def close_async(self) -> None:
        """
        Await actual executor shutdown without allowing caller cancellation to abandon the closer.
        等待实际执行器关闭，不允许调用方取消放弃关闭线程。
        Return after native workers have joined; this does not close core runtimes or callback pumps.
        在原生工作线程汇合后返回；这不关闭核心运行时或回调泵。
        """
        self.request_close()
        await self._observe(self._closed)
        await asyncio.to_thread(self._closer.join)

    @staticmethod
    def _wait(future: Future[Any], timeout: float | None) -> Any:
        """
        Observe future without cancellation and normalize Python 3.10's distinct futures timeout exception.
        不取消地观察 future，并规范化 Python 3.10 独立的 futures 超时异常。
        Return the retained result or raise built-in TimeoutError, preserving future ownership.
        返回保留结果或抛出内置 TimeoutError，同时保留 future 所有权。
        """
        try:
            return future.result(timeout)
        except FutureTimeoutError as error:
            raise TimeoutError("embedded command observation timed out") from error

    @staticmethod
    async def _observe(future: Future[Any]) -> Any:
        """
        Shield a caller-loop observer while the actual future stays owned by a driver receipt or closer.
        屏蔽调用方循环观察者，同时实际 future 继续由驱动器回执或关闭线程拥有。
        Return its result; caller cancellation never cancels the original concurrent future.
        返回其结果；调用方取消绝不取消原始并发 future。
        """
        # Consume abandoned observer errors without changing the retained concurrent future's result.
        # 消费已放弃观察者的错误，不改变保留并发 future 的结果。
        observer = asyncio.wrap_future(future)
        observer.add_done_callback(EmbeddedCommandDriver._observer_returned)
        return await asyncio.shield(observer)

    @staticmethod
    def _observer_returned(observer: asyncio.Future[Any]) -> None:
        """
        Consume a detached loop observer's exception after completion without discarding its owned receipt.
        在完成后消费已分离循环观察者的异常，不丢弃其拥有型回执。
        Return nothing and leave explicitly cancelled observer futures untouched.
        无返回值，并保持显式取消的观察者 future 不变。
        """
        if not observer.cancelled():
            observer.exception()
