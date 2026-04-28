# luaskills-sdk

Python SDK for integrating the LuaSkills runtime through the public JSON FFI surface.

Python SDK，用于通过公共 JSON FFI 接入 LuaSkills 运行时。

The SDK wraps native library loading, JSON FFI buffers, engine lifecycle, formal skill roots, authority-aware management calls, skill config, provider callbacks, and runtime asset installation. Hosts should not need to hand-write `FfiBorrowedBuffer`, `FfiOwnedBuffer`, or low-level JSON envelopes for normal integration.

SDK 封装了原生动态库加载、JSON FFI buffer、engine 生命周期、正式 skill root、带权限语义的管理调用、skill config、provider callback 与 runtime 资产安装。宿主在常规集成中不需要手写 `FfiBorrowedBuffer`、`FfiOwnedBuffer` 或底层 JSON 包络。

## Installation

```bash
pip install luaskills-sdk
```

The Python wheel does not embed native runtime binaries or LuaRocks modules. Prepare a `runtime_root` with `install-runtime`, then pass that root to `LuaSkillsClient`.

Python wheel 不内置原生 runtime 二进制文件或 LuaRocks 模块。请先用 `install-runtime` 准备 `runtime_root`，再把该 root 传给 `LuaSkillsClient`。

```powershell
luaskills install-runtime --database none --runtime-root D:\runtime\luaskills
luaskills version --runtime-root D:\runtime\luaskills
```

After installation, the SDK automatically resolves `luaskills.dll` / `libluaskills.so` / `libluaskills.dylib` from `runtime_root/libs`. You usually do not need `LUASKILLS_LIB`.

安装完成后，SDK 会从 `runtime_root/libs` 自动解析 `luaskills.dll` / `libluaskills.so` / `libluaskills.dylib`。通常不需要设置 `LUASKILLS_LIB`。

Use `library_path` or `LUASKILLS_LIB` only when your host intentionally manages native libraries outside the SDK runtime root.

只有当宿主明确在 SDK runtime root 之外自行管理原生动态库时，才需要使用 `library_path` 或 `LUASKILLS_LIB`。

## Runtime Assets

`install-runtime` downloads GitHub Release assets, verifies `.sha256` sidecars, extracts native files and Lua runtime packages, and writes:

`install-runtime` 会下载 GitHub Release 资产、校验 `.sha256` 旁路文件、解压原生文件与 Lua runtime 包，并写入：

```text
runtime_root/resources/luaskills-sdk-runtime-manifest.json
```

Supported database modes:

支持的数据库模式：

- `none`: installs the Lua runtime archive and the LuaSkills FFI SDK archive, without database providers.
- `none`：安装 Lua runtime 归档与 LuaSkills FFI SDK 归档，但不安装数据库 provider。
- `vldb-direct`: installs `vldb-sqlite-lib` and `vldb-lancedb-lib` dynamic libraries and uses `dynamic_library` provider mode.
- `vldb-direct`：安装 `vldb-sqlite-lib` 与 `vldb-lancedb-lib` 动态库，并使用 `dynamic_library` provider 模式。
- `vldb-controller`: installs `vldb-controller` and uses managed `space_controller` provider mode.
- `vldb-controller`：安装 `vldb-controller`，并使用托管的 `space_controller` provider 模式。
- `host-callback`: installs no VLDB binaries and generates `host_callback + json` host options.
- `host-callback`：不安装 VLDB 二进制文件，只生成 `host_callback + json` 宿主配置。

Default LuaSkills assets:

默认 LuaSkills 资产：

- `lua-runtime-{platform}.tar.gz`: installed by default; provides `lua_packages`, runtime `libs`, `resources`, and runtime licenses.
- `lua-runtime-{platform}.tar.gz`：默认安装；提供 `lua_packages`、运行时 `libs`、`resources` 与运行时授权材料。
- `luaskills-ffi-sdk-{platform}.tar.gz`: installed by default; provides the public FFI dynamic library, headers, and FFI licenses.
- `luaskills-ffi-sdk-{platform}.tar.gz`：默认安装；提供公共 FFI 动态库、头文件与 FFI 授权材料。
- `lua-deps-{platform}.tar.gz`: not installed by the SDK; it is a build-time bundle for CI, source builds, or advanced native module rebuilds.
- `lua-deps-{platform}.tar.gz`：SDK 不默认安装；它是 CI、源码构建或高级原生模块重建使用的构建期依赖包。

```powershell
luaskills install-runtime --database none --runtime-root D:\runtime\luaskills
luaskills install-runtime --database vldb-direct --runtime-root D:\runtime\luaskills
luaskills install-runtime --database vldb-controller --runtime-root D:\runtime\luaskills
luaskills install-runtime --database host-callback --runtime-root D:\runtime\luaskills
```

Use `--dry-run` to inspect exact release URLs before downloading.

下载前可用 `--dry-run` 检查准确的 release URL。

```powershell
luaskills install-runtime --database vldb-direct --runtime-root D:\runtime\luaskills --dry-run
```

Advanced hosts that already manage Lua packages can skip the Lua runtime archive:

已经自行管理 Lua 包的高级宿主可以跳过 Lua runtime 归档：

