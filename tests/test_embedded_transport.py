"""
Verify native result ownership and Python interruption boundaries without external runtime assets.
验证原生结果所有权及 Python 中断边界，不依赖外部运行时资源。
"""

from __future__ import annotations

import ctypes
import json
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from luaskills import EmbeddedRuntimeError, EmbeddedTransport, EmbeddedTransportConfig, EmbeddedTransportError
from luaskills.embedded_transport import _NativeConfig, _NativeResult


def config() -> EmbeddedTransportConfig:
    """
    Return explicit small transport budgets for each isolated test owner.
    为每个隔离测试所有者返回显式小型传输预算。
    """
    return EmbeddedTransportConfig(max_runtimes=2, max_result_buffers=4,
        max_result_bytes=32768, max_response_bytes=8192, max_request_bytes=8192)


class NativeFunction:
    """
    Emulate a ctypes function's configurable signature while preserving the actual pointer ABI.
    模拟 ctypes 函数的可配置签名，同时保留实际指针 ABI。
    """

    def __init__(self, callback):
        """
        Retain a test callback receiving the exact native arguments.
        保留接收精确原生参数的测试回调。
        """
        self.callback = callback

    def __call__(self, *args):
        """
        Forward unchanged native arguments and return the test status.
        转发未更改的原生参数，并返回测试状态。
        """
        return self.callback(*args)


class NativeLibrary:
    """
    Controlled native failure source that owns allocated bytes until exact descriptor release.
    可控原生故障源，在精确描述符释放前拥有已分配字节。
    """

    def __init__(self):
        """
        Initialize high-bit identities, explicit replies and observable ownership.
        初始化高位身份、显式响应及可观察所有权。
        """
        # Values above signed int64 prove every uint64 identity bit survives the binding.
        # 超过有符号 int64 的值证明绑定保留 uint64 身份的全部位。
        self.identity = (1 << 63) + 55
        self.next_allocation = (1 << 63) + 101
        self.reply = b'{"protocol_version":1,"status":"ok","result":null}'
        self.request_status = 0
        self.release_status = 0
        self.interrupt_after_publication = False
        self.allocations = {}
        self.received = []
        self.released = []
        self.entered = threading.Event()
        self.proceed = threading.Event()
        self.proceed.set()
        self.closed = False
        self.freed = False
        self.luaskills_ffi_embedded_transport_new_v1 = NativeFunction(self.new)
        self.luaskills_ffi_embedded_transport_close_v1 = NativeFunction(self.close)
        self.luaskills_ffi_embedded_transport_free_v1 = NativeFunction(self.free)
        self.luaskills_ffi_embedded_result_free_v1 = NativeFunction(self.result_free)
        self.luaskills_ffi_embedded_request_v1 = NativeFunction(self.request)

    def new(self, config_pointer, output):
        """
        Validate real ctypes structure layout and write the full native identity.
        校验实际 ctypes 结构布局，并写入完整原生身份。
        """
        native = ctypes.cast(config_pointer, ctypes.POINTER(_NativeConfig)).contents
        assert native.struct_size == ctypes.sizeof(_NativeConfig)
        assert native.protocol_version == 1
        assert native.max_response_bytes == config().max_response_bytes
        ctypes.cast(output, ctypes.POINTER(ctypes.c_uint64))[0] = self.identity
        return 0

    def request(self, identity, borrowed, output):
        """
        Read exact borrowed JSON, optionally block, and publish bytes through a real result pointer.
        读取精确借用 JSON，可选阻塞，并通过实际结果指针发布字节。
        """
        assert identity == self.identity
        self.received.append(json.loads(ctypes.string_at(borrowed.ptr, borrowed.len)))
        self.entered.set()
        assert self.proceed.wait(5), "test did not release native call"
        if self.request_status:
            return self.request_status
        allocation = self.next_allocation
        self.next_allocation += 1
        storage = (ctypes.c_uint8 * len(self.reply)).from_buffer_copy(self.reply)
        self.allocations[allocation] = storage
        result = ctypes.cast(output, ctypes.POINTER(_NativeResult)).contents
        result.ptr = ctypes.cast(storage, ctypes.POINTER(ctypes.c_uint8))
        result.len = len(storage)
        result.allocation_id = allocation
        if self.interrupt_after_publication:
            raise KeyboardInterrupt("injected interruption after native publication")
        return 0

    def result_free(self, identity, result):
        """
        Reject changed descriptors; preserve owned memory until a successful exact free.
        拒绝被修改的描述符；精确释放成功前保留拥有内存。
        """
        assert identity == self.identity
        storage = self.allocations[result.allocation_id]
        assert result.len == len(storage)
        assert ctypes.addressof(storage) == ctypes.addressof(result.ptr.contents)
        if self.release_status:
            return self.release_status
        self.released.append(result.allocation_id)
        del self.allocations[result.allocation_id]
        return 0

    def close(self, identity):
        """
        Record explicit close while preserving existing request ownership.
        记录显式关闭，同时保留已有请求所有权。
        """
        assert identity == self.identity
        self.closed = True
        return 0

    def free(self, identity):
        """
        Report busy until explicit close and all native result ownership have drained.
        在显式关闭及全部原生结果所有权排空前报告忙碌。
        """
        assert identity == self.identity
        if not self.closed or self.allocations:
            return 3
        self.freed = True
        return 0


