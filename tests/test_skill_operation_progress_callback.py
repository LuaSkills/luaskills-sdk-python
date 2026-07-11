from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

# Make the source package importable when tests run from one checkout.
# 从检出目录运行测试时让源码包可导入。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from luaskills.ffi import LuaSkillsJsonFfi, SkillOperationProgressEvent


class RecordingFfi(LuaSkillsJsonFfi):
    """
    Minimal FFI double that records JSON callback setter calls.
    记录 JSON callback setter 调用的最小 FFI 替身。
    """

    def __init__(self) -> None:
        """
        Initialize an empty callback registration call list.
        初始化空的 callback 注册调用列表。
        """

        self.calls: list[tuple[str, str, object | None]] = []

    def _set_json_provider_callback(self, kind: str, function_name: str, callback: object | None) -> None:
        """
        Record one callback registration request without loading a native library.
        记录一次 callback 注册请求而不加载原生动态库。
        """

        self.calls.append((kind, function_name, callback))


class SkillOperationProgressCallbackTests(unittest.TestCase):
    """
    Unit tests for skill operation progress callback registration.
    skill 操作进度 callback 注册的单元测试。
    """

    def test_register_and_clear_progress_callback_use_native_symbol(self) -> None:
        """
        Verify progress callback helpers target the native progress callback setter.
        校验进度 callback 辅助方法指向原生进度 callback setter。
        """

        ffi = RecordingFfi()

        def callback(event: SkillOperationProgressEvent) -> dict[str, Any]:
            """
            Return a JSON object while recording that the event type is accepted.
            返回 JSON 对象，同时记录事件类型可被接受。
            """

            return {"operation_id": event.get("operation_id")}

        ffi.set_skill_operation_progress_json_callback(callback)
        ffi.clear_skill_operation_progress_json_callback()

        self.assertEqual(
            ffi.calls,
            [
                (
                    "skill-operation-progress",
                    "luaskills_ffi_set_skill_operation_progress_json_callback",
                    callback,
                ),
                (
                    "skill-operation-progress",
                    "luaskills_ffi_set_skill_operation_progress_json_callback",
                    None,
                ),
            ],
        )

    def test_clear_all_json_provider_callbacks_uses_every_native_symbol(self) -> None:
        """
        Verify unified callback cleanup forwards every known callback slot.
        校验统一 callback 清理会转发所有已知 callback 槽位。
        """

        ffi = RecordingFfi()

        ffi.clear_json_provider_callbacks()

        self.assertEqual(
            ffi.calls,
            [
                (
                    "sqlite",
                    "luaskills_ffi_set_sqlite_provider_json_callback",
                    None,
                ),
                (
                    "lancedb",
                    "luaskills_ffi_set_lancedb_provider_json_callback",
                    None,
                ),
                (
                    "host-tool",
                    "luaskills_ffi_set_host_tool_json_callback",
                    None,
                ),
                (
                    "skill-operation-progress",
                    "luaskills_ffi_set_skill_operation_progress_json_callback",
                    None,
                ),
                (
                    "model-embed",
                    "luaskills_ffi_set_model_embed_json_callback",
                    None,
                ),
                (
                    "model-llm",
                    "luaskills_ffi_set_model_llm_json_callback",
                    None,
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()
