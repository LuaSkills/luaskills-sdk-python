"""
Verify the Lua application integer policy through an independently installed native SDK.
通过独立安装的原生 SDK 验证 Lua 应用整数政策。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any

from luaskills import (
    CallbackPumpConfig, EmbeddedCallbackPump, EmbeddedClient, EmbeddedCommandDriver,
    EmbeddedDriverConfig, EmbeddedResultReleaseError, EmbeddedRuntimeError, EmbeddedRuntimeScope,
    EmbeddedTransport, EmbeddedTransportConfig, HostCapability,
)
from luaskills.examples.embedded_runtime import (
    PLUGIN_ID, TIMEOUT_MS, cleanup_preserving_error, close_unscoped_runtime, initialize, take,
)


def verify_flow(driver: EmbeddedCommandDriver, transport: EmbeddedTransport,
                root: Path, package: Path) -> None:
    """
    Use driver/transport and authorized root/package to verify exact ingress, callback and cleanup evidence.
    使用 driver/transport 及授权 root/package 验证精确入站、回调及清理证据。
    Return only after the original reservation's native runtime and pump have actually closed.
    仅在原预留的原生运行时及泵实际关闭后返回。
    """
    # Retain the original reservation until its exact native slot has been removed.
    # 保留原预留，直到其精确原生槽已被移除。
    reservation = EmbeddedClient(driver).reserve()
    try:
        runtime = reservation.result(TIMEOUT_MS / 1000)
    except EmbeddedResultReleaseError:
        # Recover only the delivered identity from this receipt, then use the existing owned cleaner.
        # 仅从此回执恢复已交付身份，随后使用既有拥有型清理器。
        runtime = reservation.delivered_result()
        transport.release_results()
        close_unscoped_runtime(runtime, transport)
        reservation.forget()
        raise
    try:
        initialize(runtime, root)
        # Adopt the actual pump before module admission; the existing cleaner handles interrupted construction.
        # 模块入场前接管实际泵；既有清理器处理被中断构造。
        pump = EmbeddedCallbackPump(transport, runtime.runtime_id, CallbackPumpConfig(
            max_concurrent_handlers=1, max_pending_commands=4, poll_interval_ms=2,
        ))
        scope = EmbeddedRuntimeScope(runtime, pump=pump)
    except BaseException:
        cleanup_preserving_error(lambda: close_unscoped_runtime(runtime, transport))
        reservation.forget()
        raise
    try:
        with scope:
            # Exact identities prove original ledger completion without relying on evolving record positions.
            # 精确身份证明原始账本完成，不依赖会变化的记录位置。
            requests: list[str] = []

            def handler(value: Any, context: Any) -> Any:
                """
                Record context's request, report real commit and return u64 maximum for unsafe value only.
                记录 context 的请求、报告真实提交，仅对 unsafe value 返回 u64 最大值。
                """
                requests.append(context.request_id)
                context.report_effects("committed")
                return 2**64 - 1 if value == "unsafe" else value

            pump.register([HostCapability({
                "name": "python.policy", "version": "1.0.0", "description": "Lua application value policy acceptance",
                "input_schema": True, "output_schema": True, "execution": "queued", "permissions": ["python.host"],
                "scope": "invocation", "max_concurrent": 1, "max_call_ms": TIMEOUT_MS,
                "max_input_bytes": 1024, "max_output_bytes": 1024, "effects": "mutating", "idempotency": "none",
            }, handler, "sync")], timeout=TIMEOUT_MS / 1000)
            # Initialization itself calls the host, exposing any rejected argument that reaches a VM.
            # 初始化自身调用宿主，暴露任何到达 VM 的被拒绝参数。
            pool = take(runtime.register_pool({
                "plugin_id": PLUGIN_ID, "generation": "policy-generation-1", "package_root": package.as_posix(),
                "dependencies_file": "dependencies.yaml", "mounts": {}, "security_partition": "python-policy",
                "source": "local init=vulcan.host.call('python.policy','initialization'); assert(init.ok); return {call=function(a) return vulcan.host.call('python.policy',a) end}",
                "exports": [{"name": "call", "input_schema": True, "output_schema": True}],
            }, {
                "kind": "shared", "min_resident_vms": 0, "max_resident_vms": 1, "max_running_calls": 1,
                "max_queued_calls": 4, "reuse": "reusable", "serial": False, "backend": "in_process",
                "idle_ttl_ms": None, "max_uses": None,
            }, ["python.host"], "policy-v1", initialization_capabilities=["python.policy"]))
            # Context uses the exact generated invocation fields; it carries no application values.
            # 上下文使用精确生成调用字段；不携带应用值。
            invocation = {"request_context": None, "client_budget": None, "tool_config": None}
            for value in (2**53, -(2**53), {"nested": [2**64 - 1]}):
                # Native rejected receipts are consumed once and never replayed.
                # 原生被拒绝回执单次消费，绝不重播。
                rejected = pool.submit("call", value, invocation, TIMEOUT_MS)
                try:
                    rejected.result(TIMEOUT_MS / 1000)
                except EmbeddedRuntimeError as failure:
                    if failure.code != "invalid_argument":
                        raise
                else:
                    raise RuntimeError("unsafe application integer reached operation admission")
                finally:
                    rejected.forget()
            if requests or take(runtime.list_operations(pool.pool_id, None, 16))["operation_ids"]:
                raise RuntimeError("unsafe application integer initialized Lua or admitted an operation")
            for value in (2**53 - 1, -(2**53 - 1), float(2**53), 1e100):
                # Accepted exact operation ownership survives until terminal result observation.
                # 已接纳精确操作所有权存活至终态结果观察。
                operation = take(pool.submit("call", value, invocation, TIMEOUT_MS))
                snapshot = operation.wait(TIMEOUT_MS / 1000)
                if snapshot["phase"] != "succeeded" or not snapshot["value"]["ok"]:
                    raise RuntimeError(f"safe endpoint or finite Float failed: {snapshot!r}")
                if snapshot["value"]["value"] != value or type(snapshot["value"]["value"]) is not type(value):
                    raise RuntimeError(f"safe endpoint or finite Float changed: {snapshot!r}")
                take(operation.forget())
            # Lua may successfully return a capability error envelope; that never implies rollback.
            # Lua 可以成功返回能力错误信封；这绝不意味着回滚。
            unsafe = take(pool.submit("call", "unsafe", invocation, TIMEOUT_MS))
            snapshot = unsafe.wait(TIMEOUT_MS / 1000)
            # Overall Lua execution remains unknown despite this callback's exact committed evidence.
            # 尽管此回调具有精确已提交证据，整体 Lua 执行仍保持未知。
            if snapshot["effects"] != "unknown":
                raise RuntimeError(f"overall Lua effects lost their independent unknown state: {snapshot!r}")
            envelope = snapshot["value"]
            if snapshot["phase"] != "succeeded" or envelope["ok"] or envelope["error"]["code"] != "invalid_argument" or envelope["effects"] != "committed":
                raise RuntimeError(f"unsafe callback lost committed error envelope: {snapshot!r}")
            # Match the latest actual handler by exact request identity.
            # 按精确请求身份匹配最近实际处理器。
            effect = next(entry for entry in snapshot["host_effects"] if entry["request_id"] == requests[-1])
            if effect["phase"] != "completed" or effect["effects"] != "committed":
                raise RuntimeError(f"original committed completion evidence changed: {effect!r}")
            take(unsafe.forget())
            # A normal follow-up proves the accepted completion did not poison callback ownership.
            # 正常后续调用证明已接纳完成没有破坏回调所有权。
            normal = take(pool.submit("call", "normal", invocation, TIMEOUT_MS))
            if normal.wait(TIMEOUT_MS / 1000)["value"]["value"] != "normal":
                raise RuntimeError("callback pump cannot deliver after unsafe integer completion")
            take(normal.forget())
            if len(requests) != 7:
                raise RuntimeError("initialization and business callbacks were lost or replayed")
        if not scope.status["closed"] or not pump.status["closed"] or pump.status["failure"] is not None or pump.status["request_ids"] or pump.status["pending_acknowledgements"]:
            raise RuntimeError("policy validation retained callback ownership")
    finally:
        # Reuse the same scope coordinator on failures, preserving any original error and live owners.
        # 失败时复用同一作用域协调器，保留任何原始错误及存活所有者。
        cleanup_preserving_error(scope.close)
        reservation.forget()


def run_policy(library: Path, expected_description: dict[str, Any]) -> None:
    """
    Load exact library with expected_description and verify policy in a temporary authorized package.
    加载精确 library 及 expected_description，在临时授权包内验证政策。
    Return only after existing owned cleaners release driver, transport and temporary package.
    仅在既有拥有型清理器释放驱动器、传输及临时包后返回。
    """
    with tempfile.TemporaryDirectory(prefix="luaskills-embedded-policy-") as temporary:
        # This new root owns the sole explicit source generation.
        # 此新根拥有唯一显式源码代次。
        root = Path(temporary).resolve()
        package = root / "plugin-generations" / PLUGIN_ID
        package.mkdir(parents=True)
        (package / "dependencies.yaml").write_text("{}\n", encoding="utf-8")
        transport = EmbeddedTransport(EmbeddedTransportConfig(
            max_runtimes=1, max_result_buffers=8, max_result_bytes=262144,
            max_response_bytes=32768, max_request_bytes=65536,
        ), library_path=library)
        try:
            if transport.core_description != expected_description:
                raise RuntimeError("policy library differs from frozen candidate description")
            # Borrow the bounded driver until the policy's exact runtime has been removed.
            # 借用有界驱动器，直到政策的精确运行时已被移除。
            driver = EmbeddedCommandDriver(transport, EmbeddedDriverConfig(
                work_threads=1, max_work_commands=8, max_control_commands=8,
            ))
            try:
                verify_flow(driver, transport, root, package)
            finally:
                cleanup_preserving_error(lambda: driver.close(TIMEOUT_MS / 1000))
        finally:
            def close_transport() -> None:
                """
                Close and free this exact transport only when native ownership permits; return nothing.
                仅在原生所有权允许时关闭及释放此精确传输；无返回值。
                """
                transport.close()
                transport.free()
            cleanup_preserving_error(close_transport)


def main() -> None:
    """
    Require explicit library, SHA-256 and frozen description arguments; run installed policy and print nothing.
    要求显式库、SHA-256 及冻结描述参数；运行已安装政策且不打印内容。
    """
    # Explicit paths cannot discover or replace the approved native binary.
    # 显式路径不能发现或替换已批准原生二进制。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--library-sha256", required=True)
    parser.add_argument("--description", type=Path, required=True)
    args = parser.parse_args()
    if hashlib.sha256(args.library.read_bytes()).hexdigest() != args.library_sha256:
        raise RuntimeError("policy native library SHA-256 mismatch")
    run_policy(args.library.resolve(strict=True), json.loads(args.description.read_text(encoding="utf-8")))


if __name__ == "__main__":
    main()
