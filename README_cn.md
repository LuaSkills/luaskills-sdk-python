# luaskills-sdk

中文文档。英文默认文档见 [README.md](README.md)。

LuaSkills 主仓库：[LuaSkills/luaskills](https://github.com/LuaSkills/luaskills)

Python SDK，用于通过公共 JSON FFI 接入 LuaSkills 运行时。

SDK 封装了原生动态库加载、JSON FFI buffer、engine 生命周期、正式 skill root、带权限语义的管理调用、skill config、provider callback、宿主工具 callback 与 runtime 资产安装。宿主在常规集成中不需要手写底层 FFI buffer 或 JSON 包络。

## 安装

```bash
pip install luaskills-sdk
```

Python wheel 不内置原生 runtime 二进制文件或 LuaRocks 模块。请先用 `install-runtime` 准备 `runtime_root`，再把该 root 传给 `LuaSkillsClient`。

```powershell
luaskills install-runtime --database none --runtime-root D:\runtime\luaskills
luaskills version --runtime-root D:\runtime\luaskills
```

安装完成后，SDK 会从 `runtime_root/libs` 自动解析 `luaskills.dll` / `libluaskills.so` / `libluaskills.dylib`。通常不需要设置 `LUASKILLS_LIB`。

只有当宿主明确在 SDK runtime root 之外自行管理原生动态库时，才需要使用 `library_path` 或 `LUASKILLS_LIB`。

## Runtime 资产

`install-runtime` 会下载 GitHub Release 资产、校验 `.sha256` 旁路文件、解压原生文件与 Lua runtime 包，并写入：

```text
runtime_root/resources/luaskills-sdk-runtime-manifest.json
```

支持的数据库模式：

- `none`：安装 Lua runtime 归档与 LuaSkills FFI SDK 归档，但不安装数据库 provider。
- `vldb-direct`：安装 `vldb-sqlite-lib` 与 `vldb-lancedb-lib` 动态库，并使用 `dynamic_library` provider 模式。
- `vldb-controller`：安装 `vldb-controller`，并使用托管的 `space_controller` provider 模式。
- `host-callback`：不安装 VLDB 二进制文件，只生成 `host_callback + json` 宿主配置。

默认 LuaSkills 资产：

- `LuaSkills/luaskills-packages` 发布的 `lua-runtime-packages-{platform}.tar.gz`：默认安装；提供 `lua_packages`、packages 侧运行时 `libs`、`resources` 与第三方运行时授权材料。
- `luaskills-ffi-sdk-{platform}.tar.gz`：默认安装；提供公共 FFI 动态库、头文件与 FFI 授权材料。
- `lua-deps-{platform}.tar.gz`：SDK 不默认安装；它是 CI、源码构建或高级原生模块重建使用的构建期依赖包。

默认情况下，SDK 会把 LuaSkills core 固定到自身对应版本，并从兼容的 `0.1` 协议线中自动解析最新已发布的 runtime packages patch 版本。

## 版本对齐

- 尽量让 SDK 与 LuaSkills core 保持同一条当前发布版本线。
- 当前 SDK 默认指向 LuaSkills core 标签 `v0.4.2`。
- runtime packages 与 native deps 仍然来自拆分后的 `LuaSkills/luaskills-packages` 及相关发布资产。

```powershell
luaskills install-runtime --database none --runtime-root D:\runtime\luaskills
luaskills install-runtime --database vldb-direct --runtime-root D:\runtime\luaskills
luaskills install-runtime --database vldb-controller --runtime-root D:\runtime\luaskills
luaskills install-runtime --database host-callback --runtime-root D:\runtime\luaskills
```

下载前可用 `--dry-run` 检查准确的 release URL：

```powershell
luaskills install-runtime --database vldb-direct --runtime-root D:\runtime\luaskills --dry-run
```

已经自行管理 Lua 包的高级宿主可以跳过 Lua runtime 归档：

```powershell
luaskills install-runtime --database none --runtime-root D:\runtime\luaskills --skip-lua-runtime
```

## 基础用法

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

只有在明确绕过 runtime manifest 时才需要使用 `library_path`：

```python
from luaskills import LuaSkillsClient

with LuaSkillsClient(
    library_path="D:/path/to/luaskills.dll",
    runtime_root="D:/runtime/luaskills",
) as client:
    print(client.version())
```

## CLI 流程

基于已准备 runtime root 的 CLI 完整链路：

```powershell
luaskills install-runtime --database none --runtime-root D:\runtime\luaskills
luaskills version --runtime-root D:\runtime\luaskills
luaskills list --runtime-root D:\runtime\luaskills
luaskills call demo-standard-ffi-skill-ping '{"note":"python"}' --runtime-root D:\runtime\luaskills
```

如果需要 VLDB 直连动态库：

```powershell
luaskills install-runtime --database vldb-direct --runtime-root D:\runtime\luaskills
```

如果更希望使用共享 controller 模式：

```powershell
luaskills install-runtime --database vldb-controller --runtime-root D:\runtime\luaskills
```

## Provider Callback

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

callback 必须在 `engine_new` 前注册；engine 创建后再切换 callback 不会 retroactive 影响已存在的 engine。

## 宿主工具 Callback

`vulcan.host.*` 使用通过 `luaskills_ffi_set_host_tool_json_callback` 注册的固定宿主工具 callback。请在运行可能调用宿主工具的 skill 前完成注册：

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

callback 会收到 `{ action, tool_name, args }`。`list` 应返回宿主开放给 Lua 的工具元数据；`has` 应返回 boolean，或带有 `exists` / `has` / `available` 的对象；`call` 应返回一次完整的 table 形态结果。宿主关闭时调用 `ffi.clear_host_tool_json_callback()` 清理注册。该桥接刻意不支持 stream。

## 模型 Callback

`vulcan.models.*` 使用通过 `luaskills_ffi_set_model_embed_json_callback` 与 `luaskills_ffi_set_model_llm_json_callback` 注册的固定模型 callback。Lua skill 只能调用 `vulcan.models.embed(text)` 与 `vulcan.models.llm(system, user)`；provider 选择、模型名、密钥、temperature、thinking、限额和 stream 策略全部归宿主管理。

请在创建或使用可能运行模型类 skill 的 engine 前注册模型 callback。`LuaSkillsJsonFfi` 实例需要在 callback 生效期间保持存活；宿主关闭或测试清理时应显式清理 callback。

SDK callback 是宿主模型边界：

- 它接收 LuaSkills 发来的固定请求结构。
- 它应使用宿主选择的 provider 和宿主管理的配置发起真实模型调用。
- provider 成功时返回裸成功载荷。
- provider 失败且需要排查时返回结构化错误包络，保留 `provider_message`、`provider_code`、`provider_status`。
- 不要在 provider 错误字段里暴露 API key、Authorization header、签名或完整原始请求头。

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

embedding callback 会收到 `{ text, caller }`，LLM callback 会收到 `{ system, user, caller }`。成功时返回裸响应载荷；provider 失败时返回 `{ ok: false, error: { code, message, provider_message?, provider_code?, provider_status? } }`。宿主关闭时调用 `ffi.clear_model_embed_json_callback()` 和 `ffi.clear_model_llm_json_callback()` 清理注册。

注册后的最小运行时检查：

```python
status = client.run_lua("return vulcan.models.status()")
embed_result = client.run_lua('return vulcan.models.embed("hello")')
llm_result = client.run_lua('return vulcan.models.llm("system", "user")')
```

常见对接问题：

- `model_unavailable`：对应 callback 没有注册，或在 skill 调用前已经被清理。
- 缺少 provider 细节：请从 callback 返回结构化错误包络，而不是直接抛出 provider 异常。
- 缺少 FFI symbol：请确认 runtime 动态库包含 `luaskills_ffi_set_model_embed_json_callback` 与 `luaskills_ffi_set_model_llm_json_callback`。
- `caller` 字段为空：请通过已加载 runtime skill 或 runtime `run_lua` 上下文调用，不要用脱离 runtime 的 provider 单元测试判断 caller context。

## 示例

wheel 内置可运行示例：

```bash
python -m luaskills.examples.basic
python -m luaskills.examples.host_tool_callback
python -m luaskills.examples.provider_callback
python -m luaskills.examples.runtime_lease
```

源码仓库示例还包含 query、lifecycle 与持久 runtime-lease 流程，并带有一个内置 USER 层夹具 skill：

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

夹具 skill 位于 `examples/fixture_runtime/user_skills/demo-standard-ffi-skill`，因此委托查询示例不需要 System 权限也能看到它。

完整示例索引与 runtime 注意事项见 [examples/README_cn.md](examples/README_cn.md)。英文示例指南见 [examples/README.md](examples/README.md)。

## 持久运行时租约

普通租约入口请使用 `client.runtime_leases()`；如果宿主希望通过最新原生库提供的专用 system runtime-lease 导出固定注入 authority，请使用 `client.system(authority).runtime_leases()`。

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
    )
    result = session.eval("counter = (counter or 0) + 1; return { counter = counter }")
    print(result["result"])
    print(session.status())
    print(session.close())
