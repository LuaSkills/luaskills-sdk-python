"""
Execute real typed embedded calls, queued callbacks and owned shutdown without runtime downloads.
执行真实类型化嵌入式调用、队列回调及拥有型关闭，不下载运行时。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import tempfile
import time
import sys
from typing import Any, Callable, TypeVar

from luaskills import (
    CallbackPumpConfig, EmbeddedCallbackPump, EmbeddedClient, EmbeddedCommandDriver,
    EmbeddedDriverConfig, EmbeddedPending, EmbeddedRuntime, EmbeddedRuntimeScope, EmbeddedTransport,
    EmbeddedTransportConfig, HostCallbackContext, HostCapability, create_engine_options,
)
from luaskills.embedded_compatibility import decode_core_description


# Preserve the delivered handle type while returning each completed SDK receipt quota.
# 归还每个已完成 SDK 回执配额时保留已交付句柄类型。
T = TypeVar("T")
# One host-assigned plugin identity, separate from untrusted Lua arguments.
# 唯一宿主分配插件身份，与不可信 Lua 参数分开。
PLUGIN_ID = "python-embedded-example"
# One finite example execution budget shared by native submission and observation.
# 唯一有限示例执行预算，由原生提交及观察共享。
TIMEOUT_MS = 10000


def take(pending: EmbeddedPending[T]) -> T:
    """
    Observe pending within the example budget, forget its SDK receipt and return its delivered value.
    在示例预算内观察 pending、遗忘其 SDK 回执并返回已交付值。
    Failed delivery stays retained for diagnosis instead of silently replaying a command.
    失败交付保留供诊断，不静默重放命令。
    """
    # A successful observation is the evidence required to return the local quota.
    # 成功观察是归还本地配额所需证据。
    value = pending.result(TIMEOUT_MS / 1000)
    pending.forget()
    return value


async def take_async(pending: EmbeddedPending[T]) -> T:
    """
    Await pending without blocking the caller loop, forget its SDK receipt and return the value.
    不阻塞调用方循环地等待 pending、遗忘其 SDK 回执并返回值。
    Cancellation leaves the driver-owned receipt available rather than replaying admission.
    取消保持驱动器拥有的回执可用，不重放入场。
    """
    # The async observer does not own the native command's lifetime.
    # 异步观察者不拥有原生命令寿命。
    value = await pending.result_async()
    pending.forget()
    return value


def cleanup_preserving_error(action: Callable[[], None]) -> None:
    """
    Execute action without replacing an active original exception; return after successful cleanup.
    执行 action 时不替换活动原始异常；成功清理后返回。
    A cleanup failure remains explicit as the original exception's cause and never authorizes premature release.
    清理失败显式保留为原始异常的原因，绝不授权过早释放。
    """
    # Exception state belongs to the enclosing finally/except; retain both original and cleanup evidence.
    # 异常状态来自外层 finally/except；保留原始及清理两种证据。
    original_error = sys.exc_info()[1]
    try:
        action()
    except BaseException as cleanup_error:
        if original_error is not None:
            raise original_error from cleanup_error
        raise


def capability(mode: str, calls: list[str]) -> HostCapability:
    """
    Bind mode's read-only descriptor to a sync or async handler that records into calls; return it.
    将 mode 的只读描述符绑定到记录 calls 的同步或异步处理器；返回能力声明。
    Trusted caller checks use HostCallbackContext, independently of application arguments.
    可信调用方检查使用 HostCallbackContext，与应用参数独立。
    """
    def sync_handler(arguments: Any, context: HostCallbackContext) -> Any:
        """
        Validate context's trusted plugin, record arguments' marker and return the original JSON value.
        校验 context 的可信插件、记录 arguments 的标记并返回原始 JSON 值。
        """
        if context.caller["plugin_id"] != PLUGIN_ID:
            raise RuntimeError("callback trusted plugin identity mismatch")
        calls.append(arguments["marker"])
        return arguments["value"]

    async def async_handler(arguments: Any, context: HostCallbackContext) -> Any:
        """
        Yield on the pump-owned loop, then validate context and return arguments' original JSON value.
        在事件泵拥有的循环让出执行，再校验 context 并返回 arguments 的原始 JSON 值。
        """
        await asyncio.sleep(0)
        return sync_handler(arguments, context)

    return HostCapability({
        "name": "python." + mode, "version": "1.0.0", "description": "Embedded Python example callback",
        "input_schema": True, "output_schema": True, "execution": "queued",
        "permissions": ["python.host"], "scope": "invocation", "max_concurrent": 1,
        "max_call_ms": TIMEOUT_MS, "max_input_bytes": 1024, "max_output_bytes": 1024,
        "effects": "read_only", "idempotency": "none",
    }, sync_handler if mode == "sync" else async_handler, mode)


def _run(library: Path, inputs_sha256: str | None, *, asynchronous: bool,
         expected_description: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Own temporary files, transport and driver for library; select asynchronous observation and return evidence.
    为 library 拥有临时文件、传输及驱动器；选择 asynchronous 观察并返回证据。
    inputs_sha256 adds frozen candidate identity to the SDK's existing description admission checks.
    inputs_sha256 在 SDK 既有描述入场校验上附加冻结候选身份。
    expected_description requires equality with the caller's entire frozen native description when supplied.
    提供 expected_description 时要求与调用方完整冻结原生描述相等。
    """
    with tempfile.TemporaryDirectory(prefix="luaskills-embedded-example-") as temporary:
        # Package authorization is explicit and outside the legacy System root.
        # 包授权显式声明，位于旧 System 根之外。
        root = Path(temporary).resolve()
        package = root / "plugin-generations" / PLUGIN_ID
        package.mkdir(parents=True)
        (package / "dependencies.yaml").write_text("{}\n", encoding="utf-8")
        # Result reservations cover driver workers, pump controls and the scope's reserved slot.
        # 结果预留覆盖驱动线程、事件泵控制及作用域预留槽。
        transport = EmbeddedTransport(EmbeddedTransportConfig(
            max_runtimes=1, max_result_buffers=8, max_result_bytes=8 * 32768,
            max_response_bytes=32768, max_request_bytes=65536,
        ), library_path=library)
        try:
            # Constructor already validated the packaged contract before creating transport ownership.
            # 构造器已在创建传输所有权前校验包内契约。
            description = transport.core_description
            if inputs_sha256 is not None and description["build"]["inputs_sha256"] != inputs_sha256:
                raise RuntimeError("native candidate inputs_sha256 identity mismatch")
            if expected_description is not None and description != expected_description:
                raise RuntimeError("native candidate full description identity mismatch")
            # All higher-level calls borrow this explicit bounded driver.
            # 全部高级调用借用此显式有界驱动器。
            driver = EmbeddedCommandDriver(transport, EmbeddedDriverConfig(
                work_threads=1, max_work_commands=8, max_control_commands=8,
            ))
            try:
                if asynchronous:
                    return asyncio.run(_async_flow(driver, transport, root, package, description))
                return _sync_flow(driver, transport, root, package, description)
            finally:
                cleanup_preserving_error(lambda: driver.close(TIMEOUT_MS / 1000))
        finally:
            def close_transport() -> None:
                """
                Close this exact transport then free it only if native and SDK ownership checks permit release.
                关闭此精确传输，仅在原生及 SDK 所有权校验允许时释放。
                """
                transport.close()
                transport.free()

            cleanup_preserving_error(close_transport)


