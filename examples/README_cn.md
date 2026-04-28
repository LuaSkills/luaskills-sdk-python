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

`lifecycle.py` 演示通过普通 Skills plane 执行 `disable` 与 `enable`。

```powershell
python .\examples\lifecycle.py
```

`provider_callback.py` 演示在 engine 创建前注册 JSON SQLite provider callback。

```powershell
python .\examples\provider_callback.py
```

## Wheel 示例

wheel 也内置模块示例，便于快速烟测：

```powershell
python -m luaskills.examples.basic
python -m luaskills.examples.provider_callback
```

## Fixture Skill

夹具 skill 位于 `examples/fixture_runtime/user_skills/demo-standard-ffi-skill`。它故意放在 USER 层，这样委托查询示例不需要 System 权限也能看到它。

## 示例发布包

仓库工作流 **Examples Release** 会在匹配的 PyPI 包发布后生成 `luaskills-sdk-python-examples-{VERSION}.zip`。工作流会从 PyPI 安装 `luaskills-sdk=={VERSION}` 并运行示例，通过后再上传资产。

release tag 使用 `examples-v{VERSION}`，因此示例资产与 SDK 包版本保持分离。
