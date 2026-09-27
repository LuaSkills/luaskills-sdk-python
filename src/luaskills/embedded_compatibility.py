"""
Validate immutable native metadata before creating any embedded ownership.
在创建任何嵌入式所有权前校验不可变原生元数据。
"""

from __future__ import annotations

import ctypes
import re
import sys
from typing import Any, cast, get_args

from .embedded_contract import (
    EMBEDDED_CONTRACT_SHA256, EMBEDDED_CORE_VERSION, EMBEDDED_DESCRIPTION_VERSION,
    EMBEDDED_PROTOCOL_VERSION, EMBEDDED_REQUIRED_CAPABILITIES, EMBEDDED_ROOT_COMMANDS,
    EMBEDDED_RUNTIME_COMMANDS, OutputCoreDescription, OutputEmbeddedBuildIdentity, OutputExecutionBackend,
)
from .embedded_json import decode_embedded_json


class EmbeddedCompatibilityError(RuntimeError):
    """
    Report a rejected native description before transport allocation, without fallback or retries.
    在传输分配前报告被拒绝的原生描述，不降级或重试。
    """


def _names(value: Any, field: str) -> set[str]:
    """
    Return unique nonempty strings from the named JSON array; malformed metadata raises compatibility failure.
    从指定 JSON 数组返回唯一非空字符串；格式错误的元数据抛出兼容失败。
    """
    if type(value) is not list or any(type(item) is not str or not item for item in value):
        raise EmbeddedCompatibilityError(f"invalid native description array: {field}")
    if len(set(value)) != len(value):
        raise EmbeddedCompatibilityError(f"duplicate native description names: {field}")
    return set(value)


def decode_core_description(encoded: bytes) -> OutputCoreDescription:
    """
    Decode copied bytes, validate generated requirements and process ABI, and return an independent description.
    解码复制字节、校验生成要求及进程 ABI，并返回独立描述。
    Input hashes are provenance only; this function does not authenticate a loaded binary or its publisher.
    输入摘要仅代表来源；本函数不认证已加载二进制或其发布者。
    """
    try:
        # Decode once with the common strict codec, including duplicate-key and numeric checks.
        # 通过公共严格编解码器解码一次，包括重复键及数值检查。
        value = decode_embedded_json(encoded.decode("utf-8"))
    except (ValueError, RecursionError) as error:
        raise EmbeddedCompatibilityError("invalid native core description JSON") from error
    if type(value) is not dict or not OutputCoreDescription.__required_keys__ <= value.keys():
        raise EmbeddedCompatibilityError("incomplete native core description")
    for name, expected in (
        ("description_version", EMBEDDED_DESCRIPTION_VERSION),
        ("protocol_version", EMBEDDED_PROTOCOL_VERSION),
        ("abi_structure_version", EMBEDDED_PROTOCOL_VERSION),
        ("core_version", EMBEDDED_CORE_VERSION),
    ):
        if type(value[name]) is not type(expected) or value[name] != expected:
            raise EmbeddedCompatibilityError(f"native {name} mismatch: expected {expected!r}, received {value[name]!r}")
    for name, required in (
        ("commands", EMBEDDED_ROOT_COMMANDS),
        ("runtime_commands", EMBEDDED_RUNTIME_COMMANDS),
        ("capabilities", EMBEDDED_REQUIRED_CAPABILITIES),
        ("execution_backends", ("in_process",)),
    ):
        if not set(required) <= _names(value[name], name):
            raise EmbeddedCompatibilityError(f"native {name} does not meet the SDK contract")
    if not set(value["execution_backends"]) <= set(get_args(OutputExecutionBackend)):
        raise EmbeddedCompatibilityError("unknown native execution backend")
    # Validate every generated build field; the only non-text member is its feature inventory.
    # 校验每个生成构建字段；唯一非文本成员为功能清单。
    build = value["build"]
    if type(build) is not dict or not OutputEmbeddedBuildIdentity.__required_keys__ <= build.keys():
        raise EmbeddedCompatibilityError("incomplete native build identity")
    for name in OutputEmbeddedBuildIdentity.__required_keys__ - {"cargo_features"}:
        if type(build[name]) is not str or not build[name]:
            raise EmbeddedCompatibilityError(f"invalid native build identity: {name}")
        if name.endswith("_sha256") and re.fullmatch(r"[0-9a-f]{64}", build[name]) is None:
            raise EmbeddedCompatibilityError(f"invalid native build digest: {name}")
    _names(build["cargo_features"], "cargo_features")
    if build["contract_sha256"] != EMBEDDED_CONTRACT_SHA256:
        raise EmbeddedCompatibilityError("native embedded contract SHA-256 mismatch")
    # The loader enforces machine instruction compatibility; compare OS and actual interpreter pointer width.
    # 加载器负责机器指令兼容；比较操作系统及实际解释器指针位宽。
    target_os = {"win32": "windows", "linux": "linux", "darwin": "macos"}.get(sys.platform)
    if target_os is None or build["target_os"] != target_os:
        raise EmbeddedCompatibilityError("native target operating system mismatch or unsupported interpreter platform")
    if build["pointer_width"] != str(ctypes.sizeof(ctypes.c_void_p) * 8):
        raise EmbeddedCompatibilityError("native pointer width mismatch")
    return cast(OutputCoreDescription, value)
