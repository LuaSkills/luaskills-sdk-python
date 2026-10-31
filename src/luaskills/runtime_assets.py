"""
Runtime asset planning and installation helpers for the Python LuaSkills SDK.
Python LuaSkills SDK 的运行时资产规划与安装辅助工具。
"""

from __future__ import annotations

import hashlib
import copy
import json
import os
import platform
import base64
import re
import subprocess
import shutil
import stat
import tarfile
import tempfile
import urllib.request
import zipfile
from enum import Enum
from pathlib import Path, PureWindowsPath
from typing import Any, Callable, Iterator

from .roots import normalized_path

DEFAULT_LUASKILLS_VERSION = "v0.7.4"
"""
Default LuaSkills release tag used by SDK runtime installation.
SDK 运行时安装使用的默认 LuaSkills 发布标签。
"""

DEFAULT_LUASKILLS_PACKAGES_SERIES = "0.1"
"""
Default luaskills-packages release series used by SDK runtime installation.
SDK 运行时安装使用的默认 luaskills-packages 发布协议线。
"""




SHA256_HEX_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
"""
Strict SHA-256 hexadecimal digest pattern used for downloaded runtime assets.
下载运行时资产使用的严格 SHA-256 十六进制摘要模式。
"""

SHA512_BASE64_PATTERN = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")
"""
Strict SHA-512 Base64 digest pattern used for npm integrity strings.
npm integrity 字符串使用的严格 SHA-512 Base64 摘要模式。
"""

DEFAULT_MANAGED_PYTHON_VERSION = "3.14.6"
"""
Default managed CPython version installed for Lua-driven child runtimes.
Lua 调度子运行时安装使用的默认受管 CPython 版本。
"""

DEFAULT_MANAGED_UV_VERSION = "0.11.28"
"""
Default standalone uv version used to install managed Python environments.
安装受管 Python 环境使用的默认独立 uv 版本。
"""

DEFAULT_MANAGED_NODE_VERSION = "24.18.0"
"""
Default managed Node.js version installed for Lua-driven child runtimes.
Lua 调度子运行时安装使用的默认受管 Node.js 版本。
"""

DEFAULT_MANAGED_PNPM_VERSION = "11.11.0"
"""
Default pnpm version used to install managed Node.js dependencies.
安装受管 Node.js 依赖使用的默认 pnpm 版本。
"""

RUNTIME_MANIFEST_FILE_NAME = "luaskills-sdk-runtime-manifest.json"
"""
Manifest file name written into the runtime resources directory.
写入 runtime resources 目录的清单文件名。
"""


class RuntimeDatabasePreset(str, Enum):
    """
    Database integration preset selected by SDK users.
    SDK 用户选择的数据库集成预设。
    """

    NONE = "none"
    """
    Do not install or configure database providers.
    不安装也不配置数据库 provider。
    """



    HOST_CALLBACK = "host-callback"
    """
    Let the host provide SQLite JSON callbacks without installing database assets.
    由宿主提供 SQLite JSON 回调，不安装数据库资产。
    """


class ManagedRuntimeTarget(str, Enum):
    """
    Managed child runtime group selected by SDK installation.
    SDK 安装时选择的受管子运行时分组。
    """

    NONE = "none"
    """
    Do not install managed child runtimes.
    不安装受管子运行时。
    """

    ALL = "all"
    """
    Install Python, uv, Node.js, and pnpm.
    安装 Python、uv、Node.js 与 pnpm。
    """

    PYTHON = "python"
    """
    Install Python and uv.
    安装 Python 与 uv。
    """

    NODE = "node"
    """
    Install Node.js and pnpm.
    安装 Node.js 与 pnpm。
    """

    PACKAGE_MANAGERS = "package-managers"
    """
    Install uv and pnpm, including managed Node.js required by pnpm.
    安装 uv 与 pnpm，并包含 pnpm 所需的受管 Node.js。
    """


def resolve_runtime_platform_target(system: str | None = None, machine: str | None = None) -> dict[str, str]:
    """
    Return the runtime platform target for the current Python process.
    返回当前 Python 进程对应的运行时平台目标。
    """

    os_name = (system or platform.system()).lower()
    arch_name = normalize_arch(machine or platform.machine())
    if os_name == "windows" and arch_name == "x86_64":
        return {
            "platform_key": "windows-x64",
            "target_triple": "x86_64-pc-windows-msvc",
            "archive_ext": ".zip",
            "dynamic_library_ext": ".dll",
            "luaskills_library_name": "luaskills.dll",
        }
    if os_name == "darwin" and arch_name in {"x86_64", "aarch64"}:
        return darwin_target(arch_name, "macos-x64" if arch_name == "x86_64" else "macos-arm64")
    if os_name == "linux" and arch_name in {"x86_64", "aarch64"}:
        return linux_target(arch_name, "linux-x64" if arch_name == "x86_64" else "linux-arm64")
    raise ValueError(f"unsupported runtime platform: {os_name}/{arch_name}")


def build_runtime_install_manifest(
    *,
    runtime_root: str | os.PathLike[str],
    database: RuntimeDatabasePreset | str = RuntimeDatabasePreset.NONE,
    luaskills_version: str = DEFAULT_LUASKILLS_VERSION,
    lua_runtime_version: str | None = None,
    lua_runtime_series: str = DEFAULT_LUASKILLS_PACKAGES_SERIES,
    include_luaskills_ffi: bool = True,
    include_lua_runtime: bool = True,
    luaskills_repo: str = "LuaSkills/luaskills",
    lua_runtime_repo: str | None = None,
    managed_runtimes: ManagedRuntimeTarget | str = ManagedRuntimeTarget.NONE,
    managed_python_version: str = DEFAULT_MANAGED_PYTHON_VERSION,
    managed_uv_version: str = DEFAULT_MANAGED_UV_VERSION,
    managed_node_version: str = DEFAULT_MANAGED_NODE_VERSION,
    managed_pnpm_version: str = DEFAULT_MANAGED_PNPM_VERSION,
    force_managed_runtimes: bool = False,
) -> dict[str, Any]:
    """
    Build one deterministic runtime installation manifest.
    构造一个确定性的运行时安装清单。
    """

    resolved_root = Path(runtime_root).expanduser().resolve()
    preset = normalize_database_preset(database)
    target = resolve_runtime_platform_target()
    resolved_lua_runtime_version = lua_runtime_version or resolve_release_tag_for_series(
        lua_runtime_repo or "LuaSkills/luaskills-packages",
        lua_runtime_series,
    )
    assets = build_runtime_asset_descriptors(
        target=target,
        luaskills_version=luaskills_version,
        include_luaskills_ffi=include_luaskills_ffi,
        include_lua_runtime=include_lua_runtime,
        luaskills_repo=luaskills_repo,
        lua_runtime_repo=lua_runtime_repo or "LuaSkills/luaskills-packages",
        lua_runtime_version=resolved_lua_runtime_version,
    )
    return {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "runtime_root": normalized_path(resolved_root),
        "database_mode": preset.value,
        "platform": target,
        "assets": assets,
        "host_options_patch": build_host_options_patch(preset),
        "managed_runtimes": build_managed_runtime_install_plan(
            resolved_root,
            managed_runtimes,
            managed_python_version,
            managed_uv_version,
            managed_node_version,
            managed_pnpm_version,
        ),
    }