def initialize(runtime: Any, root: Path) -> None:
    """
    Initialize runtime using isolated root and register the plugin; return after readiness is proven.
    使用隔离 root 初始化 runtime 并注册插件；证明就绪后返回。
    Real status must prove readiness; initialization acknowledgement alone is insufficient.
    真实状态必须证明就绪；仅初始化确认不够。
    """
    # Fixture budgets match the already exercised native integration layout.
    # 夹具预算对应已执行的原生集成布局。
    limits = {
        "max_registered_plugins": 4, "max_registered_pools": 4, "max_sessions": 4,
        "max_registered_capabilities": 4, "max_resident_vms": 2, "max_running_calls": 2,
        "max_queued_calls": 4, "max_queued_bytes": 4096, "max_operations": 16,
        "max_effect_records_per_operation": 8, "max_effect_bytes_per_operation": 8192,
        "max_host_requests": 4, "max_host_request_bytes": 8192, "max_value_bytes": 1024,
    }
    take(runtime.initialize(create_engine_options(root, host_options={
        "system_lua_lib_dir": (root / "system_lua_lib").as_posix(), "allow_network_download": False,
    }), limits))
    if take(runtime.status())["initialization"] != "ready":
        raise RuntimeError("native runtime initialization did not become ready")
    take(runtime.register_plugin(PLUGIN_ID, {name: limits[name] for name in (
        "max_registered_pools", "max_sessions", "max_resident_vms", "max_running_calls",
        "max_queued_calls", "max_queued_bytes", "max_operations",
    )}))


