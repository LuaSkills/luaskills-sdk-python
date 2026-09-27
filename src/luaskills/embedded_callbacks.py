"""
Host callback declarations and cooperative context for the embedded runtime queue.
嵌入式运行时队列的宿主回调声明与协作上下文。
"""

from __future__ import annotations

import asyncio
import contextvars
import copy
import threading
import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Literal, Mapping, get_args

from .embedded_contract import OutputEffectState as EffectState
from .embedded_transport import EmbeddedRuntimeError


# A callback's active runtime identity also travels into its synchronous worker context.
# 回调的活动运行时身份也传入其同步工作线程上下文。
HOST_CALLBACK_RUNTIME: contextvars.ContextVar[str | None] = contextvars.ContextVar("luaskills_host_callback_runtime", default=None)


@dataclass(frozen=True)
class HostCapability:
    """
    Bind an explicit queued core descriptor to one retained Python handler and its declared execution mode.
    将显式队列核心描述符绑定到一个保留的 Python 处理器及其声明执行模式。
    """

    # Exact core declaration; the pump copies it before native publication.
    # 精确核心声明；事件泵在原生发布前复制。
    descriptor: Mapping[str, Any]
    # Handler receives application arguments and a trusted HostCallbackContext.
    # 处理器接收应用参数及可信 HostCallbackContext。
    handler: Callable[[Any, HostCallbackContext], Any]
    # Sync handlers execute in bounded workers; async handlers execute on the pump-owned event loop.
    # 同步处理器在有界工作线程执行；异步处理器在事件泵拥有的循环执行。
    mode: Literal["sync", "async"]

    def __post_init__(self) -> None:
        """
        Validate the Python handler contract before core registration can publish any identity.
        在核心注册能发布任何身份前校验 Python 处理器契约。
        """
        if self.mode not in ("sync", "async") or not callable(self.handler):
            raise ValueError("host capability requires a callable and explicit sync or async mode")
        if self.descriptor.get("execution") != "queued":
            raise ValueError("Python host capabilities require explicitly queued execution")

    def snapshot(self) -> HostCapability:
        """
        Copy the caller's declaration while retaining the exact handler object without wrapping its identity.
        复制调用方声明，同时保留精确处理器对象，不包装其身份。
        """
        return HostCapability(copy.deepcopy(dict(self.descriptor)), self.handler, self.mode)


class HostCallbackContext:
    """
    Trusted immutable caller identity, cooperative cancellation and explicit host effect evidence.
    可信不可变调用方身份、协作取消及显式宿主副作用证据。
    """

    def __init__(self, request: Mapping[str, Any], effects: str, loop: asyncio.AbstractEventLoop) -> None:
        """
        Bind one actual delivered request and its descriptor effects to the pump's owned event loop.
        将一个实际已交付请求及其描述符副作用绑定到事件泵拥有的循环。
        """
        if effects not in ("read_only", "mutating"):
            raise ValueError("unknown capability effects declaration")
        # Exact core-generated request and registration identities.
        # 精确核心生成的请求与注册身份。
        self._request_id = request["request_id"]
        self._registration_id = request["registration_id"]
        # Caller authority is separate from freely mutable application arguments.
        # 调用方权威独立于可自由修改的应用参数。
        self._caller = MappingProxyType(copy.deepcopy(request["caller"]))
        # Remaining time is advisory; the core retains its original authoritative deadline.
        # 剩余时间仅供参考；核心保留其原始权威截止时间。
        self._deadline = time.monotonic() + request["remaining_ms"] / 1000
        # Explicit effect evidence is shared safely with synchronous callback workers.
        # 显式副作用证据与同步回调工作线程安全共享。
        self._lock = threading.Lock()
        self._effects: EffectState = "not_applicable" if effects == "read_only" else "unknown"
        self._cancellation: Mapping[str, str] | None = None
        # Both waiting forms observe one cancellation publication from the core status channel.
        # 两种等待形式观察来自核心状态通道的同一次取消发布。
        self._cancelled = threading.Event()
        self._async_cancelled = asyncio.Event()
        self._loop = loop

    @property
    def request_id(self) -> str:
        """
        Return the immutable core request identity used for exact completion acknowledgement.
        返回用于精确完成确认的不可变核心请求身份。
        """
        return self._request_id

    @property
    def registration_id(self) -> str:
        """
        Return the immutable registration identity that selected this exact retained handler.
        返回选择此精确保留处理器的不可变注册身份。
        """
        return self._registration_id

    @property
    def caller(self) -> Mapping[str, Any]:
        """
        Return the read-only trusted caller fields without granting application arguments mutation authority.
        返回只读可信调用方字段，不授予应用参数修改权威的能力。
        """
        return self._caller

    @property
    def effects(self) -> EffectState:
        """
        Return the host's last explicit effect report, including after a handler raises an exception.
        返回宿主最近的显式副作用报告，包含处理器抛出异常之后。
        """
        with self._lock:
            return self._effects

    def report_effects(self, effects: EffectState) -> None:
        """
        Record actual transaction evidence; callers must not infer this value from cancellation or success.
        记录实际事务证据；调用方不得从取消或成功推断此值。
        """
        if effects not in get_args(EffectState):
            raise ValueError("unknown host effect state")
        with self._lock:
            self._effects = effects

    @property
    def cancellation(self) -> Mapping[str, str] | None:
        """
        Return the first observed core cancellation reason without declaring that the handler has stopped.
        返回首次观察到的核心取消原因，不宣称处理器已停止。
        """
        with self._lock:
            return self._cancellation

    @property
    def remaining_ms(self) -> int:
        """
        Return nonnegative advisory remaining milliseconds derived from the original delivered budget.
        返回从原始已交付预算派生的非负参考剩余毫秒数。
        """
        return max(0, int((self._deadline - time.monotonic()) * 1000))

    def raise_if_cancelled(self) -> None:
        """
        Raise the exact observed cancellation error; raising does not imply any effect rollback.
        抛出精确观察到的取消错误；抛出不代表任何副作用回滚。
        """
        # Read once so error code and message share the same immutable publication.
        # 只读一次，使错误码及消息共享同一不可变发布。
        reason = self.cancellation
        if reason is not None:
            raise EmbeddedRuntimeError(reason["code"], reason["message"])

    def wait_cancelled(self, timeout: float | None = None) -> bool:
        """
        Block a synchronous handler until cancellation or timeout; never block the pump's async event loop.
        阻塞同步处理器直到取消或超时；绝不阻塞事件泵异步循环。
        """
        try:
            # A running loop identifies an async handler that must use the nonblocking form.
            # 活动循环表示异步处理器，必须使用非阻塞形式。
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self._loop:
            raise RuntimeError("use wait_cancelled_async inside an async host handler")
        return self._cancelled.wait(timeout)

    async def wait_cancelled_async(self) -> None:
        """
        Await cancellation on this callback's owned loop without cancelling or abandoning native work.
        在此回调拥有的循环上等待取消，不取消或放弃原生工作。
        """
        if asyncio.get_running_loop() is not self._loop:
            raise RuntimeError("callback cancellation must be awaited on its owning event loop")
        await self._async_cancelled.wait()

    def _observe_cancellation(self, reason: Mapping[str, str]) -> None:
        """
        Publish the first authoritative core cancellation to both sync and async waiters on the owning loop.
        在拥有循环上向同步与异步等待方发布首次权威核心取消。
        """
        with self._lock:
            if self._cancellation is not None:
                return
            self._cancellation = MappingProxyType(dict(reason))
        self._cancelled.set()
        self._async_cancelled.set()