def install_runtime_assets(**options: Any) -> dict[str, Any]:
    """
    Install native runtime assets and write the shared manifest.
    安装原生运行时资产并写入共享清单。
    """

    manifest = build_runtime_install_manifest(**options)
    runtime_root = Path(manifest["runtime_root"])
    ensure_runtime_directories(runtime_root)
    with tempfile.TemporaryDirectory(prefix="luaskills-runtime-assets-") as temporary_root:
        for asset in manifest["assets"]:
            install_one_asset(runtime_root, asset, Path(temporary_root), manifest["platform"])
    if manifest.get("managed_runtimes"):
        install_managed_runtimes(runtime_root, manifest["managed_runtimes"], bool(options.get("force_managed_runtimes")))
    manifest["host_options_patch"] = build_host_options_patch(normalize_database_preset(manifest["database_mode"]))
    write_runtime_install_manifest(manifest)
    return manifest


def write_runtime_install_manifest(manifest: dict[str, Any]) -> Path:
    """
    Write one runtime install manifest into the runtime resources directory.
    将单个运行时安装清单写入 runtime resources 目录。
    """

    manifest_path = runtime_manifest_path(manifest["runtime_root"])
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def load_runtime_install_manifest(runtime_root: str | os.PathLike[str]) -> dict[str, Any] | None:
    """
    Load one runtime install manifest from the runtime resources directory.
    从 runtime resources 目录加载单个运行时安装清单。
    """

    manifest_path = runtime_manifest_path(runtime_root)
    if not manifest_path.exists():
        return None
    return decode_runtime_install_manifest(manifest_path, manifest_path.read_text(encoding="utf-8"))


def runtime_manifest_path(runtime_root: str | os.PathLike[str]) -> Path:
    """
    Return the absolute runtime manifest path for one runtime root.
    返回单个 runtime root 对应的绝对运行时清单路径。
    """

    return Path(runtime_root).expanduser().resolve() / "resources" / RUNTIME_MANIFEST_FILE_NAME


def decode_runtime_install_manifest(manifest_path: Path, raw: str) -> dict[str, Any]:
    """
    Decode one runtime install manifest with path-aware diagnostics.
    使用带路径上下文的诊断解码单个运行时安装清单。
    """

    if not raw.strip():
        raise ValueError(f"runtime install manifest {manifest_path} is empty")
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"runtime install manifest {manifest_path} is invalid JSON: {error}") from error
    if not isinstance(manifest, dict):
        raise ValueError(f"runtime install manifest {manifest_path} must be one JSON object")
    return manifest


def host_options_from_runtime_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """
    Convert one runtime manifest into host option overrides.
    将单个运行时清单转换为宿主选项覆盖。
    """

    runtime_root = manifest.get("runtime_root")
    if not isinstance(runtime_root, str) or not runtime_root.strip():
        raise ValueError("runtime manifest runtime_root must be a string path")
    return sanitize_runtime_manifest_host_options(Path(runtime_root), manifest.get("host_options_patch") or {})


def sanitize_runtime_manifest_host_options(runtime_root: Path, patch: object) -> dict[str, Any]:
    """
    Validate a manifest patch for runtime_root and return an independent host-options map.
    校验 runtime_root 的清单补丁并返回独立宿主选项映射。
    Reject retired database fields explicitly so old installations cannot restore bundled providers.
    显式拒绝退役数据库字段，防止旧安装恢复捆绑提供方。
    """
    if not isinstance(patch, dict):
        raise ValueError("host_options_patch must be one object")
    for key in ("sqlite_library_path", "sqlite_provider_mode", "lancedb_library_path", "lancedb_provider_mode", "lancedb_callback_mode", "space_controller"):
        if key in patch:
            raise ValueError(f"host_options_patch.{key} was removed in 0.7.3; register SQLite with the host")
    return dict(patch)




def resolve_luaskills_library_path_from_runtime(runtime_root: str | os.PathLike[str], target: dict[str, str] | None = None) -> Path | None:
    """
    Resolve an installed LuaSkills dynamic library from one runtime root.
    从单个 runtime root 解析已安装的 LuaSkills 动态库。
    """

    resolved_target = target or resolve_runtime_platform_target()
    libs_dir = Path(runtime_root).expanduser().resolve() / "libs"
    for candidate in luaskills_library_candidates(resolved_target):
        candidate_path = libs_dir / candidate
        if candidate_path.exists():
            return candidate_path
    return None


def normalize_database_preset(value: RuntimeDatabasePreset | str) -> RuntimeDatabasePreset:
    """
    Normalize one database preset string.
    归一化单个数据库预设字符串。
    """

    try:
        return value if isinstance(value, RuntimeDatabasePreset) else RuntimeDatabasePreset(value)
    except ValueError as error:
        raise ValueError(f"unsupported database preset: {value}") from error


def normalize_managed_runtime_target(value: ManagedRuntimeTarget | str | None) -> ManagedRuntimeTarget:
    """
    Normalize one managed runtime target string.
    归一化单个受管运行时目标字符串。
    """

    try:
        return value if isinstance(value, ManagedRuntimeTarget) else ManagedRuntimeTarget(value or ManagedRuntimeTarget.NONE.value)
    except ValueError as error:
        raise ValueError(f"unsupported managed runtime target: {value}") from error


