# LuaSkills Python SDK 示例

中文示例文档。英文默认文档见 [README.md](README.md)。

LuaSkills 主仓库：[LuaSkills/luaskills](https://github.com/LuaSkills/luaskills)

这些示例使用发布后的 SDK 包形态，适合复制到宿主应用中参考。

## Runtime 准备

运行示例前先安装 runtime 资产：

```powershell
luaskills install-runtime --database none --runtime-root .\examples\fixture_runtime
```

如果宿主自行管理原生动态库，也可以设置 `LUASKILLS_LIB`：

```powershell
$env:LUASKILLS_LIB = "D:\runtime\luaskills\libs\luaskills.dll"
```

## 示例索引

`basic.py` 通过 `LuaSkillsClient.version` 查询 JSON FFI 版本。

```powershell
python .\examples\basic.py
```

`query.py` 会加载内置 USER 层夹具 skill，列出委托工具可见入口，检查 `is_skill`，解析 `skill_name_for_tool`，并读取 help/completion 查询面。

```powershell
python .\examples\query.py
```

`call.py` 演示带调用上下文的 `call_skill` 与 `run_lua`。

```powershell
python .\examples\call.py
```

`host_tool_callback.py` 注册一个 mock `model.embed` 宿主工具 callback，并从内联 Lua 调用 `vulcan.host.list`、`vulcan.host.has` 与 `vulcan.host.call`。

```powershell
python .\examples\host_tool_callback.py
```

`lifecycle.py` 演示通过普通 Skills plane 执行 `disable` 与 `enable`。

```powershell
python .\examples\lifecycle.py
```

`runtime_lease.py` 演示一个持久运行时租约、绑定 authority 的 system 查询，以及复用同一个交互式子进程句柄的连续 `eval` 调用。

```powershell
python .\examples\runtime_lease.py
```

`provider_callback.py` 演示在 engine 创建前注册 JSON SQLite provider callback。

```powershell
python .\examples\provider_callback.py
```

模型 callback 对接见主 [SDK README](../README_cn.md#模型-callback)。通用示例不直接调用真实模型 provider，因为模型凭证、provider 选择、预算与脱敏策略都归宿主管理。

## Wheel 示例

`embedded_runtime.py` 使用真实 `EmbeddedClient`、`EmbeddedCallbackPump` 和 `EmbeddedRuntimeScope`，演示同步与 asyncio 调用、显式 VM 预热、可复用就绪查询及关闭函数回调。它要求显式匹配原生库，自动创建临时包布局，不下载 runtime 资产：

```powershell
python -m luaskills.examples.embedded_runtime --library D:\candidate\luaskills.dll --mode both
```

泵线程启动后构造被中断时，`transport.callback_pump(runtime_id)` 在现有所有权锁内返回该精确运行时的实际保留事件泵，返回类型为 `EmbeddedCallbackPump | None`。示例先关闭并汇合此所有者，再移除运行时。只读查询不创建或撤销所有者；`None` 不证明原生工作完成。预留观察取消时恢复原回执，不重新提交预留；交付未知时保留回执及原生所有权，并显式失败。

精确分发产物对冻结原生候选的本地验收使用独立原生门禁。描述文件是候选实际 `luaskills_ffi_embedded_describe_v1` 返回的 JSON 字节；SDK 复用既有生成契约校验，并要求与已加载原生库完整描述一致：

```powershell
python scripts/verify_embedded_native_distribution.py --wheel dist\luaskills_sdk-0.6.1-py3-none-any.whl --sdist dist\luaskills_sdk-0.6.1.tar.gz --library D:\candidate\luaskills.dll --library-sha256 <frozen-library-sha256> --description D:\candidate\core-description.json
```

wheel/sdist 名称必须使用本次构建的精确产物。门禁在缺库或身份错误时失败，执行既有离线分发校验；若本地已有 twine，额外执行 `twine check --strict`。它仅用本地已有构建工具重新构建选定 sdist，然后将两个 wheel 分别安装到独立 venv，排除用户 site 和源码目录导入。每个安装环境还执行真实启动拒绝、迟到启动中断、预留取消及未知交付回归；跳过原生测试不能通过此门禁。不会发布包或下载运行时。构建工具必须已满足 `pyproject.toml`，缺失本地后端时 sdist 构建失败。单平台通过不证明其它平台或正式发布库通过。

wheel 也内置模块示例，便于快速烟测：

```powershell
python -m luaskills.examples.basic
python -m luaskills.examples.host_tool_callback
python -m luaskills.examples.provider_callback
python -m luaskills.examples.runtime_lease
```

## Fixture Skill

夹具 skill 位于 `examples/fixture_runtime/user_skills/demo-standard-ffi-skill`。它故意放在 USER 层，这样委托查询示例不需要 System 权限也能看到它。

## 示例发布包

仓库工作流 **Examples Release** 在明确正式 SDK 完成轮次成功后生成 `luaskills-sdk-python-examples-{SDK_VERSION}.zip`。必须提供精确 SDK 源码 SHA、独立版本、核心标签及提交、候选及完成双方 run ID、attempt、完成源码 SHA 和匹配原生平台。工作流认证原已签名候选及独立成功完成凭据，冷安装带摘要的正式 PyPI 包，并使用记录的精确核心库执行 `embedded_runtime.py`。归档包含已跟踪示例、绑定已测 wheel 摘要的 requirements 及稳定 `PUBLICATION.json`，不包含虚拟环境或生成运行时文件。排序且不压缩的 ZIP 成员采用固定时间，跨重试生成相同归档及摘要字节；公共修改前还将精确字节上传为 artifact。

release tag 保持 `examples-v{SDK_VERSION}` 并指向相同固定 SDK 源码 SHA，先在草稿中上传全部资产，再正式发布。正式发布相同字节可复用，不同字节或追加资产直接失败；不会覆盖资产，也不会追加到正式 SDK Release。
