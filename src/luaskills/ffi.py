"""
Low-level ctypes bridge for the public LuaSkills JSON FFI surface.
公共 LuaSkills JSON FFI 表面的底层 ctypes 桥。
"""

from __future__ import annotations

import ctypes
import json
import os
import threading
from pathlib import Path
from typing import Any, Callable, Literal, TypedDict

from .runtime_assets import resolve_luaskills_library_path_from_runtime


class FfiBorrowedBuffer(ctypes.Structure):
    """
    Borrowed byte-buffer view passed into JSON FFI requests.
    传入 JSON FFI 请求的借用字节缓冲视图。
    """

    _fields_ = [
        ("ptr", ctypes.POINTER(ctypes.c_uint8)),
        ("len", ctypes.c_size_t),
    ]


class FfiOwnedBuffer(ctypes.Structure):
    """
    Owned byte-buffer container returned by JSON FFI calls.
    由 JSON FFI 调用返回的拥有型字节缓冲容器。
    """

    _fields_ = [
        ("ptr", ctypes.POINTER(ctypes.c_uint8)),
        ("len", ctypes.c_size_t),
    ]


# Host-side JSON provider callback implemented by SDK callers.
# 由 SDK 调用方实现的宿主侧 JSON provider callback。
JsonProviderCallback = Callable[[Any], Any]

# Host-tool bridge action names emitted by vulcan.host.*.
# vulcan.host.* 发出的宿主工具桥接动作名称。
HostToolJsonAction = Literal["list", "has", "call"]


class HostToolJsonRequest(TypedDict):
    """
    Host-tool bridge request delivered to the SDK callback.
    传递给 SDK callback 的宿主工具桥接请求。
    """

    # Requested host-tool bridge action.
    # 请求的宿主工具桥接动作。
    action: HostToolJsonAction
    # Optional host tool name for has and call actions.
    # has 与 call 动作使用的可选宿主工具名称。
    tool_name: str | None
    # JSON payload converted from the Lua table argument.
    # 从 Lua table 参数转换得到的 JSON 载荷。
    args: Any


# Host-side tool bridge JSON callback implemented by SDK callers.
# 由 SDK 调用方实现的宿主工具桥接 JSON callback。
HostToolJsonCallback = Callable[[HostToolJsonRequest], Any]

# Standard model capability names exposed by vulcan.models.*.
# vulcan.models.* 暴露的标准模型能力名称。
RuntimeModelCapability = Literal["embed", "llm"]


class RuntimeModelCaller(TypedDict, total=False):
    """
    Caller context attached by LuaSkills to each model callback request.
    LuaSkills 附加到每个模型 callback 请求上的调用方上下文。
    """

    # Skill identifier that owns the active Lua entry.
    # 拥有当前 Lua 入口的 skill 标识符。
    skill_id: str | None
    # Local entry name declared by the owning skill.
    # 所属 skill 声明的局部入口名称。
    entry_name: str | None
    # Canonical runtime tool name currently executing.
    # 当前正在执行的 canonical 运行时工具名称。
    canonical_tool_name: str | None
    # Runtime root name that owns the current skill.
    # 拥有当前 skill 的运行时根名称。
    root_name: str | None
    # Host-visible absolute skill directory.
    # 对宿主可见的绝对 skill 目录。
    skill_dir: str | None
    # Host-provided client name from the current request context.
    # 当前请求上下文中的宿主提供客户端名称。
    client_name: str | None
    # Host-provided request identifier from the current request context.
    # 当前请求上下文中的宿主提供请求标识符。
    request_id: str | None


class RuntimeModelUsage(TypedDict, total=False):
    """
    Optional token usage metadata returned by host-managed model providers.
    宿主管理模型 provider 返回的可选 token 用量元数据。
    """

    # Optional input token count.
    # 可选输入 token 数量。
    input_tokens: int | None
    # Optional output token count.
    # 可选输出 token 数量。
    output_tokens: int | None