def resolve_managed_runtime_platform_target(system: str | None = None, machine: str | None = None) -> dict[str, str]:
    """
    Return the managed runtime platform target for the current Python process.
    返回当前 Python 进程对应的受管运行时平台目标。
    """

    os_name = (system or platform.system()).lower()
    arch_name = normalize_arch(machine or platform.machine())
    if os_name == "windows" and arch_name == "x86_64":
        return {
            "platform_key": "windows-x64",
            "uv_asset_name": "uv-x86_64-pc-windows-msvc.zip",
            "node_asset_template": "node-v{version}-win-x64.zip",
            "node_extract_template": "node-v{version}-win-x64",
            "uv_executable": "uv.exe",
            "node_executable": "node.exe",
        }
    if os_name == "darwin" and arch_name in {"x86_64", "aarch64"}:
        node_arch = "x64" if arch_name == "x86_64" else "arm64"
        platform_key = "macos-x64" if arch_name == "x86_64" else "macos-arm64"
        return managed_unix_target(platform_key, arch_name, node_arch, "darwin", ".tar.gz")
    if os_name == "linux" and arch_name in {"x86_64", "aarch64"}:
        node_arch = "x64" if arch_name == "x86_64" else "arm64"
        platform_key = "linux-x64" if arch_name == "x86_64" else "linux-arm64"
        return managed_unix_target(platform_key, arch_name, node_arch, "linux", ".tar.xz")
    raise ValueError(f"unsupported managed runtime platform: {os_name}/{arch_name}")


def build_managed_runtime_install_plan(
    runtime_root: Path,
    target: ManagedRuntimeTarget | str,
    python_version: str,
    uv_version: str,
    node_version: str,
    pnpm_version: str,
) -> dict[str, Any] | None:
    """
    Build one managed runtime installation plan for the SDK manifest.
    为 SDK 清单构造一个受管运行时安装计划。
    """

    normalized_target = normalize_managed_runtime_target(target)
    if normalized_target == ManagedRuntimeTarget.NONE:
        return None
    managed_platform = resolve_managed_runtime_platform_target()
    return {
        "target": normalized_target.value,
        "platform": managed_platform,
        "python_version": python_version,
        "uv_version": uv_version,
        "node_version": node_version,
        "pnpm_version": pnpm_version,
        "installed_paths": managed_runtime_installed_paths(runtime_root, managed_platform, python_version, uv_version, node_version, pnpm_version),
    }


def managed_unix_target(platform_key: str, rust_arch: str, node_arch: str, node_os: str, node_archive_ext: str) -> dict[str, str]:
    """
    Build one Unix-like managed runtime target descriptor.
    构造一个类 Unix 受管运行时目标描述。
    """

    uv_os = "apple-darwin" if node_os == "darwin" else "unknown-linux-gnu"
    return {
        "platform_key": platform_key,
        "uv_asset_name": f"uv-{rust_arch}-{uv_os}.tar.gz",
        "node_asset_template": f"node-v{{version}}-{node_os}-{node_arch}{node_archive_ext}",
        "node_extract_template": f"node-v{{version}}-{node_os}-{node_arch}",
        "uv_executable": "uv",
        "node_executable": "bin/node",
    }


def normalize_arch(value: str) -> str:
    """
    Normalize one architecture string to release asset naming.
    将单个架构字符串归一化为发布资产命名。
    """

    lowered = value.lower()
    if lowered in {"x86_64", "amd64", "x64"}:
        return "x86_64"
    if lowered in {"aarch64", "arm64"}:
        return "aarch64"
    raise ValueError(f"unsupported architecture: {value}")


def darwin_target(arch_name: str, platform_key: str) -> dict[str, str]:
    """
    Build one macOS runtime platform descriptor.
    构造单个 macOS 运行时平台描述。
    """

    return {
        "platform_key": platform_key,
        "target_triple": f"{arch_name}-apple-darwin",
        "archive_ext": ".tar.gz",
        "dynamic_library_ext": ".dylib",
        "luaskills_library_name": "libluaskills.dylib",
    }


def linux_target(arch_name: str, platform_key: str) -> dict[str, str]:
    """
    Build one Linux runtime platform descriptor.
    构造单个 Linux 运行时平台描述。
    """

    return {
        "platform_key": platform_key,
        "target_triple": f"{arch_name}-unknown-linux-gnu",
        "archive_ext": ".tar.gz",
        "dynamic_library_ext": ".so",
        "luaskills_library_name": "libluaskills.so",
    }


def build_runtime_asset_descriptors(
    *,
    target: dict[str, str],
    luaskills_version: str,
    include_luaskills_ffi: bool,
    include_lua_runtime: bool,
    luaskills_repo: str,
    lua_runtime_repo: str,
    lua_runtime_version: str,
) -> list[dict[str, Any]]:
    """
    Build every asset descriptor required by one manifest.
    构造单个清单所需的全部资产描述。
    """

    assets: list[dict[str, Any]] = []
    if include_lua_runtime:
        asset_name = f"lua-runtime-packages-{target['platform_key']}.tar.gz"
        assets.append(release_asset("lua_runtime", lua_runtime_repo, lua_runtime_version, asset_name, "resources/lua-runtime-manifest.json"))
    if include_luaskills_ffi:
        asset_name = f"luaskills-ffi-sdk-{target['platform_key']}.tar.gz"
        assets.append(release_asset("luaskills_ffi", luaskills_repo, luaskills_version, asset_name, f"libs/{target['luaskills_library_name']}"))
    return assets


def release_asset(role: str, repository: str, version: str, asset_name: str, installed_path: str | None) -> dict[str, Any]:
    """
    Build one release asset descriptor from exact naming inputs.
    从精确命名输入构造单个发布资产描述。
    """

    base_url = f"https://github.com/{repository}/releases/download/{version}/{asset_name}"
    return {
        "role": role,
        "repository": repository,
        "version": version,
        "asset_name": asset_name,
        "sha256_asset_name": f"{asset_name}.sha256",
        "download_url": base_url,
        "sha256_url": f"{base_url}.sha256",
        "installed_path": installed_path,
    }


