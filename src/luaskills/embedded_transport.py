"""
Owned, thread-safe bindings for the version-one embedded runtime transport.
版本一嵌入式运行时传输的拥有型、线程安全绑定。
"""

from __future__ import annotations

import ctypes
import os
import sys
import threading
from dataclasses import dataclass, fields
from typing import Any, Mapping

from .embedded_contract import EMBEDDED_DESCRIPTION_MAX_BYTES, EMBEDDED_PROTOCOL_VERSION, EmbeddedNativeStatus, OutputCoreDescription
from .embedded_compatibility import EmbeddedCompatibilityError, decode_core_description
from .embedded_json import decode_embedded_json, encode_embedded_json
from .ffi import FfiBorrowedBuffer, resolve_library_path


# Each SDK control executor has one worker; ownership admission reserves the same native frame capacity.
# 每个 SDK 控制执行器拥有一个工作线程；所有权入场预留相同原生帧容量。
EMBEDDED_CONTROL_WORKERS = 1


# Strong owners remain reachable through construction interruption until explicit native free.
# 强所有者跨构造中断保持可达，直到显式原生释放。
_LIVE_TRANSPORTS: dict[int, "EmbeddedTransport"] = {}
# This lock protects only table operations; it never surrounds native calls or owner-lock acquisition.
# 此锁仅保护表操作；绝不包围原生调用或所有者锁获取。
_LIVE_TRANSPORTS_LOCK = threading.Lock()


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
        Store code and message as exact core diagnostics; return an exception with a stable readable form.
        将 code 与 message 保存为精确核心诊断；返回具有稳定可读形式的异常。
        """
        # Exact structured core error code.
        # 精确结构化核心错误码。
        self.code = code
        # Exact diagnostic supplied by the native core.
        # 原生核心提供的精确诊断。
        self.message = message
        super().__init__(f"{code}: {message}")


class EmbeddedResultReleaseError(EmbeddedTransportError):
    """
    Preserve an already copied native response when releasing its owned buffer fails.
    当释放拥有型缓冲失败时，保留已经复制的原生响应。
    This error never authorizes replaying the command: a resource or external effect may already exist.
    此错误绝不授权重放命令：资源或外部副作用可能已经存在。
    """

    def __init__(self, status: int, response_bytes: bytes | None) -> None:
        """
        Retain exact release status and any response bytes copied before the failed release.
        保留精确释放状态及释放失败前已复制的任何响应字节。
        Return an error whose delivery evidence survives explicit later buffer-release recovery.
        返回在后续显式缓冲释放恢复后仍保留交付证据的错误。
        """
        super().__init__("luaskills_ffi_embedded_result_free_v1", status)
        # None means no response was copied; an empty response is distinct and remains a decoding failure.
        # None 表示未复制响应；空响应与其不同，仍属于解码失败。
        self._response_bytes = response_bytes

    @property
    def response_bytes(self) -> bytes | None:
        """
        Return immutable copied bytes, independently of the original native buffer's current lifetime.
        返回不可变复制字节，独立于原始原生缓冲的当前寿命。
        None reports missing evidence; callers must not infer command rejection from missing evidence.
        None 表示缺少证据；调用方不得据此推断命令已被拒绝。
        """
        return self._response_bytes

    def delivered_result(self) -> Any:
        """
        Decode copied bytes using normal envelope rules; return the original result without issuing native work.
        使用正常信封规则解码复制字节；返回原始结果，不发起原生工作。
        Raise the original business or parse error, or report absent evidence explicitly.
        抛出原始业务或解析错误，或明确报告证据缺失。
        """
        if self._response_bytes is None:
            raise RuntimeError("no copied embedded response is available")
        return EmbeddedTransport._decode(self._response_bytes.decode("utf-8"))


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
        self._config = config
        # Short local ownership lock; never held while executing a runtime request.
        # 局部所有权短锁；执行运行时请求时绝不持有。
        self._lock = threading.Lock()
        # Actual Python calls, including decoding and result release, that forbid local free.
        # 阻止局部释放的实际 Python 调用，包含解码与结果释放。
        self._active_calls = 0
        # Constructor admission becomes true only while the original native creation call is active.
        # 仅在原始原生创建调用活动期间，构造准入状态才为真。
        self._constructing = False
        # Exact native results retained until their matching free succeeds, including explicit release errors.
        # 保留到匹配释放成功的精确原生结果，包含显式释放错误。
        self._results: dict[int, _NativeResult] = {}
        # Exact callback pump owners prevent duplicate consumption and transport release between polling calls.
        # 精确回调泵所有者阻止重复消费及轮询调用间隙中的传输释放。
        self._callback_pumps: dict[str, embedded_pump.EmbeddedCallbackPump] = {}
        # One lifecycle coordinator per adopted runtime keeps drainage independent of command receipt quotas.
        # 每个接管运行时拥有一个生命周期协调器，使排空独立于命令回执配额。
        self._runtime_scopes: dict[str, object] = {}
        # One bounded command driver retains this transport until all of its native workers actually return.
        # 一个有界命令驱动器保留此传输，直到其全部原生工作线程实际返回。
        self._command_driver: object | None = None
        # Command executor slots reserved independently of callback pump executors.
        # 独立于回调泵执行器预留的命令执行器槽。
        self._command_slots = 0
        # The original uint64 output cell is the sole native identity authority.
        # 原始 uint64 输出单元是唯一原生身份权威。
        self._transport_identity = ctypes.c_uint64()
        # An interrupted native free retains explicit uncertainty for one exact recovery attempt.
        # 被中断的原生释放保留显式不确定状态，供一次精确恢复尝试使用。
        self._free_uncertain = False
        # Exact result identities whose native release may have completed before Python interruption.
        # 原生释放可能在 Python 中断前已完成的精确结果身份。
        self._uncertain_result_releases: set[int] = set()
        # Copy and validate borrowed metadata before the first constructor can publish a native handle.
        # 在首个构造函数可能发布原生句柄前，复制并校验借用元数据。
        self._description_bytes = self._read_description()
        self._bind()
        # Prefix and field widths follow the native header rather than Python object size.
        # 前缀与字段位宽遵循原生头文件，而非 Python 对象大小。
        native_config = _NativeConfig(
            struct_size=ctypes.sizeof(_NativeConfig),
            protocol_version=EMBEDDED_PROTOCOL_VERSION,
            **{field.name: getattr(config, field.name) for field in fields(config)},
        )
        # Materialize pointer wrappers before publishing the recoverable owner.
        # 发布可恢复所有者前先实体化指针包装。
        config_pointer = ctypes.byref(native_config)
        identity_pointer = ctypes.byref(self._transport_identity)
        # Mark this one original call under the owner lock, then release the lock before native execution.
        # 在所有者锁内标记这一次原始调用，随后在原生执行前释放该锁。
        with self._lock:
            self._constructing = True
            self._active_calls += 1
        try:
            # Retain the fully bound owner, library and sole output cell before native publication.
            # 在原生发布前保留完整绑定的所有者、动态库及唯一输出单元。
            with _LIVE_TRANSPORTS_LOCK:
                _LIVE_TRANSPORTS[id(self)] = self
            # Pending Python interruption leaves this same owner reachable without an adoption copy.
            # 待处理 Python 中断会让同一所有者保持可达，不存在接管副本。
            status = self._new(config_pointer, identity_pointer)
            self._check("luaskills_ffi_embedded_transport_new_v1", status)
            if self._transport_identity.value == 0:
                raise RuntimeError("embedded transport constructor returned a zero identity")
        finally:
            # End only the actual constructor call; the original cell needs no later identity copy.
            # 仅结束实际构造调用；原始单元不需要随后复制身份。
            with self._lock:
                self._constructing = False
                self._active_calls -= 1
            # Zero proves no native owner was published, including interruption before native entry.
            # 零值证明没有发布原生所有者，包含进入原生调用前发生的中断。
            if self._transport_identity.value == 0:
                with _LIVE_TRANSPORTS_LOCK:
                    if _LIVE_TRANSPORTS.get(id(self)) is self:
                        del _LIVE_TRANSPORTS[id(self)]
                    elif id(self) in _LIVE_TRANSPORTS:
                        raise RuntimeError("embedded transport live-owner identity is inconsistent")

    @property
    def _transport_id(self) -> int | None:
        """
        Read the original uint64 output and return None for zero without maintaining a second identity.
        读取原始 uint64 输出，为零时返回 None，不维护第二份身份。
        Internal callers acquire the owner lock before using the returned native identity.
        内部调用方在使用返回的原生身份前获取所有者锁。
        """
        return self._transport_identity.value or None

    @staticmethod
    def live_transports() -> tuple[EmbeddedTransport, ...]:
        """
        Return a frozen snapshot of exact strong owners, including interrupted construction.
        返回精确强所有者的冻结快照，包含被中断的构造。
        The snapshot performs no native call and never proves publication, drainage or successful cleanup.
        此快照不执行原生调用，也不证明发布、排空或清理成功。
        """
        with _LIVE_TRANSPORTS_LOCK:
            return tuple(_LIVE_TRANSPORTS.values())

    @property
    def core_description(self) -> OutputCoreDescription:
        """
        Return an independent validated snapshot of the exact loaded core, without a native request.
        返回精确已加载核心的独立已校验快照，不发起原生请求。
        """
        return decode_core_description(self._description_bytes)

    def _read_description(self) -> bytes:
        """
        Bind the required bootstrap symbol and copy bounded library-owned bytes without freeing them.
        绑定必需引导符号，复制有界且由动态库拥有的字节，绝不释放它们。
        Missing symbols, invalid buffers or incompatible metadata fail before native ownership exists.
        缺少符号、无效缓冲或不兼容元数据在原生所有权存在前失败。
        """
        try:
            # This read-only function requires no transport identity and returns no caller-owned result.
            # 此只读函数无需传输身份，也不返回调用方拥有的结果。
            describe = self._library.luaskills_ffi_embedded_describe_v1
        except AttributeError as error:
            raise EmbeddedCompatibilityError("native core lacks luaskills_ffi_embedded_describe_v1") from error
        describe.argtypes = [ctypes.POINTER(FfiBorrowedBuffer)]
        describe.restype = ctypes.c_int32
        # The CDLL owner remains strongly retained throughout this call and the subsequent copy.
        # 在此调用及后续复制全过程中，CDLL 所有者始终被强引用保留。
        borrowed = FfiBorrowedBuffer()
        self._check("luaskills_ffi_embedded_describe_v1", describe(ctypes.byref(borrowed)))
        if not borrowed.ptr or not 0 < borrowed.len <= EMBEDDED_DESCRIPTION_MAX_BYTES:
            raise EmbeddedCompatibilityError("invalid native core description buffer")
        encoded = ctypes.string_at(borrowed.ptr, borrowed.len)
        decode_core_description(encoded)
        return encoded

    @property
    def config(self) -> EmbeddedTransportConfig:
        """
        Return the immutable original native budgets used by SDK admission and request encoding.
        返回 SDK 入场及请求编码使用的不可变原始原生预算。
        No setter may let Python-side limits drift from the already-created native transport.
        不提供能使 Python 端限制偏离已创建原生传输的设置入口。
        """
        return self._config

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
        if status != EmbeddedNativeStatus.OK:
            raise EmbeddedTransportError(function_name, status)

    def _begin(self) -> int:
        """
        Retain local call ownership and return the exact live native identity, or reject use after free.
        保留局部调用所有权并返回精确活动原生身份，或拒绝释放后使用。
        """
        with self._lock:
            if self._constructing:
                raise RuntimeError("embedded transport constructor is still active")
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
        Send a root command and return its successful result, separating native and business failures.
        发送根命令并返回成功结果，区分原生失败与业务失败。
        """
        return self._request_encoded(self._encode_request(command))


    @staticmethod
    def _decode(text: str) -> Any:
        """
        Validate the exact versioned envelope and preserve result presence independently of null or false.
        校验精确版本化信封，并独立于空值或假值保留结果字段存在性。
        """
        # Native UTF-8 has already been decoded strictly before parsing.
        # 原生 UTF-8 已在解析前严格解码。
        envelope = decode_embedded_json(text)
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

    def _encode_request(self, command: Mapping[str, Any]) -> bytes:
        """
        Freeze a strict command into owned, bounded UTF-8 bytes before native execution can start.
        在原生执行能够开始前，将严格命令冻结为拥有型有界 UTF-8 字节。
        """
        # Exact serialization is shared by ordinary requests and retained callback acknowledgements.
        # 普通请求及保留回调确认共享精确序列化。
        return encode_embedded_json({"protocol_version":EMBEDDED_PROTOCOL_VERSION,
            "command":dict(command)}, self.config.max_request_bytes)

    def _request_encoded(self, encoded: bytes) -> Any:
        """
        Execute owned command bytes and retain delivery evidence if exact native output release fails.
        执行拥有型命令字节，并在精确原生输出释放失败时保留交付证据。
        Return the decoded result; errors retain native ownership until explicit release recovery.
        返回解码结果；错误保留原生所有权，直到显式释放恢复。
        """
        if len(encoded) > self.config.max_request_bytes:
            raise ValueError("embedded request exceeds max_request_bytes")
        # Backing bytes stay alive until the synchronous native call has returned.
        # 后备字节保持存活，直到同步原生调用返回。
        storage = (ctypes.c_uint8 * len(encoded)).from_buffer_copy(encoded)
        # Each invocation owns one independently zeroed descriptor and an optional immutable response copy.
        # 每次调用拥有一个独立清零的描述符及可选不可变响应副本。
        result = _NativeResult()
        response_bytes: bytes | None = None
        # Local call ownership extends through parsing and release.
        # 局部调用所有权延续到解析及释放完成。
        identity = self._begin()
        try:
            self._check("luaskills_ffi_embedded_request_v1", self._request(
                identity, FfiBorrowedBuffer(storage, len(encoded)), ctypes.byref(result)))
            response_bytes = ctypes.string_at(result.ptr, result.len)
            return self._decode(response_bytes.decode("utf-8"))
        finally:
            try:
                # Native publication may finish before a Python interruption is raised on return.
                # 原生发布可能在 Python 返回时抛出中断前已经完成。
                if result.allocation_id != 0:
                    with self._lock:
                        self._results[result.allocation_id] = result
                        self._uncertain_result_releases.add(result.allocation_id)
                    status = self._result_free(identity, result)
                    if status != EmbeddedNativeStatus.OK:
                        with self._lock:
                            self._uncertain_result_releases.remove(result.allocation_id)
                        raise EmbeddedResultReleaseError(status, response_bytes)
                    with self._lock:
                        del self._results[result.allocation_id]
                        self._uncertain_result_releases.remove(result.allocation_id)
            finally:
                self._end()


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
            if self._constructing:
                raise RuntimeError("embedded transport constructor is still active")
            if self._active_calls:
                raise RuntimeError("embedded transport still has active calls")
            if self._transport_id is None:
                raise RuntimeError("embedded transport has been freed")
            for allocation_id, result in list(self._results.items()):
                # A prior interruption authorizes only exact same-descriptor absence as completed release.
                # 先前中断仅授权将精确同一描述符的缺失视为已完成释放。
                recovering = allocation_id in self._uncertain_result_releases
                self._uncertain_result_releases.add(allocation_id)
                status = self._result_free(self._transport_id, result)
                if status == EmbeddedNativeStatus.OK or (status == EmbeddedNativeStatus.NOT_FOUND and recovering):
                    del self._results[allocation_id]
                    self._uncertain_result_releases.remove(allocation_id)
                    continue
                self._uncertain_result_releases.remove(allocation_id)
                self._check("luaskills_ffi_embedded_result_free_v1", status)

    def free(self) -> None:
        """
        Remove native ownership only after close and actual drainage; failure leaves this object usable for drainage.
        仅在关闭及实际排空后移除原生所有权；失败后此对象仍可用于排空。
        """
        with self._lock:
            if self._constructing:
                raise RuntimeError("embedded transport constructor is still active")
            if self._transport_id is None:
                raise RuntimeError("embedded transport has been freed")
            if self._active_calls or self._results or self._callback_pumps or self._runtime_scopes or self._command_driver is not None:
                raise RuntimeError("embedded transport still owns active calls or results")
            # Only a prior interrupted attempt may interpret exact native absence as completed release.
            # 只有先前被中断的尝试可以把精确原生缺失解释为释放完成。
            recovering = self._free_uncertain
            self._free_uncertain = True
            status = self._free(self._transport_id)
            if status != EmbeddedNativeStatus.OK and not (status == EmbeddedNativeStatus.NOT_FOUND and recovering):
                self._free_uncertain = False
                self._check("luaskills_ffi_embedded_transport_free_v1", status)
            # Remove the global recovery path only after actual success or proven interrupted success.
            # 仅在实际成功或证实先前中断已成功后移除全局恢复路径。
            with _LIVE_TRANSPORTS_LOCK:
                if _LIVE_TRANSPORTS.get(id(self)) is not self:
                    raise RuntimeError("embedded transport live-owner identity is inconsistent")
                del _LIVE_TRANSPORTS[id(self)]
            self._transport_identity.value = 0
            self._free_uncertain = False

    def callback_pump(self, runtime_id: str) -> embedded_pump.EmbeddedCallbackPump | None:
        """
        Return the actual retained callback pump for this transport's exact runtime_id, or None if no owner exists.
        返回此传输精确 runtime_id 的实际保留回调泵；不存在所有者时返回 None。
        This read-only snapshot uses the sole ownership registry under its lock; it never creates or releases owners.
        此只读快照在所有权锁内使用唯一注册表；绝不创建或释放所有者。
        The returned strong reference can close and join a pump whose constructor was interrupted after thread start.
        返回的强引用可关闭并汇合在线程启动后构造器被中断的回调泵。
        None proves only absence of a retained SDK pump, not native runtime readiness, closure or delivery success.
        None 仅证明不存在保留 SDK 泵，不证明原生运行时就绪、关闭或交付成功。
        """
        with self._lock:
            return self._callback_pumps.get(runtime_id)

    def _claim_callback_pump(self, runtime_id: str, owner: embedded_pump.EmbeddedCallbackPump) -> None:
        """
        Retain one exact pump owner for a runtime before its thread starts; this is SDK ownership, not native registration.
        在线程启动前为运行时保留一个精确泵所有者；这是 SDK 所有权，而非原生注册。
        """
        with self._lock:
            if self._constructing:
                raise RuntimeError("embedded transport constructor is still active")
            if self._transport_id is None:
                raise RuntimeError("embedded transport has been freed")
            if runtime_id in self._callback_pumps:
                raise RuntimeError("embedded runtime already has a Python callback pump")
            if runtime_id in self._runtime_scopes:
                raise RuntimeError("attach callback pumps before adopting an embedded runtime scope")
            if len(self._callback_pumps) >= self.config.max_runtimes:
                raise RuntimeError("callback pump ownership exceeds transport runtime capacity")
            self._check_worker_reservation(self._command_slots + (len(self._callback_pumps) + len(self._runtime_scopes) + 1) * EMBEDDED_CONTROL_WORKERS)
            self._callback_pumps[runtime_id] = owner

    def _claim_command_driver(self, owner: object, native_slots: int) -> None:
        """
        Retain one driver owner and its native_slots before it can enqueue or execute native work.
        在驱动器能够排队或执行原生工作前，保留一个驱动器所有者及其 native_slots。
        Return nothing; duplicate ownership and use after native free fail explicitly.
        无返回值；重复所有权及原生释放后使用明确失败。
        """
        with self._lock:
            if self._constructing:
                raise RuntimeError("embedded transport constructor is still active")
            if self._transport_id is None:
                raise RuntimeError("embedded transport has been freed")
            if self._command_driver is not None:
                raise RuntimeError("embedded transport already has a command driver")
            self._check_worker_reservation(native_slots + (len(self._callback_pumps) + len(self._runtime_scopes)) * EMBEDDED_CONTROL_WORKERS)
            self._command_driver = owner
            self._command_slots = native_slots

    def _release_command_driver(self, owner: object) -> None:
        """
        Release the exact driver owner after both native executors have joined, retaining other owners.
        在两个原生执行器均汇合后释放精确驱动器所有者，保留其他所有者。
        Return nothing; a mismatched owner cannot change transport lifetime.
        无返回值；不匹配的所有者无法改变传输寿命。
        """
        with self._lock:
            if self._command_driver is not owner:
                raise RuntimeError("embedded command driver ownership identity does not match")
            self._command_driver = None
            self._command_slots = 0

    def _check_worker_reservation(self, slots: int) -> None:
        """
        Check worst-case native frame reservations for slots while the local ownership lock is held.
        持有局部所有权锁时，为 slots 检查最坏情况原生帧预留。
        Return nothing; insufficient count or aggregate response bytes fail before publishing an SDK owner.
        无返回值；数量或聚合响应字节不足时，在发布 SDK 所有者前失败。
        """
        # Core admission reserves max_response_bytes before dispatch, not the eventual small receipt size.
        # 核心在分发前预留 max_response_bytes，而非最终较小的回执大小。
        required_bytes = slots * self.config.max_response_bytes
        if slots > self.config.max_result_buffers or required_bytes > self.config.max_result_bytes:
            raise EmbeddedRuntimeError("capacity_exceeded", f"transport needs {slots} result slots and {required_bytes} result bytes for SDK workers")

    def _release_callback_pump(self, runtime_id: str, owner: object) -> None:
        """
        Release only the exact pump owner after all of its real threads and native calls have drained.
        仅在实际线程及原生调用全部排空后释放精确泵所有者。
        """
        with self._lock:
            if self._callback_pumps.get(runtime_id) is not owner:
                raise RuntimeError("callback pump ownership identity does not match")
            del self._callback_pumps[runtime_id]

    def _claim_runtime_scope(self, runtime_id: str, owner: object, pump: object | None) -> None:
        """
        Adopt exact runtime_id and its existing pump with one reserved native control slot for owner.
        为 owner 接管精确 runtime_id 及其现有 pump，并预留一个原生控制槽。
        Return only after bounded ownership is published; reject duplicate or omitted live pump ownership.
        仅在发布有界所有权后返回；拒绝重复所有权或遗漏活动事件泵。
        """
        with self._lock:
            if self._constructing:
                raise RuntimeError("embedded transport constructor is still active")
            if self._transport_id is None:
                raise RuntimeError("embedded transport has been freed")
            if runtime_id in self._runtime_scopes:
                raise RuntimeError("embedded runtime already has a lifecycle scope")
            if self._callback_pumps.get(runtime_id) is not pump:
                raise RuntimeError("runtime scope must adopt the exact existing callback pump")
            if len(self._runtime_scopes) >= self.config.max_runtimes:
                raise RuntimeError("runtime scope ownership exceeds transport runtime capacity")
            self._check_worker_reservation(self._command_slots +
                (len(self._callback_pumps) + len(self._runtime_scopes) + 1) * EMBEDDED_CONTROL_WORKERS)
            self._runtime_scopes[runtime_id] = owner

    def _release_runtime_scope(self, runtime_id: str, owner: object) -> None:
        """
        Release only owner's exact lifecycle claim after proven native drainage or failed thread startup.
        仅在原生排空得到证明或线程启动失败后，释放 owner 的精确生命周期声明。
        Return nothing; mismatched ownership cannot remove another coordinator's reservation.
        无返回值；所有权不匹配时不能移除其他协调器的预留。
        """
        with self._lock:
            if self._runtime_scopes.get(runtime_id) is not owner:
                raise RuntimeError("embedded runtime scope ownership mismatch")
            del self._runtime_scopes[runtime_id]

    def _check_unmanaged_runtime(self, runtime_id: str) -> None:
        """
        Reject independent typed runtime release while runtime_id is owned by a lifecycle scope.
        runtime_id 由生命周期作用域拥有时，拒绝独立类型运行时释放。
        Return nothing; the scope uses its reserved control path to perform the actual release.
        无返回值；作用域通过其预留控制路径执行实际释放。
        """
        with self._lock:
            if runtime_id in self._runtime_scopes:
                raise RuntimeError("close the owning embedded runtime scope before independent release")


# Bind the concrete pump module only after its required transport declarations exist; keep runtime type hints resolvable.
# 仅在事件泵所需传输声明存在后绑定具体泵模块；保持运行时类型提示可解析。
from . import embedded_pump
