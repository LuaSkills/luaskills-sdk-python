"""
Verify embedded contract bytes and standalone usability in an explicitly selected wheel and source distribution.
验证显式指定的 wheel 及源码分发包中的嵌入式契约字节与独立可用性。
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import zipfile


# Repository inputs are compared with distributable bytes, not a second version or digest authority.
# 仓库输入与可分发字节比较，不创建第二套版本或摘要权威。
ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ARTIFACTS = (
    "luaskills/__init__.py",
    "luaskills/embedded_client.py",
    "luaskills/embedded_scope.py",
    "luaskills/embedded_driver.py",
    "luaskills/embedded_transport.py",
    "luaskills/embedded_json.py",
    "luaskills/embedded_compatibility.py",
    "luaskills/embedded_pump.py",
    "luaskills/embedded_callbacks.py",
    "luaskills/embedded_contract.py",
    "luaskills/contracts/embedded/v1/contract.json",
    "luaskills/contracts/embedded/v1/contract.sha256",
    "luaskills/contracts/embedded/v1/README.md",
    "luaskills/py.typed",
)


def verify_wheel(path: Path) -> None:
    """
    Compare path's packaged contract files with source, then import the actual wheel in isolated Python.
    比较 path 的包内契约文件与源码，然后在隔离 Python 中导入实际 wheel。
    Return nothing; missing, duplicate or changed members and unresolved type references fail verification.
    无返回值；缺失、重复或改变的成员及未解析类型引用使验证失败。
    """
    with zipfile.ZipFile(path) as archive:
        # Duplicate entries can resolve differently between readers, so reject them before name-based reads.
        # 重复条目在不同读取器中可能解析不同，因此在按名称读取前拒绝。
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("wheel contains duplicate member names")
        for name in PACKAGE_ARTIFACTS:
            if archive.read(name) != (ROOT / "src" / name).read_bytes():
                raise ValueError(f"wheel contains stale embedded artifact: {name}")
    # -I ignores PYTHONPATH and user site packages; the SDK must import solely from this selected wheel.
    # -I 忽略 PYTHONPATH 和用户 site 包；SDK 必须只从此选定 wheel 导入。
    probe = """
import hashlib
import importlib.resources
import json
import sys
import typing
sys.path.insert(0, sys.argv[1])
from luaskills import embedded_contract as contract
from luaskills import embedded_client as client
from luaskills import embedded_scope as scope
from luaskills import embedded_compatibility as compatibility
import luaskills
assert contract.__file__.startswith(sys.argv[1])
assert client.__file__.startswith(sys.argv[1])
assert scope.__file__.startswith(sys.argv[1])
assert compatibility.__file__.startswith(sys.argv[1])
assert luaskills.EmbeddedCompatibilityError is compatibility.EmbeddedCompatibilityError
# Resolve imported recursive aliases in their defining contract namespace, as required by typing on Python 3.10.
# 按 Python 3.10 typing 的要求，在定义契约命名空间解析导入的递归别名。
for declaration in (client.EmbeddedClient, client.EmbeddedPending, client.EmbeddedRuntime, client.EmbeddedPlugin,
                    client.EmbeddedPool, client.EmbeddedSession, client.EmbeddedSessionOpen, client.EmbeddedOperation,
                    scope.EmbeddedRuntimeScope):
    assert getattr(luaskills, declaration.__name__) is declaration
    typing.get_type_hints(declaration)
    for method in vars(declaration).values():
        if callable(method) and hasattr(method, "__annotations__"):
            typing.get_type_hints(method, localns=vars(contract))
# Resources must resolve inside the selected wheel, independently of repository paths.
# 资源必须在选定 wheel 内解析，独立于仓库路径。
resource = importlib.resources.files("luaskills").joinpath("contracts", "embedded", "v1")
encoded = resource.joinpath("contract.json").read_bytes()
assert hashlib.sha256(encoded).hexdigest() == contract.EMBEDDED_CONTRACT_SHA256
assert json.loads(encoded)["protocol_version"] == contract.EMBEDDED_PROTOCOL_VERSION
for name in contract.__all__:
    # Resolve actual imported field annotations rather than only compiling their text.
    # 解析实际导入的字段注解，而非仅编译其文本。
    declaration = getattr(contract, name)
    if typing.is_typeddict(declaration):
        typing.get_type_hints(declaration)