finally:
    client.close()
```

## 迁移说明

- 现有 `client.system(authority)` 生命周期调用保持兼容；返回的 wrapper 现在额外暴露查询辅助方法和 `runtime_leases()`。
- `RuntimeLeaseHandle` 会持久化 `lease_id + sid + generation`，并在 `eval`、`status`、`close` 时自动补回身份护栏。
- `client.system(authority).runtime_leases()` 依赖最新原生库提供的专用 `luaskills_ffi_system_runtime_lease_*` 导出；如果这组导出缺失，会立即报错而不是静默降级。
- 当宿主在 `request_context.client_capabilities.host_result` 中显式开启结构化结果后，`call_skill()` 会返回独立的 `host_result` 字段，供 IDE 原生结构化结果消费。
- 当 `host_result["kind"] == "change_set"` 时，宿主应把 `payload` 按 `RuntimeChangeSetPayload` 解析。
- canonical `change_set` 现在使用文件生命周期记录；`modify` 通过 hunk 级 `before + delete[] + insert[] + after` 表达具体修改。
- `create` 与 `delete` 文件记录直接携带整文件 `content`，`rename` 记录携带 `old_path` 与 `new_path`。
- `runtime_leases().create()` 与 `create_handle()` 现在支持 `cwd`、`workspace_root`、`lua_roots`、`c_roots`、`mounts` 等宿主路径选项。

## 权限与管理

查询类接口默认使用 `DelegatedTool`，因此委托工具看不到 ROOT skills。

`System` 只表示宿主可以管理 ROOT；它不表示可以绕过 ROOT 所有权或同名 `skill_id` 冲突规则。

普通管理面应固定目标为 USER 或 PROJECT：

```powershell
luaskills install LuaSkills/luaskills-demo-skill --target-root USER
luaskills update LuaSkills/luaskills-demo-skill --target-root USER
luaskills uninstall luaskills-demo-skill --target-root USER
```

system 管理面只应通过可信宿主或管理员界面开放：

```powershell
luaskills system-install LuaSkills/luaskills-demo-skill --target-root ROOT --authority system
```

如果 system 命令被封装给普通 tools，宿主 wrapper 应固定传入 `--authority delegated_tool`，而不是让调用方自行选择。

## Skill Config

skill config 是普通的 `skill_id + key` 配置存储面。配置只有在 Lua skill 主动读取时才会影响行为；它不是运行时强制策略层。

## 常见问题

### 安装 runtime 资产时出现 `fetch failed`

`install-runtime` 使用 Python `urllib` 下载 GitHub Release 资产。在代理环境中，请先配置标准代理环境变量。

```powershell
$env:HTTP_PROXY = "http://127.0.0.1:10808"
$env:HTTPS_PROXY = "http://127.0.0.1:10808"
luaskills install-runtime --database none --runtime-root D:\runtime\luaskills
```

### `LuaSkills library path is required`

这表示 SDK 找不到 LuaSkills 原生动态库。请运行 `install-runtime`、传入 `--runtime-root`，或设置 `LUASKILLS_LIB`。

```powershell
luaskills install-runtime --database none --runtime-root D:\runtime\luaskills
luaskills version --runtime-root D:\runtime\luaskills
```

### 运行时缺少 Lua 模块

如果 skill 运行时出现 Lua 模块加载错误，请确认运行 `install-runtime` 时没有使用 `--skip-lua-runtime`，并且 `runtime_root/lua_packages` 存在。默认安装器正是通过 `LuaSkills/luaskills-packages` 的 runtime packages 来满足这部分 Lua 侧依赖。

```powershell
luaskills install-runtime --database none --runtime-root D:\runtime\luaskills
Test-Path D:\runtime\luaskills\lua_packages
```

## 验证

源码环境可运行：

```bash
python -m compileall src/luaskills
PYTHONPATH=src python -m luaskills.cli version --runtime-root D:/runtime/luaskills
```

## 发布

发布版本记录在 `VERSION`。发布前请保持 `VERSION` 与 `pyproject.toml` 一致。

如果要做生态统一发布，必须先发布 `LuaSkills/luaskills-packages`，再发布 `LuaSkills/luaskills`，确保本 SDK 默认安装器引用的 runtime 资产已经存在。

发布前执行：

```bash
python -m build
twine check dist/*
```

每次 PyPI publish 都必须使用新的 patch 版本；已发布版本不能覆盖。

推荐统一发布顺序：`luaskills-packages` -> `luaskills` 核心仓库 -> TypeScript SDK -> Python SDK -> Go SDK -> 各 SDK 的 examples release。

PyPI 发布成功后，手动运行 GitHub Actions 里的 **Examples Release** 工作流。它会读取 `VERSION`，从 PyPI 安装 `luaskills-sdk=={VERSION}`，安装 LuaSkills runtime 资产，运行示例冒烟测试，然后创建或更新 `examples-v{VERSION}` GitHub Release，并上传：

- `luaskills-sdk-python-examples-{VERSION}.zip`
- `luaskills-sdk-python-examples-{VERSION}.zip.sha256`

示例 release tag 故意使用 `examples-v` 前缀，因为它是示例资产发布，不是 SDK 包版本。