def resolve_release_tag_for_series(repository: str, series: str) -> str:
    """
    Resolve the newest published release tag inside one semantic-version series.
    解析单个语义化版本协议线中的最新已发布标签。
    """

    try:
        major_text, minor_text = series.split(".", 1)
        major = int(major_text)
        minor = int(minor_text)
    except ValueError as error:
        raise ValueError(f"invalid release series: {series}") from error
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/releases?per_page=100",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "luaskills-sdk-python",
        },
    )
    with urllib.request.urlopen(request) as response:
        releases = json.loads(response.read().decode("utf-8"))
    candidates: list[tuple[int, str]] = []
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        parsed = parse_release_semver(str(release.get("tag_name") or ""))
        if parsed is None:
            continue
        parsed_major, parsed_minor, parsed_patch = parsed
        if parsed_major == major and parsed_minor == minor:
            candidates.append((parsed_patch, str(release["tag_name"])))
    if not candidates:
        raise ValueError(f"no published release found in series {series} for {repository}")
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def parse_release_semver(tag: str) -> tuple[int, int, int] | None:
    """
    Parse one release tag into a semantic-version tuple when supported.
    将单个发布标签解析为受支持的语义化版本元组。
    """

    normalized = tag[1:] if tag.startswith("v") else tag
    parts = normalized.split(".")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None


def build_host_options_patch(database: RuntimeDatabasePreset) -> dict[str, Any]:
    """
    Return SQLite transport options for the selected host registration preset.
    返回所选宿主注册预设的 SQLite 传输选项。
    Database files and provider lifetime remain owned by the host; no assets are installed.
    数据库文件及提供方生命周期由宿主拥有；不安装数据库资产。
    """
    if database == RuntimeDatabasePreset.HOST_CALLBACK:
        return {"sqlite_callback_mode": "json"}
    return {}


def luaskills_library_candidates(target: dict[str, str]) -> list[str]:
    """
    Return candidate LuaSkills dynamic library names for one platform.
    返回单个平台对应的 LuaSkills 动态库候选名称。
    """

    names = [target["luaskills_library_name"]]
    dynamic_ext = target["dynamic_library_ext"]
    if dynamic_ext == ".dll":
        names.append("libluaskills.dll")
    elif dynamic_ext == ".dylib":
        names.append("luaskills.dylib")
    else:
        names.append("luaskills.so")
    return list(dict.fromkeys(names))


def resolve_installed_asset(runtime_root: Path, assets: list[dict[str, Any]], role: str) -> str | None:
    """
    Resolve the absolute path for one installed asset role.
    解析单个已安装资产角色对应的绝对路径。
    """

    for asset in assets:
        if asset["role"] == role and asset.get("installed_path"):
            return normalized_path(runtime_root / asset["installed_path"])
    return None


def ensure_runtime_directories(runtime_root: Path) -> None:
    """
    Ensure runtime directories used by SDK-managed assets exist.
    确保 SDK 管理资产使用的 runtime 目录存在。
    """

    for directory_name in ["bin", "libs", "include", "lua_packages", "licenses", "resources", "dependencies"]:
        (runtime_root / directory_name).mkdir(parents=True, exist_ok=True)


def resolve_managed_runtime_installed_path(runtime_root: Path, plan: dict[str, Any], runtime_name: str) -> Path:
    """
    Resolve one managed runtime installation path inside the runtime root.
    在 runtime root 内解析单个受管运行时安装路径。
    """

    installed_paths = plan.get("installed_paths")
    if not isinstance(installed_paths, dict):
        raise ValueError("managed runtime installed_paths must be one object")
    path_value = installed_paths.get(runtime_name)
    return resolve_managed_runtime_child_path(runtime_root, path_value, f"managed runtime installed path for {runtime_name}")


def resolve_managed_runtime_child_path(root: Path, path_value: object, context: str) -> Path:
    """
    Resolve one relative child path and reject paths outside the root.
    解析单个相对子路径，并拒绝 root 外部路径。
    """

    if not isinstance(path_value, str):
        raise ValueError(f"{context} must be a string")
    if not path_value or "\x00" in path_value or Path(path_value).is_absolute() or PureWindowsPath(path_value).is_absolute():
        raise ValueError(f"{context} must be a relative path inside its root")
    normalized_segments = path_value.replace("\\", "/").split("/")
    if any(segment in {"", ".", ".."} for segment in normalized_segments):
        raise ValueError(f"{context} must be a relative path inside its root")
    resolved_root = root.resolve()
    unresolved_child = resolved_root / path_value
    resolved_child = unresolved_child.resolve()
    if resolved_child == resolved_root or resolved_root not in resolved_child.parents:
        raise ValueError(f"{context} escapes its root: {path_value}")
    return resolved_child


def install_managed_runtimes(runtime_root: Path, plan: dict[str, Any], force: bool = False) -> None:
    """
    Install every managed child runtime selected by one plan.
    安装一个计划选择的全部受管子运行时。
    """

    target = normalize_managed_runtime_target(plan.get("target"))
    if target in {ManagedRuntimeTarget.ALL, ManagedRuntimeTarget.PYTHON}:
        install_managed_python_runtime(runtime_root, plan, force)
    if target in {ManagedRuntimeTarget.ALL, ManagedRuntimeTarget.NODE}:
        install_managed_node_runtime(runtime_root, plan, force)
        install_managed_pnpm_runtime(runtime_root, plan, force)
    if target == ManagedRuntimeTarget.PACKAGE_MANAGERS:
        install_managed_uv_runtime(runtime_root, plan, force)
        install_managed_node_runtime(runtime_root, plan, force)
        install_managed_pnpm_runtime(runtime_root, plan, force)


def install_managed_uv_runtime(runtime_root: Path, plan: dict[str, Any], force: bool) -> Path:
    """
    Install one managed uv executable.
    安装一个受管 uv 可执行文件。
    """

    uv_target = resolve_managed_runtime_installed_path(runtime_root, plan, "uv")
    uv_executable = resolve_managed_runtime_child_path(uv_target, plan["platform"]["uv_executable"], "managed uv executable")
    if uv_executable.exists() and not force:
        return uv_executable
    if force and uv_target.exists():
        shutil.rmtree(uv_target)
    asset_name = plan["platform"]["uv_asset_name"]
    asset_url = f"https://github.com/astral-sh/uv/releases/download/{plan['uv_version']}/{asset_name}"
    with tempfile.TemporaryDirectory(prefix="luaskills-managed-uv-") as temporary_text:
        temporary_root = Path(temporary_text)
        archive_path = temporary_root / asset_name
        checksum_path = temporary_root / f"{asset_name}.sha256"
        extract_directory = temporary_root / "extract"
        urllib.request.urlretrieve(asset_url, archive_path)
        urllib.request.urlretrieve(f"{asset_url}.sha256", checksum_path)
        verify_sha256(archive_path, checksum_path.read_text(encoding="utf-8"))
        extract_archive(archive_path, extract_directory)
        executable_name = "uv.exe" if platform.system().lower() == "windows" else "uv"
        extracted_uv = find_file(extract_directory, lambda name: name == executable_name)
        if extracted_uv is None:
            raise FileNotFoundError(f"uv executable was not found in {asset_name}")
        uv_target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(extracted_uv, uv_executable)
        uv_executable.chmod(0o755)
    write_managed_runtime_manifest(
        uv_target,
        {
            "schema_version": 1,
            "runtime": "uv",
            "version": plan["uv_version"],
            "platform": plan["platform"]["platform_key"],
            "executable": plan["platform"]["uv_executable"],
            "source": asset_url,
        },
    )
    run_process([str(uv_executable), "--version"])
    return uv_executable


