"""
Prove compatibility rejection happens before native ownership and borrowed metadata remains independent.
证明兼容拒绝发生在原生所有权创建前，且借用元数据保持独立。
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from luaskills import EmbeddedCompatibilityError, EmbeddedTransport, EmbeddedTransportError
from luaskills import embedded_contract as contract
from test_embedded_transport import NativeLibrary, config, core_description


class EmbeddedCompatibilityTests(unittest.TestCase):
    """
    Exercise constructor admission with malformed/mismatched native metadata and one real-library integration.
    使用错误或不匹配的原生元数据测试构造入场，并执行一次实际动态库集成。
    """

    def assert_rejected(self, native, error_type=EmbeddedCompatibilityError):
        """
        Require a constructor error with zero transport allocations, commands or result releases.
        要求构造抛错，且传输分配、命令和结果释放均为零。
        """
        with patch("luaskills.embedded_transport.ctypes.CDLL", return_value=native):
            with self.assertRaises(error_type):
                EmbeddedTransport(config(), library_path=Path(__file__))
        self.assertEqual(native.constructor_calls, 0)
        self.assertFalse(native.received)
        self.assertFalse(native.released)
        self.assertFalse(native.allocations)

    def test_versions_contract_platform_and_capabilities_reject_before_allocation(self):
        """
        Reject each incompatible identity independently, including bool/float versions and missing capabilities.
        独立拒绝每种不兼容身份，包括布尔或浮点版本及缺少能力。
        """
        for field, invalid in (
            ("description_version", 2), ("protocol_version", 2), ("abi_structure_version", 2),
            ("protocol_version", True), ("protocol_version", 1.0), ("core_version", "0.0.0"),
            ("commands", []), ("runtime_commands", []), ("capabilities", []),
            ("execution_backends", ["worker_process"]),
            ("execution_backends", ["in_process", "unknown"]),
            ("capabilities", ["strict_json_v1", "strict_json_v1"]),
            ("capabilities", [False]),
        ):
            with self.subTest(field=field, invalid=invalid):
                value = core_description()
                value[field] = invalid
                native = NativeLibrary()
                native.description_bytes = json.dumps(value).encode()
                self.assert_rejected(native)
        for field, invalid in (
            ("contract_sha256", "0" * 64), ("inputs_sha256", "bad"),
            ("target_os", "unsupported"), ("pointer_width", "0"), ("rustc", None),
            ("cargo_features", ["DUPLICATE", "DUPLICATE"]),
        ):
            with self.subTest(build=field):
                value = core_description()
                value["build"][field] = invalid
                native = NativeLibrary()
                native.description_bytes = json.dumps(value).encode()
                self.assert_rejected(native)

    def test_missing_fields_and_strict_json_are_rejected(self):
        """
        Cover all generated required fields plus malformed UTF-8, duplicate JSON keys and missing objects.
        覆盖全部生成必需字段，以及错误 UTF-8、重复 JSON 键及缺少对象。
        """
        for group in (None, "build"):
            original = core_description()
            for field in (original if group is None else original[group]):
                with self.subTest(group=group, field=field):
                    value = core_description()
                    del (value if group is None else value[group])[field]
                    native = NativeLibrary()
                    native.description_bytes = json.dumps(value).encode()
                    self.assert_rejected(native)
        for encoded in (b"\xff", b"[]", b"null", b"{", b'{"core_version":1,"core_version":2}'):
            with self.subTest(encoded=encoded):
                native = NativeLibrary()
                native.description_bytes = encoded
                self.assert_rejected(native)

    def test_bootstrap_symbol_status_and_buffer_bounds_fail_before_copy(self):
        """
        Reject missing symbols, native errors and unsafe buffer shapes without touching borrowed memory.
        拒绝缺少符号、原生错误及不安全缓冲形状，不触碰借用内存。
        """
        native = NativeLibrary()
        del native.luaskills_ffi_embedded_describe_v1
        self.assert_rejected(native)
        native = NativeLibrary()
        native.description_status = contract.EmbeddedNativeStatus.INTERNAL
        self.assert_rejected(native, EmbeddedTransportError)
        for length, null in ((0, False), (contract.EMBEDDED_DESCRIPTION_MAX_BYTES + 1, False), (16, True)):
            with self.subTest(length=length, null=null):
                native = NativeLibrary()
                native.description_length = length
                native.description_null = null
                with patch("luaskills.embedded_transport.ctypes.string_at", side_effect=AssertionError("unexpected copy")):
                    self.assert_rejected(native)

    def test_snapshot_is_independent_and_additive_capabilities_are_accepted(self):
        """
        Allow extra semantic capabilities while keeping metadata independent of caller mutations and native storage.
        允许额外语义能力，同时使元数据独立于调用方修改及原生存储。
        """
        native = NativeLibrary()
        value = core_description()
        value["capabilities"].append("future_optional_capability")
        native.description_bytes = json.dumps(value).encode()
        with patch("luaskills.embedded_transport.ctypes.CDLL", return_value=native):
            transport = EmbeddedTransport(config(), library_path=Path(__file__))
        try:
            snapshot = transport.core_description
            self.assertEqual(snapshot, value)
            snapshot["build"]["cargo_features"].append("MUTATED")
            snapshot["capabilities"].clear()
            native.description_bytes = b"invalid after copy"
            self.assertEqual(transport.core_description, value)
            self.assertEqual(native.constructor_calls, 1)
            self.assertFalse(native.released)
        finally:
            transport.close()
            transport.free()

    @unittest.skipUnless(os.environ.get("LUASKILLS_LIB"), "requires an explicit matching native library")
    def test_actual_library_describes_before_transport_and_matches_live_commands(self):
        """
        Read actual native metadata and compare it with the existing transport describe response.
        读取实际原生元数据，并与既有传输描述响应比较。
        """
        transport = EmbeddedTransport(config(), library_path=os.environ["LUASKILLS_LIB"])
        try:
            description = transport.core_description
            self.assertEqual(description["build"]["contract_sha256"], contract.EMBEDDED_CONTRACT_SHA256)
            self.assertIn("rustc ", description["build"]["rustc"])
            self.assertEqual(description["execution_backends"], ["in_process"])
            live = transport.request({"type": "describe"})
            for field in ("core_version", "protocol_version", "abi_structure_version", "commands", "runtime_commands"):
                self.assertEqual(description[field], live[field])
        finally:
            transport.close()
            transport.free()
