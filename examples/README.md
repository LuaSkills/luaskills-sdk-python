# LuaSkills Python SDK Examples

These examples use the published SDK package shape and are intended to be copied into host applications.

这些示例使用发布后的 SDK 包形态，适合复制到宿主应用中参考。

## Runtime Preparation

Install runtime assets before running examples:

运行示例前先安装 runtime 资产：

```powershell
luaskills install-runtime --database none --runtime-root .\examples\fixture_runtime
```

If you already manage the native library yourself, set `LUASKILLS_LIB` instead:

如果宿主自行管理原生动态库，也可以设置 `LUASKILLS_LIB`：

```powershell
$env:LUASKILLS_LIB = "D:\runtime\luaskills\libs\luaskills.dll"
```

## Example Index

`basic.py` queries the JSON FFI version through `LuaSkillsClient.version`.

`basic.py` 通过 `LuaSkillsClient.version` 查询 JSON FFI 版本。

```powershell
python .\examples\basic.py
```

`query.py` loads the bundled USER-layer fixture skill, lists delegated-visible entries, checks `is_skill`, resolves `skill_name_for_tool`, and reads help/completion surfaces.

`query.py` 会加载内置 USER 层夹具 skill，列出委托工具可见入口，检查 `is_skill`，解析 `skill_name_for_tool`，并读取 help/completion 查询面。

```powershell
python .\examples\query.py
```

`call.py` demonstrates `call_skill` and `run_lua` with an invocation context.

`call.py` 演示带调用上下文的 `call_skill` 与 `run_lua`。

```powershell
python .\examples\call.py
```

`lifecycle.py` demonstrates `disable` and `enable` through the ordinary Skills plane.

`lifecycle.py` 演示通过普通 Skills plane 执行 `disable` 与 `enable`。

```powershell
python .\examples\lifecycle.py
```

`provider_callback.py` registers a JSON SQLite provider callback before engine creation.

`provider_callback.py` 演示在 engine 创建前注册 JSON SQLite provider callback。

```powershell
python .\examples\provider_callback.py
```

## Wheel Examples

The wheel also ships module examples for quick smoke tests:

wheel 也内置模块示例，便于快速烟测：

```powershell
python -m luaskills.examples.basic
python -m luaskills.examples.provider_callback
```

## Fixture Skill

The fixture skill is stored at `examples/fixture_runtime/user_skills/demo-standard-ffi-skill`. It intentionally lives in USER so delegated-query examples can see it without System authority.

夹具 skill 位于 `examples/fixture_runtime/user_skills/demo-standard-ffi-skill`。它故意放在 USER 层，这样委托查询示例不需要 System 权限也能看到它。