def install_managed_python_runtime(runtime_root: Path, plan: dict[str, Any], force: bool) -> None:
    """
    Install one managed CPython runtime through managed uv.
    通过受管 uv 安装一个受管 CPython 运行时。
    """

    uv_executable = install_managed_uv_runtime(runtime_root, plan, force)
    python_root = resolve_managed_runtime_installed_path(runtime_root, plan, "python")
    if (python_root / "runtime-manifest.json").exists() and not force:
        return
    if force and python_root.exists():
        shutil.rmtree(python_root)
    python_root.mkdir(parents=True, exist_ok=True)
    install_command = [str(uv_executable), "python", "install", plan["python_version"]]
    if force:
        install_command.append("--reinstall")
    run_process(install_command, env={"UV_PYTHON_INSTALL_DIR": str(python_root)})
    python_executable_text = run_process_capture([str(uv_executable), "python", "find", plan["python_version"]], env={"UV_PYTHON_INSTALL_DIR": str(python_root)})
    python_executable = Path(python_executable_text.strip().splitlines()[0])
    if not python_executable.exists():
        raise FileNotFoundError(f"uv installed Python {plan['python_version']} but no interpreter path could be resolved")
    write_managed_runtime_manifest(
        python_root,
        {
            "schema_version": 1,
            "runtime": "python",
            "version": plan["python_version"],
            "platform": plan["platform"]["platform_key"],
            "executable": str(python_executable.resolve().relative_to(python_root.resolve())).replace("\\", "/"),
            "source": "uv-managed-python",
            "package_manager": "uv",
            "package_manager_version": plan["uv_version"],
        },
    )
    run_process([str(python_executable), "--version"])


def install_managed_node_runtime(runtime_root: Path, plan: dict[str, Any], force: bool) -> Path:
    """
    Install one managed Node.js archive.
    安装一个受管 Node.js 归档。
    """

    node_target = resolve_managed_runtime_installed_path(runtime_root, plan, "node")
    node_executable = resolve_managed_runtime_child_path(node_target, plan["platform"]["node_executable"], "managed Node.js executable")
    if node_executable.exists() and not force:
        return node_executable
    if force and node_target.exists():
        shutil.rmtree(node_target)
    asset_name = render_version_template(plan["platform"]["node_asset_template"], plan["node_version"])
    extract_name = render_version_template(plan["platform"]["node_extract_template"], plan["node_version"])
    base_url = f"https://nodejs.org/dist/v{plan['node_version']}"
    asset_url = f"{base_url}/{asset_name}"
    with tempfile.TemporaryDirectory(prefix="luaskills-managed-node-") as temporary_text:
        temporary_root = Path(temporary_text)
        archive_path = temporary_root / asset_name
        shasums_path = temporary_root / "SHASUMS256.txt"
        extract_directory = temporary_root / "extract"
        urllib.request.urlretrieve(asset_url, archive_path)
        urllib.request.urlretrieve(f"{base_url}/SHASUMS256.txt", shasums_path)
        verify_named_sha256(archive_path, shasums_path.read_text(encoding="utf-8"), asset_name)
        extract_archive(archive_path, extract_directory)
        extracted_root = extract_directory / extract_name
        if not extracted_root.exists():
            raise FileNotFoundError(f"Node archive root '{extract_name}' was not found in {asset_name}")
        node_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(extracted_root, node_target, dirs_exist_ok=True)
    write_managed_runtime_manifest(
        node_target,
        {
            "schema_version": 1,
            "runtime": "node",
            "version": plan["node_version"],
            "platform": plan["platform"]["platform_key"],
            "executable": plan["platform"]["node_executable"],
            "source": asset_url,
        },
    )
    run_process([str(node_executable), "--version"])
    return node_executable


def install_managed_pnpm_runtime(runtime_root: Path, plan: dict[str, Any], force: bool) -> None:
    """
    Install one managed pnpm package without changing global npm state.
    安装一个受管 pnpm 包，且不修改全局 npm 状态。
    """

    node_executable = install_managed_node_runtime(runtime_root, plan, force)
    pnpm_target = resolve_managed_runtime_installed_path(runtime_root, plan, "pnpm")
    pnpm_entry = pnpm_target / "bin" / "pnpm.cjs"
    if pnpm_entry.exists() and not force:
        return
    if force and pnpm_target.exists():
        shutil.rmtree(pnpm_target)
    metadata = json.loads(download_text(f"https://registry.npmjs.org/pnpm/{plan['pnpm_version']}"))
    tarball_url = str(metadata["dist"]["tarball"])
    integrity = str(metadata["dist"]["integrity"])
    if not integrity.startswith("sha512-"):
        raise ValueError(f"pnpm metadata for {plan['pnpm_version']} does not contain a sha512 integrity tarball")
    with tempfile.TemporaryDirectory(prefix="luaskills-managed-pnpm-") as temporary_text:
        temporary_root = Path(temporary_text)
        tarball_path = temporary_root / f"pnpm-{plan['pnpm_version']}.tgz"
        extract_directory = temporary_root / "extract"
        urllib.request.urlretrieve(tarball_url, tarball_path)
        verify_sha512_integrity(tarball_path, integrity)
        extract_archive(tarball_path, extract_directory)
        package_root = extract_directory / "package"
        if not package_root.exists():
            raise FileNotFoundError("pnpm package root was not found in tarball")
        pnpm_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(package_root, pnpm_target, dirs_exist_ok=True)
    write_managed_runtime_manifest(
        pnpm_target,
        {
            "schema_version": 1,
            "runtime": "pnpm",
            "version": plan["pnpm_version"],
            "platform": "any",
            "executable": "bin/pnpm.cjs",
            "source": tarball_url,
            "node_runtime_version": plan["node_version"],
        },
    )
    run_process([str(node_executable), str(pnpm_entry), "--version"])


