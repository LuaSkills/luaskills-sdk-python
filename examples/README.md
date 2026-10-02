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

`host_tool_callback.py` registers a mock `model.embed` host-tool callback and exercises `vulcan.host.list`, `vulcan.host.has`, and `vulcan.host.call` from inline Lua.

```powershell
python .\examples\host_tool_callback.py
```

`lifecycle.py` demonstrates `disable` and `enable` through the ordinary Skills plane.

```powershell
python .\examples\lifecycle.py
```

`runtime_lease.py` demonstrates one persistent runtime lease, authority-bound system queries, and repeated `eval` calls that reuse one interactive child-process handle.

```powershell
python .\examples\runtime_lease.py
```

`provider_callback.py` registers a JSON SQLite provider callback before engine creation.

```powershell
python .\examples\provider_callback.py
```

Model callback integration is documented in the main [SDK README](../README.md#model-callback). The generic examples do not call a real model provider because model credentials, provider choice, budgets, and redaction policy are host-owned.

## Wheel Examples

`embedded_runtime.py` uses the real `EmbeddedClient`, `EmbeddedCallbackPump` and `EmbeddedRuntimeScope` for synchronous and asyncio calls, explicit VM prewarming, reusable readiness and finalizer callbacks. It requires an explicit matching library and creates its own temporary package layout without downloading runtime assets:

```powershell
python -m luaskills.examples.embedded_runtime --library D:\candidate\luaskills.dll --mode both
```

If pump construction is interrupted after its thread starts, `transport.callback_pump(runtime_id)` returns the actual retained pump for that exact runtime under the existing ownership lock. Its return type is `EmbeddedCallbackPump | None`. The example closes and joins that owner before removing the runtime. This read-only query never creates or unclaims an owner; `None` does not prove native completion. Cancellation during reserve observation recovers the original receipt instead of submitting another reserve. Unknown delivery retains its receipt and native ownership with an explicit failure.

For local acceptance of exact distribution artifacts against a frozen native candidate, use the independent native gate. The description is the candidate's actual `luaskills_ffi_embedded_describe_v1` JSON bytes. The SDK validates its existing generated contract and requires full equality with the loaded library description:

```powershell
python scripts/verify_embedded_native_distribution.py --wheel dist\luaskills_sdk-0.6.0-py3-none-any.whl --sdist dist\luaskills_sdk-0.6.0.tar.gz --library D:\candidate\luaskills.dll --library-sha256 <frozen-library-sha256> --description D:\candidate\core-description.json
```

Select the exact wheel/sdist names from your build. The gate requires missing-library and identity errors to fail, runs the existing offline distribution checks, uses `twine check --strict` when already available, rebuilds only the selected sdist with locally installed build tools, and installs each wheel into a separate venv with user site and checkout imports disabled. Each installation also runs actual startup-refusal, late-start interruption, reserve-cancellation and unknown-delivery regressions; native skips cannot pass this gate. No package publication or runtime download occurs. Build tools must already satisfy `pyproject.toml`; an unavailable local backend fails the sdist build. Passing on one platform does not prove acceptance on other platforms or release libraries.

The wheel also ships module examples for quick smoke tests:

```powershell
python -m luaskills.examples.basic
python -m luaskills.examples.host_tool_callback
python -m luaskills.examples.provider_callback
python -m luaskills.examples.runtime_lease
```

## Fixture Skill

The fixture skill is stored at `examples/fixture_runtime/user_skills/demo-standard-ffi-skill`. It intentionally lives in USER so delegated-query examples can see it without System authority.

## Release Package

The repository workflow **Examples Release** creates `luaskills-sdk-python-examples-{SDK_VERSION}.zip` after the explicit formal SDK completion attempt succeeds. Supply exact SDK source SHA/version, independent core tag/commit, both candidate and completion run IDs/attempts, completion source SHA and matching native platform. It authenticates the original signed candidate and separate successful completion, cold-installs the hashed official PyPI package and runs `embedded_runtime.py` against the exact recorded core library. The archive contains tracked examples, requirements with the tested wheel hash and stable `PUBLICATION.json`; it excludes virtual environments and generated runtime files. Sorted stored ZIP members with fixed timestamps produce identical archive/sidecar bytes across retries; exact bytes are uploaded as an artifact before public mutation.

The release tag remains `examples-v{SDK_VERSION}`, pointing at the same fixed SDK source SHA. The workflow uploads every asset to a draft before publishing; final equal bytes may be reused, while different bytes or appending to a final release fail. It never overwrites assets or appends to the final SDK Release.
