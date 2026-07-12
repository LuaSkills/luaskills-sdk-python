"""
Verify managed runtime host roots and the read-only resolver SDK contract.
校验受管运行时宿主根与只读解析器 SDK 契约。
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

# SourceRoot makes the checkout package importable without installing it.
# SourceRoot 让检出目录中的包无需安装即可导入。
SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from luaskills.client import (  # noqa: E402
    LuaSkillsClient,
    create_engine_options,
    default_host_options,
    default_managed_runtime_config,
)
from luaskills.runtime_assets import resolve_managed_runtime_platform_target  # noqa: E402


class RecordingFfi:
    """
    Record one JSON FFI request and return a deterministic runtime descriptor.
    记录单次 JSON FFI 请求并返回确定性的运行时描述符。
    """

    # Calls stores every function name and payload received by this test double.
    # Calls 保存该测试替身收到的每个函数名与载荷。
    calls: list[tuple[str, dict[str, object]]] = []

    def __init__(self, library_path: object, runtime_root: object) -> None:
        """
        Accept the same constructor arguments as the production JSON bridge.
        接受与生产 JSON 桥相同的构造参数。

        Args:
            library_path: Optional native library path.
            runtime_root: Optional runtime root used for library discovery.
        Returns:
            None.

        参数：
            library_path：可选原生库路径。
            runtime_root：用于发现原生库的可选运行根。
        返回：
            无。
        """

        # ConstructorArguments prove the public wrapper forwards both discovery inputs unchanged.
        # ConstructorArguments 证明公共封装会原样转发两个发现参数。
        self.constructor_arguments = (library_path, runtime_root)

    def call_json(self, function_name: str, payload: dict[str, object]) -> dict[str, object]:
        """
        Record one resolver request and return its stable descriptor shape.
        记录单次解析器请求并返回稳定描述符形状。

        Args:
            function_name: Native JSON FFI function name.
            payload: JSON-serializable resolver request.
        Returns:
            One deterministic managed runtime descriptor.

        参数：
            function_name：原生 JSON FFI 函数名。
            payload：可 JSON 序列化的解析器请求。
        返回：
            一份确定性的受管运行时描述符。
        """

        self.calls.append((function_name, payload))
        return {
            "runtime": "python",
            "version": "3.14.4",
            "platform": "windows-x64",
            "install_root": "D:/shared/python/cpython-3.14.4-windows-x64",
            "executable": "D:/shared/python/cpython-3.14.4-windows-x64/python.exe",
            "manifest_hash": "a" * 64,
            "executable_hash": "b" * 64,
        }


class ManagedRuntimeHostRootsTests(unittest.TestCase):
    """
    Verify Python SDK parameters stay aligned with the 0.5.1 JSON FFI.
    校验 Python SDK 参数与 0.5.1 JSON FFI 保持一致。
    """

    def test_default_host_options_include_explicit_managed_roots(self) -> None:
        """
        Keep both managed roots explicit and unset in the complete default payload.
        在完整默认载荷中保留两个显式但未设置的受管根。
        """

        with TemporaryDirectory() as temporary_text:
            # Options is the complete JSON object passed to engine creation.
            # Options 是传给引擎创建流程的完整 JSON 对象。
            options = default_host_options(temporary_text)
        self.assertIn("managed_runtime_distribution_root", options)
        self.assertIsNone(options["managed_runtime_distribution_root"])
        self.assertIn("managed_runtime_environment_root", options)
        self.assertIsNone(options["managed_runtime_environment_root"])
        self.assertEqual(options["managed_runtime_config"], default_managed_runtime_config())

    def test_engine_options_preserve_custom_managed_runtime_config(self) -> None:
        """
        Preserve one complete host-selected B3-B7 policy in the engine creation payload.
        在引擎创建载荷中保留一份完整的宿主选择 B3-B7 策略。
        """

        # Config uses nondefault values so a missing merge field remains observable.
        # Config 使用非默认值，使合并字段缺失保持可观察。
        config = {
            "worker_pool_max_size_per_environment": 6,
            "worker_idle_ttl_secs": 30,
            "persistent_session_limit_per_engine": 64,
            "persistent_session_default_buffer_limit_bytes_per_stream": 262_144,
            "invoke_default_timeout_ms": 12_000,
        }
        with TemporaryDirectory() as temporary_text:
            # Options is the exact JSON engine payload built by the public SDK helper.
            # Options 是公共 SDK 辅助器构造的精确 JSON 引擎载荷。
            options = create_engine_options(
                temporary_text,
                host_options={"managed_runtime_config": config},
            )

        self.assertEqual(options["host_options"]["managed_runtime_config"], config)

    def test_resolver_forwards_exact_public_ffi_payload(self) -> None:
        """
        Normalize the distribution root and call only the public read-only resolver.
        规范化发行根并且只调用公共只读解析器。
        """

        RecordingFfi.calls = []
        with TemporaryDirectory(prefix="LuaSkills 发行根 ") as temporary_text:
            # DistributionRoot exercises spaces and non-ASCII host paths.
            # DistributionRoot 覆盖包含空格与非 ASCII 字符的宿主路径。
            distribution_root = Path(temporary_text)
            with patch("luaskills.client.LuaSkillsJsonFfi", RecordingFfi):
                # Descriptor is the typed result returned to the host.
                # Descriptor 是返回给宿主的类型化结果。
                descriptor = LuaSkillsClient.resolve_managed_runtime_install(
                    distribution_root,
                    "python",
                    "3.14.4",
                    "windows-x64",
                )

        self.assertEqual(descriptor["runtime"], "python")
        self.assertEqual(len(RecordingFfi.calls), 1)
        function_name, payload = RecordingFfi.calls[0]
        self.assertEqual(function_name, "luaskills_ffi_managed_runtime_resolve_json")
        self.assertEqual(payload["distribution_root"], distribution_root.resolve().as_posix())
        self.assertEqual(payload["runtime"], "python")
        self.assertEqual(payload["version"], "3.14.4")
        self.assertEqual(payload["platform"], "windows-x64")

    def test_resolver_rejects_unknown_runtime_before_ffi(self) -> None:
        """
        Reject an unknown runtime name without opening a native bridge.
        在打开原生桥之前拒绝未知运行时名称。
        """

        with self.assertRaisesRegex(ValueError, "runtime must be either"):
            LuaSkillsClient.resolve_managed_runtime_install(
                "D:/shared",
                "ruby",  # type: ignore[arg-type]
                "3.3.0",
                "windows-x64",
            )

    def test_resolver_rejects_relative_and_tilde_distribution_roots(self) -> None:
        """
        Reject every non-absolute distribution spelling before native library discovery.
        在发现原生库之前拒绝所有非绝对发行根写法。

        Returns:
            None after both relative path forms are rejected.

        返回：
            两种相对路径形式均被拒绝后返回无。
        """

        # RelativeRoots contains ordinary and user-home shorthand paths that must remain non-authoritative.
        # RelativeRoots 包含普通相对路径与用户主目录缩写，二者都不能成为授权路径。
        relative_roots = ("relative/runtimes", "~/managed-runtimes")
        for distribution_root in relative_roots:
            with self.subTest(distribution_root=distribution_root):
                with self.assertRaisesRegex(ValueError, "must be an absolute path"):
                    LuaSkillsClient.resolve_managed_runtime_install(
                        distribution_root,
                        "python",
                        "3.14.4",
                        "windows-x64",
                    )

    @unittest.skipUnless(os.environ.get("LUASKILLS_LIB"), "LUASKILLS_LIB is not configured")
    def test_real_resolver_round_trip(self) -> None:
        """
        Resolve one temporary Node installation through the real LuaSkills JSON FFI library.
        通过真实 LuaSkills JSON FFI 库解析一个临时 Node 安装。
        """

        # Target is the authoritative SDK mapping for the current native runner.
        # Target 是当前原生 runner 的权威 SDK 映射。
        target = resolve_managed_runtime_platform_target()
        with TemporaryDirectory(prefix="LuaSkills SDK 发行根 ") as temporary_text:
            # DistributionRoot is the isolated host-owned asset root.
            # DistributionRoot 是隔离的宿主自有资产根。
            distribution_root = Path(temporary_text) / "runtimes"
            # InstallRoot follows the exact Rust Node installation naming contract.
            # InstallRoot 遵循精确 Rust Node 安装命名契约。
            install_root = (
                distribution_root
                / "node"
                / f"node-24.18.0-{target['platform_key']}"
            )
            # ExecutablePath follows the published archive layout for this runner.
            # ExecutablePath 遵循当前 runner 的已发布归档布局。
            executable_path = install_root / target["node_executable"]
            executable_path.parent.mkdir(parents=True, exist_ok=True)
            executable_path.write_bytes(b"node executable")
            (install_root / "runtime-manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runtime": "node",
                        "version": "24.18.0",
                        "platform": target["platform_key"],
                        "executable": target["node_executable"],
                    }
                ),
                encoding="utf-8",
            )

            # Descriptor is decoded from the real native response envelope.
            # Descriptor 从真实原生响应包络解码。
            descriptor = LuaSkillsClient.resolve_managed_runtime_install(
                distribution_root,
                "node",
                "24.18.0",
                target["platform_key"],
                library_path=os.environ["LUASKILLS_LIB"],
            )

            self.assertTrue(os.path.samefile(descriptor["install_root"], install_root))
            self.assertTrue(os.path.samefile(descriptor["executable"], executable_path))
            self.assertEqual(len(descriptor["manifest_hash"]), 64)
            self.assertEqual(len(descriptor["executable_hash"]), 64)


if __name__ == "__main__":
    unittest.main()