def register_pool(runtime: Any, package: Path) -> Any:
    """
    Register package's reusable module on runtime after callback publication and return its typed pool handle.
    回调发布后在 runtime 上注册 package 的可复用模块并返回类型池句柄。
    Pool registration freezes capability identity, so handlers must exist before this call.
    池注册冻结能力身份，因此处理器必须先于此调用存在。
    """
    return take(runtime.register_pool({
        "plugin_id": PLUGIN_ID, "generation": "example-generation-1", "package_root": package.as_posix(),
        "dependencies_file": "dependencies.yaml", "mounts": {}, "security_partition": "python-example",
        "source": "return {call=function(a) return vulcan.capabilities.call(a.capability,a) end, shutdown=function() return vulcan.capabilities.call('python.sync',{marker='finalizer',value='closed'}) end}",
        "exports": [{"name": name, "input_schema": True, "output_schema": True} for name in ("call", "shutdown")],
        "finalizer": {"export": "shutdown", "arguments": None, "timeout_ms": TIMEOUT_MS},
    }, {
        "kind": "shared", "min_resident_vms": 0, "max_resident_vms": 1,
        "max_running_calls": 1, "max_queued_calls": 4, "reuse": "reusable", "serial": False,
        "backend": "in_process", "idle_ttl_ms": None, "max_uses": None,
    }, ["python.host"], "example-v1"))


def verify_result(snapshot: dict[str, Any], value: Any) -> None:
    """
    Require snapshot's successful callback value and read-only effect evidence to equal value; return nothing.
    要求 snapshot 的成功回调值及只读副作用证据与 value 一致；无返回值。
    """
    if snapshot["phase"] != "succeeded" or snapshot["value"] != {
        "ok": True, "value": value, "effects": "not_applicable",
    }:
        raise RuntimeError(f"native callback result mismatch: {snapshot!r}")
    if not snapshot["host_effects"]:
        raise RuntimeError("native callback effect evidence is missing")


def verify_closed(scope: EmbeddedRuntimeScope, pump: EmbeddedCallbackPump, calls: list[str],
                  description: dict[str, Any], mode: str) -> dict[str, Any]:
    """
    Require scope and pump closure plus calls' finalizer evidence; return description and mode diagnostics.
    要求 scope 与 pump 关闭及 calls 的关闭函数证据；返回 description 与 mode 诊断。
    """
    if not scope.status["closed"] or not pump.status["closed"] or calls != [mode, "finalizer"]:
        raise RuntimeError(f"native cleanup evidence mismatch: {scope.status!r}, {pump.status!r}, {calls!r}")
    if pump.status["request_ids"] or pump.status["registration_ids"] or pump.status["failure"] is not None:
        raise RuntimeError("native callback ownership remains after scope closure")
    return {"mode": mode, "build": description["build"], "callbacks": calls, "scope_closed": True,
            "pump_closed": True}


