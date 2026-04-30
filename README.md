# luaskills-sdk

English documentation is the default package documentation. For Chinese, see [README_cn.md](README_cn.md).

Main LuaSkills repository: [LuaSkills/luaskills](https://github.com/LuaSkills/luaskills)

Python SDK for integrating the LuaSkills runtime through the public JSON FFI surface.

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

- `lua-runtime-{platform}.tar.gz`: installed by default; provides `lua_packages`, runtime `libs`, `resources`, and runtime licenses.
- `luaskills-ffi-sdk-{platform}.tar.gz`: installed by default; provides the public FFI dynamic library, headers, and FFI licenses.
- `lua-deps-{platform}.tar.gz`: not installed by the SDK; it is a build-time bundle for CI, source builds, or advanced native module rebuilds.

```powershell
luaskills install-runtime --database none --runtime-root D:\runtime\luaskills
luaskills install-runtime --database vldb-direct --runtime-root D:\runtime\luaskills
luaskills install-runtime --database vldb-controller --runtime-root D:\runtime\luaskills
luaskills install-runtime --database host-callback --runtime-root D:\runtime\luaskills
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

## Examples

The wheel includes runnable examples:

```bash
python -m luaskills.examples.basic
python -m luaskills.examples.host_tool_callback
python -m luaskills.examples.provider_callback
```

Source-tree examples include query and lifecycle flows with a bundled USER-layer fixture skill:

```powershell
luaskills install-runtime --database none --runtime-root .\examples\fixture_runtime
python .\examples\basic.py
python .\examples\call.py
python .\examples\host_tool_callback.py
python .\examples\query.py
python .\examples\lifecycle.py
python .\examples\provider_callback.py
```

The fixture skill lives at `examples/fixture_runtime/user_skills/demo-standard-ffi-skill`, so delegated-query examples can see it without System authority.

See [examples/README.md](examples/README.md) for the full example index and runtime notes. The Chinese example guide is [examples/README_cn.md](examples/README_cn.md).

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

Skill config is a plain `skill_id + key` storage surface. Configuration only affects behavior when the Lua skill reads it. It is not a hard runtime policy layer.

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

If a skill fails with Lua module loading errors, make sure `install-runtime` was run without `--skip-lua-runtime` and that `runtime_root/lua_packages` exists.

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

Before publishing:

```bash
python -m build
twine check dist/*
```

Use a new patch version for every PyPI publish. Published versions cannot be overwritten.

After PyPI publishes successfully, run the GitHub Actions workflow **Examples Release** manually. It reads `VERSION`, installs `luaskills-sdk=={VERSION}` from PyPI, installs LuaSkills runtime assets, runs the examples, then creates or updates the `examples-v{VERSION}` GitHub Release with:

- `luaskills-sdk-python-examples-{VERSION}.zip`
- `luaskills-sdk-python-examples-{VERSION}.zip.sha256`

The examples release tag intentionally uses the `examples-v` prefix because it is an examples asset release, not an SDK package version.
