from __future__ import annotations

import ctypes
import sys
import unittest
from pathlib import Path

# Make the source package importable when tests run from one checkout.
# 从检出目录运行测试时让源码包可导入。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from luaskills.ffi import FfiOwnedBuffer, LuaSkillsError, LuaSkillsJsonFfi


class FakeLibrary:
    """
    Minimal native library double that records buffer frees.
    记录缓冲释放的最小原生库替身。
    """

    def __init__(self) -> None:
        """
        Initialize the free counter.
        初始化释放计数器。
        """

        self.free_count = 0

    def luaskills_ffi_buffer_free(self, _buffer: FfiOwnedBuffer) -> None:
        """
        Record one native buffer release.
        记录一次原生缓冲释放。
        """

        self.free_count += 1


def make_ffi() -> tuple[LuaSkillsJsonFfi, FakeLibrary]:
    """
    Build one LuaSkillsJsonFfi shell without loading a native library.
    构造一个不会加载原生库的 LuaSkillsJsonFfi 外壳。
    """

    ffi = LuaSkillsJsonFfi.__new__(LuaSkillsJsonFfi)
    library = FakeLibrary()
    ffi.library = library
    return ffi, library


def owned_buffer_from_text(text: str) -> tuple[FfiOwnedBuffer, object]:
    """
    Build one owned-buffer view backed by Python storage for tests.
    构造一个由 Python 存储支撑的测试用拥有型缓冲视图。
    """

    payload = text.encode("utf-8")
    storage = (ctypes.c_uint8 * len(payload)).from_buffer_copy(payload)
    return (
        FfiOwnedBuffer(
            ptr=ctypes.cast(storage, ctypes.POINTER(ctypes.c_uint8)),
            len=len(payload),
        ),
        storage,
    )


class FfiEnvelopeErrorTests(unittest.TestCase):
    """
    Unit tests for malformed FFI envelope diagnostics.
    畸形 FFI 包络诊断的单元测试。
    """

    def test_empty_envelope_reports_luaskills_error(self) -> None:
        """
        Verify empty native responses are reported with FFI function context.
        校验空原生响应会带 FFI 函数上下文报告。
        """

        ffi, library = make_ffi()

        with self.assertRaisesRegex(LuaSkillsError, "luaskills_ffi_demo_json: empty JSON FFI response envelope"):
            ffi._decode_envelope("luaskills_ffi_demo_json", FfiOwnedBuffer())
        self.assertEqual(library.free_count, 1)

    def test_invalid_envelope_reports_luaskills_error(self) -> None:
        """
        Verify malformed JSON envelopes are wrapped as SDK errors.
        校验畸形 JSON 包络会包装为 SDK 错误。
        """

        ffi, _ = make_ffi()
        buffer, _storage = owned_buffer_from_text("{")

        with self.assertRaisesRegex(LuaSkillsError, "luaskills_ffi_demo_json: invalid JSON FFI response envelope"):
            ffi._decode_envelope("luaskills_ffi_demo_json", buffer)

    def test_non_object_envelope_reports_luaskills_error(self) -> None:
        """
        Verify non-object JSON envelopes are rejected before field access.
        校验非对象 JSON 包络会在字段访问前被拒绝。
        """

        ffi, _ = make_ffi()
        buffer, _storage = owned_buffer_from_text("[1]")

        with self.assertRaisesRegex(LuaSkillsError, "luaskills_ffi_demo_json: JSON FFI response envelope must be one object"):
            ffi._decode_envelope("luaskills_ffi_demo_json", buffer)


if __name__ == "__main__":
    unittest.main()
