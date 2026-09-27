"""
Preserve embedded JSON number, Unicode and object-member semantics before native publication.
在原生发布前保留嵌入式 JSON 数值、Unicode 及对象成员语义。
"""

from __future__ import annotations

import json
import math
import sys
from typing import Any


# JSON integer tokens use the core's signed/unsigned 64-bit union; floats retain separate intent.
# JSON 整数字面量使用核心有符号／无符号 64 位并集；浮点保留独立意图。
_INTEGER_MIN = -(1 << 63)
_INTEGER_MAX = (1 << 64) - 1


def _integer(token: str) -> int | float:
    """
    Decode integer token exactly; return negative zero as a float and reject native-range overflow.
    精确解码整数 token；将负零作为浮点返回，并拒绝超出原生范围。
    """
    if token == "-0":
        return -0.0
    # Python integers are unbounded, but accepting more bits would change meaning inside serde_json.
    # Python 整数无位数限制，但接受更多位会改变 serde_json 内的含义。
    value = int(token)
    if not _INTEGER_MIN <= value <= _INTEGER_MAX:
        raise ValueError("embedded JSON integer exceeds 64-bit representation")
    return value


def _float(token: str) -> float:
    """
    Decode floating token into finite binary64; reject overflow rather than returning infinity.
    将浮点 token 解码为有限双精度数；拒绝溢出，不返回无穷大。
    """
    value = float(token)
    if not math.isfinite(value):
        raise ValueError("embedded JSON float is not finite")
    return value


def _constant(token: str) -> None:
    """
    Reject Python's non-JSON numeric token extensions; this callback never returns normally.
    拒绝 Python 的非 JSON 数值 token 扩展；此回调不会正常返回。
    """
    raise ValueError(f"invalid embedded JSON constant: {token}")


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """
    Return one object from decoded pairs, rejecting duplicate names before their evidence disappears.
    从已解码 pairs 返回一个对象，在证据消失前拒绝重复名称。
    """
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("embedded JSON contains duplicate object members")
        result[key] = value
    return result


def decode_embedded_json(text: str) -> Any:
    """
    Decode strict JSON text without losing integer bits, negative zero or explicit null.
    解码严格 JSON text，不丢失整数位、负零或显式空值。
    Return built-in JSON values; invalid Unicode, duplicates and non-finite numbers raise ValueError.
    返回内置 JSON 值；无效 Unicode、重复成员及非有限数抛出 ValueError。
    """
    value = json.loads(text, parse_int=_integer, parse_float=_float,
        parse_constant=_constant, object_pairs_hook=_object)
    # Python's decoder retains unpaired surrogate escapes, unlike Rust strings; validate every decoded string.
    # Python 解码器会保留不成对代理转义，区别于 Rust 字符串；校验每个已解码字符串。
    pending = [value]
    while pending:
        current = pending.pop()
        if type(current) is str:
            current.encode("utf-8", errors="strict")
        elif type(current) is dict:
            pending.extend(current.keys())
            pending.extend(current.values())
        elif type(current) is list:
            pending.extend(current)
    return value


def encode_embedded_json(value: Any, max_bytes: int) -> bytes:
    """
    Freeze built-in JSON value into owned UTF-8 bytes within positive max_bytes, without serialization hooks.
    将内置 JSON value 冻结为正 max_bytes 内的拥有型 UTF-8 字节，不调用序列化钩子。
    Return exact integer/float representations; invalid keys, cycles or unsupported values raise ValueError.
    返回精确整数／浮点表示；无效键、循环或不支持的值抛出 ValueError。
    """
    if type(max_bytes) is not int or not 0 < max_bytes <= sys.maxsize:
        raise ValueError("embedded JSON max_bytes must fit a positive native size")
    # Each appended fragment consumes its actual encoded size before it joins the owned output.
    # 每个追加片段在加入拥有型输出前消耗其实际编码大小。
    output = bytearray()
    ancestors: set[int] = set()

    def append(fragment: bytes) -> None:
        """
        Append bounded fragment or reject it before output exceeds the caller's byte ceiling.
        追加有界 fragment，或在输出超过调用方字节上限前拒绝。
        """
        if len(fragment) > max_bytes - len(output):
            raise ValueError("embedded request exceeds max_request_bytes")
        output.extend(fragment)

    def quoted(text: str) -> None:
        """
        Append JSON-quoted text after cheap size admission, preserving strict UTF-8 and escaped controls.
        在廉价大小入场检查后追加 JSON 引号 text，保留严格 UTF-8 及转义控制字符。
        """
        if len(text) > max_bytes - len(output):
            raise ValueError("embedded request exceeds max_request_bytes")
        append(json.dumps(text, ensure_ascii=False).encode("utf-8", errors="strict"))

    def visit(current: Any) -> None:
        """
        Encode current by exact built-in type; only ancestors participate in cycle detection.
        按精确内置类型编码 current；仅祖先参与循环检测。
        """
        if current is None:
            append(b"null")
        elif type(current) is bool:
            append(b"true" if current else b"false")
        elif type(current) is int:
            if not _INTEGER_MIN <= current <= _INTEGER_MAX:
                raise ValueError("embedded JSON integer exceeds 64-bit representation")
            append(str(current).encode("ascii"))
        elif type(current) is float:
            if not math.isfinite(current):
                raise ValueError("embedded JSON float is not finite")
            append(json.dumps(current, allow_nan=False).encode("ascii"))
        elif type(current) is str:
            quoted(current)
        elif type(current) in (list, dict):
            identity = id(current)
            if identity in ancestors:
                raise ValueError("embedded JSON contains a cycle")
            ancestors.add(identity)
            try:
                if type(current) is list:
                    append(b"[")
                    for index, child in enumerate(current):
                        if index:
                            append(b",")
                        visit(child)
                    append(b"]")
                else:
                    append(b"{")
                    for index, (key, child) in enumerate(current.items()):
                        if type(key) is not str:
                            raise ValueError("embedded JSON object keys must be strings")
                        if index:
                            append(b",")
                        quoted(key)
                        append(b":")
                        visit(child)
                    append(b"}")
            finally:
                ancestors.remove(identity)
        else:
            raise ValueError("embedded JSON requires built-in JSON values")

    visit(value)
    return bytes(output)