class EmbeddedTransportTests(unittest.TestCase):
    """
    Test the actual binding with controlled native errors, result bytes and concurrent calls.
    使用可控原生错误、结果字节及并发调用测试实际绑定。
    """

    def setUp(self):
        """
        Load an isolated fake library through the same constructor used by production callers.
        通过生产调用方使用的相同构造函数加载隔离模拟库。
        """
        self.native = NativeLibrary()
        self.loader = patch("luaskills.embedded_transport.ctypes.CDLL", return_value=self.native)
        self.loader.start()
        self.addCleanup(self.loader.stop)
        self.transport = EmbeddedTransport(config(), library_path=Path(__file__))

    def tearDown(self):
        """
        Require exact result drainage before closing and freeing each surviving test owner.
        关闭及释放每个存活测试所有者前要求精确结果排空。
        """
        self.native.proceed.set()
        self.native.release_status = 0
        if not self.native.freed:
            self.transport.release_results()
            self.transport.close()
            self.transport.free()
        self.assertFalse(self.native.allocations)

    def test_uint64_identity_unicode_and_explicit_null(self):
        """
        Preserve high-bit IDs, Unicode, embedded NUL and successful null across exact buffer release.
        跨精确缓冲释放保留高位身份、Unicode、嵌入空字符及成功空值。
        """
        self.assertIsNone(self.transport.request({"type":"probe","value":"中文\0🦥"}))
        self.assertEqual(self.native.received[-1]["command"]["value"], "中文\0🦥")
        self.assertEqual(self.native.released, [(1 << 63) + 101])
        self.assertFalse(self.native.allocations)

    def test_parse_failure_always_releases_actual_result(self):
        """
        Invalid UTF-8, JSON, version and missing success fields must release their returned allocations.
        无效 UTF-8、JSON、版本及缺失成功字段必须释放对应返回分配。
        """
        for reply in [b"\xff", b"{", b'{"protocol_version":2,"status":"ok","result":0}',
            b'{"protocol_version":1,"status":"ok"}']:
            with self.subTest(reply=reply):
                self.native.reply = reply
                with self.assertRaises((UnicodeDecodeError, ValueError)):
                    self.transport.request({"type":"describe"})
                self.assertFalse(self.native.allocations)

    def test_transport_and_business_errors_remain_distinct(self):
        """
        Native rejection owns no result, while delivered business errors release their owned buffer.
        原生拒绝不拥有结果；已交付业务错误则释放其拥有缓冲。
        """
        self.native.request_status = 4
        with self.assertRaises(EmbeddedTransportError) as native_error:
            self.transport.request({"type":"describe"})
        self.assertEqual(native_error.exception.status, 4)
        self.assertFalse(self.native.released)
        self.native.request_status = 0
        self.native.reply = b'{"protocol_version":1,"status":"error","error":{"code":"busy","message":"still draining"}}'
        with self.assertRaises(EmbeddedRuntimeError) as business_error:
            self.transport.request({"type":"describe"})
        self.assertEqual(business_error.exception.code, "busy")
        self.assertEqual(business_error.exception.message, "still draining")
        self.assertEqual(str(business_error.exception), "busy: still draining")
        self.assertEqual(business_error.exception.args, ("busy: still draining",))
        self.assertEqual(len(self.native.released), 1)

    def test_release_failure_retains_descriptor_and_blocks_free(self):
        """
        Preserve exact result ownership after failed free and allow explicit release recovery.
        释放失败后保留精确结果所有权，并允许显式恢复释放。
        """
        self.native.release_status = 6
        with self.assertRaises(EmbeddedTransportError):
            self.transport.request({"type":"describe"})
        with self.assertRaisesRegex(RuntimeError, "owns active calls or results"):
            self.transport.free()
        self.assertEqual(len(self.native.allocations), 1)
        self.native.release_status = 0
        self.transport.release_results()
        self.assertFalse(self.native.allocations)

    def test_python_interruption_releases_already_published_native_result(self):
        """
        A Python interruption raised at native return cannot leak a result that was already published.
        原生返回时抛出的 Python 中断不能泄漏已经发布的结果。
        """
        self.native.interrupt_after_publication = True
        with self.assertRaises(KeyboardInterrupt):
            self.transport.request({"type":"describe"})
        self.assertEqual(len(self.native.released), 1)
        self.assertFalse(self.native.allocations)

    def test_close_remains_live_while_a_request_is_blocked(self):
        """
        Concurrent close must progress, but actual free and result recovery wait for the request to return.
        并发关闭必须推进，但实际释放及结果恢复需等待请求返回。
        """
        self.native.proceed.clear()
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.transport.request, {"type":"describe"})
            try:
                self.assertTrue(self.native.entered.wait(5))
                self.transport.close()
                self.assertTrue(self.native.closed)
                with self.assertRaisesRegex(RuntimeError, "owns active calls or results"):
                    self.transport.free()
                with self.assertRaisesRegex(RuntimeError, "active calls"):
                    self.transport.release_results()
            finally:
                self.native.proceed.set()
            self.assertIsNone(future.result(timeout=5))
        self.transport.free()
        with self.assertRaisesRegex(RuntimeError, "has been freed"):
            self.transport.request({"type":"describe"})

    def test_budget_types_and_invalid_json_fail_before_native_execution(self):
        """
        Reject wrapping integer inputs and non-finite JSON without creating native request ownership.
        拒绝回绕整数输入与非有限 JSON，不创建原生请求所有权。
        """
        for invalid in [True, 0, -1, 1.5, sys.maxsize + 1]:
            with self.assertRaises(ValueError):
                EmbeddedTransportConfig(max_runtimes=invalid, max_result_buffers=1,
                    max_result_bytes=1, max_response_bytes=1, max_request_bytes=1)
        with self.assertRaises(ValueError):
            self.transport.request({"value":float("nan")})
        with self.assertRaisesRegex(ValueError, "exceeds max_request_bytes"):
            self.transport.request({"value":"x" * config().max_request_bytes})
        self.assertFalse(self.native.received)


if __name__ == "__main__":
    unittest.main()