def close_unscoped_runtime(runtime: EmbeddedRuntime, transport: EmbeddedTransport) -> None:
    """
    Drain a delivered runtime after failed scope construction; query transport's actual pump owner and close it first.
    作用域构造失败后排空已交付 runtime；查询 transport 实际泵所有者并先关闭。
    Return only after actual pump workers and native runtime closure, then release the exact runtime slot.
    仅在实际泵线程及原生运行时关闭后返回，随后释放精确运行时槽。
    This path precedes pool/callback registration and never replaces an existing scope coordinator.
    此路径先于池及回调注册，绝不替代已有作用域协调器。
    """
    # The sole ownership registry also retains pumps whose constructor was interrupted after real thread startup.
    # 唯一所有权注册表同样保留实际线程启动后构造器被中断的事件泵。
    pump = transport.callback_pump(runtime.runtime_id)
    if pump is not None:
        pump.close()
    take(runtime.request_close())
    while not take(runtime.status())["closed"]:
        # No timeout authorizes premature release; wait for the core's actual lifecycle evidence.
        # 超时不能授权过早释放；等待核心实际生命周期证据。
        time.sleep(0.01)
    take(runtime.free())


def _sync_flow(driver: EmbeddedCommandDriver, transport: EmbeddedTransport, root: Path,
               package: Path, description: dict[str, Any]) -> dict[str, Any]:
    """
    Exercise sync typed calls on driver/transport using root/package; return description and cleanup evidence.
    在 driver/transport 上使用 root/package 执行同步类型调用；返回 description 及清理证据。
    """
    # Callback history independently proves finalizer delivery during scope drainage.
    # 回调历史独立证明作用域排空期间关闭函数的交付。
    calls: list[str] = []
    runtime = take(EmbeddedClient(driver).reserve())
    # A pump can poll only a ready runtime; failed construction still needs explicit slot cleanup.
    # 事件泵只能轮询就绪运行时；构造失败仍需要显式槽清理。
    try:
        initialize(runtime, root)
        pump = EmbeddedCallbackPump(transport, runtime.runtime_id, CallbackPumpConfig(
            max_concurrent_handlers=1, max_pending_commands=4, poll_interval_ms=2,
        ))
        scope = EmbeddedRuntimeScope(runtime, pump=pump)
    except BaseException:
        close_unscoped_runtime(runtime, transport)
        raise
    with scope:
        # Registration follows runtime readiness; finalization needs its retained handler until scope exit.
        # 注册发生在运行时就绪后；关闭函数直到作用域退出都需要保留的处理器。
        pump.register([capability("sync", calls)], timeout=TIMEOUT_MS / 1000)
        pool = register_pool(runtime, package)
        operation = take(pool.prewarm_instance({"request_context": None, "client_budget": None, "tool_config": None}, TIMEOUT_MS))
        if operation.wait(TIMEOUT_MS / 1000)["phase"] != "succeeded":
            raise RuntimeError("native prewarm failed")
        take(operation.forget())
        if take(pool.reusable_status())["ready"] != 1:
            raise RuntimeError("native reusable pool is not ready after prewarm")
        operation = take(pool.submit("call", {"capability": "python.sync", "marker": "sync", "value": None},
            {"request_context": None, "client_budget": None, "tool_config": None}, TIMEOUT_MS))
        verify_result(operation.wait(TIMEOUT_MS / 1000), None)
        take(operation.forget())
    return verify_closed(scope, pump, calls, description, "sync")


