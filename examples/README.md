# LuaSkills Python SDK Examples

English documentation is the default example documentation. For Chinese, see [README_cn.md](README_cn.md).

Main LuaSkills repository: [LuaSkills/luaskills](https://github.com/LuaSkills/luaskills)

These examples use the published SDK package shape and are intended to be copied into host applications.

## Runtime Preparation

Install runtime assets before running examples:

```powershell
luaskills install-runtime --database none --runtime-root .\examples\fixture_runtime
```

If you already manage the native library yourself, set `LUASKILLS_LIB` instead:

```powershell
$env:LUASKILLS_LIB = "D:\runtime\luaskills\libs\luaskills.dll"
```

## Example Index

`basic.py` queries the JSON FFI version through `LuaSkillsClient.version`.

```powershell
python .\examples\basic.py
```

`query.py` loads the bundled USER-layer fixture skill, lists delegated-visible entries, checks `is_skill`, resolves `skill_name_for_tool`, and reads help/completion surfaces.

```powershell
python .\examples\query.py
```

`call.py` demonstrates `call_skill` and `run_lua` with an invocation context.

```powershell
python .\examples\call.py
```

`lifecycle.py` demonstrates `disable` and `enable` through the ordinary Skills plane.

```powershell
python .\examples\lifecycle.py
```

`provider_callback.py` registers a JSON SQLite provider callback before engine creation.

```powershell
python .\examples\provider_callback.py
```

## Wheel Examples

The wheel also ships module examples for quick smoke tests:

```powershell
python -m luaskills.examples.basic
python -m luaskills.examples.provider_callback
```

## Fixture Skill

The fixture skill is stored at `examples/fixture_runtime/user_skills/demo-standard-ffi-skill`. It intentionally lives in USER so delegated-query examples can see it without System authority.

## Release Package

The repository workflow **Examples Release** creates `luaskills-sdk-python-examples-{VERSION}.zip` after the matching PyPI package is published. The workflow installs `luaskills-sdk=={VERSION}` from PyPI and runs the examples before uploading the asset.

The release tag is `examples-v{VERSION}` so example assets stay separate from SDK package versions.
