# luaskills-sdk

English documentation is the default package documentation. For Chinese, see [README_cn.md](README_cn.md).

Main LuaSkills repository: [LuaSkills/luaskills](https://github.com/LuaSkills/luaskills)

Python SDK for integrating the LuaSkills runtime through the public JSON FFI surface.

`0.5.7` is the current release line. It retains the strict package-level skill configuration contract and defaults runtime assets to LuaSkills core `v0.5.7`, vldb-controller `v0.2.3`, and vldb-sqlite `v0.1.6`.

The SDK wraps native library loading, JSON FFI buffers, engine lifecycle, formal skill roots, authority-aware management calls, skill config, provider callbacks, host-tool callbacks, and runtime asset installation. Hosts should not need to hand-write low-level FFI buffers or JSON envelopes for normal integration.

## Installation

```bash
pip install luaskills-sdk
```

The Python wheel does not embed native runtime binaries or LuaRocks modules. Prepare a `runtime_root` with `install-runtime`, then pass that root to `LuaSkillsClient`.

```powershell
luaskills install-runtime --database none --runtime-root D:\runtime\luaskills
luaskills version --runtime-root D:\runtime\luaskills
```

After installation, the SDK automatically resolves `luaskills.dll` / `libluaskills.so` / `libluaskills.dylib` from `runtime_root/libs`. You usually do not need `LUASKILLS_LIB`.

Use `library_path` or `LUASKILLS_LIB` only when your host intentionally manages native libraries outside the SDK runtime root.

## Runtime Assets

The source distribution includes a unified script that does not require the Python CLI and directly fetches LuaSkills FFI, Lua runtime packages, and VLDB:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/deps/sync_runtime_assets.ps1 -Target all -Database vldb-controller -RuntimeRoot D:\runtime\luaskills
```

```bash
RUNTIME_ROOT=/opt/luaskills scripts/deps/sync_runtime_assets.sh all vldb-controller
```

Supported targets are `all`, `luaskills`, `lua`, and `vldb`. VLDB presets are `none`, `vldb-controller`, `vldb-direct`, and `host-callback`. The scripts pin LuaSkills to `v0.5.7` by default and accept explicit release-version overrides.

`install-runtime` downloads GitHub Release assets, verifies `.sha256` sidecars, extracts native files and Lua runtime packages, and writes:

```text
runtime_root/resources/luaskills-sdk-runtime-manifest.json
```

Supported database modes:

- `none`: installs the Lua runtime archive and the LuaSkills FFI SDK archive, without database providers.
- `vldb-direct`: installs `vldb-sqlite-lib` and `vldb-lancedb-lib` dynamic libraries and uses `dynamic_library` provider mode.
- `vldb-controller`: installs `vldb-controller` and uses managed `space_controller` provider mode.
- `host-callback`: installs no VLDB binaries and generates `host_callback + json` host options.

Default LuaSkills assets:

- `lua-runtime-packages-{platform}.tar.gz` from `LuaSkills/luaskills-packages`: installed by default; provides `lua_packages`, package-side runtime `libs`, `resources`, and third-party runtime licenses.
- `luaskills-ffi-sdk-{platform}.tar.gz`: installed by default; provides the public FFI dynamic library, headers, and FFI licenses.
- `lua-deps-{platform}.tar.gz`: not installed by the SDK; it is a build-time bundle for CI, source builds, or advanced native module rebuilds.

Managed Python and Node.js child runtimes are optional. Use `--managed-runtimes all` when Lua skills need `vulcan.runtime.python.*` or `vulcan.runtime.node.*`; the installer places Python, `uv`, Node.js, and `pnpm` under `runtime_root/dependencies/runtimes/...`.

Managed child runtimes support Windows x64, Linux x64/ARM64, and macOS x64/ARM64. Windows ARM is explicitly rejected before any download or target-directory creation. Source distributions also include the standalone `scripts/deps/fetch_managed_runtimes.ps1`, `scripts/deps/fetch_managed_runtimes.sh`, and `scripts/debug-tools/managed_runtime_layout_check.py` tools used to prepare and validate debug runtime roots.

The current exact managed dependency versions are Python `3.14.6`, uv `0.11.28`, Node.js `24.18.0`, and pnpm `11.11.0`. Package `dependencies.yaml` files must declare the same exact runtime and package-manager versions unless the host deliberately installs another supported version.

### Host-selected managed runtime roots

LuaSkills 0.5.1 separates the LuaSkills data root, the read-only interpreter distribution root, and the writable managed-environment root. Both explicit managed roots must be absolute; when omitted, LuaSkills keeps the compatible `runtime_root/dependencies/runtimes` and `runtime_root/dependencies/envs` layout.

```python
from luaskills import LuaSkillsClient

distribution_root = "D:/VulcanCode/dependencies/runtimes"
environment_root = "D:/VulcanCodeData/managed-runtime-envs"

client = LuaSkillsClient(
    runtime_root="D:/VulcanCodeData/luaskills",
    host_options={
        "managed_runtime_distribution_root": distribution_root,
        "managed_runtime_environment_root": environment_root,
        "managed_runtime_config": {
            "worker_pool_max_size_per_environment": 8,
            "worker_idle_ttl_secs": 120,
            "persistent_session_limit_per_engine": 128,
            "persistent_session_default_buffer_limit_bytes_per_stream": 2 * 1024 * 1024,
            "invoke_default_timeout_ms": 30_000,
        },
    },
)

python_install = LuaSkillsClient.resolve_managed_runtime_install(
    distribution_root,
    "python",
    "3.14.6",
    "windows-x64",
    runtime_root="D:/VulcanCodeData/luaskills",
)
```

`default_managed_runtime_config()` returns the stable engine defaults: `4` Workers per exact environment/package-owner pool, `60` idle seconds, `256` persistent sessions, `1 MiB` per session output stream, and no default invoke timeout. Start from that complete object when changing individual values. Every configured number must be positive; per-call `invoke.timeout_ms` and per-session `session.open.buffer_limit_bytes` override only their matching engine defaults.

The standalone fetch and debug tools accept the same split layout:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/deps/fetch_managed_runtimes.ps1 -RuntimeRoot D:\VulcanCodeData\luaskills -DistributionRoot D:\VulcanCode\dependencies\runtimes -Target all
python scripts/debug-tools/managed_runtime_layout_check.py D:\VulcanCodeData\luaskills --distribution-root D:\VulcanCode\dependencies\runtimes --environment-root D:\VulcanCodeData\managed-runtime-envs
```

The SDK keeps LuaSkills core aligned with the SDK release and resolves runtime packages from the compatible `0.1` series by selecting the newest published patch automatically.

## Version Alignment

- Keep the SDK and LuaSkills core on the same current release line whenever possible.
- The current SDK defaults to LuaSkills core tag `v0.5.7`.
- Runtime packages and native dependencies still come from the split `LuaSkills/luaskills-packages` and related release assets.
- SDK default host options pass `runtime_root`, null managed-root override slots, and the complete stable `managed_runtime_config`; LuaSkills derives the fixed data layout until the host explicitly overrides roots or policy.
- Host tools live directly under `runtime_root/bin`, not `runtime_root/bin/tools`.

```powershell
luaskills install-runtime --database none --runtime-root D:\runtime\luaskills
luaskills install-runtime --database vldb-direct --runtime-root D:\runtime\luaskills
luaskills install-runtime --database vldb-controller --runtime-root D:\runtime\luaskills
luaskills install-runtime --database host-callback --runtime-root D:\runtime\luaskills
luaskills install-runtime --database none --managed-runtimes all --runtime-root D:\runtime\luaskills
```

Use `--dry-run` to inspect exact release URLs before downloading:

```powershell
luaskills install-runtime --database vldb-direct --runtime-root D:\runtime\luaskills --dry-run
```

Advanced hosts that already manage Lua packages can skip the Lua runtime archive:

```powershell
luaskills install-runtime --database none --runtime-root D:\runtime\luaskills --skip-lua-runtime
```

## Basic Usage

Prepare `runtime_root`, then create the client without an explicit `library_path`:

```python
from luaskills import Authority, LuaSkillsClient, RuntimeRoots

runtime_root = "D:/runtime/luaskills"
roots = RuntimeRoots.standard(runtime_root)

with LuaSkillsClient(runtime_root=runtime_root) as client:
    client.load_from_roots(roots)
    entries = client.list_entries(Authority.DELEGATED_TOOL)
    result = client.call_skill("demo-standard-ffi-skill-ping", {"note": "python-sdk"})

    print(entries)
    print(result["content"])
```

Use `library_path` only when bypassing the runtime manifest:

```python
from luaskills import LuaSkillsClient

with LuaSkillsClient(
    library_path="D:/path/to/luaskills.dll",
    runtime_root="D:/runtime/luaskills",
) as client:
    print(client.version())
```

## CLI Flow

End-to-end CLI flow with a prepared runtime root:

```powershell
luaskills install-runtime --database none --runtime-root D:\runtime\luaskills
luaskills version --runtime-root D:\runtime\luaskills
luaskills list --runtime-root D:\runtime\luaskills
luaskills call demo-standard-ffi-skill-ping '{"note":"python"}' --runtime-root D:\runtime\luaskills
```

If you need VLDB direct libraries:

```powershell
luaskills install-runtime --database vldb-direct --runtime-root D:\runtime\luaskills
```

If you prefer the shared controller mode:

```powershell
luaskills install-runtime --database vldb-controller --runtime-root D:\runtime\luaskills
```

## Provider Callback

SQLite / LanceDB `host_callback + json` mode can be registered through the SDK before engine creation:

```python
from luaskills import LuaSkillsClient, LuaSkillsJsonFfi

runtime_root = "D:/runtime/luaskills"
ffi = LuaSkillsJsonFfi(runtime_root=runtime_root)


def sqlite_provider(request):
    return {"ok": True, "request": request}


ffi.set_sqlite_provider_json_callback(sqlite_provider)

try:
    client = LuaSkillsClient(
        runtime_root=runtime_root,
        host_options={
            "sqlite_provider_mode": "host_callback",
            "sqlite_callback_mode": "json",
        },
    )
    client.close()
finally:
    ffi.clear_sqlite_provider_json_callback()
```

Callbacks must be registered before `engine_new`. Changing callbacks later does not retroactively affect already-created engines.

## Host Tool Callback

`vulcan.host.*` uses the fixed host-tool callback registered through `luaskills_ffi_set_host_tool_json_callback`. Register it before running skills that may call host-owned tools:

```python
from luaskills import HostToolJsonRequest, LuaSkillsJsonFfi

# Runtime root used by the host integration.
# 宿主集成使用的运行时根目录。
runtime_root = "D:/runtime/luaskills"
# Low-level FFI bridge that owns callback registration.
# 持有 callback 注册的底层 FFI 桥。
ffi = LuaSkillsJsonFfi(runtime_root=runtime_root)


def host_tool_callback(request: HostToolJsonRequest):
    """
    Handle list, has, and call actions from vulcan.host.*.
    处理来自 vulcan.host.* 的 list、has 和 call 动作。
    """

    if request["action"] == "list":
        return [{"name": "model.embed", "description": "embedding model bridge"}]
    if request["action"] == "has":
        return request["tool_name"] == "model.embed"
    if request["action"] == "call":
        return {"ok": True, "value": {"request": request["args"]}}
    return {"ok": False, "error": {"code": "unsupported_action", "message": request["action"]}}


ffi.set_host_tool_json_callback(host_tool_callback)
```

The callback receives `{ action, tool_name, args }`. `list` should return host-visible tool metadata, `has` should return a boolean or an object with `exists` / `has` / `available`, and `call` should return one complete table-shaped result. Call `ffi.clear_host_tool_json_callback()` during shutdown. Streaming is intentionally outside this bridge.

## Model Callback

`vulcan.models.*` uses fixed model callbacks registered through `luaskills_ffi_set_model_embed_json_callback` and `luaskills_ffi_set_model_llm_json_callback`. Lua skills can only call `vulcan.models.embed(text)` and `vulcan.models.llm(system, user)`; provider selection, model names, keys, temperature, thinking, limits, and stream policy stay fully host-owned.

Register model callbacks before creating or using an engine that may run model-aware skills. Keep the `LuaSkillsJsonFfi` instance alive for as long as the callback should stay registered, and clear callbacks during shutdown or test teardown.

The SDK callback is the host boundary:

- It receives a fixed request shape from LuaSkills.
- It should call the host-selected provider using host-managed configuration.
- It should return a bare success payload for successful provider calls.
- It should return an error envelope for provider failures that need `provider_message`, `provider_code`, or `provider_status`.
- It should not expose API keys, Authorization headers, signatures, or raw request headers in provider error fields.

```python
from luaskills import LuaSkillsJsonFfi, RuntimeModelEmbedRequest, RuntimeModelLlmRequest

runtime_root = "D:/runtime/luaskills"
ffi = LuaSkillsJsonFfi(runtime_root=runtime_root)


def embed_callback(request: RuntimeModelEmbedRequest):
    return {
        "vector": [0.1, 0.2, 0.3],
        "dimensions": 3,
        "usage": {"input_tokens": len(request["text"])},
    }


def llm_callback(request: RuntimeModelLlmRequest):
    if "missing-model" in request["user"]:
        return {
            "ok": False,
            "error": {
                "code": "provider_error",
                "message": "model provider rejected the request",
                "provider_message": "raw provider message after host-side redaction",
                "provider_code": "model_not_found",
                "provider_status": 404,
            },
        }
    return {
        "assistant": f"handled {request['system']}: {request['user']}",
        "usage": {"input_tokens": 12, "output_tokens": 8},
    }


ffi.set_model_embed_json_callback(embed_callback)
ffi.set_model_llm_json_callback(llm_callback)
```

The callback request includes `{ text, caller }` for embeddings and `{ system, user, caller }` for LLM calls. Return bare success payloads, or `{ ok: false, error: { code, message, provider_message?, provider_code?, provider_status? } }` for provider failures. Call `ffi.clear_model_embed_json_callback()` and `ffi.clear_model_llm_json_callback()` during shutdown.

Minimal runtime check after registration:

```python
status = client.run_lua("return vulcan.models.status()")
embed_result = client.run_lua('return vulcan.models.embed("hello")')
llm_result = client.run_lua('return vulcan.models.llm("system", "user")')
```

Common integration mistakes:

- `model_unavailable`: the matching callback was not registered or was cleared before the skill call.
- Missing provider details: return a structured error envelope instead of raising provider errors from the callback.
- Missing FFI symbol: install a LuaSkills runtime that exports `luaskills_ffi_set_model_embed_json_callback` and `luaskills_ffi_set_model_llm_json_callback`.
- Empty `caller` fields: call through a loaded runtime skill or a runtime `run_lua` context, not a detached provider unit test.

## Examples

The wheel includes runnable examples:

```bash
python -m luaskills.examples.basic
python -m luaskills.examples.host_tool_callback
python -m luaskills.examples.provider_callback
python -m luaskills.examples.runtime_lease
```

Source-tree examples include query, lifecycle, and persistent runtime-lease flows with a bundled USER-layer fixture skill:

```powershell
luaskills install-runtime --database none --runtime-root .\examples\fixture_runtime
python .\examples\basic.py
python .\examples\call.py
python .\examples\host_tool_callback.py
python .\examples\query.py
python .\examples\lifecycle.py
python .\examples\runtime_lease.py
python .\examples\provider_callback.py
```

The fixture skill lives at `examples/fixture_runtime/user_skills/demo-standard-ffi-skill`, so delegated-query examples can see it without System authority.

See [examples/README.md](examples/README.md) for the full example index and runtime notes. The Chinese example guide is [examples/README_cn.md](examples/README_cn.md).

## Persistent Runtime Leases

Use `client.runtime_leases()` for the public lease endpoints, or `client.system(authority).runtime_leases()` when the host wants fixed authority injection through the dedicated system runtime-lease exports provided by the latest native library.

```python
from luaskills import Authority, LuaSkillsClient

client = LuaSkillsClient(runtime_root="D:/runtime/luaskills")

try:
    leases = client.system(Authority.SYSTEM).runtime_leases()
    session = leases.create_handle(
        "demo-session",
        ttl_sec=600,
        replace=True,
        cwd="D:/runtime/luaskills/system_lua_lib",
        mounts={"channel": "demo"},
        system_package={"id": "debug-plugin", "root": "D:/runtime/luaskills/system_lua_lib/debug-plugin", "dependencies_file": "dependencies.json"},
    )
    result = session.eval("counter = (counter or 0) + 1; return { counter = counter }")
    print(result["result"])
    print(session.status())
    print(session.close())
finally:
    client.close()
```

## Embedded Runtime Transport (Development)

Wire types live in `luaskills.embedded_contract`: separate `Input*` and `Output*` declarations preserve missing fields versus explicit null, including arbitrary-precision Python integers. The generated `EmbeddedNativeStatus` is also available at package level. The transport and callback pump use these generated protocol and effect constants. See the packaged [offline contract and synchronization instructions](src/luaskills/contracts/embedded/v1/README.md); run `python scripts/generate_embedded_contract.py --check` to reject stale output. The wheel and source distribution both carry the exact core JSON and SHA-256, and the source distribution includes the generator.

`EmbeddedTransport` binds the five version-one embedded C entrypoints. This development API requires a matching locally built core exporting those symbols; the existing 0.5.7 release assets do not provide it. The version bump and published asset alignment are handled at release freeze.

Pass an explicit `EmbeddedTransportConfig` and the existing `library_path` or `runtime_root` selection. `request(command)` accepts a root command and returns its successful `result`, including `None` for explicit JSON null. Native return codes raise `EmbeddedTransportError` with `status`; delivered core failures raise `EmbeddedRuntimeError` with `code` and `message`. The binding preserves all 64 identity bits and releases each native result even when decoding fails or Python raises an interruption at native return.

Requests may run concurrently. `close()` permanently requests closure while keeping core queries and host acknowledgements available. Drain and remove every runtime with the core lifecycle commands, then call `free()`. Failed native free leaves the transport available for drainage; no destructor silently frees live runtimes or unloads the library. If result release explicitly fails, the exact descriptor remains owned and `release_results()` can retry after active calls have returned.

`EmbeddedResultReleaseError` is a transport-error subtype that retains immutable `response_bytes` when they were copied before release failed. `delivered_result()` re-decodes that copy with the normal success/business-error rules, without issuing native work. This preserves an already-created runtime, pool, session or operation identity. Release recovery and delivery recovery are separate: retry `release_results()` to release memory, inspect the retained receipt to recover its identity, and never infer that the mutation should be submitted again. Missing or invalid copied bytes remain an explicit lack of delivery evidence.

`EmbeddedCommandDriver(transport, EmbeddedDriverConfig(work_threads=..., max_work_commands=..., max_control_commands=...))` provides an owned asynchronous FFI channel. `submit(command)` returns an `EmbeddedCommand` immediately after freezing its JSON and retaining its receipt. Use `result(timeout=...)` or `await result_async()` to observe the same actual command. Cancelling an observer, closing its asyncio loop or timing out does not cancel native execution. `driver.commands` keeps exact receipt objects recoverable by their driver-local `command_id`; `request` and successful results are independent copies. Call `forget()` only after delivery has actually returned and its result or failure is handled. Completed receipts continue occupying their lane's quota until forgotten; forgetting a receipt never forgets a core operation.

One driver owns a transport at a time. It has separate work and short-control executors and retention quotas. Runtime construction cannot consume the SDK control worker or its receipt quota. Ownership admission also reserves the corresponding native result slots and worst-case `max_response_bytes` for every driver worker and callback-pump control worker. Insufficient transport count or aggregate-byte capacity fails before publishing the owner; transport budgets cannot be reassigned after construction. Direct low-level requests and retained failed-release buffers consume additional native capacity and must be included in the host's capacity/recovery policy.

Driver `request_close()` fences new commands and starts an owned shutdown; `close(timeout=...)` and `close_async()` observe actual executor joins. A timed-out or cancelled close leaves that shutdown active. Closing the driver does not close core runtimes or callback pumps. Keep the driver and pump available while cancelling/draining the core, handle pending receipts, free the closed runtimes, then close the driver and free the transport. The driver rejects blocking `operation_wait`; use short `operation_status` queries so native workers remain available. Nested driver calls from host callbacks are explicitly unsupported until controlled dependency tracking is implemented.

`EmbeddedClient(driver)` adds typed runtime, plugin, pool, session and operation handles using the generated input and output types. Native commands return `EmbeddedPending[T]` immediately; observe with `result(timeout=...)` or `await result_async()`. Both observe the same command, even after an earlier observer was cancelled. `pending.receipt` exposes the exact driver receipt. After handling delivery, explicitly call `pending.forget()` to return its SDK quota. `pending.delivered_result()` can project copied success after a result-release error without resubmission; native buffer recovery still requires `transport.release_results()`.

For runtime annotation introspection, use `typing.get_type_hints(method, localns=vars(luaskills.embedded_contract))`: imported recursive aliases require their defining namespace on the supported Python versions. Static type checking uses the generated declarations directly; the package verifier checks both the actual wheel's declarations and these explicitly resolved method annotations.

Use `client.reserve()` to obtain a runtime handle before calling its one-shot `initialize(engine_options, runtime_config)`. The initialization receipt acknowledges the attempt; always query `status()` to distinguish `ready`, `failed` and `faulted` and read the retained error. After interrupted initialization, retain that identity and query status rather than retrying construction. `client.runtime(id)` and the runtime's `plugin(id)`, `pool(id)`, `session(id)` and `operation(id)` bind known identities without probing or claiming readiness. Native commands validate their existence and ownership.

`runtime.register_plugin(...)` and `register_pool(...)` return acknowledged handles. `pool.submit(export, arguments, context, timeout_ms)` and `session.submit(...)` return operation handles; `timeout_ms` is the core execution deadline. `pool.open_session(timeout_ms)` returns `EmbeddedSessionOpen`, containing both `session` and its separate `initialization` operation. Observe that operation before treating initialization as successful; a session receipt alone is insufficient.

`operation.wait(timeout=..., poll_interval=...)` and `await operation.wait_async(poll_interval=...)` poll short status commands and return the full terminal snapshot, including failure and effect evidence. The synchronous timeout and `asyncio.wait_for` affect only observation. Explicit `operation.cancel()` requests cooperative cancellation; its boolean result is not completion evidence. Polling consumes successful read-only SDK receipts; interrupted or failed receipts remain in `driver.commands` for recovery. `operation.forget()` removes a terminal **core record**, and its returned pending receipt must also be handled and forgotten.

Runtime, plugin, pool and session `request_close()` methods return closure acknowledgements; inspect actual native state before `free()` or `forget()`. These typed handles borrow the driver. With `LUASKILLS_LIB` and `PYTHONPATH=src` set, `-p test_embedded_client.py` exercises real shared/dedicated pools, fixed-session state, lifecycle barriers and late committed callbacks.

`EmbeddedRuntimeScope(runtime, pump=existing_pump)` owns ordered shutdown of one known runtime and its exact optional pump. Use `with scope as owner:` or `async with scope as owner:`, and access the typed handle through `owner.runtime`. A scope can be entered once; duplicate owners are rejected. A reserved runtime may be adopted before initialization when no pump is needed. For callback runtimes, initialize and check `ready`, create the pump, then adopt both together. New pumps cannot be attached after adoption. The scope borrows the transport and driver, so other runtimes remain usable.

Scope construction reserves one additional native control slot and its worst-case response bytes before starting a non-daemon coordinator. `request_close()` starts background cleanup; `close(timeout=...)` and `close_async()` observe it. Cleanup closes native admission, joins the callback pump, waits for actual native worker/VM drainage, and then removes the exact runtime slot. Driver receipt quota exhaustion cannot block these controls. The scope never closes the shared transport or driver, and independent typed `runtime.free()` is rejected while the scope owns it. Context exit releases core operation records too; retain needed result/effect evidence before releasing the runtime. Durable effect recovery remains a separate implementation milestone.

Observer timeout, cancellation or caller-loop closure leaves cleanup owned and queryable through `scope.status`. A delivered result-buffer release failure retains the last proven checkpoint; `retry_close(...)` or `retry_close_async()` explicitly recovers retained transport buffers and resumes without repeating an acknowledged mutation. This shared transport recovery rejects active readers. Native capacity rejection of the scope's root controls also permits explicit retry after capacity becomes available. Ordinary repeated close observes the same attempt. Other unproven failures keep ownership and report `retryable=False`; they do not authorize replay or unloading. Use `-p test_embedded_scope.py` for actual context-exit, initialization-failure, callback-lifetime and release-recovery tests.

`EmbeddedCallbackPump(transport, runtime_id, config)` owns queued Python callbacks for an already initialized runtime. Supply `CallbackPumpConfig(max_concurrent_handlers=..., max_pending_commands=..., poll_interval_ms=...)` with explicit positive limits. Exactly one pump may own a runtime on a transport. Register its queued capabilities exclusively through that pump; do not separately consume the same core request queue.

| API | Contract |
| --- | --- |
| `HostCapability(descriptor, handler, mode)` | Uses the exact queued core descriptor; `mode` is explicitly `sync` or `async`. The pump snapshots the descriptor and retains the actual handler. |
| `register(...)` / `register_async(...)` | Publish one atomic batch and return immutable registration IDs. Replacements never reroute existing requests by name. |
| `unregister(id, timeout=...)` / `unregister_async(id)` | Stop new dispatch and wait for actual handler drainage. Already dispatched handlers are not cancelled merely by unregistering. |
| `request_close()` / `close(timeout=...)` / `close_async()` | Retire all handlers; actual closure waits for callbacks, acknowledgements and owned threads. A timeout or cancelled observer preserves ownership. |
| `status` / `retry_acknowledgements(timeout=...)` | Expose retained identities and acknowledgement failures. Explicit delivery retry never repeats a business handler; lost success receipts require exact core completion evidence. |

Each handler receives `(arguments, context)` and returns its ordinary JSON value, including `None`. `context.caller`, `request_id` and `registration_id` carry trusted core identity independently of application arguments. Cancellation is cooperative: use `raise_if_cancelled()`, `wait_cancelled(timeout)` or `await wait_cancelled_async()` and explicitly cancel the original operation when needed. `remaining_ms` is advisory. Mutating handlers report actual effects with `context.report_effects(...)`; the default is `unknown`, and neither success nor cancellation implies commit or rollback. Exceptions, invalid JSON and oversized results retain the last effect report. A completion frame explicitly rejected by the native request parser becomes a bounded callback failure with those same effects. A failure freeing an already returned native result does not authorize rewriting the completion.

Synchronous handlers run on bounded workers. Asynchronous handlers run on the pump's dedicated event loop and must use resources created for that loop. They must not block it, return before their own effects finish, or wait for the same pump to drain from within a callback. Cancelling a caller's asyncio task or closing its loop does not cancel the owned handler or unregister task. After runtime cancellation, keep the pump alive through actual handler completion, close the pump, then free the native runtime and transport. If acknowledgement recovery cannot establish exact completion, retain the operation record and resolve the reported error; do not forget that evidence or unload the library.

The low-level transport remains callable concurrently. Blocking native waits must not consume every transport admission slot; reserve capacity for the callback pump and control operations. The pump itself uses short control requests and never issues `operation_wait`.

Native integration coverage is in `tests/test_embedded_native_e2e.py`. With `PYTHONPATH=src` and `LUASKILLS_LIB` selecting the matching development library, run `rtk proxy python -m unittest discover -s tests -p test_embedded_native_e2e.py -v`. These tests exercise actual Lua state, structured values, cancellation, concurrent control and late committed callback results.

Run the same command with `-p test_embedded_pump.py` for real sync/async callback lifetime, bounded admission, caller-loop cancellation, late effects and lost-acknowledgement recovery. Full SDK regression uses `rtk proxy python -m unittest discover -s tests -v` with those same environment variables.

`-p test_embedded_driver.py` additionally checks independent control capacity, frozen receipts, cancelled-loop recovery, joined worker ownership, and actual Lua operation identity recovery after native buffer-release failure.

Synchronous pump observation timeouts raise the built-in `TimeoutError` on every supported Python version, including 3.10. The timeout preserves the underlying command and callback ownership. Async observer cancellation follows the owning-loop rules above.

## Migration Notes

- Existing `client.system(authority)` lifecycle calls keep working; the returned wrapper now also exposes query helpers and `runtime_leases()`.
- `RuntimeLeaseHandle` persists `lease_id + sid + generation` and automatically reattaches identity guards on `eval`, `status`, and `close`.
- `client.system(authority).runtime_leases()` requires the dedicated `luaskills_ffi_system_runtime_lease_*` exports from the latest native library and fails fast when they are missing.
- When the host explicitly enables `request_context.client_capabilities.host_result`, `call_skill()` returns one independent `host_result` field for IDE-native structured results.
- When `host_result["kind"] == "change_set"`, hosts should treat `payload` as `RuntimeChangeSetPayload`.
- Canonical `change_set` payloads now use file lifecycle records plus hunk-level `before + delete[] + insert[] + after` blocks for `modify` changes.
- `create` and `delete` file records carry full-file `content`, while `rename` records carry `old_path` and `new_path`.
- Public leases accept `cwd`, `workspace_root`, `lua_roots`, `c_roots`, and `mounts`. System leases require `system_package`, reject `lua_roots/c_roots`, and derive roots from the trusted package manifest.
- `poll_managed_session_events()`, `wait_managed_session_events()`, and `set_managed_session_wake_callback()` expose the 0.5.1 event surface.

## Authority And Management

Query APIs default to `DelegatedTool`, so ROOT skills are hidden from delegated tools.

`System` only means the host may manage ROOT. It does not bypass ROOT ownership or same-`skill_id` conflict rules.

Ordinary management should target USER or PROJECT:

```powershell
luaskills install LuaSkills/luaskills-demo-skill --target-root USER
luaskills update LuaSkills/luaskills-demo-skill --target-root USER
luaskills uninstall luaskills-demo-skill --target-root USER
```

System management should be exposed only through trusted host/admin surfaces:

```powershell
luaskills system-install LuaSkills/luaskills-demo-skill --target-root ROOT --authority system
```

If a system command is wrapped for ordinary tools, bind `--authority delegated_tool` in the host wrapper instead of letting the caller choose it.

## Skill Config

Skill config is declared by each effective package. Discover the declaration before requesting or changing values:

```python
schema = client.config.describe("my-skill")
status = client.config.validate("my-skill")

write = client.config.set("my-skill", {
    "api_key": "value",
    "retry_count": 3,
})
client.config.set(
    "my-skill",
    "retry_count",
    4,
    expected_revision=write["revision"],
)
client.config.get("my-skill", "api_key")
client.config.list("my-skill")
client.config.delete(
    "my-skill",
    "api_key",
    expected_revision=write["revision"],
)
client.config.refresh()
events = client.config.poll_events(limit=100)
```

Set `host_options["skill_config_root"]` to an absolute user-level directory. LuaSkills stores ordinary and ROOT-owned package configuration separately under `skills/config.json` and `system-skills/config.json`. Every raw `list()` entry includes `store_scope`, so retained records with the same package id remain unambiguous across both files. The strict versioned documents use decimal-string revisions, cross-process companion locks, atomic replacement, cached snapshots, and file-watch reloads. Old unversioned documents are rejected.

`describe()` returns names, types, constraints, UI hints, package-authored descriptions, enum options, defaults, and unambiguous value states. `mode="installed"` discovers physical packages without executing Lua. Writes are accepted only for declared keys, must satisfy declaration and package validator rules, and commit atomically as one package batch.

Values are omitted by default. `include_values=True` returns unmasked effective values. The SDK and LuaSkills do not authorize or mask this data; the host must allow, deny, force, or obtain user approval for disclosure and mutations. Lua code can modify only its own package, while host SDK calls are intentionally unrestricted.

`expected_revision` enables compare-and-swap writes and deletes. `poll_events`, `wait_for_events`, and `watch_events` expose ordered local-write and external-reload events. A missing configuration should be handled by showing `describe()` output and asking the user or an authorized AI tool for the declared parameters.

CLI equivalents:

```bash
luaskills config describe my-skill --skill-config-root /absolute/user-config
luaskills config validate my-skill
luaskills config describe my-skill --include-values
luaskills config describe --installed --root-name ROOT
luaskills config set my-skill retry_count 3 --expected-revision 7
luaskills config set-batch my-skill '{"retry_count":4,"mode":"safe"}'
luaskills config refresh skills
luaskills config events --after-sequence 12 --limit 100
```

The CLI defaults `--skill-config-root` to `<runtime-root>/config`; hosts embedding the SDK must still choose and pass their own absolute user-level root.

Configuration survives package uninstall; explicit cleanup belongs to the host. Configuration only affects behavior when the Lua skill reads it and is not a hard runtime policy layer.

## Troubleshooting

### `fetch failed` while installing runtime assets

`install-runtime` uses Python `urllib` to download GitHub Release assets. In proxy environments, configure the standard proxy variables before running it.

```powershell
$env:HTTP_PROXY = "http://127.0.0.1:10808"
$env:HTTPS_PROXY = "http://127.0.0.1:10808"
luaskills install-runtime --database none --runtime-root D:\runtime\luaskills
```

### `LuaSkills library path is required`

This means the SDK could not find a native LuaSkills library. Run `install-runtime`, pass `--runtime-root`, or set `LUASKILLS_LIB`.

```powershell
luaskills install-runtime --database none --runtime-root D:\runtime\luaskills
luaskills version --runtime-root D:\runtime\luaskills
```

### Lua modules are missing at runtime

If a skill fails with Lua module loading errors, make sure `install-runtime` was run without `--skip-lua-runtime` and that `runtime_root/lua_packages` exists. The default installer uses `LuaSkills/luaskills-packages` runtime packages specifically to satisfy these Lua-side dependencies.

```powershell
luaskills install-runtime --database none --runtime-root D:\runtime\luaskills
Test-Path D:\runtime\luaskills\lua_packages
```

## Verification

For source-tree validation:

```bash
python -m compileall src/luaskills
PYTHONPATH=src python -m luaskills.cli version --runtime-root D:/runtime/luaskills
```

## Publishing

The release version is stored in `VERSION`. Keep `VERSION` and `pyproject.toml` aligned before publishing.

For one unified ecosystem release, publish `LuaSkills/luaskills-packages` first, then publish `LuaSkills/luaskills`, so the default runtime installer assets for this SDK already exist.

Before publishing:

```bash
python -m build
twine check dist/*
```

Use a new patch version for every PyPI publish. Published versions cannot be overwritten.

Recommended unified publish order: `luaskills-packages` -> `luaskills` core release -> TypeScript SDK -> Python SDK -> Go SDK -> SDK examples releases.

After PyPI publishes successfully, run the GitHub Actions workflow **Examples Release** manually. It reads `VERSION`, installs `luaskills-sdk=={VERSION}` from PyPI, installs LuaSkills runtime assets, runs the examples, then creates or updates the `examples-v{VERSION}` GitHub Release with:

- `luaskills-sdk-python-examples-{VERSION}.zip`
- `luaskills-sdk-python-examples-{VERSION}.zip.sha256`

The examples release tag intentionally uses the `examples-v` prefix because it is an examples asset release, not an SDK package version.