async def _async_flow(driver: EmbeddedCommandDriver, transport: EmbeddedTransport, root: Path,
                      package: Path, description: dict[str, Any]) -> dict[str, Any]:
    """
    Exercise asyncio calls on driver/transport using root/package; return description and cleanup evidence.
    在 driver/transport 上使用 root/package 执行 asyncio 调用；返回 description 及清理证据。
    """
    # Sync finalization and async business callbacks share the same explicitly owned pump.
    # 同步关闭函数及异步业务回调共享同一个显式拥有的事件泵。
    calls: list[str] = []
    # Retain the one admission receipt before observing it; cancellation cannot revoke its native allocation.
    # 观察前保留唯一入场回执；取消不能撤销其原生分配。
    reservation = EmbeddedClient(driver).reserve()
    try:
        runtime = await take_async(reservation)
    except BaseException as observer_error:
        try:
            # Recover only this original delivery, never submit another reserve or infer an unknown identity.
            # 仅恢复此原交付，绝不重新提交预留或推断未知身份。
            runtime = await asyncio.to_thread(take, reservation)
            await asyncio.to_thread(close_unscoped_runtime, runtime, transport)
        except BaseException as recovery_error:
            raise observer_error from recovery_error
        raise
    # Setup runs off the caller loop and finishes before the pump starts querying native readiness.
    # 初始化在调用方循环外执行，并在事件泵开始查询原生就绪前完成。
    try:
        await asyncio.to_thread(initialize, runtime, root)
        pump = EmbeddedCallbackPump(transport, runtime.runtime_id, CallbackPumpConfig(
            max_concurrent_handlers=1, max_pending_commands=4, poll_interval_ms=2,
        ))
        scope = EmbeddedRuntimeScope(runtime, pump=pump)
    except BaseException:
        await asyncio.to_thread(close_unscoped_runtime, runtime, transport)
        raise
    async with scope:
        await pump.register_async([capability("sync", calls), capability("async", calls)])
        pool = await asyncio.to_thread(register_pool, runtime, package)
        operation = await take_async(pool.prewarm_instance({"request_context": None, "client_budget": None, "tool_config": None}, TIMEOUT_MS))
        if (await operation.wait_async())["phase"] != "succeeded":
            raise RuntimeError("native async prewarm failed")
        await take_async(operation.forget())
        if (await take_async(pool.reusable_status()))["ready"] != 1:
            raise RuntimeError("native async reusable pool is not ready after prewarm")
        operation = await take_async(pool.submit("call", {"capability": "python.async", "marker": "async", "value": {"text": "中文", "null": None, "array": []}},
            {"request_context": None, "client_budget": None, "tool_config": None}, TIMEOUT_MS))
        verify_result(await operation.wait_async(), {"text": "中文", "null": None, "array": []})
        await take_async(operation.forget())
    return verify_closed(scope, pump, calls, description, "async")


def main() -> None:
    """
    Require --library, optionally check candidate digests and run --mode; print JSON acceptance evidence.
    要求 --library、可选校验候选摘要并运行 --mode；输出 JSON 验收证据。
    Return nothing; missing libraries, identity mismatch, callbacks and cleanup failures exit unsuccessfully.
    无返回值；缺库、身份不匹配、回调及清理失败均以失败退出。
    """
    # Explicit selection never falls back to installed runtime assets or a downloaded latest release.
    # 显式选择绝不回退到已安装运行时资产或下载最新发布。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--library-sha256")
    parser.add_argument("--inputs-sha256")
    parser.add_argument("--description", type=Path)
    parser.add_argument("--mode", choices=("sync", "async", "both"), default="both")
    args = parser.parse_args()
    library = args.library.resolve(strict=True)
    if not library.is_file():
        raise ValueError("native library must be a regular file")
    if args.library_sha256 is not None and hashlib.sha256(library.read_bytes()).hexdigest() != args.library_sha256:
        raise ValueError("native candidate library SHA-256 mismatch")
    # Use the SDK's existing strict description validator, not a second candidate protocol.
    # 使用 SDK 既有严格描述校验器，不创建第二套候选协议。
    expected_description = None if args.description is None else decode_core_description(args.description.read_bytes())
    for mode in (("sync", "async") if args.mode == "both" else (args.mode,)):
        print(json.dumps(_run(library, args.inputs_sha256, asynchronous=mode == "async",
                             expected_description=expected_description), ensure_ascii=False))


if __name__ == "__main__":
    main()
