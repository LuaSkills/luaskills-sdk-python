"""
Runtime installer core-series resolution and archive contract digest tests, all offline.
运行时安装器核心系列解析及归档契约摘要测试，全部离线执行。
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import sys
import tarfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

# Make the source package importable when tests run from one checkout.
# 从检出目录运行测试时让源码包可导入。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from luaskills import runtime_assets
from luaskills.embedded_contract import EMBEDDED_CONTRACT_SHA256, EMBEDDED_CORE_SERIES
from luaskills.runtime_assets import DEFAULT_LUASKILLS_SERIES, build_runtime_install_manifest, install_one_asset


class FakeReleaseListing(io.BytesIO):
    """
    Serve one fixed GitHub release listing as the `urlopen` context manager, recording each request URL.
    以 `urlopen` 上下文管理器形式提供固定的 GitHub release 列表，并记录每个请求地址。
    """

    def __enter__(self) -> "FakeReleaseListing":
        """Return this readable listing."""
        return self

    def __exit__(self, *_: object) -> None:
        """Close nothing; the buffer is discarded with the test."""


def fake_listing(releases: list[dict[str, object]], requests: list[str]):
    """
    Return an `urlopen` replacement that answers every request with releases and records its URL.
    返回 `urlopen` 替身：对每个请求返回 releases 并记录其地址。
    """

    def opener(request: object) -> FakeReleaseListing:
        requests.append(getattr(request, "full_url", str(request)))
        return FakeReleaseListing(json.dumps(releases).encode("utf-8"))

    return opener


class RuntimeCoreSeriesTests(unittest.TestCase):
    """
    Verify the default core series, explicit-tag membership and the archive contract digest gate.
    验证默认核心系列、显式标签归属及归档契约摘要门禁。
    """

    def series_tag(self, patch_number: int) -> str:
        """Return the exact tag of one patch inside the SDK core series."""
        return f"v{DEFAULT_LUASKILLS_SERIES}.{patch_number}"

    def test_default_series_mirrors_the_packaged_contract(self) -> None:
        """
        Require the installer series to equal the generated contract series, the only authority for compatibility.
        要求安装器系列等于生成契约系列，后者是兼容性的唯一权威。
        """

        self.assertEqual(DEFAULT_LUASKILLS_SERIES, EMBEDDED_CORE_SERIES)

    def test_default_resolves_newest_published_patch_of_the_series(self) -> None:
        """
        Pick the highest numeric patch, skipping drafts, prereleases, other series and non-semver tags.
        选择数值最高的补丁版本，跳过草稿、预发布、其他系列及非语义化标签。
        """

        major, minor = (int(part) for part in DEFAULT_LUASKILLS_SERIES.split("."))
        releases = [
            {"tag_name": self.series_tag(2), "draft": False, "prerelease": False},
            {"tag_name": self.series_tag(10), "draft": False, "prerelease": False},
            {"tag_name": self.series_tag(11), "draft": True, "prerelease": False},
            {"tag_name": self.series_tag(12), "draft": False, "prerelease": True},
            {"tag_name": f"v{major}.{minor + 1}.0", "draft": False, "prerelease": False},
            {"tag_name": f"v{major + 1}.{minor}.99", "draft": False, "prerelease": False},
            {"tag_name": "lua-deps-2026-11-01", "draft": False, "prerelease": False},
            {"tag_name": self.series_tag(9), "draft": False, "prerelease": False},
        ]
        requests: list[str] = []
        with TemporaryDirectory() as temporary_text, \
                patch.object(runtime_assets.urllib.request, "urlopen", side_effect=fake_listing(releases, requests)):
            manifest = build_runtime_install_manifest(runtime_root=temporary_text, lua_runtime_version="v0.1.6")
        (asset,) = [item for item in manifest["assets"] if item["role"] == "luaskills_ffi"]
        self.assertEqual(asset["version"], self.series_tag(10))
        self.assertIn(f"/releases/download/{self.series_tag(10)}/", asset["download_url"])
        self.assertEqual(requests, ["https://api.github.com/repos/LuaSkills/luaskills/releases?per_page=100"])

    def test_default_series_without_published_patch_fails(self) -> None:
        """
        Fail explicitly when the series has no published final release, without trying an older series.
        系列内没有已发布正式版本时明确失败，不尝试更旧的系列。
        """

        major, minor = (int(part) for part in DEFAULT_LUASKILLS_SERIES.split("."))
        releases = [
            {"tag_name": self.series_tag(0), "draft": True, "prerelease": False},
            {"tag_name": f"v{major}.{max(minor - 1, 0)}.5" if minor else f"v{max(major - 1, 0)}.9.5", "draft": False, "prerelease": False},
        ]
        with TemporaryDirectory() as temporary_text, \
                patch.object(runtime_assets.urllib.request, "urlopen", side_effect=fake_listing(releases, [])), \
                self.assertRaisesRegex(ValueError, "no published release found in series"):
            build_runtime_install_manifest(runtime_root=temporary_text, lua_runtime_version="v0.1.6")

    def test_explicit_tag_inside_series_is_used_without_listing(self) -> None:
        """
        Use an explicit in-series tag as given and never query the release listing.
        原样使用系列内显式标签，且不查询 release 列表。
        """

        with TemporaryDirectory() as temporary_text, \
                patch.object(runtime_assets.urllib.request, "urlopen", side_effect=AssertionError("unexpected network")):
            manifest = build_runtime_install_manifest(
                runtime_root=temporary_text, luaskills_version=self.series_tag(4), lua_runtime_version="v0.1.6")
        (asset,) = [item for item in manifest["assets"] if item["role"] == "luaskills_ffi"]
        self.assertEqual(asset["version"], self.series_tag(4))

    def test_explicit_tag_outside_series_is_rejected_before_network(self) -> None:
        """
        Reject other series and inexact tags before any listing or download.
        在任何列表查询或下载前拒绝其他系列及非精确标签。
        """

        major, minor = (int(part) for part in DEFAULT_LUASKILLS_SERIES.split("."))
        for tag in (f"v{major}.{minor + 1}.0", f"v{major + 1}.{minor}.0", "v0.8.2" if DEFAULT_LUASKILLS_SERIES != "0.8" else "v0.7.0",
                    f"v{DEFAULT_LUASKILLS_SERIES}", f"{DEFAULT_LUASKILLS_SERIES}.0", f"v{DEFAULT_LUASKILLS_SERIES}.0-rc.1",
                    f"v{DEFAULT_LUASKILLS_SERIES}.01"):
            with self.subTest(tag=tag), TemporaryDirectory() as temporary_text, \
                    patch.object(runtime_assets.urllib.request, "urlopen", side_effect=AssertionError("unexpected network")), \
                    self.assertRaisesRegex(ValueError, "outside the SDK core series"):
                build_runtime_install_manifest(runtime_root=temporary_text, luaskills_version=tag, lua_runtime_version="v0.1.6")

    def install_fixture_archive(self, runtime_root: Path, digest_text: str | None) -> None:
        """
        Build one FFI archive with the given contract digest file (None omits it) and install it offline.
        构造带有指定契约摘要文件（None 表示省略）的 FFI 归档，并离线安装。
        """

        target = runtime_assets.resolve_runtime_platform_target()
        library_name = target["luaskills_library_name"]
        members = {f"lib/{library_name}": b"fixture library", "include/luaskills_ffi.h": b"/* fixture */\n"}
        if digest_text is not None:
            members["contracts/embedded/v1/contract.sha256"] = digest_text.encode("utf-8")
        archive_bytes = io.BytesIO()
        with tarfile.open(fileobj=archive_bytes, mode="w:gz") as archive:
            for name, content in members.items():
                info = tarfile.TarInfo(name)
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
        payload = archive_bytes.getvalue()
        asset = runtime_assets.release_asset(
            "luaskills_ffi", "LuaSkills/luaskills", self.series_tag(3),
            f"luaskills-ffi-sdk-{target['platform_key']}.tar.gz", f"libs/{library_name}")

        def retrieve(_url: str, destination: Path) -> None:
            Path(destination).write_bytes(payload)

        sidecar = f"{hashlib.sha256(payload).hexdigest()}  {asset['asset_name']}\n"
        with TemporaryDirectory() as temporary_text, \
                patch.object(runtime_assets, "download_text", return_value=sidecar), \
                patch.object(runtime_assets.urllib.request, "urlretrieve", side_effect=retrieve):
            install_one_asset(runtime_root, asset, Path(temporary_text), target)

    def test_archive_with_matching_contract_digest_installs(self) -> None:
        """
        Install an archive whose contract digest equals the SDK contract digest.
        安装契约摘要等于 SDK 契约摘要的归档。
        """

        with TemporaryDirectory() as temporary_text:
            runtime_root = Path(temporary_text)
            self.install_fixture_archive(runtime_root, f"{EMBEDDED_CONTRACT_SHA256}  contract.json\n")
            library_name = runtime_assets.resolve_runtime_platform_target()["luaskills_library_name"]
            self.assertTrue((runtime_root / "libs" / library_name).is_file())

    def test_archive_contract_digest_mismatch_is_rejected_before_install(self) -> None:
        """
        Reject a different, malformed or missing archive contract digest before any file reaches the runtime root.
        在任何文件进入运行时根之前，拒绝不同、格式错误或缺失的归档契约摘要。
        """

        other = "0" * 64 if EMBEDDED_CONTRACT_SHA256 != "0" * 64 else "1" * 64
        for digest_text, message in (
            (f"{other}  contract.json\n", "does not match this SDK's contract"),
            (f"{EMBEDDED_CONTRACT_SHA256}  other.json\n", "malformed contract digest"),
            ("not-a-digest  contract.json\n", "malformed contract digest"),
            (None, "does not contain contracts/embedded/v1/contract.sha256"),
        ):
            with self.subTest(digest_text=digest_text), TemporaryDirectory() as temporary_text:
                runtime_root = Path(temporary_text) / "runtime"
                runtime_root.mkdir()
                with self.assertRaisesRegex(ValueError, message):
                    self.install_fixture_archive(runtime_root, digest_text)
                self.assertEqual(list(runtime_root.iterdir()), [])
                shutil.rmtree(runtime_root)


if __name__ == "__main__":
    unittest.main()