class RuntimeModelEmbedRequest(TypedDict):
    """
    Embedding request delivered to the SDK callback.
    传递给 SDK callback 的 embedding 请求。
    """

    # Single input text requested by Lua.
    # Lua 请求的单条输入文本。
    text: str
    # Caller context captured from the active Lua runtime scope.
    # 从当前 Lua 运行时作用域捕获的调用方上下文。
    caller: RuntimeModelCaller


class RuntimeModelEmbedResponse(TypedDict, total=False):
    """
    Embedding response returned by the SDK callback.
    SDK callback 返回的 embedding 响应。
    """

    # Embedding vector returned by the host-managed model provider.
    # 宿主管理模型 provider 返回的 embedding 向量。
    vector: list[float]
    # Number of vector dimensions reported by the host.
    # 宿主报告的向量维度数量。
    dimensions: int
    # Optional token usage metadata reported by the host.
    # 宿主报告的可选 token 用量元数据。
    usage: RuntimeModelUsage | None


class RuntimeModelLlmRequest(TypedDict):
    """
    Non-streaming LLM request delivered to the SDK callback.
    传递给 SDK callback 的非流式 LLM 请求。
    """

    # System instruction text supplied by Lua.
    # Lua 提供的 system 指令文本。
    system: str
    # User message text supplied by Lua.
    # Lua 提供的 user 消息文本。
    user: str
    # Caller context captured from the active Lua runtime scope.
    # 从当前 Lua 运行时作用域捕获的调用方上下文。
    caller: RuntimeModelCaller


class RuntimeModelLlmResponse(TypedDict, total=False):
    """
    Non-streaming LLM response returned by the SDK callback.
    SDK callback 返回的非流式 LLM 响应。
    """

    # Assistant text returned by the host-managed model provider.
    # 宿主管理模型 provider 返回的 assistant 文本。
    assistant: str
    # Optional token usage metadata reported by the host.
    # 宿主报告的可选 token 用量元数据。
    usage: RuntimeModelUsage | None


# Stable model error codes accepted by the JSON callback bridge.
# JSON callback 桥接受的稳定模型错误码。
RuntimeModelErrorCode = Literal[
    "model_unavailable",
    "invalid_argument",
    "provider_error",
    "timeout",
    "budget_exceeded",
    "internal_error",
]


class RuntimeModelError(TypedDict, total=False):
    """
    Structured model error returned by a model JSON callback.
    模型 JSON callback 返回的结构化模型错误。
    """

    # Stable LuaSkills-level model error code.
    # 稳定的 LuaSkills 级模型错误码。
    code: RuntimeModelErrorCode
    # Human-readable error summary.
    # 人类可读的错误摘要。
    message: str
    # Optional raw provider error text after host-side redaction.
    # 宿主侧脱敏后的可选 provider 原始错误文本。
    provider_message: str | None
    # Optional raw provider error code.
    # 可选 provider 原始错误码。
    provider_code: str | None
    # Optional provider status such as an HTTP status code.
    # 可选 provider 状态，例如 HTTP 状态码。
    provider_status: int | None


class RuntimeModelErrorEnvelope(TypedDict):
    """
    Error envelope returned by a model JSON callback.
    模型 JSON callback 返回的错误包络。
    """

    # Always false for callback error envelopes.
    # callback 错误包络中固定为 false。
    ok: Literal[False]
    # Structured model error payload.
    # 结构化模型错误载荷。
    error: RuntimeModelError


# Host-side model embedding JSON callback implemented by SDK callers.
# 由 SDK 调用方实现的宿主侧模型 embedding JSON callback。
ModelEmbedJsonCallback = Callable[[RuntimeModelEmbedRequest], RuntimeModelEmbedResponse | RuntimeModelErrorEnvelope]