```powershell
luaskills install-runtime --database none --runtime-root D:\runtime\luaskills --skip-lua-runtime
```

## Basic Usage

Prepare `runtime_root`, then create the client without an explicit `library_path`:

准备好 `runtime_root` 后，无需显式 `library_path` 即可创建 client：

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

只有在明确绕过 runtime manifest 时才需要使用 `library_path`：

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

基于已准备 runtime root 的 CLI 完整链路：

```powershell
luaskills install-runtime --database none --runtime-root D:\runtime\luaskills
luaskills version --runtime-root D:\runtime\luaskills
luaskills list --runtime-root D:\runtime\luaskills
luaskills call demo-standard-ffi-skill-ping '{"note":"python"}' --runtime-root D:\runtime\luaskills
```

If you need VLDB direct libraries:

如果需要 VLDB 直连动态库：

```powershell
luaskills install-runtime --database vldb-direct --runtime-root D:\runtime\luaskills
```

If you prefer the shared controller mode:

如果更希望使用共享 controller 模式：

```powershell
luaskills install-runtime --database vldb-controller --runtime-root D:\runtime\luaskills
```

## Provider Callback

SQLite / LanceDB `host_callback + json` mode can be registered through the SDK before engine creation:

SQLite / LanceDB 的 `host_callback + json` 模式可以在 engine 创建前通过 SDK 注册：

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

callback 必须在 `engine_new` 前注册；engine 创建后再切换 callback 不会 retroactive 影响已存在的 engine。

## Examples

The wheel includes runnable examples:

wheel 内置可运行示例：

```bash
python -m luaskills.examples.basic
python -m luaskills.examples.provider_callback
```

The source repository also keeps `examples/basic.py` and `examples/provider_callback.py` for direct reading.

源码仓库中同样保留 `examples/basic.py` 与 `examples/provider_callback.py`，便于直接阅读。

## Authority And Management

Query APIs default to `DelegatedTool`, so ROOT skills are hidden from delegated tools.

查询类接口默认使用 `DelegatedTool`，因此委托工具看不到 ROOT skills。

`System` only means the host may manage ROOT. It does not bypass ROOT ownership or same-`skill_id` conflict rules.

`System` 只表示宿主可以管理 ROOT；它不表示可以绕过 ROOT 所有权或同名 `skill_id` 冲突规则。

Ordinary management should target USER or PROJECT:

普通管理面应固定目标为 USER 或 PROJECT：

```powershell
luaskills install LuaSkills/luaskills-demo-skill --target-root USER
luaskills update LuaSkills/luaskills-demo-skill --target-root USER
luaskills uninstall luaskills-demo-skill --target-root USER
```

System management should be exposed only through trusted host/admin surfaces:

system 管理面只应通过可信宿主或管理员界面开放：

```powershell
luaskills system-install LuaSkills/luaskills-demo-skill --target-root ROOT --authority system
```

If a system command is wrapped for ordinary tools, bind `--authority delegated_tool` in the host wrapper instead of letting the caller choose it.

如果 system 命令被封装给普通 tools，宿主 wrapper 应固定传入 `--authority delegated_tool`，而不是让调用方自行选择。

## Skill Config

Skill config is a plain `skill_id + key` storage surface. Configuration only affects behavior when the Lua skill reads it. It is not a hard runtime policy layer.

skill config 是普通的 `skill_id + key` 配置存储面。配置只有在 Lua skill 主动读取时才会影响行为；它不是运行时强制策略层。

## Troubleshooting

### `fetch failed` while installing runtime assets

`install-runtime` uses Python `urllib` to download GitHub Release assets. In proxy environments, configure the standard proxy variables before running it.

`install-runtime` 使用 Python `urllib` 下载 GitHub Release 资产。在代理环境中，请先配置标准代理环境变量。

```powershell
$env:HTTP_PROXY = "http://127.0.0.1:10808"
$env:HTTPS_PROXY = "http://127.0.0.1:10808"
luaskills install-runtime --database none --runtime-root D:\runtime\luaskills
```

### `LuaSkills library path is required`

This means the SDK could not find a native LuaSkills library. Run `install-runtime`, pass `--runtime-root`, or set `LUASKILLS_LIB`.

这表示 SDK 找不到 LuaSkills 原生动态库。请运行 `install-runtime`、传入 `--runtime-root`，或设置 `LUASKILLS_LIB`。

```powershell
luaskills install-runtime --database none --runtime-root D:\runtime\luaskills
luaskills version --runtime-root D:\runtime\luaskills
```

### Lua modules are missing at runtime

If a skill fails with Lua module loading errors, make sure `install-runtime` was run without `--skip-lua-runtime` and that `runtime_root/lua_packages` exists.

如果 skill 运行时出现 Lua 模块加载错误，请确认运行 `install-runtime` 时没有使用 `--skip-lua-runtime`，并且 `runtime_root/lua_packages` 存在。

```powershell
luaskills install-runtime --database none --runtime-root D:\runtime\luaskills
Test-Path D:\runtime\luaskills\lua_packages
```

## Verification

For source-tree validation:

源码环境可运行：

```bash
python -m compileall src/luaskills
PYTHONPATH=src python -m luaskills.cli version --runtime-root D:/runtime/luaskills
```
