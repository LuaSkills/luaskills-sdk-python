"""
Owned, thread-safe bindings for the version-one embedded runtime transport.
版本一嵌入式运行时传输的拥有型、线程安全绑定。
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import threading
from dataclasses import dataclass, fields
from typing import Any, Mapping

from .ffi import FfiBorrowedBuffer, resolve_library_path


# The version selected by these exact five native entrypoints; never negotiate a legacy fallback.
# 这五个精确原生入口选择的版本；绝不协商旧协议兜底。
EMBEDDED_PROTOCOL_VERSION = 1


class EmbeddedTransportError(RuntimeError):
    """
    Preserve the native function name and integer status for a failed transport operation.
    为失败传输操作保留原生函数名称和整数状态码。
    """

    def __init__(self, function_name: str, status: int) -> None:
        """
        Store exact native failure evidence; constructing this error performs no retries.
        保存精确原生失败证据；构造此错误不执行重试。
        """
        # The concrete entrypoint that failed.
        # 失败的具体入口。
        self.function_name = function_name
        # Stable native return code, separate from core business error codes.
        # 稳定原生返回码，独立于核心业务错误码。
        self.status = status
        super().__init__(f"{function_name} failed with embedded transport status {status}")


class EmbeddedRuntimeError(RuntimeError):
    """
    Preserve a delivered core business failure independently of native transport success.
    独立于原生传输成功，保留已交付的核心业务失败。
    """

    def __init__(self, code: str, message: str) -> None:
        """
        Store the core's exact code and English diagnostic without inferring operation effects.
        保存核心精确错误码及英文诊断，不推断操作副作用。
        """
        # Exact structured core error code.
        # 精确结构化核心错误码。
        self.code = code
        # Exact diagnostic supplied by the native core.
        # 原生核心提供的精确诊断。
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, kw_only=True)
class EmbeddedTransportConfig:
    """
    Explicit positive transport budgets; core validation remains authoritative for their relationships.
    显式正数传输预算；预算之间的关系仍以核心校验为权威。
    """

    # Retained runtime registrations, including failed or draining registrations.
    # 保留的运行时注册，包含失败或正在排空的注册。
    max_runtimes: int
    # Published results and in-flight response reservations together.
    # 已发布结果与在途响应预留的合计数量。
    max_result_buffers: int
    # Published bytes plus worst-case bytes reserved by active requests.
    # 已发布字节与活动请求预留的最坏情况字节。
    max_result_bytes: int
    # Maximum complete response frame size, including its JSON envelope.
    # 完整响应帧最大大小，包含 JSON 信封。
    max_response_bytes: int
    # Maximum encoded UTF-8 request size.
    # 最大已编码 UTF-8 请求大小。
    max_request_bytes: int

    def __post_init__(self) -> None:
        """
        Reject non-integers and values that ctypes would wrap before native validation.
        在原生校验前拒绝非整数及 ctypes 会回绕的数值。
        """
        for field in fields(self):
            # Raw caller value is checked before any C integer conversion.
            # 在任何 C 整数转换前检查调用方原始值。
            value = getattr(self, field.name)
            if type(value) is not int or not 0 < value <= sys.maxsize:
                raise ValueError(f"{field.name} must be a positive integer no greater than {sys.maxsize}")


class _NativeConfig(ctypes.Structure):
    """
    Exact FfiEmbeddedTransportConfigV1 layout from the matching public core header.
    来自匹配核心公开头文件的精确 FfiEmbeddedTransportConfigV1 布局。
    """

    # Field order and C widths are part of the versioned ABI.
    # 字段顺序与 C 位宽属于版本化 ABI。
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("protocol_version", ctypes.c_uint32),
        ("max_runtimes", ctypes.c_uint64),
        ("max_result_buffers", ctypes.c_uint64),
        ("max_result_bytes", ctypes.c_uint64),
        ("max_response_bytes", ctypes.c_uint64),
        ("max_request_bytes", ctypes.c_uint64),
    ]


class _NativeResult(ctypes.Structure):
    """
    Exact immutable result descriptor; release only with the same transport and new result free entrypoint.
    精确不可变结果描述符；只能通过同一传输及新结果释放入口释放。
    """

    # The descriptor must remain unchanged from receipt through exact release.
    # 描述符从接收到精确释放期间必须保持不变。
    _fields_ = [
        ("ptr", ctypes.POINTER(ctypes.c_uint8)),
        ("len", ctypes.c_size_t),
        ("allocation_id", ctypes.c_uint64),
    ]


class EmbeddedTransport:
    """
    Own one native transport and its result descriptors; request calls may run concurrently.
    拥有一个原生传输及其结果描述符；请求调用可以并发运行。
    Keep this object alive until all runtimes drain and free() succeeds; this class never unloads a live library.
    在全部运行时排空且 free() 成功前保持此对象存活；此类绝不卸载活动动态库。
    """

    def __init__(
        self,
        config: EmbeddedTransportConfig,
        *,
        library_path: str | os.PathLike[str] | None = None,
        runtime_root: str | os.PathLike[str] | None = None,
    ) -> None:
        """
        Bind all required symbols before creating native ownership from explicit config and library selection.
        从显式配置和动态库选择创建原生所有权前，绑定全部必需符号。
        """
        # Resolved path uses the existing SDK's authoritative library selection.
        # 解析后的路径使用既有 SDK 的权威动态库选择。
        self.library_path = resolve_library_path(library_path, runtime_root)
        # Retain the actual library throughout every native call and result lifetime.
        # 在每个原生调用与结果寿命期间保留实际动态库。
        self._library = ctypes.CDLL(str(self.library_path))
        # Immutable caller budgets govern this transport's native admission.
        # 不可变调用方预算治理此传输的原生入场。
        self.config = config
        # Short local ownership lock; never held while executing a runtime request.
        # 局部所有权短锁；执行运行时请求时绝不持有。
        self._lock = threading.Lock()
        # Actual Python calls, including decoding and result release, that forbid local free.
        # 阻止局部释放的实际 Python 调用，包含解码与结果释放。
        self._active_calls = 0
        # Exact native results retained until their matching free succeeds, including explicit release errors.
        # 保留到匹配释放成功的精确原生结果，包含显式释放错误。
        self._results: dict[int, _NativeResult] = {}
        # None only after actual native free has succeeded.
        # 仅在实际原生释放成功后为 None。
        self._transport_id: int | None = None
        self._bind()
        # Prefix and field widths follow the native header rather than Python object size.
        # 前缀与字段位宽遵循原生头文件，而非 Python 对象大小。
        native_config = _NativeConfig(
            struct_size=ctypes.sizeof(_NativeConfig),
            protocol_version=EMBEDDED_PROTOCOL_VERSION,
            **{field.name: getattr(config, field.name) for field in fields(config)},
        )
        # uint64 output preserves identities above JavaScript's and signed int64's ranges.
        # uint64 输出保留超出 JavaScript 与有符号 int64 范围的身份。
        identity = ctypes.c_uint64()
        self._check("luaskills_ffi_embedded_transport_new_v1", self._new(ctypes.byref(native_config), ctypes.byref(identity)))
        self._transport_id = identity.value

    def _bind(self) -> None:
        """
        Configure exact C signatures; a missing new symbol fails before any native transport is allocated.
        配置精确 C 签名；缺少新符号时在分配任何原生传输前失败。
        """
        # Each bound function keeps the CDLL owner reachable.
        # 每个绑定函数保持 CDLL 所有者可达。
        self._new = self._library.luaskills_ffi_embedded_transport_new_v1
        self._new.argtypes = [ctypes.POINTER(_NativeConfig), ctypes.POINTER(ctypes.c_uint64)]
        self._new.restype = ctypes.c_int32
        self._close = self._library.luaskills_ffi_embedded_transport_close_v1
        self._close.argtypes = [ctypes.c_uint64]
        self._close.restype = ctypes.c_int32
        self._free = self._library.luaskills_ffi_embedded_transport_free_v1
        self._free.argtypes = [ctypes.c_uint64]
        self._free.restype = ctypes.c_int32
        self._result_free = self._library.luaskills_ffi_embedded_result_free_v1
        self._result_free.argtypes = [ctypes.c_uint64, _NativeResult]
        self._result_free.restype = ctypes.c_int32
        self._request = self._library.luaskills_ffi_embedded_request_v1
        self._request.argtypes = [ctypes.c_uint64, FfiBorrowedBuffer, ctypes.POINTER(_NativeResult)]
        self._request.restype = ctypes.c_int32

    @staticmethod
    def _check(function_name: str, status: int) -> None:
        """
        Raise exact transport failure for nonzero status without interpreting business results.
        为非零状态抛出精确传输失败，不解释业务结果。
        """
        if status != 0:
            raise EmbeddedTransportError(function_name, status)

    def _begin(self) -> int:
        """
        Retain local call ownership and return the exact live native identity, or reject use after free.
        保留局部调用所有权并返回精确活动原生身份，或拒绝释放后使用。
        """
        with self._lock:
            if self._transport_id is None:
                raise RuntimeError("embedded transport has been freed")
            self._active_calls += 1
            return self._transport_id

    def _end(self) -> None:
        """
        Release exactly one actual local call after all its native and buffer work has returned.
        在全部原生及缓冲工作返回后精确释放一个实际局部调用。
        """
        with self._lock:
            self._active_calls -= 1

    def request(self, command: Mapping[str, Any]) -> Any:
        """
        Send a root command, free its native result exactly once, and return the successful JSON result.
        发送根命令，精确一次释放其原生结果，并返回成功 JSON 结果。
        Native and business failures raise different error classes; JSON null returns None without losing presence.
        原生失败与业务失败抛出不同错误类；JSON 空值返回 None，但不会丢失字段存在性。
        """
        # Strict JSON never converts NaN or infinity into an invalid native request.
        # 严格 JSON 绝不将 NaN 或无穷大转换为无效原生请求。
        encoded = json.dumps(
            {"protocol_version": EMBEDDED_PROTOCOL_VERSION, "command": dict(command)},
            ensure_ascii=False, allow_nan=False, separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > self.config.max_request_bytes:
            raise ValueError("embedded request exceeds max_request_bytes")
        # Backing bytes remain alive until the synchronous ctypes call returns.
        # 后备字节保持存活，直到同步 ctypes 调用返回。
        storage = (ctypes.c_uint8 * len(encoded)).from_buffer_copy(encoded)
        # Every native request receives its own zeroed result descriptor.
        # 每个原生请求均取得独立清零的结果描述符。
        result = _NativeResult()
        # Local ownership extends through parsing and exact buffer release.
        # 局部所有权延续到解析及精确缓冲释放完成。
        identity = self._begin()
        try:
            self._check("luaskills_ffi_embedded_request_v1", self._request(
                identity, FfiBorrowedBuffer(storage, len(encoded)), ctypes.byref(result),
            ))
            # Copy by explicit byte length, preserving embedded NUL and Unicode.
            # 按显式字节长度复制，保留嵌入空字符及 Unicode。
            text = ctypes.string_at(result.ptr, result.len).decode("utf-8")
            return self._decode(text)
        finally:
            try:
                # A Python interruption can be raised on return after native code has already published its result.
                # 原生代码已发布结果后，Python 中断可能在返回时抛出。
                if result.allocation_id != 0:
                    with self._lock:
                        self._results[result.allocation_id] = result
                    self._check("luaskills_ffi_embedded_result_free_v1", self._result_free(identity, result))
                    with self._lock:
                        del self._results[result.allocation_id]
            finally:
                self._end()

    @staticmethod
    def _decode(text: str) -> Any:
        """
        Validate the exact versioned envelope and preserve result presence independently of null or false.
        校验精确版本化信封，并独立于空值或假值保留结果字段存在性。
        """
        # Native UTF-8 has already been decoded strictly before parsing.
        # 原生 UTF-8 已在解析前严格解码。
        envelope = json.loads(text)
        if not isinstance(envelope, dict) or type(envelope.get("protocol_version")) is not int or envelope["protocol_version"] != EMBEDDED_PROTOCOL_VERSION:
            raise ValueError("invalid embedded response protocol version")
        if envelope.get("status") == "ok" and set(envelope) == {"protocol_version", "status", "result"}:
            return envelope["result"]
        if envelope.get("status") == "error" and set(envelope) == {"protocol_version", "status", "error"}:
            # Core EmbeddedError has exactly two string fields.
            # 核心 EmbeddedError 精确包含两个字符串字段。
            error = envelope["error"]
            if isinstance(error, dict) and set(error) == {"code", "message"} and isinstance(error["code"], str) and isinstance(error["message"], str):
                raise EmbeddedRuntimeError(error["code"], error["message"])
        raise ValueError("invalid embedded response envelope")

    def close(self) -> None:
        """
        Permanently request close for all owned runtimes while retaining query and acknowledgement access.
        永久请求关闭全部拥有运行时，同时保留查询及确认访问。
        """
        # A close call itself retains local ownership until the native stack returns.
        # 关闭调用自身保留局部所有权，直到原生调用栈返回。
        identity = self._begin()
        try:
            self._check("luaskills_ffi_embedded_transport_close_v1", self._close(identity))
        finally:
            self._end()

    def release_results(self) -> None:
        """
        Retry only exact descriptors retained after failed result release; reject while any caller may still read.
        仅重试结果释放失败后保留的精确描述符；任何调用方可能仍在读取时拒绝。
        """
        with self._lock:
            if self._active_calls:
                raise RuntimeError("embedded transport still has active calls")
            if self._transport_id is None:
                raise RuntimeError("embedded transport has been freed")
            for allocation_id, result in list(self._results.items()):
                self._check("luaskills_ffi_embedded_result_free_v1", self._result_free(self._transport_id, result))
                del self._results[allocation_id]

    def free(self) -> None:
        """
        Remove native ownership only after close and actual drainage; failure leaves this object usable for drainage.
        仅在关闭及实际排空后移除原生所有权；失败后此对象仍可用于排空。
        """
        with self._lock:
            if self._transport_id is None:
                raise RuntimeError("embedded transport has been freed")
            if self._active_calls or self._results:
                raise RuntimeError("embedded transport still owns active calls or results")
            self._check("luaskills_ffi_embedded_transport_free_v1", self._free(self._transport_id))
            self._transport_id = None