# Host-side model LLM JSON callback implemented by SDK callers.
# 由 SDK 调用方实现的宿主侧模型 LLM JSON callback。
ModelLlmJsonCallback = Callable[[RuntimeModelLlmRequest], RuntimeModelLlmResponse | RuntimeModelErrorEnvelope]


JSON_PROVIDER_CALLBACK_TYPE = ctypes.CFUNCTYPE(
    ctypes.c_int32,
    FfiBorrowedBuffer,
    ctypes.c_void_p,
    ctypes.POINTER(FfiOwnedBuffer),
    ctypes.POINTER(FfiOwnedBuffer),
)


class JsonProviderSlotState:
    """
    Process-local owner state for one native JSON provider callback slot.
    单个原生 JSON provider callback 槽位的进程内 owner 状态。
    """

    def __init__(
        self,
        library_path: Path,
        owner_token: object,
        callback_wrapper: JSON_PROVIDER_CALLBACK_TYPE,
    ) -> None:
        """
        Store one native callback owner token and its live wrapper.
        存储单个原生 callback owner 令牌及其存活包装器。
        """

        self.library_path = library_path
        self.owner_token = owner_token
        self.callback_wrapper = callback_wrapper


_JSON_PROVIDER_CALLBACK_LOCK = threading.RLock()
_JSON_PROVIDER_CALLBACK_SLOTS: dict[tuple[str, str], JsonProviderSlotState] = {}


class LuaSkillsError(RuntimeError):
    """
    Error raised when one LuaSkills JSON FFI call reports failure.
    当 LuaSkills JSON FFI 调用报告失败时抛出的错误。
    """

    def __init__(self, function_name: str, message: str) -> None:
        """
        Create one SDK error with the failing FFI function name.
        使用失败的 FFI 函数名称创建一个 SDK 错误。
        """

        super().__init__(f"{function_name}: {message}")
        self.function_name = function_name


