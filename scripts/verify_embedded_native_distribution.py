"""
Require a frozen native candidate and independently install exact wheel/sdist artifacts for real acceptance.
要求冻结原生候选，独立安装精确 wheel/sdist 产物进行真实验收。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import venv

def digest(value: str) -> str:
    """
    Validate value as a lowercase SHA-256 command-line digest and return it; malformed input fails.
    校验 value 为小写 SHA-256 命令行摘要并返回；格式错误输入失败。
    """
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise argparse.ArgumentTypeError("expected a lowercase SHA-256 digest")
    return value


def require_candidate(library: Path, expected_sha256: str, description: Path) -> None:
    """
    Require regular library/description files and library's expected_sha256 before installation; return nothing.
    在安装前要求 library/description 为普通文件且库符合 expected_sha256；无返回值。
    The installed SDK validates all description fields before reserving a runtime.
    已安装 SDK 在预留运行时前校验全部描述字段。
    """
    if not library.is_file():
        raise ValueError(f"required native candidate library is missing: {library}")
    if not description.is_file():
        raise ValueError(f"required frozen native description is missing: {description}")
    if hashlib.sha256(library.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("native candidate library SHA-256 mismatch")


def accept_install(artifact: Path, environment: Path, library: Path, library_sha256: str,
                   description: Path) -> None:
    """
    Install artifact into environment, require isolated imports and run library's real example with frozen identity.
    将 artifact 安装进 environment、要求隔离导入并运行 library 的真实示例及冻结身份校验。
    library_sha256 and description are exact caller-selected candidate evidence; return only on real acceptance.
    library_sha256 与 description 为调用方精确选择的候选证据；仅真实验收通过后返回。
    """
    venv.EnvBuilder(with_pip=True, system_site_packages=False).create(environment)
    # Python's platform-specific venv layout is explicit, without probing alternative interpreter locations.
    # Python 平台特定 venv 布局显式声明，不探测替代解释器位置。
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    subprocess.run([str(python), "-I", "-m", "pip", "install", "--no-index", "--no-deps",
                    "--disable-pip-version-check", str(artifact)], cwd=environment, check=True)
    # -I excludes the checkout, PYTHONPATH and user site; every embedded module must live in this venv.
    # -I 排除检出目录、PYTHONPATH 及用户 site；每个嵌入式模块必须位于此 venv。
    probe = """
import importlib, pathlib, sys
root = pathlib.Path(sys.prefix).resolve()
for name in ('luaskills', 'luaskills.embedded_contract', 'luaskills.embedded_client',
             'luaskills.embedded_pump', 'luaskills.embedded_scope', 'luaskills.examples.embedded_runtime',
             'luaskills.examples.embedded_value_policy'):
    module = importlib.import_module(name)
    if not pathlib.Path(module.__file__).resolve().is_relative_to(root):
        raise RuntimeError('SDK import escaped isolated installation: ' + name)
"""
    subprocess.run([str(python), "-I", "-c", probe], cwd=environment, check=True)
    subprocess.run([str(python), "-I", "-X", "utf8", "-m", "luaskills.examples.embedded_runtime",
                    "--library", str(library), "--library-sha256", library_sha256,
                    "--description", str(description), "--mode", "both"], cwd=environment, check=True)
    # Application policy acceptance executes only the independent installed module in this isolated environment.
    # 应用政策验收仅在此隔离环境内执行独立安装模块。
    subprocess.run([str(python), "-I", "-X", "utf8", "-m", "luaskills.examples.embedded_value_policy",
                    "--library", str(library), "--library-sha256", library_sha256,
                    "--description", str(description)], cwd=environment, check=True, timeout=60)
    # Fault-inject Python startup while retaining the actual installed SDK and native candidate.
    # 保留实际已安装 SDK 及原生候选，同时向 Python 启动注入故障。
    startup_probe = """
import sys, unittest
suite = unittest.defaultTestLoader.discover(sys.argv[1], pattern='test_embedded_example_native_startup.py')
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful() or bool(result.skipped) or result.testsRun == 0)
"""
    subprocess.run([str(python), "-I", "-X", "utf8", "-c", startup_probe,
                    str(Path(__file__).resolve().parents[1] / "tests")], cwd=environment,
                   env=dict(os.environ, LUASKILLS_LIB=str(library)), check=True)


def main() -> None:
    """
    Consume explicit --wheel/--sdist/--library/--library-sha256/--description arguments and enforce native acceptance.
    消费显式 --wheel/--sdist/--library/--library-sha256/--description 参数并强制原生验收。
    Return nothing; missing candidates, mismatched identities or any skipped native scenario cannot pass.
    无返回值；缺候选、身份不匹配或跳过任何原生场景均不能通过。
    """
    # Caller-supplied artifact paths prohibit latest selection or automatic runtime acquisition.
    # 调用方提供的产物路径禁止选择最新文件或自动获取运行时。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sdist", type=Path, required=True)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--library-sha256", type=digest, required=True)
    parser.add_argument("--description", type=Path, required=True)
    args = parser.parse_args()
    # Missing native input fails before optional/offline tests can suggest a successful native gate.
    # 缺少原生输入时先失败，避免可选或离线测试暗示原生门禁成功。
    library = args.library.resolve()
    description = args.description.resolve()
    require_candidate(library, args.library_sha256, description)
    wheel = args.wheel.resolve(strict=True)
    sdist = args.sdist.resolve(strict=True)
    # Existing compatibility tests receive exactly this candidate, so their native assertion cannot skip.
    # 既有兼容测试接收精确此候选，因而其原生断言不能跳过。
    environment = dict(os.environ, LUASKILLS_LIB=str(library))
    subprocess.run([sys.executable, "-X", "utf8", str(Path(__file__).with_name("verify_embedded_distribution.py")),
                    "--wheel", str(wheel), "--sdist", str(sdist)], env=environment, check=True)
    if importlib.util.find_spec("twine") is not None:
        subprocess.run([sys.executable, "-m", "twine", "check", "--strict", str(wheel), str(sdist)], check=True)
    else:
        print("twine is unavailable; package metadata check was not run.")
    with tempfile.TemporaryDirectory(prefix="luaskills-native-distribution-") as temporary:
        # Build only the selected sdist with already installed backend tools; no network or global installation.
        # 仅用已安装后端工具构建选定 sdist；不访问网络或全局安装。
        root = Path(temporary)
        built = root / "sdist-wheel"
        built.mkdir()
        subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-index", "--no-deps",
                        "--no-build-isolation", "--disable-pip-version-check", "--wheel-dir", str(built),
                        str(sdist)], cwd=root, check=True)
        # This directory is new and contains outputs from exactly one selected source distribution.
        # 此目录新建，仅包含单个选定源码分发包的输出。
        rebuilt = list(built.glob("*.whl"))
        if len(rebuilt) != 1:
            raise ValueError("selected source distribution must build exactly one wheel")
        accept_install(wheel, root / "wheel-venv", library, args.library_sha256, description)
        accept_install(rebuilt[0], root / "sdist-venv", library, args.library_sha256, description)
    print("Native wheel and independently rebuilt source distribution accepted: sync, asyncio, callbacks, prewarm and cleanup.")


if __name__ == "__main__":
    main()