"""
    subprocess.run([sys.executable, "-I", "-c", probe, str(path.resolve())], check=True)
    # Execute shared assertions against the wheel's codec and resources in another isolated interpreter.
    # 在另一隔离解释器中，对 wheel 的编码器及资源执行共享断言。
    vector_probe = "import runpy, sys; sys.path.insert(0, sys.argv[1]); suite = sys.argv[2]; sys.argv = [suite]; runpy.run_path(suite, run_name='__main__')"
    subprocess.run([sys.executable, "-I", "-c", vector_probe, str(path.resolve()),
        str(ROOT / "tests/test_embedded_json_vectors.py")], check=True)
    # Run native admission fault cases against the selected wheel; an explicit DLL also enables real integration.
    # 对选定 wheel 执行原生入场故障用例；显式 DLL 同时启用实际集成验证。
    compatibility_probe = "import sys, unittest; sys.path.insert(0, sys.argv[1]); suite = unittest.defaultTestLoader.discover(sys.argv[2], pattern='test_embedded_compatibility.py'); result = unittest.TextTestRunner(verbosity=2).run(suite); sys.exit(not result.wasSuccessful())"
    subprocess.run([sys.executable, "-I", "-c", compatibility_probe, str(path.resolve()),
        str(ROOT / "tests")], check=True)


def verify_sdist(path: Path) -> None:
    """
    Verify path's source artifacts and regenerate in a temporary directory containing only declared inputs.
    验证 path 的源码产物，并在仅含声明输入的临时目录中重新生成。
    Return nothing; never extract arbitrary archive members or search for neighboring repositories.
    无返回值；绝不解压任意归档成员或搜索相邻仓库。
    """
    with tarfile.open(path, "r:gz") as archive, tempfile.TemporaryDirectory() as temporary:
        # Python sdists own exactly one top-level directory; member selection then uses explicit relative names.
        # Python 源码包恰有一个顶层目录；随后通过显式相对名称选择成员。
        names = archive.getnames()
        if len(names) != len(set(names)):
            raise ValueError("source distribution contains duplicate member names")
        roots = {name.split("/")[0] for name in names}
        if len(roots) != 1 or not next(iter(roots)):
            raise ValueError("source distribution must have one named root")
        prefix = next(iter(roots)) + "/"
        # Only these verified files are materialized; tar names never become destination filesystem paths.
        # 只落盘这些经验证文件；tar 名称绝不成为目标文件系统路径。
        artifacts = ["scripts/generate_embedded_contract.py", "scripts/verify_embedded_distribution.py", "tests/test_embedded_json_vectors.py", "tests/test_embedded_compatibility.py", "tests/test_embedded_transport.py", *("src/" + name for name in PACKAGE_ARTIFACTS)]
        destination = Path(temporary)
        for name in artifacts:
            member = archive.getmember(prefix + name)
            if not member.isfile():
                raise ValueError(f"source artifact is not a regular file: {name}")
            stream = archive.extractfile(member)
            assert stream is not None
            with stream:
                content = stream.read()
            if content != (ROOT / name).read_bytes():
                raise ValueError(f"source distribution contains stale embedded artifact: {name}")
            output = destination / name
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(content)
        subprocess.run([sys.executable, "-I", str(destination / "scripts/generate_embedded_contract.py"), "--check"], cwd=destination, check=True)


def main() -> None:
    """
    Verify the explicit --wheel and --sdist command-line paths without publishing either artifact.
    验证命令行显式 --wheel 和 --sdist 路径，不发布任何产物。
    Return nothing; any mismatch exits unsuccessfully for use as a release gate.
    无返回值；任何不一致均以失败退出，以便作为发布门禁。
    """
    # No latest-file selection: the caller supplies the exact artifacts from its build step.
    # 不选择最新文件：调用方提供其构建步骤的精确产物。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sdist", type=Path, required=True)
    args = parser.parse_args()
    verify_wheel(args.wheel)
    verify_sdist(args.sdist)
    print("Embedded contract wheel import and standalone source generation verified.")


if __name__ == "__main__":
    main()
