#!/usr/bin/env bash
set -euo pipefail

# ScriptRoot identifies the shared dependency script directory.
# ScriptRoot 标识共享依赖脚本目录。
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# RepositoryRoot identifies the SDK or LuaSkills repository root.
# RepositoryRoot 标识 SDK 或 LuaSkills 仓库根目录。
REPOSITORY_ROOT="$(cd "$SCRIPT_ROOT/../.." && pwd)"
# Target selects the asset group synchronized into the runtime root.
# Target 选择要同步到运行根目录的资产分组。
TARGET="${1:-all}"
# RuntimeRoot receives all synchronized assets.
# RuntimeRoot 接收全部同步资产。
RUNTIME_ROOT="${RUNTIME_ROOT:-output}"
# LuaSkillsVersion optionally stores an exact LuaSkills release tag; empty selects the newest published patch
# of the core series named by the SDK's embedded contract. An explicit tag must belong to that series.
# LuaSkillsVersion 可选保存精确 LuaSkills 发布标签；为空时选择 SDK 嵌入式契约所指核心系列最新已发布的补丁版本。
# 显式标签必须属于该系列。
LUASKILLS_VERSION="${LUASKILLS_VERSION:-}"

case "$TARGET" in
  all|luaskills)
    RUNTIME_ROOT="$RUNTIME_ROOT" LUASKILLS_VERSION="$LUASKILLS_VERSION" "$REPOSITORY_ROOT/scripts/ffi/fetch_ffi.sh"
    ;;
esac

case "$TARGET" in
  all|lua)
    RUNTIME_ROOT="$RUNTIME_ROOT" "$SCRIPT_ROOT/fetch_deps.sh" lua
    ;;
esac

case "$TARGET" in
  all|luaskills|lua) ;;
  *) echo "Usage: $0 [all|luaskills|lua]" >&2; exit 2 ;;
esac

echo "Runtime asset target '$TARGET' synchronized into $RUNTIME_ROOT"
