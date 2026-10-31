"""Retain captured SQLite callbacks while SDK-owned native engines or transports exist.
在 SDK 拥有的原生引擎或传输存活期间保留已捕获的 SQLite 回调。
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Callable

# State is keyed by the canonical library path used by both native SDK surfaces.
# 状态按两个原生 SDK 接口共同使用的规范库路径索引。
_LOCK = threading.RLock()
# Counts include creation in progress, preventing replacement from freeing a captured pointer.
# 计数包含正在创建的实例，防止替换操作释放已捕获指针。
_SCOPES: dict[str, int] = {}
# Retired wrappers are released only after the last native owner has been freed successfully.
# 退役包装器仅在最后一个原生所有者成功释放后才释放。
_RETIRED: dict[str, list[object]] = {}
# JSON engines can be freed through a different FFI facade for the same native library.
# JSON 引擎可以通过同一原生库的另一个 FFI 外观释放。
JSON_ENGINE_SCOPES: dict[tuple[str, int], Callable[[], None]] = {}


def library_key(library_path: str | Path) -> str:
    """Return the canonical case-normalized key for an explicitly resolved native library.
    返回显式已解析原生库的规范大小写键。
    """
    return os.path.normcase(str(Path(library_path).resolve()))


def retain_sqlite_scope(library_path: str | Path) -> Callable[[], None]:
    """Pin callback generations for library_path and return an idempotent native-owner release.
    固定 library_path 的回调代次，并返回幂等的原生所有者释放函数。
    The caller must invoke the release only after successful native destruction or failed creation.
    调用方仅能在原生销毁成功或创建失败后执行释放函数。
    """
    # Key identifies the single library whose global callback is captured by native engines.
    # 键标识原生引擎捕获全局回调的唯一库。
    key = library_key(library_path)
    # Released prevents duplicate destruction paths from decrementing another owner's count.
    # released 防止重复销毁路径减少其他所有者的计数。
    released = False
    with _LOCK:
        _SCOPES[key] = _SCOPES.get(key, 0) + 1

    def release() -> None:
        """Drop this native owner's pin once and release retired wrappers outside the lock.
        仅丢弃此原生所有者的固定一次，并在锁外释放退役包装器。
        """
        nonlocal released
        # Detached keeps callback destructors outside the registry lock.
        # detached 使回调析构发生在注册表锁外。
        detached: list[object] = []
        with _LOCK:
            if released:
                return
            released = True
            _SCOPES[key] -= 1
            if _SCOPES[key] == 0:
                del _SCOPES[key]
                detached = _RETIRED.pop(key, [])
        detached.clear()

    return release


def retire_sqlite_callback(library_path: str | Path, callback: object) -> None:
    """Retain a replaced/cleared callback only while its library has potential native owners.
    仅在库存在潜在原生所有者时保留已替换或清空的回调。
    """
    # Key is identical to the owner key even when Windows path casing differs.
    # 即使 Windows 路径大小写不同，此键仍与所有者键相同。
    key = library_key(library_path)
    with _LOCK:
        if _SCOPES.get(key, 0):
            _RETIRED.setdefault(key, []).append(callback)
