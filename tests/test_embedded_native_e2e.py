"""
Run the actual Python transport against an explicitly selected newly built LuaSkills library.
对显式选择的新构建 LuaSkills 动态库运行实际 Python 传输。
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from luaskills import EmbeddedRuntimeError, EmbeddedTransport, EmbeddedTransportConfig, EmbeddedTransportError, create_engine_options


class EmbeddedNativeFixture:
    """
    Share one isolated real native runtime layout across transport and callback integration tests.
    在传输与回调集成测试之间共享一个隔离的实际原生运行时布局。
    """

    def setUp(self):
        """
        Create the host-authorized package outside System for every real embedded SDK scenario.
        为每个真实嵌入式 SDK 场景在 System 外创建宿主授权包。
        """
        # Temporary files outlive the actual native shutdown cleanup registered below.
        # 临时文件比下方注册的实际原生关闭清理存活更久。
        self.directory = tempfile.TemporaryDirectory(prefix="luaskills-embedded-python-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.plugin_id = "python-embedded-test"
        self.system_root = self.root / "system_lua_lib"
        # Formal modules use the exact declaration rather than legacy System-root containment.
        # 正式模块使用精确声明，不依赖旧 System 根包含关系。
        self.package_root = self.root / "plugin-generations" / self.plugin_id
        self.package_root.mkdir(parents=True)
        (self.package_root / "dependencies.yaml").write_text("{}\n", encoding="utf-8")
        # These are fixture budgets, with enough transport room for the entire bounded core snapshot.
        # 这些是夹具预算，传输空间足以容纳整个有界核心快照。
        self.transport = EmbeddedTransport(EmbeddedTransportConfig(
            max_runtimes=1, max_result_buffers=4, max_result_bytes=131072,
            max_response_bytes=32768, max_request_bytes=65536,
        ), library_path=os.environ["LUASKILLS_LIB"])
        self.runtime_id = None
        self.addCleanup(self._drain)
        self.runtime_id = self.transport.request({"type":"runtime_reserve"})["runtime_id"]
        self.runtime_limits = {
            "max_registered_plugins":4, "max_registered_pools":4, "max_sessions":4,
            "max_registered_capabilities":4, "max_resident_vms":2, "max_running_calls":2,
            "max_queued_calls":4, "max_queued_bytes":4096, "max_operations":16,
            "max_effect_records_per_operation":8, "max_effect_bytes_per_operation":8192,
            "max_host_requests":4, "max_host_request_bytes":8192, "max_value_bytes":1024,
        }
        self.transport.request({"type":"runtime_initialize", "runtime_id":self.runtime_id,
            "engine_options":create_engine_options(self.root, host_options={
                "system_lua_lib_dir":self.system_root.as_posix(), "allow_network_download":False,
            }), "runtime_config":self.runtime_limits})
        status = self.transport.request({"type":"runtime_status", "runtime_id":self.runtime_id})
        self.assertEqual(status["initialization"], "ready", status)
        self.command({"type":"plugin_register", "plugin_id":self.plugin_id,
            "config":{name:self.runtime_limits[name] for name in (
                "max_registered_pools", "max_sessions", "max_resident_vms", "max_running_calls",
                "max_queued_calls", "max_queued_bytes", "max_operations",
            )}})

    def _drain(self):
        """
        Require actual native worker closure before removing the known runtime and freeing its transport.
        移除已知运行时及释放传输前要求实际原生工作线程关闭。
        """
        self.transport.close()
        if self.runtime_id is not None:
            deadline = time.monotonic() + 5
            while True:
                status = self.transport.request({"type":"runtime_status", "runtime_id":self.runtime_id})
                if status["closed"]:
                    break
                self.assertLess(time.monotonic(), deadline, status)
                time.sleep(0.001)
            self.transport.request({"type":"runtime_free", "runtime_id":self.runtime_id})
        self.transport.free()

    def command(self, operation):
        """
        Execute one exact-runtime command and return the successful business result.
        执行一个精确运行时命令，并返回成功业务结果。
        """
        return self.transport.request({"type":"runtime", "runtime_id":self.runtime_id, "operation":operation})

    def pool(self, source, finalizer=None, reuse="reusable"):
        """
        Register source and optional finalizer with the caller's explicit reuse policy.
        按调用方显式复用策略注册源码及可选关闭回调。
        Return the exact registered pool identity for subsequent fixture commands.
        返回精确已注册池身份，供后续夹具命令使用。
        """
        request = {"type":"pool_register", "definition":{
            "plugin_id":self.plugin_id, "generation":"python-generation-1",
            "package_root":self.package_root.as_posix(), "dependencies_file":"dependencies.yaml",
            "workspace_root":None, "cwd":None, "mounts":{}, "security_partition":"python-test",
            "source":source, "exports":[{"name":"call", "input_schema":True, "output_schema":True}],
        }, "policy":{
            "kind":"shared", "min_resident_vms":0, "max_resident_vms":2,
            "max_running_calls":2, "max_queued_calls":4, "reuse":reuse, "serial":False,
            "backend":"in_process", "idle_ttl_ms":None, "max_uses":None,
        }, "permissions":["python.host"], "execution_revision":"python-v1"}
        if finalizer is not None:
            request["definition"]["finalizer"] = finalizer
            request["definition"]["exports"].append({"name":finalizer["export"], "input_schema":True, "output_schema":True})
        return self.command(request)["pool_id"]

    def submit(self, pool_id, arguments):
        """
        Admit an ordinary call with a finite execution budget and explicit trusted host context.
        使用有限执行预算及显式可信宿主上下文接纳普通调用。
        """
        return self.command({"type":"call_submit", "timeout_ms":10000, "call":{
            "pool_id":pool_id, "export":"call", "arguments":arguments,
            "context":{"request_context":None, "client_budget":None, "tool_config":None},
        }})["operation_id"]

    def terminal(self, operation_id):
        """
        Read a terminal core snapshot without inferring completion from a timeout or cancellation request.
        读取核心终态快照，不从超时或取消请求推断完成。
        """
        deadline = time.monotonic() + 5
        while True:
            snapshot = self.command({"type":"operation_status", "operation_id":operation_id})
            if snapshot["phase"] in ("succeeded", "failed", "cancelled"):
                return snapshot
            self.assertLess(time.monotonic(), deadline, snapshot)
            time.sleep(0.001)

@unittest.skipUnless(os.environ.get("LUASKILLS_LIB"), "LUASKILLS_LIB is not configured")
class EmbeddedNativeIntegrationTests(EmbeddedNativeFixture, unittest.TestCase):
    """
    Verify real C signatures, core lifetime, Lua state and callback ownership without mock native calls.
    验证实际 C 签名、核心寿命、Lua 状态及回调所有权，不模拟原生调用。
    """

    def test_automatic_finalization_preserves_null_and_independent_failure(self):
        """
        Consume real automatic closing through ctypes and retain both results including successful null.
        通过 ctypes 消费真实自动关闭，并保留包含成功空值的两个结果。
        """
        pool_id = self.pool(
            "local called=false; local fail=false; return {call=function(a) called=true; fail=a; return nil end, shutdown=function() assert(called); if fail then error('closing failed') end; return nil end}",
            {"export":"shutdown", "arguments":None, "timeout_ms":1000}, reuse="single_call",
        )
        for fail in (False, True):
            with self.subTest(closing_failure=fail):
                snapshot = self.terminal(self.submit(pool_id, fail))
                self.assertEqual(snapshot["phase"], "failed" if fail else "succeeded", snapshot)
                stages = snapshot["finalization"]
                self.assertEqual(stages["business"], {"status":"succeeded", "value":None})
                self.assertEqual(stages["business_effect_count"], 0)
                if fail:
                    self.assertEqual(stages["outcome"]["status"], "failed")
                    self.assertEqual(stages["outcome"]["error"], snapshot["error"])
                else:
                    self.assertEqual(stages["outcome"], {"status":"succeeded", "value":None})
                    self.assertIn("value", snapshot)
                    self.assertIsNone(snapshot["value"])

    def test_session_finalization_has_independent_queryable_operation(self):
        """
        Retain business results while observing reserved capacity and the session's independent closing outcome.
        保留业务结果，同时观察预留容量及会话独立关闭结果。
        """
        pool_id = self.pool(
            "local n=0; return {call=function() n=n+1; return tostring(n) end, shutdown=function() return tostring(n) end}",
            {"export":"shutdown", "arguments":None, "timeout_ms":1000}, reuse="session",
        )
        opening = self.command({"type":"session_open", "pool_id":pool_id, "timeout_ms":5000})
        self.assertEqual(self.terminal(opening["operation_id"])["phase"], "succeeded")
        session_id = opening["session_id"]
        self.assertEqual(self.command({"type":"plugin_status", "plugin_id":self.plugin_id})["reserved_operations"], 1)
        operation_id = self.command({"type":"session_submit", "session_id":session_id, "export":"call",
            "arguments":None, "context":{"request_context":None, "client_budget":None, "tool_config":None}, "timeout_ms":5000})["operation_id"]
        business = self.terminal(operation_id)
        self.assertEqual(business["value"], "1")
        self.command({"type":"session_close", "session_id":session_id})
        deadline = time.monotonic() + 5
        while True:
            session = self.command({"type":"session_status", "session_id":session_id})
            if session["phase"] == "closed":
                break
            self.assertLess(time.monotonic(), deadline, session)
            time.sleep(0.001)
        self.assertNotEqual(session["finalization_operation"], operation_id)
        closing = self.terminal(session["finalization_operation"])
        self.assertEqual(closing["phase"], "succeeded")
        self.assertEqual(closing["finalization"]["business"], {"status":"succeeded", "value":None})
        self.assertEqual(closing["finalization"]["outcome"], {"status":"succeeded", "value":"1"})
        self.assertEqual(self.command({"type":"operation_status", "operation_id":operation_id}), business)
        self.assertEqual(self.command({"type":"plugin_status", "plugin_id":self.plugin_id})["reserved_operations"], 0)

    def test_reusable_finalization_is_discovered_after_later_business_ids(self):
        """
        Discover the reserved closing identity by publication order and retain same-VM state through the actual DLL.
        通过实际 DLL 按发布顺序发现预留关闭身份，并保留同 VM 状态。
        """
        pool_id = self.pool(
            "local n=0; return {call=function() n=n+1; return tostring(n) end, shutdown=function() return tostring(n) end}",
            {"export":"shutdown", "arguments":None, "timeout_ms":1000}, reuse="reusable",
        )
        # Two business IDs span the earlier reservation without publishing it as an executable operation.
        # 两个业务身份跨越较早预留，但不将预留发布为可执行操作。
        business = []
        for expected in ("1", "2"):
            operation_id = self.submit(pool_id, None)
            result = self.terminal(operation_id)
            self.assertEqual(result["value"], expected)
            business.append((operation_id, result))
        self.command({"type":"pool_close", "pool_id":pool_id})
        deadline = time.monotonic() + 5
        while True:
            page = self.command({"type":"operation_list", "pool_id":pool_id,
                "after_operation_id":business[-1][0], "limit":1})
            if page["operation_ids"]:
                break
            self.assertLess(time.monotonic(), deadline, page)
            time.sleep(0.001)
        self.assertEqual(len(page["operation_ids"]), 1)
        closing_id = page["operation_ids"][0]
        self.assertEqual(page["after_operation_id"], closing_id)
        closing = self.terminal(closing_id)
        self.assertEqual(closing["phase"], "succeeded")
        self.assertTrue(closing["context"]["finalization_instance_id"].startswith("embedded-vm:"))
        self.assertIsNone(closing["context"]["caller"]["session_id"])
        self.assertEqual(closing["finalization"]["outcome"], {"status":"succeeded", "value":"2"})
        for operation_id, previous in business:
            self.assertNotEqual(operation_id, closing_id)
            self.assertEqual(self.command({"type":"operation_status", "operation_id":operation_id}), previous)

    def test_application_integer_policy_before_admission(self):
        """
        Reject nested unsafe integers before source initialization; echo safe endpoints and finite floats.
        在源码初始化前拒绝嵌套不安全整数；回传安全端点及有限浮点数。
        Return nothing after exact native operation observations and normal fixture cleanup.
        精确观察原生操作并正常清理夹具后无返回值。
        """
        # Initialization is an observable tripwire if any rejected request creates a VM.
        # 若被拒绝请求创建 VM，初始化会成为可观察的触发器。
        rejecting_pool = self.pool("error('invalid arguments reached initialization')")
        for value in (2**53, -(2**53), {"nested": [2**64 - 1]}):
            with self.assertRaises(EmbeddedRuntimeError) as failure:
                self.submit(rejecting_pool, value)
            self.assertEqual(failure.exception.code, "invalid_argument")
        self.assertEqual(self.command({"type": "operation_list", "pool_id": rejecting_pool,
            "after_operation_id": None, "limit": 16})["operation_ids"], [])
        # Python float supplies an explicit JSON Float even at the rejected integer's magnitude.
        # Python float 即使处于被拒绝整数的量级也提供显式 JSON Float。
        echo_pool = self.pool("return {call=function(a) return a end}")
        for value in (2**53 - 1, -(2**53 - 1), float(2**53), 1e100):
            # Forget exact admitted operations after checking their real terminal snapshots.
            # 检查真实终态快照后遗忘精确已入场操作。
            operation_id = self.submit(echo_pool, value)
            result = self.terminal(operation_id)
            self.assertEqual(result["phase"], "succeeded", result)
            self.assertEqual(result["value"], value)
            self.assertIs(type(result["value"]), type(value))
            self.command({"type": "operation_forget", "operation_id": operation_id})

    def test_actual_lua_state_json_types_and_native_lifecycle(self):
        """
        Preserve Lua state and structured values through ctypes, then release each retained operation.
        通过 ctypes 保留 Lua 状态与结构化值，随后释放每个保留操作。
        """
        description = self.transport.request({"type":"describe"})
        self.assertIn("host_request_complete", description["runtime_commands"])
        pool_id = self.pool("local n=0; return {call=function(a) n=n+1; return {count=n,arg=a} end}")
        arguments = {"text":"中文\0🦥", "array":[], "object":{}, "null":None, "boolean":False}
        for count in (1, 2):
            operation_id = self.submit(pool_id, arguments)
            done = self.terminal(operation_id)
            self.assertEqual(done["phase"], "succeeded", done)
            self.assertEqual(done["value"], {"count":count, "arg":arguments})
            self.command({"type":"operation_forget", "operation_id":operation_id})
            with self.assertRaises(EmbeddedRuntimeError) as error:
                self.command({"type":"operation_status", "operation_id":operation_id})
            self.assertEqual(error.exception.code, "not_found")
        # Null at the operation's own value field must remain present, separate from an absent value.
        # 操作自身 value 字段为空值时必须仍然存在，与字段缺失区分。
        null_pool = self.pool("return {call=function(a) return a end}")
        null_result = self.terminal(self.submit(null_pool, None))
        self.assertEqual(null_result["phase"], "succeeded", null_result)
        self.assertIn("value", null_result)
        self.assertIsNone(null_result["value"])

    def test_real_callback_wait_cancel_and_late_committed_acknowledgement(self):
        """
        Keep the control channel live during native wait and preserve a late host commit after cancellation.
        原生等待期间保持控制通道活动，并在取消后保留迟到宿主提交。
        """
        registration = self.command({"type":"capabilities_register", "descriptors":[{
            "name":"python.callback", "version":"1.0.0", "description":"Python integration callback",
            "input_schema":True, "output_schema":True, "execution":"queued", "permissions":["python.host"],
            "scope":"invocation", "max_concurrent":1, "max_call_ms":10000,
            "max_input_bytes":1024, "max_output_bytes":1024, "effects":"mutating", "idempotency":"none",
        }]})["registration_ids"][0]
        pool_id = self.pool("return {call=function(a) vulcan.context.request.request_id='lua-forged'; return vulcan.capabilities.call('python.callback',a) end}")
        # The original host request is supplied before admission, outside Lua-owned arguments.
        # 原宿主请求在入场前提供，位于 Lua 所有参数之外。
        operation_id = self.command({"type":"call_submit", "timeout_ms":10000, "call":{
            "pool_id":pool_id, "export":"call", "arguments":{"plugin_id":"forged", "request_id":"argument-forged", "value":None},
            "context":{"request_context":{"request_id":"python-host-request"}, "client_budget":None, "tool_config":None},
        }})["operation_id"]
        deadline = time.monotonic() + 5
        while True:
            requests = self.command({"type":"host_requests_take", "limit":1})
            if requests:
                self.assertEqual(len(requests), 1)
                request = requests[0]
                break
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.001)
        with ThreadPoolExecutor(max_workers=1) as executor:
            waiting = executor.submit(self.command, {"type":"operation_wait", "operation_id":operation_id, "wait_ms":5000})
            try:
                self.assertEqual(request["registration_id"], registration)
                self.assertEqual(request["caller"]["plugin_id"], self.plugin_id)
                self.assertEqual(request["caller"]["operation_id"], operation_id)
                self.assertEqual(request["caller"]["request_id"], "python-host-request")
                self.assertNotEqual(request["request_id"], request["caller"]["request_id"])
                self.assertEqual(request["arguments"]["request_id"], "argument-forged")
                self.assertEqual(request["arguments"]["plugin_id"], "forged")
                self.command({"type":"operation_cancel", "operation_id":operation_id})
                self.transport.close()
                with self.assertRaises(EmbeddedRuntimeError) as closed:
                    self.submit(pool_id, None)
                self.assertEqual(closed.exception.code, "closed")
                self.assertFalse(waiting.done())
                self.assertEqual(self.command({"type":"host_request_status", "request_id":request["request_id"]})["phase"], "dispatched")
            finally:
                self.command({"type":"host_request_complete", "request_id":request["request_id"],
                    "outcome":{"ok":True, "value":None, "effects":"committed"}})
            done = waiting.result(timeout=5)
        self.assertEqual(done["phase"], "cancelled", done)
        self.assertEqual(done["context"]["caller"]["request_id"], "python-host-request")
        self.assertTrue(all(effect["caller"]["request_id"] == "python-host-request" for effect in done["host_effects"]))
        self.assertTrue(any(effect["effects"] == "committed" for effect in done["host_effects"]))
        with self.assertRaises(EmbeddedTransportError) as busy:
            self.transport.free()
        self.assertEqual(busy.exception.status, 3)


if __name__ == "__main__":
    unittest.main()