def install_one_asset(runtime_root: Path, asset: dict[str, Any], temporary_root: Path, target: dict[str, str]) -> None:
    """
    Download, verify, extract, and install one asset.
    下载、校验、解压并安装单个资产。
    """

    # Validate the supported role before downloading or extracting any archive.
    # 在下载或解压归档前验证受支持的角色。
    if asset["role"] not in ("lua_runtime", "luaskills_ffi"):
        raise ValueError(f"Unsupported runtime asset role: {asset['role']}")
    asset_directory = temporary_root / asset["role"]
    archive_path = asset_directory / asset["asset_name"]
    extract_directory = asset_directory / "extract"
    asset_directory.mkdir(parents=True, exist_ok=True)
    sha256_text = download_text(asset["sha256_url"])
    urllib.request.urlretrieve(asset["download_url"], archive_path)
    verify_sha256(archive_path, sha256_text)
    extract_archive(archive_path, extract_directory)
    if asset["role"] == "lua_runtime":
        install_lua_runtime(runtime_root, extract_directory, asset)
    elif asset["role"] == "luaskills_ffi":
        install_luaskills_ffi(runtime_root, extract_directory, target, asset)



def download_text(url: str) -> str:
    """
    Download one UTF-8 text file.
    下载单个 UTF-8 文本文件。
    """

    with urllib.request.urlopen(url) as response:
        return response.read().decode("utf-8")


def verify_sha256(file_path: Path, sha256_text: str) -> None:
    """
    Verify one downloaded archive against a SHA-256 sidecar.
    使用 SHA-256 旁路文件校验单个已下载归档。
    """

    tokens = sha256_text.strip().split()
    if not tokens:
        raise ValueError(f"invalid SHA-256 sidecar for {file_path}")
    expected_hash = normalize_sha256_hash(tokens[0], f"SHA-256 sidecar for {file_path}")
    actual_hash = file_sha256(file_path)
    if expected_hash != actual_hash:
        raise ValueError(f"SHA-256 mismatch for {file_path}: expected {expected_hash}, got {actual_hash}")


def verify_named_sha256(file_path: Path, sha256_text: str, asset_name: str) -> None:
    """
    Verify one downloaded archive against a named SHA-256 manifest.
    使用包含文件名的 SHA-256 清单校验单个已下载归档。
    """

    expected_hash = ""
    for line in sha256_text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1] == asset_name:
            expected_hash = normalize_sha256_hash(parts[0], f"checksum entry for {asset_name}")
            break
    if not expected_hash:
        raise ValueError(f"checksum entry for {asset_name} was not found")
    actual_hash = file_sha256(file_path)
    if expected_hash != actual_hash:
        raise ValueError(f"SHA-256 mismatch for {file_path}: expected {expected_hash}, got {actual_hash}")


def verify_sha512_integrity(file_path: Path, integrity: str) -> None:
    """
    Verify one downloaded npm tarball against an integrity string.
    使用 npm integrity 字符串校验单个已下载 tarball。
    """

    expected_digest = normalize_sha512_integrity_digest(file_path, integrity)
    actual_digest = file_sha512_base64(file_path)
    if expected_digest != actual_digest:
        raise ValueError(f"SHA-512 integrity mismatch for {file_path}")


def normalize_sha256_hash(hash_text: str, context: str) -> str:
    """
    Normalize and validate one SHA-256 hexadecimal digest.
    归一化并校验单个 SHA-256 十六进制摘要。
    """

    normalized = hash_text.lower()
    if not SHA256_HEX_PATTERN.fullmatch(normalized):
        raise ValueError(f"invalid SHA-256 digest in {context}: {hash_text}")
    return normalized


def normalize_sha512_integrity_digest(file_path: Path, integrity: str) -> str:
    """
    Extract and validate one SHA-512 Base64 digest from an integrity string.
    从 integrity 字符串提取并校验单个 SHA-512 Base64 摘要。
    """

    if not integrity.startswith("sha512-"):
        raise ValueError(f"invalid SHA-512 integrity for {file_path}")
    digest = integrity.removeprefix("sha512-")
    if not digest or len(digest) % 4 != 0 or not SHA512_BASE64_PATTERN.fullmatch(digest):
        raise ValueError(f"invalid SHA-512 integrity for {file_path}")
    return digest


def file_sha256(file_path: Path) -> str:
    """
    Compute the SHA-256 hash for one file.
    计算单个文件的 SHA-256 哈希。
    """

    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_sha512_base64(file_path: Path) -> str:
    """
    Compute the SHA-512 hash for one file as Base64.
    计算单个文件的 SHA-512 Base64 哈希。
    """

    digest = hashlib.sha512()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return base64.b64encode(digest.digest()).decode("ascii")


def extract_archive(archive_path: Path, destination: Path) -> None:
    """
    Extract one .zip or .tar.gz archive.
    解压单个 .zip 或 .tar.gz 归档。
    """

    destination.mkdir(parents=True, exist_ok=True)
    if archive_path.name.endswith(".zip"):
        with zipfile.ZipFile(archive_path) as archive:
            validate_zip_members(destination, archive)
            archive.extractall(destination)
        return
    with tarfile.open(archive_path) as archive:
        validate_tar_members(destination, archive)
        # Resume the iterator only after the previous member has actually been extracted.
        # 仅在前一个成员实际提取后继续迭代器。
        # This checks live link aliases on Python 3.10 too, while extractall retains deferred directory metadata.
        # 此方式在 Python 三点十同样检查实际链接别名，同时由 extractall 保留延后目录元数据处理。
        archive.extractall(destination, members=validated_tar_members(destination, archive))


def validate_zip_members(destination: Path, archive: zipfile.ZipFile) -> None:
    """
    Validate that every zip member extracts inside the destination directory.
    校验每个 zip 成员都会解压到目标目录内部。
    """

    for member in archive.infolist():
        validate_archive_member_path(destination, member.filename)


