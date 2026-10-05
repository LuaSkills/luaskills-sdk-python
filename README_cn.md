# luaskills-sdk

中文文档。英文默认文档见 [README.md](README.md)。

LuaSkills 主仓库：[LuaSkills/luaskills](https://github.com/LuaSkills/luaskills)

Python SDK，用于通过公共 JSON FFI 接入 LuaSkills 运行时。

本 Python SDK 源码面向 `0.6.5` 发布线，独立绑定 LuaSkills core `0.6.1`；发布与资产验证遵循发布工作流。它沿用严格的技能包级配置契约，并将运行时资产默认值设为 LuaSkills core `v0.6.1`、vldb-controller `v0.2.3` 与 vldb-sqlite `v0.1.6`。

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

源码包还提供不依赖 Python CLI 的统一同步脚本，可直接拉取 LuaSkills FFI、Lua runtime packages 与 VLDB：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/deps/sync_runtime_assets.ps1 -Target all -Database vldb-controller -RuntimeRoot D:\runtime\luaskills
```

```bash
RUNTIME_ROOT=/opt/luaskills scripts/deps/sync_runtime_assets.sh all vldb-controller
```

目标支持 `all`、`luaskills`、`lua`、`vldb`；VLDB 模式支持 `none`、`vldb-controller`、`vldb-direct`、`host-callback`。脚本默认固定 LuaSkills `v0.6.1`，并允许显式覆盖发布版本。

`install-runtime` 会下载 GitHub Release 资产、校验 `.sha256` 旁路文件、解压原生文件与 Lua runtime 包，并写入：

```text
runtime_root/resources/luaskills-sdk-runtime-manifest.json
```

SDK `0.6.3` 校验归档成员的原始名称，并在提取每个 tar 成员前，对照已经提取的条目重新检查路径及链接目标。成员名中的父组件、绝对或越界目标，以及没有先前常规文件或常规硬链接链来源的硬链接都会被拒绝。操作系统允许创建链接时，合法相对符号链接和常规硬链接链仍受支持；目录元数据继续由标准 tar 提取流程保留。这项保护支持 Python `>=3.10`，不依赖较新解释器的默认提取过滤器。

SDK `0.6.4` 保留回调返回时捕获的副作用快照，返回值非法或超过编码上限时也保持该证据。通过保留上下文别名提交的迟到报告不能改写已经完成的结果。取消和编码失败不表示事务已回滚。

SDK `0.6.5` 在原生构造可能发布身份前保留精确传输所有者、已加载动态库及原始 `uint64` 输出单元。Python 在原生发布后处理中断时，`EmbeddedTransport.live_transports()` 返回同一所有者供显式关闭及释放；构造恢复不会创建或重放原生工作。精确结果及传输释放也跨中断保留不确定状态，仅在先前同一所有者的释放尝试被中断时接受 `NOT_FOUND`。

支持的数据库模式：

- `none`：安装 Lua runtime 归档与 LuaSkills FFI SDK 归档，但不安装数据库 provider。
- `vldb-direct`：安装 `vldb-sqlite-lib` 与 `vldb-lancedb-lib` 动态库，并使用 `dynamic_library` provider 模式。
- `vldb-controller`：安装 `vldb-controller`，并使用托管的 `space_controller` provider 模式。
- `host-callback`：不安装 VLDB 二进制文件，只生成 `host_callback + json` 宿主配置。

默认 LuaSkills 资产：

- `LuaSkills/luaskills-packages` 发布的 `lua-runtime-packages-{platform}.tar.gz`：默认安装；提供 `lua_packages`、packages 侧运行时 `libs`、`resources` 与第三方运行时授权材料。
- `luaskills-ffi-sdk-{platform}.tar.gz`：默认安装；提供公共 FFI 动态库、头文件与 FFI 授权材料。
- `lua-deps-{platform}.tar.gz`：SDK 不默认安装；它是 CI、源码构建或高级原生模块重建使用的构建期依赖包。

受管 Python 与 Node.js 子运行时是可选项。当 Lua skill 需要 `vulcan.runtime.python.*` 或 `vulcan.runtime.node.*` 时，使用 `--managed-runtimes all`；安装器会把 Python、`uv`、Node.js 与 `pnpm` 放入 `runtime_root/dependencies/runtimes/...`。

受管子运行时支持 Windows x64、Linux x64/ARM64 与 macOS x64/ARM64。Windows ARM 会在任何下载或目标目录创建前被明确拒绝。源码分发包还包含 `scripts/deps/fetch_managed_runtimes.ps1`、`scripts/deps/fetch_managed_runtimes.sh` 与 `scripts/debug-tools/managed_runtime_layout_check.py` 独立工具，用于准备和校验 debug 运行时根目录。

当前受管依赖精确版本为 Python `3.14.6`、uv `0.11.28`、Node.js `24.18.0`、pnpm `11.11.0`。除非宿主有意安装其他受支持版本，否则包内 `dependencies.yaml` 必须声明相同的运行时与包管理器精确版本。

### 宿主指定受管运行时根

LuaSkills 0.5.1 将 LuaSkills 数据根、只读解释器发行根和可写受管环境根拆分为三个边界。两个显式受管根都必须是绝对路径；未设置时继续使用兼容的 `runtime_root/dependencies/runtimes` 与 `runtime_root/dependencies/envs` 布局。

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

`default_managed_runtime_config()` 返回稳定引擎默认值：单个精确环境/包所有者池 `4` 个 Worker、空闲 `60` 秒、`256` 个持久会话、每个 Session 输出流 `1 MiB`，且 invoke 无默认超时。调整单项时应从这份完整对象开始。所有配置数值必须为正；单次 `invoke.timeout_ms` 与单个 Session 的 `session.open.buffer_limit_bytes` 只覆盖各自对应的引擎默认值。

独立拉取与调试工具接受相同的拆分布局：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/deps/fetch_managed_runtimes.ps1 -RuntimeRoot D:\VulcanCodeData\luaskills -DistributionRoot D:\VulcanCode\dependencies\runtimes -Target all
python scripts/debug-tools/managed_runtime_layout_check.py D:\VulcanCodeData\luaskills --distribution-root D:\VulcanCode\dependencies\runtimes --environment-root D:\VulcanCodeData\managed-runtime-envs
```

Python SDK `0.6.5` 默认固定到独立版本的 LuaSkills core `v0.6.1`，并从兼容的 `0.1` 协议线中自动解析最新已发布的 runtime packages patch 版本。

## 版本对齐

- SDK 补丁版本与核心版本独立；使用包内生成契约要求的精确核心版本。
- 本源码默认指向 LuaSkills core 标签 `v0.6.1`。
- runtime packages 与 native deps 仍然来自拆分后的 `LuaSkills/luaskills-packages` 及相关发布资产。
- SDK 默认 host options 传入 `runtime_root`、两个空的受管根覆盖槽与完整稳定的 `managed_runtime_config`；宿主未显式覆盖时，LuaSkills 会推导固定数据布局。
- 宿主工具直接放在 `runtime_root/bin`，不再放到 `runtime_root/bin/tools`。

```powershell
luaskills install-runtime --database none --runtime-root D:\runtime\luaskills
luaskills install-runtime --database vldb-direct --runtime-root D:\runtime\luaskills
luaskills install-runtime --database vldb-controller --runtime-root D:\runtime\luaskills
luaskills install-runtime --database host-callback --runtime-root D:\runtime\luaskills
luaskills install-runtime --database none --managed-runtimes all --runtime-root D:\runtime\luaskills
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
        system_package={"id": "debug-plugin", "root": "D:/runtime/luaskills/system_lua_lib/debug-plugin", "dependencies_file": "dependencies.json"},
    )
    result = session.eval("counter = (counter or 0) + 1; return { counter = counter }")
    print(result["result"])
    print(session.status())
    print(session.close())
finally:
    client.close()
```

## 嵌入式运行时传输（开发中）

可选的 `caller.request_id` 在核心入场时冻结宿主的 `context.request_context.request_id`。它区别于核心操作 ID 和排队回调请求 ID，Lua 可见上下文或参数不能替换它。同操作单次关闭保留该关联，会话开启及独立会话／可复用实例关闭省略关联。宿主仍须显式登记并校验相关作用域：关联本身不授予权限，旧历史省略的值不能用新请求补全。

通过 `initialize(engine_options, runtime_config, persistence=None)` 显式启用持久模式。省略存储参数保持纯内存行为。传入生成配置，完整声明宿主管理的绝对 `path`、`journal` 保留预算及 `worker` 回执预算；SDK 不补造存储默认值，也不回退。初始化回执只确认尝试，实际结果须查询原生状态。状态包含可选实际存储所有权，协调关闭等待核心、写入者及保留回执排空。

运行时 `storage_status / recover_storage` 提供写入者所有权观测与同一原文件的显式恢复；`history_get / history_next / history_forget` 按原**核心运行时命名空间**访问历史，该身份区别于 FFI 槽 ID。历史与恢复走工作通道；存储状态及操作方法 `persistence_failure / retry_checkpoint` 走控制通道。恢复不自动重试检查点或重放业务；无失败检查点时重试报告忙碌，返回假表示已有重试尚未完成。历史枚举使用原键游标，不提供跨调用快照。

`recover_storage_worker` 仅在受监督失败线程实际退出且全部排队／活动尝试已由监督器处理后，独立重建写入线程。健康运行时返回假；显式写入者关闭、未证实退出或中毒所有权明确拒绝。原回执、字节／数量预留及同一存储所有者保留，不重放旧写入或业务；数据库恢复及原检查点重试仍是独立显式操作。运行时关闭期间，原核心仍在排空且写入者尚未永久关闭时，仍可恢复线程。

历史不会变成活动句柄。管理对账或删除前须先遗忘仍保留的活动操作。`history_reconcile` 附加一份最终、有界宿主证明，保留原始快照、调用方及副作用身份。可信宿主必须授权对账者、证明全部原执行及外部所有者已停止，并核验整个操作及每条副作用；对账者字符串不是认证。普通 Lua 的未知副作用不能从成功返回推断。使用原命名空间、操作 ID 及前驱修订；存储恢复后精确重试同一证明可确认同一后继。返回修订用于显式删除。此 API 不查询外部系统、不重放回调、不制造中断执行结果，也不恢复失败写入者或执行栈。开发磁盘格式为第 4 版，拒绝未发布的第 1–3 版且不改写原文件；必须使用匹配的开发核心与 SDK 契约。

线类型位于 `luaskills.embedded_contract`：分开的 `Input*` 和 `Output*` 声明保留字段缺失与显式空值的区别，同时保留原生有符号／无符号 64 位范围内的精确整数。生成的 `EmbeddedNativeStatus` 也在包顶层导出。传输与回调泵使用这些生成的协议和副作用常量。详见随包分发的[离线契约及同步说明](src/luaskills/contracts/embedded/v1/README.md)；运行 `python scripts/generate_embedded_contract.py --check` 拒绝过期产物。wheel 和源码分发包均包含核心的精确 JSON 与 SHA-256，其中包括共享 JSON 向量，源码分发包另外包含生成器。

嵌入式请求接受对象键为字符串的内置 JSON 值。在原生提交前拒绝元组、自定义嵌套容器、键强制转换、循环、非有限数、越界整数和不成对 Unicode 代理。响应解码拒绝解码后重复键，保留负零、整数值浮点数、完整整数位和显式空值。畸形响应仍遵守传输的拥有型结果释放协议。此严格编码器作用于新嵌入式接口；旧 JSON FFI 的行为保持原样。

`EmbeddedTransport` 绑定五个传输入口及只读引导入口 `luaskills_ffi_embedded_describe_v1`。此接口要求使用导出这些符号的匹配核心；历史 0.5.7 发布资产不提供该接口。开发时使用匹配本地构建，并通过发布工作流验证已发布资产。

构造函数在分配传输前检查精确生成的核心版本、JSON／ABI 版本、描述版本、契约 SHA-256、必需命令及能力、进程内后端、操作系统和解释器指针位宽。原生加载器负责机器指令兼容。缺少引导符号或元数据不兼容时抛出 `EmbeddedCompatibilityError`；原生引导状态失败保留 `EmbeddedTransportError`。不回退旧核心。元数据按核心拥有的上限复制，全程保留动态库，绝不调用任何结果释放函数。`transport.core_description` 返回独立的生成类型 `OutputCoreDescription` 快照，包含构建输入证据。这些摘要描述选定源码及编译器输入，不认证二进制，也不替代发布产物校验；Rust 消费工作区可能采用不同于报告中包内锁文件的依赖图。

显式提供 `EmbeddedTransportConfig`，并使用既有 `library_path` 或 `runtime_root` 选择方式。`request(command)` 接收根命令并返回成功的 `result`，其中显式 JSON 空值返回 `None`。原生返回码通过带 `status` 的 `EmbeddedTransportError` 报告；已交付核心失败通过带 `code`、`message` 的 `EmbeddedRuntimeError` 报告。绑定保留身份全部 64 位；解码失败或 Python 在原生返回时抛出中断，仍会释放已返回结果。

请求可以并发执行。`close()` 永久请求关闭，同时保留核心查询及宿主确认访问。通过核心生命周期命令排空并移除每个运行时后，再调用 `free()`。原生释放失败后，传输仍可用于排空；析构器不会静默释放活动运行时或卸载动态库。结果释放显式失败时，精确描述符保持拥有状态，活动调用返回后可通过 `release_results()` 重试释放。

`EmbeddedResultReleaseError` 是传输错误子类，保留释放失败前已复制的不可变 `response_bytes`。`delivered_result()` 按正常成功／业务错误规则重新解码该副本，不发起原生工作，从而保留已经创建的运行时、池、会话或操作身份。释放恢复和交付恢复分开处理：通过 `release_results()` 重试释放内存，从保留回执恢复身份，绝不能推断应该重新提交变更。缺少或无效复制字节仍明确表示缺乏交付证据。

`EmbeddedCommandDriver(transport, EmbeddedDriverConfig(work_threads=..., max_work_commands=..., max_control_commands=...))` 提供拥有型异步 FFI 通道。`submit(command)` 冻结 JSON 并保留回执后立即返回 `EmbeddedCommand`，通过 `result(timeout=...)` 或 `await result_async()` 观察同一个实际命令。取消观察者、关闭其 asyncio 循环或等待超时均不取消原生执行。`driver.commands` 保留精确回执对象，可按驱动器局部 `command_id` 恢复；`request` 及成功结果均返回独立副本。只有交付实际返回且结果或失败已经处理后，才调用 `forget()`。已完成回执在遗忘前继续占用所属通道配额；遗忘回执绝不遗忘核心操作。

一个传输同时由一个驱动器拥有，工作与短控制具有独立执行器及回执配额，运行时构造无法占用 SDK 控制工作线程或其回执配额。所有权入场还为每个驱动器工作线程及回调泵控制工作线程预留相应原生结果槽和最坏 `max_response_bytes`。传输数量或聚合字节容量不足时，在发布所有者前拒绝；构造后不可重新赋值传输预算。直接底层请求及释放失败后保留的缓冲额外消耗原生容量，宿主仍须将其纳入容量／恢复策略。

驱动器 `request_close()` 封闭新命令并启动拥有型关闭；`close(timeout=...)` 和 `close_async()` 观察实际执行器汇合。超时或取消关闭观察仍保留该关闭过程。关闭驱动器不会关闭核心运行时或回调泵。取消／排空核心期间保持驱动器与泵可用，处理待完成回执，释放已关闭运行时，再关闭驱动器并释放传输。驱动器拒绝阻塞 `operation_wait`，应通过短 `operation_status` 查询保持原生工作线程可用。在实现受控依赖追踪前，宿主回调中的嵌套驱动器调用明确不受支持。

`EmbeddedClient(driver)` 使用生成输入输出类型，提供运行时、插件、池、会话及操作句柄。原生命令立即返回 `EmbeddedPending[T]`，通过 `result(timeout=...)` 或 `await result_async()` 观察；即使先前观察者被取消，两者仍观察同一命令。`pending.receipt` 暴露精确驱动器回执。处理交付后显式调用 `pending.forget()` 归还 SDK 配额。结果释放失败后可用 `pending.delivered_result()` 投影已复制成功响应，不重新提交；原生缓冲恢复仍须执行 `transport.release_results()`。

`runtime.register_capacity(plugin_id, config)` 返回待确认的 `EmbeddedCapacity`；`runtime.capacity(capacity_id)` 绑定已知精确身份。显式提供 `resources` 及聚合 `max_queued_calls`、`max_queued_bytes`。`capacity.register_pool(...)` 要求相同插件归属、池类别、成员最小值为零且上限不超过容量。成员共享聚合预留及入场额度，各自保留 Lua 状态、模块代次和能力快照；既有 `runtime.register_pool(...)` 保持独立归属。`status()`、`request_close()`、`forget()` 使用预留控制通道。关闭排空成员，必须逐个显式遗忘已关闭且排空的成员后才能遗忘容量；空容量仍保留最小预留，不代表自动预热了 VM。此开发功能要求匹配的 `capacity_groups_v1` 契约及原生库。

`policy()` 原子返回当前修订字符串、完整容量状态及 `pending_convergence`；`revise(expected_revision, config)` 使用该精确前驱和完整配置进行比较交换，返回新的字符串令牌。两项均走保留控制通道并返回可查询回执；令牌不得转成数值，SDK 不自动重试冲突。旧前驱或执行上限低于已分发操作数量返回 `busy`，不改变策略。常驻／队列缩容可保留超额实际占用并报告待收敛；固定会话保留原 VM 状态，常驻缩容会沿原清理路径退役可复用缓存。关闭后仍可查询但禁止修订；回执需显式遗忘。此开发接口要求匹配的 `capacity_policy_revisions_v1` 契约与原生库，尚未正式发布。

运行时反射注解使用 `typing.get_type_hints(method, localns=vars(luaskills.embedded_contract))`：导入的递归别名在支持的 Python 版本下需要其定义命名空间。静态类型检查直接使用生成声明；分发验证器同时检查实际 wheel 中的声明及上述显式解析的方法注解。

先用 `client.reserve()` 取得运行时句柄，再调用其单次 `initialize(engine_options, runtime_config)`。初始化回执确认的是尝试；始终查询 `status()` 区分 `ready`、`failed`、`faulted` 并读取保留错误。初始化观察中断后保留该身份并查询状态，不重新构造。`client.runtime(id)` 及运行时的 `plugin(id)`、`pool(id)`、`session(id)`、`operation(id)` 仅绑定已知身份，不探测、不声称就绪；后续原生命令校验存在性及归属。

`runtime.register_plugin(...)`、`register_pool(...)` 返回已确认句柄。`pool.submit(export, arguments, context, timeout_ms)` 和 `session.submit(...)` 返回操作句柄，其中 `timeout_ms` 是核心执行截止预算。`pool.open_session(timeout_ms)` 返回 `EmbeddedSessionOpen`，同时包含 `session` 和独立 `initialization` 操作；必须观察初始化操作，不能仅凭会话回执认定初始化成功。

运行时和容量句柄的 `register_pool(...)` 均接受仅关键字参数 `initialization_capabilities`。省略或 `None` 继承既有业务权威；`[]` 拒绝源码初始化中的全部已注册宿主回调；非空列表精确收窄已授权快照。缺失或未授权名称在注册前返回 `permission_denied`。冷初始化和预热使用同一不可变策略；业务及关闭导出保留普通授权，实时撤权仍然生效。修改名单须注册新执行域。此回调限制不是完整 Lua 沙箱。接口尚未发布，要求匹配的 `initialization_capability_policy_v1` 契约及原生库。

`pool.prewarm_instance(context, timeout_ms)` 返回 `EmbeddedPending[EmbeddedOperation]`，为明确可复用池初始化一个**额外** VM。它使用工作通道并保留原回执；独立观察所得操作，成功时读取 `value["instance_id"]`。预热不运行业务导出，但初始化仍可调用已授权宿主能力并产生副作用。满池请求以 `capacity_exceeded` 完成失败；单次／会话池在入场时拒绝。取消、持久化恢复及 `EmbeddedRuntimeScope` 清理继续保留真实回调归属。此原语不接受目标总数，也不保证永久驻留；空闲及压力策略继续生效。开发接口要求匹配的 `explicit_instance_prewarm_v1` 契约及原生库。

`pool.reusable_status()` 通过预留控制通道返回保留的待确认快照。`ready` 统计已确认可借用实例；`physical` 表示实际分配器占用，不能用来推算就绪。初始化、执行、未确认检查点及退役中的实例不可借用。运行时／池关闭或保留入场故障使就绪数归零。查询应用已声明空闲过期规则，不执行 Lua、不创建实例，快照也不预留未来容量。非复用池返回 `invalid_argument`，未知身份返回 `not_found`。观察后须显式遗忘待确认回执。此开发接口尚未发布，要求匹配的 `reusable_pool_readiness_v1` 契约及原生库。

`operation.wait(timeout=..., poll_interval=...)` 和 `await operation.wait_async(poll_interval=...)` 通过短状态命令轮询，返回包含失败及副作用证据的完整终态快照。同步超时及 `asyncio.wait_for` 仅影响观察。显式 `operation.cancel()` 请求协作取消，返回布尔值不代表完成。轮询自动消费成功的只读 SDK 回执，中断或失败的回执保留在 `driver.commands` 供恢复。`operation.forget()` 删除终态**核心记录**，其返回的待完成命令回执也须处理并遗忘。

运行时、插件、池和会话的 `request_close()` 返回关闭确认；执行 `free()` 或 `forget()` 前应核对实际原生状态。类型句柄借用驱动器。设置 `LUASKILLS_LIB` 与 `PYTHONPATH=src` 后，用 `-p test_embedded_client.py` 验证真实公共／专用池、固定会话状态、生命周期屏障及迟到提交回调。

`EmbeddedRuntimeScope(runtime, pump=existing_pump)` 拥有一个已知运行时及其精确可选泵的有序关闭。使用 `with scope as owner:` 或 `async with scope as owner:`，通过 `owner.runtime` 访问类型句柄。一个作用域只能进入一次，重复所有者被拒绝。不需要泵时可在初始化前接管预留运行时；需要回调时，先初始化并确认 `ready`，创建泵，再一起接管。接管后不能新增泵。作用域借用传输及驱动器，其他运行时仍可使用。

作用域构造在启动非守护协调线程前，额外预留一个原生控制槽及其最坏响应字节。`request_close()` 启动后台清理，`close(timeout=...)`、`close_async()` 负责观察。清理按关闭原生入场、保持回调泵运行并等待实际原生线程／VM 排空、汇合回调泵、移除精确槽位的顺序执行，驱动器回执配额耗尽不会阻塞这些控制。作用域不关闭共享传输及驱动器；接管期间拒绝独立类型 `runtime.free()`。上下文退出还会释放核心操作记录，需要保留的结果／副作用证据应在释放运行时前保存；持久副作用恢复仍是独立实施里程碑。

单次调用模块可在 `finalizer` 中声明已有 `export`、固定 `arguments` 及有限 `timeout_ms`。核心在自动关闭期间保留同一 VM 和原操作，分别保存 `finalization.business` 与 `finalization.outcome`。成功空值仍包含显式值；缺少关闭结果不证明回调从未执行。作用域关闭会保持回调交付，直到关闭函数结束；显式能力撤销仍生效。使用匹配的生成契约和核心二进制，存储恢复不重放关闭回调。

固定会话也支持此声明。开启前额外预留一个操作槽，同时计入运行时及插件保留上限；插件状态通过 `reserved_operations` 单独报告预留数量。已初始化会话关闭时消费预留，保留先前业务结果，并通过会话状态 `finalization_operation` 暴露独立关闭操作。该操作业务基线为成功空值、业务副作用数为零，实际关闭结果位于 `finalization` 的关闭结果字段。显式会话／池／插件／运行时关闭，以及业务失败或使用次数耗尽，都保留原 VM 直到关闭和真实退役结束。关闭预算在签发关闭执行时才开始。

可复用池也支持自动关闭。每个新 VM 在初始化前预留一个关闭操作槽，复用该 VM 不重复预留。空闲过期、压力驱逐、业务失败／使用额度耗尽及作用域关闭，均在业务结果发布后触发独立关闭操作。池／插件关闭排空已入场业务；显式运行时关闭仍取消业务。使用运行时 `list_operations`（线协议命令 `operation_list`），传入可选精确池过滤条件、仍保留的 `after_operation_id` 游标及显式正 `limit`，按发布顺序发现这些操作。其模块上下文包含 `finalization_instance_id`，池元数据移除后仍可查询结果。空页保留游标；遗忘游标后需要重新枚举。分页数量与响应字节仍受核心预算约束，发现不会执行回调，也不替代持久历史。

观察超时、取消或调用方循环关闭，均保持清理所有权，可通过 `scope.status` 查询。已交付结果的缓冲释放失败保留最后已证明检查点，通过 `retry_close(...)` 或 `retry_close_async()` 显式恢复保留传输缓冲并继续，不重复已确认变更。此共享传输恢复拒绝活动读取者。作用域根控制命令被原生容量拒绝时，也允许在容量恢复后显式重试。普通重复关闭仅观察同一次尝试。其他未获证明的失败保留所有权并报告 `retryable=False`，不授权重放或卸载。使用 `-p test_embedded_scope.py` 验证实际上下文退出、初始化失败、回调寿命及释放恢复。

作用域检查点要求响应携带精确 `runtime_id`，包括缓冲释放失败后的复制成功响应。状态查询还要求 `closed` 为布尔值，初始化状态属于生成契约。缺失、错配或畸形证据不能推进关闭，也不授权变更重放；未经证明的 Python 交付继续保留作用域，等待基础设施恢复。

`EmbeddedCallbackPump(transport, runtime_id, config)` 为已初始化运行时拥有队列 Python 回调。显式提供正数边界 `CallbackPumpConfig(max_concurrent_handlers=..., max_pending_commands=..., poll_interval_ms=...)`。一个传输上的同一运行时只能有一个事件泵；其队列能力须全部通过该泵注册，不得另行消费同一个核心请求队列。

| 接口 | 契约 |
| --- | --- |
| `HostCapability(descriptor, handler, mode)` | 使用精确队列核心描述符；`mode` 显式选择 `sync` 或 `async`。事件泵复制描述符并保留实际处理器。 |
| `register(...)` / `register_async(...)` | 原子发布一个批次并返回不可变注册身份。同名替换不会重定向既有请求。 |
| `unregister(id, timeout=...)` / `unregister_async(id)` | 停止新分发并等待实际处理器排空。仅注销不会取消已分发处理器。 |
| `request_close()` / `close(timeout=...)` / `close_async()` | 退役全部处理器；实际关闭等待回调、确认及拥有线程。超时或观察者取消仍保留所有权。 |
| `status` / `recovery_required` / `retry_acknowledgements(timeout=...)` | 暴露保留身份及当前恢复需求。恢复原始控制回执及失败完成确认，不重复业务处理器。 |

事件泵在进入原生前保留一条精确控制变更。注册、队列提取、注销及遗忘的交付不确定期间，不能再次提交这些变更。`status["pending_native_command"]` 标识保留命令；`recovery_required` 不包含普通在途工作，并与历史 `failure` 诊断分离。显式恢复释放保留缓冲、应用原复制回执，并通过精确核心副作用证据核对失败完成。原交付缺失或无效时仍报告错误并保留所有权；确认解决前须保留原操作的副作用记录。

事件泵消费查询证据前，要求其中携带精确请求、操作或注册身份。请求阶段来自生成契约，注册排空必须为布尔标记。身份错配的完成状态不能丢弃待确认请求。

普通已提交命令继续受 `max_pending_commands` 限制；额外预留一个共享恢复尝试，避免注销等待者耗尽恢复入口。所有路径仍使用同一个预留原生控制线程。并发恢复观察者共享该尝试，观察超时不会提前释放容量。`EmbeddedRuntimeScope` 将回调恢复需求报告为可重试排空失败，避免无限等待；`retry_close(...)` 显式恢复事件泵，再沿同一关闭检查点继续。正常存活处理器仍等待实际返回。

处理器接收 `(arguments, context)`，返回普通 JSON 值，包含 `None`。`context.caller`、`request_id`、`registration_id` 独立于应用参数携带可信核心身份。取消是协作式的：使用 `raise_if_cancelled()`、`wait_cancelled(timeout)` 或 `await wait_cancelled_async()`；需要取消执行时显式取消原操作。`remaining_ms` 仅供参考。变更处理器通过 `context.report_effects(...)` 报告真实副作用，默认值为 `unknown`；成功或取消均不隐含提交／回滚。异常、非法 JSON 及超大结果仍保留最近的副作用报告。完成帧被原生请求解析器明确拒绝时，转换为携带相同副作用的有界回调失败；已返回原生结果的释放失败不能授权改写该完成结果。

同步处理器在有界工作线程运行。异步处理器在事件泵的独立循环运行，必须使用为该循环创建的资源；不得阻塞该循环、在自身副作用完成前返回，或在回调内等待同一个泵排空。取消调用方 asyncio 任务或关闭其循环，不会取消拥有型处理器及注销任务。运行时取消后，保持事件泵存活直至实际处理器完成，关闭事件泵后再释放原生运行时和传输。确认恢复无法建立精确完成证据时，应保留原操作记录并解决已报告错误，不得遗忘该证据或卸载动态库。

底层传输仍允许并发调用。阻塞原生等待不能占满全部传输入场名额；必须为回调泵和控制操作保留容量。事件泵自身仅使用短控制请求，不发出 `operation_wait`。

原生集成验证位于 `tests/test_embedded_native_e2e.py`。设置 `PYTHONPATH=src`，并以 `LUASKILLS_LIB` 选择匹配开发动态库后，运行 `rtk proxy python -m unittest discover -s tests -p test_embedded_native_e2e.py -v`。测试覆盖实际 Lua 状态、结构化值、取消、并发控制及迟到提交回调结果。

将同一命令的测试模式改为 `-p test_embedded_pump.py`，可验证实际同步／异步回调寿命、有界入场、调用方循环取消、迟到副作用及确认丢失恢复。保持上述环境变量，使用 `rtk proxy python -m unittest discover -s tests -v` 运行 SDK 完整回归。

使用 `-p test_embedded_driver.py` 还可验证独立控制容量、冻结回执、取消循环恢复、实际工作线程汇合所有权，以及原生缓冲释放失败后的真实 Lua 操作身份恢复。

事件泵同步观察等待超时在所有支持版本（包含 Python 3.10）均抛出内置 `TimeoutError`。超时保留底层命令和回调所有权。异步观察者取消继续遵守前述拥有循环规则。

## 迁移说明

- 现有 `client.system(authority)` 生命周期调用保持兼容；返回的 wrapper 现在额外暴露查询辅助方法和 `runtime_leases()`。
- `RuntimeLeaseHandle` 会持久化 `lease_id + sid + generation`，并在 `eval`、`status`、`close` 时自动补回身份护栏。
- `client.system(authority).runtime_leases()` 依赖最新原生库提供的专用 `luaskills_ffi_system_runtime_lease_*` 导出；如果这组导出缺失，会立即报错而不是静默降级。
- 当宿主在 `request_context.client_capabilities.host_result` 中显式开启结构化结果后，`call_skill()` 会返回独立的 `host_result` 字段，供 IDE 原生结构化结果消费。
- 当 `host_result["kind"] == "change_set"` 时，宿主应把 `payload` 按 `RuntimeChangeSetPayload` 解析。
- canonical `change_set` 现在使用文件生命周期记录；`modify` 通过 hunk 级 `before + delete[] + insert[] + after` 表达具体修改。
- `create` 与 `delete` 文件记录直接携带整文件 `content`，`rename` 记录携带 `old_path` 与 `new_path`。
- 普通租约支持 `cwd`、`workspace_root`、`lua_roots`、`c_roots`、`mounts`。System 租约强制要求 `system_package`，拒绝 `lua_roots/c_roots`，并从可信包清单推导根目录。
- `poll_managed_session_events()`、`wait_managed_session_events()`、`set_managed_session_wake_callback()` 暴露 0.5.1 事件接口。

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

skill config 归属于有效技能包，而不是包内单个入口。宿主必须把 `host_options["skill_config_root"]` 设置为绝对用户级目录；普通技能包与 ROOT 所属技能包分别保存到 `skills/config.json` 和 `system-skills/config.json`。每条原始 `list()` 记录都包含 `store_scope`，因此两个文件中同名技能包的保留记录仍可明确区分。旧的无版本配置文档会被拒绝。

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
events = client.config.poll_events(limit=100)
```

`describe()` 返回名称、类型、约束、UI 提示、技能包作者说明、枚举选项、默认值与无歧义值状态；`mode="installed"` 可在不执行 Lua 的情况下发现物理技能包。写入仅允许已声明 key，必须通过声明约束和技能包校验器，并按单个技能包批次原子提交。

默认不返回配置值。`include_values=True` 返回未遮罩有效值；SDK 与 LuaSkills 不负责授权或遮罩，宿主必须对读取和修改执行允许、拒绝、强制覆盖或用户授权策略。Lua 代码只能修改自身技能包，宿主 SDK 调用则有意不加跨包限制。

`expected_revision` 为写入与删除启用比较并交换。`poll_events`、`wait_for_events`、`watch_events` 提供有序的本地写入与外部重载事件。配置缺失时，应展示 `describe()` 结果，并要求用户或已授权 AI 工具提供声明中的参数。技能包卸载后配置仍会保留，显式清理由宿主负责。配置只有在 Lua skill 主动读取时才会影响行为；它不是运行时强制策略层。

对应 CLI：

```powershell
luaskills config describe my-skill --skill-config-root D:\user-config
luaskills config validate my-skill
luaskills config describe --installed --root-name ROOT
luaskills config set my-skill retry_count 3 --expected-revision 7
luaskills config set-batch my-skill '{"retry_count":4,"mode":"safe"}'
luaskills config refresh skills
luaskills config events --after-sequence 12 --limit 100
```

CLI 默认把 `--skill-config-root` 设为 `<runtime-root>/config`；嵌入 SDK 的宿主仍必须自行选择并传入绝对用户级目录。

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

发布版本以 `pyproject.toml` 的 `project.version` 为权威，`VERSION` 是必须一致的镜像。

如果要做生态统一发布，必须先发布 `LuaSkills/luaskills-packages`，再发布 `LuaSkills/luaskills`，确保本 SDK 默认安装器引用的 runtime 资产已经存在。

正式发布使用默认分支上的 **Python SDK release** 工作流。先将 `.github/workflows/sdk-release.yml` 提交至默认分支，再提供与事件及工作流定义相同的完整 `source_sha`，以及独立已发布核心的精确 `core_tag` 和 `core_commit`。SDK 版本唯一来源是 `pyproject.toml` 的 `project.version`，`VERSION` 必须作为镜像一致；核心标签必须与包内默认运行时资产标签匹配。`artifact-only` 仅验收，不发布。

在公共核心前置条件就绪前，使用本地精确产物验收入口：

```bash
python scripts/verify_embedded_native_distribution.py --wheel <exact-wheel> --sdist <exact-sdist> --library <frozen-library> --library-sha256 <sha256> --description <actual-description-json>
```

正式工作流从冻结核心检出调用公共 helper，验证精确 GitHub 核心发布及真实 Cargo registry 消费者。每个新 runner 通过公共 `github-only` 及 `toolchain-inputs` 门禁，从已认证核心发布记录派生精确 Rust/Cargo 工具链。只构建一对 wheel/sdist，强制 `twine check --strict`，在核心声明的全部平台及最低、当前受支持 Python 中独立安装验收相同字节，原生跳过不能通过。上传前再次执行完整公共门禁，Trusted Publishing 仅上传已测字节而不重建；恢复时先核验正式现有 wheel/sdist 实际字节相同，再仅上传缺少文件，未知状态或不同字节均失败。随后冷安装正式 PyPI 包并使用同一核心库回验。每次不同的 PyPI 发布必须使用新版本，已发布文件不能覆盖。

账号所有者必须配置 `production` environment，并将 PyPI `luaskills-sdk` 的 Trusted Publisher 绑定至 `LuaSkills/luaskills-sdk-python`、`sdk-release.yml` 及 `production`。本地测试尚未验证账号绑定及生产配置；工作流不使用 PAT 或账号登录。参见 [PyPI Trusted Publisher 配置](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)。

独立 `candidate-evidence` 作业在修改 registry 或公共 Release 前，将包、实际原生报告及日志、核心凭据冻结为已签名清单。artifact 名称由冻结核心 `sdk_recovery.py` 唯一权威产生，实际上传 ID 单独记录。主 `v{SDK_VERSION}` Release 仅保存该原始已签名文件集合。原轮次可在后续发布阶段失败，但所有必需候选门禁仍须实际成功；其原状态及 `artifact-only` 模式保持不变。

恢复时，从相同固定 SDK SHA 调度 `mode=recover`，明确提供 `candidate_run_id`、`candidate_run_attempt` 及 `candidate_artifact_id`。原凭据缺失、过期或变化时在上传前失败，不重建替代候选、不选择最新轮次。仅产物候选证明已测字节，不授权发布；只有当前明确的受保护 publish/recover 操作才可重新执行核心门禁、精确 PyPI 复用或部分上传、冷消费。主 Release 仅复用相同原字节，不替换或追加。新完成凭据绑定原清单、bundle、上传 ID、精确主 Release 和新消费者，发布到独立 `recovery-v{SDK_VERSION}-r{COMPLETION_RUN_ID}-a{COMPLETION_ATTEMPT}` Release。每个 Release 均先在草稿中上传全部资产，再正式发布。

`formal-proof` 除原 `--source-sha`、SDK 与核心身份、平台外，还必须明确提供 `--candidate-run-id`、`--candidate-run-attempt`、`--completion-run-id`、`--completion-run-attempt` 及 `--completion-source-sha`。它验证两份官方签名和精确轮次 API；指定完成轮次必须整体成功。初版要求完成源码与原 SDK 源码相等。Schema 2 `accepted.json` 保留两组身份，并在新完整核心 registry 门禁及冷 PyPI 原生消费后，绑定 `fresh-formal-consumer.json` 的实际摘要；没有含混 `--run-id` 别名。本地夹具只证明门禁逻辑，不能证明真实 OIDC 发布或全部托管平台通过。发布夹具仅从明确 `SDK_RELEASE_TEST_CORE_ROOT` 检出加载共享权威；设置该环境变量后执行 `python -X utf8 tests/test_sdk_release.py`。

推荐统一发布顺序：`luaskills-packages` -> `luaskills` 核心仓库 -> TypeScript SDK -> Python SDK -> Go SDK -> 各 SDK 的 examples release。

Python 必须先通过核心 GitHub 发布及真实 Cargo 消费前置条件；TypeScript 发布独立，并非 Python 门禁依赖。Go 安装器验收消费实际 TypeScript 和 Python 发布，各 SDK 保留独立版本及源码 SHA。

明确 SDK 完成轮次成功后，从相同默认分支固定 SDK SHA 手动调度 **Examples Release**，提供候选及完成双方 run ID、attempt、独立完成源码 SHA、精确 SDK 版本、核心标签及 SHA 和匹配核心平台。它认证两条持久签名链，冷安装带摘要的正式 PyPI 包，并使用记录的精确核心库执行嵌入示例；仅归档已跟踪示例，不包含安装环境及生成运行时文件。固定时间、排序且不压缩的 ZIP 成员及稳定包证明使 ZIP、摘要文件可跨重试复现；工作流还在公共修改前将精确文件上传为 artifact。独立 `examples-v{SDK_VERSION}` Release 先以草稿上传全部资产，再正式发布：

- `luaskills-sdk-python-examples-{VERSION}.zip`
- `luaskills-sdk-python-examples-{VERSION}.zip.sha256`

`examples-v` 前缀保留现有示例下载协议，并使示例资产与正式 SDK Release 分离。现有相同字节可复用，不同字节直接拒绝，不使用 `--clobber`。