class LuaSkillsJsonFfi:
    """
    Low-level JSON FFI bridge used by higher-level Python SDK clients.
    高层 Python SDK 客户端使用的底层 JSON FFI 桥。
    """

    def __init__(
        self,
        library_path: str | os.PathLike[str] | None = None,
        runtime_root: str | os.PathLike[str] | None = None,
    ) -> None:
        """
        Load one LuaSkills dynamic library and configure shared buffer helpers.
        加载单个 LuaSkills 动态库并配置共享缓冲辅助函数。
        """

        self.library_path = resolve_library_path(library_path, runtime_root)
        self.library = ctypes.CDLL(str(self.library_path))
        self.library.luaskills_ffi_buffer_free.argtypes = [FfiOwnedBuffer]
        self.library.luaskills_ffi_buffer_free.restype = None
        self.library.luaskills_ffi_buffer_clone.argtypes = [
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(FfiOwnedBuffer),
            ctypes.POINTER(FfiOwnedBuffer),
        ]
        self.library.luaskills_ffi_buffer_clone.restype = ctypes.c_int32
        self._configure_json_provider_setter("luaskills_ffi_set_sqlite_provider_json_callback")
        self._configure_json_provider_setter("luaskills_ffi_set_lancedb_provider_json_callback")
        self._provider_owner_token = object()
        self._configured_json_provider_setters = {
            "luaskills_ffi_set_sqlite_provider_json_callback",
            "luaskills_ffi_set_lancedb_provider_json_callback",
        }

    def call_json_no_input(self, function_name: str) -> Any:
        """
        Call one JSON FFI entrypoint that does not accept input.
        调用一个不接收输入的 JSON FFI 入口。
        """

        function = getattr(self.library, function_name)
        function.argtypes = []
        function.restype = FfiOwnedBuffer
        return self._decode_envelope(function_name, function())

    def call_json(self, function_name: str, payload: dict[str, Any]) -> Any:
        """
        Call one JSON FFI entrypoint with one JSON payload.
        使用一个 JSON 载荷调用 JSON FFI 入口。
        """

        function = getattr(self.library, function_name)
        function.argtypes = [FfiBorrowedBuffer]
        function.restype = FfiOwnedBuffer
        payload_bytes = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        storage = (ctypes.c_uint8 * len(payload_bytes)).from_buffer_copy(payload_bytes)
        borrowed = FfiBorrowedBuffer(
            ptr=ctypes.cast(storage, ctypes.POINTER(ctypes.c_uint8)) if payload_bytes else None,
            len=len(payload_bytes),
        )
        return self._decode_envelope(function_name, function(borrowed))

    def set_sqlite_provider_json_callback(self, callback: JsonProviderCallback | None) -> None:
        """
        Register or clear the SQLite JSON provider callback.
        注册或清理 SQLite JSON provider callback。
        """

        self._set_json_provider_callback(
            "sqlite",
            "luaskills_ffi_set_sqlite_provider_json_callback",
            callback,
        )

    def set_lancedb_provider_json_callback(self, callback: JsonProviderCallback | None) -> None:
        """
        Register or clear the LanceDB JSON provider callback.
        注册或清理 LanceDB JSON provider callback。
        """

        self._set_json_provider_callback(
            "lancedb",
            "luaskills_ffi_set_lancedb_provider_json_callback",
            callback,
        )

    def set_host_tool_json_callback(self, callback: HostToolJsonCallback | None) -> None:
        """
        Register or clear the host-tool JSON callback.
        注册或清理宿主工具 JSON callback。
        """

        self._set_json_provider_callback(
            "host-tool",
            "luaskills_ffi_set_host_tool_json_callback",
            callback,
        )

    def set_model_embed_json_callback(self, callback: ModelEmbedJsonCallback | None) -> None:
        """
        Register or clear the model embedding JSON callback.
        注册或清理模型 embedding JSON callback。
        """

        self._set_json_provider_callback(
            "model-embed",
            "luaskills_ffi_set_model_embed_json_callback",
            callback,
        )

    def set_model_llm_json_callback(self, callback: ModelLlmJsonCallback | None) -> None:
        """
        Register or clear the model LLM JSON callback.
        注册或清理模型 LLM JSON callback。
        """

        self._set_json_provider_callback(
            "model-llm",
            "luaskills_ffi_set_model_llm_json_callback",
            callback,
        )

    def clear_sqlite_provider_json_callback(self) -> None:
        """
        Clear the SQLite JSON provider callback slot.
        清理 SQLite JSON provider callback 槽位。
        """

        self.set_sqlite_provider_json_callback(None)

    def clear_lancedb_provider_json_callback(self) -> None:
        """
        Clear the LanceDB JSON provider callback slot.
        清理 LanceDB JSON provider callback 槽位。
        """

        self.set_lancedb_provider_json_callback(None)

    def clear_host_tool_json_callback(self) -> None:
        """
        Clear the host-tool JSON callback slot.
        清理宿主工具 JSON callback 槽位。
        """

        self.set_host_tool_json_callback(None)

    def clear_model_embed_json_callback(self) -> None:
        """
        Clear the model embedding JSON callback slot.
        清理模型 embedding JSON callback 槽位。
        """

        self.set_model_embed_json_callback(None)

    def clear_model_llm_json_callback(self) -> None:
        """
        Clear the model LLM JSON callback slot.
        清理模型 LLM JSON callback 槽位。
        """

        self.set_model_llm_json_callback(None)

    def _decode_envelope(self, function_name: str, raw_buffer: FfiOwnedBuffer) -> Any:
        """
        Decode one owned JSON response envelope and release the native buffer.
        解码一个拥有型 JSON 响应包络并释放原生缓冲。
        """

        text = ""
        if raw_buffer.ptr and raw_buffer.len:
            text = ctypes.string_at(raw_buffer.ptr, raw_buffer.len).decode("utf-8")
        self.library.luaskills_ffi_buffer_free(raw_buffer)
        envelope = json.loads(text)
        if envelope.get("ok") is not True:
            raise LuaSkillsError(function_name, envelope.get("error") or "Unknown LuaSkills FFI error")
        return envelope.get("result")

    def _set_json_provider_callback(
        self,
        kind: str,
        function_name: str,
        callback: JsonProviderCallback | None,
    ) -> None:
        """
        Register or clear one concrete JSON provider callback slot.
        注册或清理一个具体 JSON provider callback 槽位。
        """

        slot_key = self._json_provider_slot_key(kind)
        with _JSON_PROVIDER_CALLBACK_LOCK:
            previous_slot = _JSON_PROVIDER_CALLBACK_SLOTS.get(slot_key)
            if callback is None:
                if previous_slot is None or previous_slot.owner_token is not self._provider_owner_token:
                    return
                self._ensure_json_provider_setter_configured(function_name)
                function = getattr(self.library, function_name)
                self._call_provider_setter(function_name, function, None)
                _JSON_PROVIDER_CALLBACK_SLOTS.pop(slot_key, None)
                return

            self._ensure_json_provider_setter_configured(function_name)
            function = getattr(self.library, function_name)
            callback_wrapper = JSON_PROVIDER_CALLBACK_TYPE(self._make_json_provider_callback(callback))
            self._call_provider_setter(function_name, function, callback_wrapper)
            _JSON_PROVIDER_CALLBACK_SLOTS[slot_key] = JsonProviderSlotState(
                self.library_path,
                self._provider_owner_token,
                callback_wrapper,
            )

    def _make_json_provider_callback(
        self,
        callback: JsonProviderCallback,
    ) -> Callable[
        [FfiBorrowedBuffer, ctypes.c_void_p, ctypes.POINTER(FfiOwnedBuffer), ctypes.POINTER(FfiOwnedBuffer)],
        int,
    ]:
        """
        Create one C-safe wrapper around a Python JSON provider callback.
        围绕 Python JSON provider callback 创建一个 C 安全包装器。
        """

        def invoke(
            request_json: FfiBorrowedBuffer,
            _user_data: ctypes.c_void_p,
            response_out: ctypes.POINTER(FfiOwnedBuffer),
            error_out: ctypes.POINTER(FfiOwnedBuffer),
        ) -> int:
            """
            Execute one callback request and translate Python errors into FFI errors.
            执行单个 callback 请求并将 Python 错误转换为 FFI 错误。
            """

            try:
                request = self._parse_borrowed_json(request_json)
                response = callback(request)
                payload = json.dumps(response, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                self._clone_bytes_into_owned_buffer(payload, response_out)
                return 0
            except BaseException as exc:
                try:
                    self._clone_bytes_into_owned_buffer(str(exc).encode("utf-8"), error_out)
                except BaseException:
                    pass
                return 1

        return invoke

    def _call_provider_setter(
        self,
        function_name: str,
        function: Any,
        callback: JSON_PROVIDER_CALLBACK_TYPE | None,
    ) -> None:
        """
        Call one provider callback setter and raise a Python SDK error on failure.
        调用单个 provider callback setter 并在失败时抛出 Python SDK 错误。
        """

        error_buffer = FfiOwnedBuffer()
        callback_pointer = ctypes.cast(callback, ctypes.c_void_p) if callback is not None else None
        status = function(callback_pointer, None, ctypes.byref(error_buffer))
        if status == 0:
            if error_buffer.ptr:
                self.library.luaskills_ffi_buffer_free(error_buffer)
            return
        message = self._read_owned_buffer(error_buffer) or "Unknown provider callback registration error"
        raise LuaSkillsError(function_name, message)

    def _clone_bytes_into_owned_buffer(
        self,
        payload: bytes,
        buffer_out: ctypes.POINTER(FfiOwnedBuffer),
    ) -> None:
        """
        Clone one Python byte payload into one luaskills-owned FFI buffer.
        将单个 Python 字节载荷克隆到一个 luaskills 自主管理的 FFI 缓冲。
        """

        error_buffer = FfiOwnedBuffer()
        if payload:
            storage = (ctypes.c_uint8 * len(payload)).from_buffer_copy(payload)
            payload_ptr = ctypes.cast(storage, ctypes.POINTER(ctypes.c_uint8))
        else:
            storage = None
            payload_ptr = None
        status = self.library.luaskills_ffi_buffer_clone(
            payload_ptr,
            len(payload),
            buffer_out,
            ctypes.byref(error_buffer),
        )
        if status == 0:
            return
        message = self._read_owned_buffer(error_buffer) or "Unknown buffer clone error"
        raise LuaSkillsError("luaskills_ffi_buffer_clone", message)

    def _parse_borrowed_json(self, raw_buffer: FfiBorrowedBuffer) -> Any:
        """
        Parse one borrowed callback JSON buffer into a Python value.
        将单个借用 callback JSON 缓冲解析为 Python 值。
        """

        if not raw_buffer.ptr or not raw_buffer.len:
            return None
        return json.loads(ctypes.string_at(raw_buffer.ptr, raw_buffer.len).decode("utf-8"))

    def _read_owned_buffer(self, raw_buffer: FfiOwnedBuffer) -> str:
        """
        Read one owned buffer as UTF-8 text and release it when present.
        将单个拥有型缓冲读取为 UTF-8 文本，并在存在时释放。
        """

        text = ""
        if raw_buffer.ptr and raw_buffer.len:
            text = ctypes.string_at(raw_buffer.ptr, raw_buffer.len).decode("utf-8")
        if raw_buffer.ptr:
            self.library.luaskills_ffi_buffer_free(raw_buffer)
        return text

    def _configure_json_provider_setter(self, function_name: str) -> None:
        """
        Configure ctypes signatures for one JSON provider callback setter.
        为单个 JSON provider callback setter 配置 ctypes 签名。
        """

        function = getattr(self.library, function_name)
        function.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(FfiOwnedBuffer),
        ]
        function.restype = ctypes.c_int32

    def _ensure_json_provider_setter_configured(self, function_name: str) -> None:
        """
        Lazily configure one JSON provider callback setter when it is first used.
        在首次使用时惰性配置单个 JSON provider callback setter。
        """

        if function_name in self._configured_json_provider_setters:
            return
        try:
            self._configure_json_provider_setter(function_name)
        except AttributeError as exc:
            raise LuaSkillsError(
                function_name,
                f"LuaSkills library does not export {function_name}; update the native runtime before using this callback",
            ) from exc
        self._configured_json_provider_setters.add(function_name)

    def _json_provider_slot_key(self, kind: str) -> tuple[str, str]:
        """
        Build one process-local provider slot key for this library and provider kind.
        为当前动态库和 provider 类型构造一个进程内 provider 槽位键。
        """

        return (str(self.library_path), kind)


def resolve_library_path(
    explicit_path: str | os.PathLike[str] | None = None,
    runtime_root: str | os.PathLike[str] | None = None,
) -> Path:
    """
    Resolve the LuaSkills dynamic library path from an explicit path or environment variable.
    从显式路径或环境变量解析 LuaSkills 动态库路径。
    """

    selected_path = explicit_path or os.environ.get("LUASKILLS_LIB")
    if not selected_path and runtime_root:
        selected_path = resolve_luaskills_library_path_from_runtime(runtime_root)
    if not selected_path:
        raise RuntimeError("LuaSkills library path is required; pass library_path, set LUASKILLS_LIB, or install runtime assets under runtime_root")
    path = Path(selected_path).expanduser().resolve()
    if not path.exists():
        raise RuntimeError(f"LuaSkills library not found: {path}")
    return path