def validate_tar_members(destination: Path, archive: tarfile.TarFile) -> None:
    """
    Preflight archive members and targets without requiring not-yet-extracted physical hardlink targets.
    预检归档成员及目标，不要求尚未提取的物理硬链接目标已存在。
    Destination is the private extraction root; archive supplies original ordered members; return None or reject.
    destination 是私有提取根；archive 提供原有序成员；返回空值或拒绝。
    """

    # Match standard tar backward lookup: only the last normalized name before this member is authoritative.
    # 匹配标准 tar 向后查找：只有当前成员之前最后一个规范化名称是权威来源。
    prior_members: dict[str, tuple[tarfile.TarInfo, ...]] = {}
    for member in archive.getmembers():
        prior_members[os.path.normpath(member.name)] = validate_tar_member(
            destination, member, prior_members, extracting=False
        )


def validated_tar_members(destination: Path, archive: tarfile.TarFile) -> Iterator[tarfile.TarInfo]:
    """
    Revalidate each original member against already extracted links immediately before yielding it.
    在交出每个原成员前，立即对照已经提取的链接重新校验。
    Destination and archive bind the extraction root and original sequence; yield validated TarInfo objects.
    destination、archive 绑定提取根及原序列；产出已校验 TarInfo 对象。
    """

    # Keep the same predecessor-name authority as preflight; no future entry can authorize a hardlink fallback.
    # 保持与预检相同的先前名称权威；后续成员不能授权硬链接回退。
    prior_members: dict[str, tuple[tarfile.TarInfo, ...]] = {}
    for member in archive.getmembers():
        # Capture the original reference chain now; later duplicate names must not replace older references.
        # 此时捕获原引用链；后续重复名称不得替换更早的引用。
        reference_chain = validate_tar_member(destination, member, prior_members, extracting=True)
        if os.name == 'nt' and member.issym():
            # Supported Windows tarfile versions pass linkname unchanged to os.symlink, which needs native separators.
            # 受支持的 Windows tarfile 版本将 linkname 原样交给 os.symlink，而该调用需要原生分隔符。
            # Normalize only an extraction view, preserving original archive names and immutable reference authority.
            # 仅规范化提取视图，保留原归档名称及不可变引用权威。
            extraction_member = copy.copy(member)
            extraction_member.linkname = member.linkname.replace('/', os.sep)
            yield extraction_member
        else:
            yield member
        prior_members[os.path.normpath(member.name)] = reference_chain


def validate_tar_member(
    destination: Path,
    member: tarfile.TarInfo,
    prior_members: dict[str, tuple[tarfile.TarInfo, ...]],
    *,
    extracting: bool,
) -> tuple[tarfile.TarInfo, ...]:
    """
    Validate one original member using prior archive names and, during extraction, the actual target type.
    用先前归档名称校验单个原成员，并在提取时检查实际目标类型。
    Destination/member identify the root and current entry; prior_members retains each previously selected chain.
    destination、member 标识根及当前成员；prior_members 保留每个先前选定的引用链。
    Extracting enables live lstat checks for every potentially recursive hardlink target.
    extracting 启用每个可能递归硬链接目标的实际 lstat 检查。
    Return the immutable original reference chain when safe; reject before standard-library extraction.
    安全时返回不可变的原引用链；在标准库提取前拒绝不安全成员。
    """

    validate_tar_member_type(member)
    validate_archive_member_path(destination, member.name)
    if member.issym():
        validate_archive_symlink_target(destination, member.name, member.linkname)
    if member.islnk():
        validate_archive_member_path(destination, member.linkname)
        # A failed os.link may re-extract this prior TarInfo at the hardlink's new location.
        # os.link 失败可能在硬链接的新位置重新提取此先前 TarInfo。
        # Retain the chain selected before this member; every nested fallback must end at the original regular entry.
        # 保留当前成员之前选定的链；每层回退必须终止于原常规成员。
        original_target = prior_members.get(os.path.normpath(member.linkname))
        if original_target is None or not original_target[-1].isfile():
            raise ValueError(f"hardlink target must be a prior regular file or regular hardlink chain: {member.linkname}")
        # Check each os.link target that the standard library can reach through its original fallback chain.
        # 检查标准库沿原回退链可能触及的每个 os.link 目标。
        for linked_member in (member, *original_target[:-1]):
            validate_archive_member_path(destination, linked_member.linkname)
            # The current name may have been overwritten, but this lookup only checks current type, not old identity.
            # 当前名称可能已经覆盖；此查找仅检查当前类型，不替换旧身份。
            current_target = prior_members.get(os.path.normpath(linked_member.linkname))
            if current_target is None or not current_target[-1].isfile():
                raise ValueError(f"hardlink fallback target is no longer a regular file: {linked_member.linkname}")
            if extracting:
                # Inspect each actual entry itself rather than following a symbolic link before nested os.link.
                # 在嵌套 os.link 前检查每个实际条目自身，不跟随符号链接。
                target = destination / linked_member.linkname
                try:
                    target_mode = target.lstat().st_mode
                except FileNotFoundError as error:
                    raise ValueError(f"hardlink target is not an extracted regular file: {linked_member.linkname}") from error
                if not stat.S_ISREG(target_mode):
                    raise ValueError(f"hardlink target is not an extracted regular file: {linked_member.linkname}")
        return (member, *original_target)
    return (member,)


def validate_tar_member_type(member: tarfile.TarInfo) -> None:
    """
    Reject tar members that are not regular files, directories, or links.
    拒绝非常规文件、目录或链接的 tar 成员。
    """

    if member.isfile() or member.isdir() or member.issym() or member.islnk():
        return
    raise ValueError(f"unsupported tar member type: {member.name}")


def validate_archive_symlink_target(destination: Path, member_name: str, link_name: str) -> None:
    """
    Validate that one archive symbolic link target resolves inside the destination directory.
    校验单个归档符号链接目标会解析到目标目录内部。
    """

    link_path = Path(link_name)
    if link_path.is_absolute():
        validate_archive_resolved_path(destination, link_name)
        return
    # A lawful symlink may use .. relative to its own parent; unlike member names, only its live bound is checked.
    # 合法符号链接可相对自身父目录使用 ..；与成员名称不同，此处仅检查其实际边界。
    validate_archive_resolved_path(destination, str(Path(member_name).parent / link_path))


def validate_archive_member_path(destination: Path, member_name: str) -> None:
    """
    Reject raw parent components and archive members whose live resolved path escapes the destination.
    拒绝原始父组件及实际解析路径逃逸目标目录的归档成员。
    Destination is the extraction root and member_name is an original archive name; return None or raise ValueError.
    destination 是提取根，member_name 是原归档名称；安全时返回 None，不安全时抛出 ValueError。
    """

    # Reject raw parent components before normalization or earlier links can change their meaning.
    # 在规范化或先前链接改变含义之前拒绝原始父组件。
    if ".." in member_name.replace("\\", "/").split("/"):
        raise ValueError(f"archive member escapes extraction directory: {member_name}")
    validate_archive_resolved_path(destination, member_name)


def validate_archive_resolved_path(destination: Path, relative_name: str) -> None:
    """
    Check a relative member or parent-relative symlink expression against the current extraction root.
    对照当前提取根检查相对成员或相对父目录的符号链接表达式。
    Destination is the root and relative_name is the expression; return None or reject absolute/escaping paths.
    destination 是根，relative_name 是表达式；返回空值或拒绝绝对、越界路径。
    """

    if not relative_name or "\x00" in relative_name or Path(relative_name).is_absolute() or PureWindowsPath(relative_name).is_absolute():
        raise ValueError(f"unsafe archive member path: {relative_name}")
    # Windows realpath normalizes a whole a/.. expression before dereferencing a; resolve a first instead.
    # Windows realpath 在解引用 a 前规范化整个 a/.. 表达式；因此先解析 a。
    # This also preserves lawful parent-relative targets while keeping one final root-bound comparison.
    # 此方式也保留合法父目录相对目标，并维持唯一的最终根边界比较。
    resolved_destination = destination.resolve()
    resolved_member_path = resolved_destination
    for component in Path(relative_name).parts:
        resolved_member_path = (resolved_member_path / component).resolve()
    if resolved_member_path != resolved_destination and resolved_destination not in resolved_member_path.parents:
        raise ValueError(f"archive member escapes extraction directory: {relative_name}")


def install_lua_runtime(runtime_root: Path, extract_directory: Path, asset: dict[str, Any]) -> None:
    """
    Install a Lua runtime archive into runtime lua_packages/libs/resources/licenses directories.
    将 Lua runtime 归档安装到 runtime 的 lua_packages/libs/resources/licenses 目录。
    """

    copy_directory_if_present(extract_directory / "lua_packages", runtime_root / "lua_packages")
    copy_directory_if_present(extract_directory / "libs", runtime_root / "libs")
    copy_directory_if_present(extract_directory / "resources", runtime_root / "resources")
    copy_directory_if_present(extract_directory / "licenses", runtime_root / "licenses")
    marker_path = runtime_root / "resources" / "lua-runtime-manifest.json"
    if not marker_path.exists():
        raise FileNotFoundError(f"Lua runtime manifest was not found after installing {asset['asset_name']}")
    asset["installed_path"] = str(marker_path.relative_to(runtime_root)).replace("\\", "/")


def install_luaskills_ffi(runtime_root: Path, extract_directory: Path, target: dict[str, str], asset: dict[str, Any]) -> None:
    """
    Install a LuaSkills FFI SDK archive into runtime include/libs/licenses directories.
    将 LuaSkills FFI SDK 归档安装到 runtime include/libs/licenses 目录。
    """

    copy_directory_if_present(extract_directory / "include", runtime_root / "include")
    copy_directory_if_present(extract_directory / "lib", runtime_root / "libs")
    copy_directory_if_present(extract_directory / "licenses", runtime_root / "licenses" / "luaskills-ffi")
    installed_path = resolve_luaskills_library_path_from_runtime(runtime_root, target)
    if installed_path is None:
        raise FileNotFoundError(f"LuaSkills dynamic library was not found after installing {asset['asset_name']}")
    asset["installed_path"] = str(installed_path.relative_to(runtime_root)).replace("\\", "/")






def copy_directory_if_present(source: Path, destination: Path) -> None:
    """
    Copy one directory only when it exists.
    仅在目录存在时复制单个目录。
    """

    if source.exists():
        shutil.copytree(source, destination, dirs_exist_ok=True)


def find_file(root: Path, predicate: Callable[[str], bool]) -> Path | None:
    """
    Find one file under a directory by base-name predicate.
    根据基础文件名谓词在目录下查找单个文件。
    """

    for path in root.rglob("*"):
        if path.is_file() and predicate(path.name):
            return path
    return None


def managed_runtime_installed_paths(
    _runtime_root: Path,
    target: dict[str, str],
    python_version: str,
    uv_version: str,
    node_version: str,
    pnpm_version: str,
) -> dict[str, str]:
    """
    Build relative managed runtime installation paths under one runtime root.
    构造单个 runtime root 下的受管运行时相对安装路径。
    """

    platform_key = target["platform_key"]
    return {
        "python": f"dependencies/runtimes/python/cpython-{python_version}-{platform_key}",
        "uv": f"dependencies/runtimes/python/uv-{uv_version}-{platform_key}",
        "node": f"dependencies/runtimes/node/node-{node_version}-{platform_key}",
        "pnpm": f"dependencies/runtimes/node/pnpm-{pnpm_version}",
    }


def write_managed_runtime_manifest(directory: Path, manifest: dict[str, Any]) -> None:
    """
    Write one managed runtime manifest without a UTF-8 BOM.
    写入一个不带 UTF-8 BOM 的受管运行时 manifest。
    """

    directory.mkdir(parents=True, exist_ok=True)
    (directory / "runtime-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_version_template(template: str, version: str) -> str:
    """
    Render one `{version}` template used by upstream managed runtime archives.
    渲染一个上游受管运行时归档使用的 `{version}` 模板。
    """

    return template.replace("{version}", version)


def run_process(command: list[str], env: dict[str, str] | None = None) -> None:
    """
    Run one child process and raise when it fails.
    运行单个子进程，并在失败时抛出异常。
    """

    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    subprocess.run(command, env=merged_env, check=True)


def run_process_capture(command: list[str], env: dict[str, str] | None = None) -> str:
    """
    Run one child process and capture stdout.
    运行单个子进程并捕获 stdout。
    """

    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    result = subprocess.run(command, env=merged_env, check=True, text=True, capture_output=True)
    return result.stdout


def utc_now_iso() -> str:
    """
    Return a compact UTC ISO timestamp.
    返回紧凑的 UTC ISO 时间戳。
    """

    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
