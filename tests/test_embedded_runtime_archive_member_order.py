"""Exercise real tar extraction order without relying on a new Python default filter.
验证真实 tar 提取顺序，不依赖新版 Python 的默认过滤器。
"""

from __future__ import annotations

from contextlib import contextmanager
import errno
import hashlib
import io
import os
from pathlib import Path
import sys
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

# Bind test imports to this checkout's actual product source, matching the existing embedded tests.
# 将测试导入绑定到此检出的实际产品源码，与既有嵌入测试保持一致。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from luaskills.runtime_assets import extract_archive, validate_tar_members, validated_tar_members, verify_named_sha256


class RuntimeArchiveMemberOrderTests(unittest.TestCase):
    """Check original archive bytes through production preflight and extraction, including lawful links.
    通过生产预检及提取核验原归档字节，包括合法链接。
    """

    def make_archive(self, root: Path, entries: list[tuple[str, str, bytes | str]]) -> Path:
        """Write declared file/directory/link entries under root; return the real archive path.
        在 root 下写入声明的文件、目录、链接成员；返回真实归档路径。
        """
        # Bind one local archive to the declared ordered entries, with no download or implicit fixture.
        # 将单个本地归档绑定到声明的有序成员，不下载或隐式创建替代夹具。
        filename = root / 'members.tar.gz'
        with tarfile.open(filename, 'w:gz') as archive:
            for name, kind, contents in entries:
                # Describe exact archive metadata; use a restrictive directory mode to test deferred fixup.
                # 描述精确归档元数据；用受限目录权限验证延后属性设置。
                member = tarfile.TarInfo(name)
                member.mtime = 123456789
                if kind == 'file':
                    member.size = len(contents)
                    archive.addfile(member, io.BytesIO(contents))
                else:
                    member.type = {'directory': tarfile.DIRTYPE, 'symlink': tarfile.SYMTYPE, 'hardlink': tarfile.LNKTYPE}[kind]
                    member.mode = 0o500 if kind == 'directory' else 0o644
                    member.linkname = contents if kind != 'directory' else ''
                    archive.addfile(member)
        return filename

    @contextmanager
    def trusted_extraction(self):
        """Use real TarFile operations with the pre-3.14 trusted default; yield no replacement archive.
        使用真实 TarFile 操作及三点十四以前的可信默认行为；不提供替代归档。
        """
        # Capture the genuine opener before temporarily selecting the supported historical filter policy.
        # 在临时选择受支持的历史过滤策略前捕获真实打开入口。
        original_open = tarfile.open

        def retain_member(member: tarfile.TarInfo, destination: str) -> tarfile.TarInfo:
            """Return the original member under the trusted policy; destination is the standard filter context.
            在可信策略下返回原成员；destination 是标准过滤器上下文。
            """
            return member

        def open_trusted(*args, **kwargs):
            """Open the actual archive with args/kwargs and return it under the old trusted policy.
            按 args、kwargs 打开实际归档并在旧可信策略下返回。
            """
            # Python 3.10 without filter support ignores this attribute; newer versions use the same raw members.
            # 不支持过滤器的 Python 三点十忽略此属性；较新版本使用同样的原成员。
            archive = original_open(*args, **kwargs)
            archive.extraction_filter = retain_member
            return archive

        with patch('luaskills.runtime_assets.tarfile.open', side_effect=open_trusted):
            yield

    def require_symlinks(self, root: Path) -> None:
        """Probe an actual local directory symlink under root; skip only when the OS denies links.
        在 root 下探测真实本地目录符号链接；仅在操作系统拒绝链接时跳过。
        """
        # Keep the permission probe separate from archive validation and record its actual errno/winerror.
        # 将权限探测与归档校验分开，并记录实际 errno、winerror。
        link = root / 'permission-probe'
        try:
            os.symlink('.', link, target_is_directory=True)
        except OSError as error:
            # Skip only actual unsupported/permission cases; unrelated filesystem errors must fail visibly.
            # 仅跳过实际不支持、权限情形；其它文件系统错误必须显式失败。
            if error.errno not in {errno.EPERM, errno.EACCES, errno.ENOSYS} and getattr(error, 'winerror', None) != 1314:
                raise
            self.skipTest(f'actual symlink unavailable: errno={error.errno}, winerror={getattr(error, "winerror", None)}')
        else:
            link.unlink()

    def test_parent_member_rejected_by_real_preflight_after_checksum(self) -> None:
        """Reject a/../owned after a -> . despite a valid checksum, without requiring link privileges.
        即使校验和有效也拒绝 a 指向点目录后出现的 a/../owned，无需链接权限。
        """
        with TemporaryDirectory() as temporary:
            # Freeze ordered original bytes and the matching named sidecar before invoking production checks.
            # 在调用生产检查前冻结有序原字节及匹配的具名旁路校验和。
            root = Path(temporary)
            filename = self.make_archive(root, [('a', 'symlink', '.'), ('a/../owned', 'file', b'outside')])
            checksum = hashlib.sha256(filename.read_bytes()).hexdigest()
            verify_named_sha256(filename, f'{checksum}  {filename.name}\n', filename.name)
            with tarfile.open(filename) as archive:
                with self.assertRaisesRegex(ValueError, 'archive member escapes extraction directory'):
                    validate_tar_members(root / 'extract', archive)
            self.assertFalse((root / 'owned').exists())

    def test_backslash_parent_member_rejected_before_normalization(self) -> None:
        """Reject a Windows parent component on every supported host before pathname normalization.
        在每个受支持宿主上于路径规范化前拒绝 Windows 父组件。
        """
        with TemporaryDirectory() as temporary:
            # Use a real archive member with the Windows separator, independent of the local OS spelling.
            # 使用含 Windows 分隔符的真实成员，不依赖本机操作系统路径写法。
            root = Path(temporary)
            filename = self.make_archive(root, [(r'a\..\owned', 'file', b'outside')])
            with self.assertRaisesRegex(ValueError, 'archive member escapes extraction directory'):
                extract_archive(filename, root / 'extract')

    def test_live_alias_target_escape_rejected(self) -> None:
        """Reject the second a/b -> .. after the first real a -> . has changed path resolution.
        在第一个真实 a 指向点目录改变路径解析后拒绝第二个 a/b 指向父目录。
        """
        with TemporaryDirectory() as temporary:
            # This case requires a real link, so lack of Windows privilege is an explicit dynamic limitation.
            # 此用例需要真实链接，因此缺少 Windows 权限是明确的动态验证限制。
            root = Path(temporary)
            self.require_symlinks(root)
            filename = self.make_archive(root, [('a', 'symlink', '.'), ('a/b', 'symlink', '..'), ('a/b/owned', 'file', b'outside')])
            with tarfile.open(filename) as archive:
                validate_tar_members(root / 'extract', archive)
            with self.trusted_extraction(), self.assertRaisesRegex(ValueError, 'archive member escapes extraction directory'):
                extract_archive(filename, root / 'extract')
            self.assertFalse((root / 'owned').exists())
            self.assertFalse((root / 'extract' / 'b').is_symlink())

    def test_hardlink_to_symbolic_member_rejected_before_extraction(self) -> None:
        """Reject a hardlink whose original fallback member is a symlink, without creating any link.
        拒绝原回退成员是符号链接的硬链接，不创建任何链接。
        """
        with TemporaryDirectory() as temporary:
            # A safe-looking target still has unsafe fallback semantics when replayed at a different location.
            # 表面安全的目标在不同位置回放时仍具有不安全的回退语义。
            root = Path(temporary)
            filename = self.make_archive(root, [('file', 'file', b'original'), ('alias', 'symlink', 'file'), ('copy', 'hardlink', 'alias')])
            with self.assertRaisesRegex(ValueError, 'hardlink target must be a prior regular file'):
                extract_archive(filename, root / 'extract')
            self.assertFalse((root / 'extract' / 'file').exists())

    def test_duplicate_target_last_prior_member_is_authoritative(self) -> None:
        """Reject a regular name overwritten by a symlink before a hardlink refers to that name.
        拒绝常规名称在硬链接引用之前被符号链接覆盖的归档。
        """
        with TemporaryDirectory() as temporary:
            # Standard tar lookup searches backward before the hardlink; an earlier regular entry is not enough.
            # 标准 tar 查找在硬链接前向后搜索；更早的常规成员并不足够。
            root = Path(temporary)
            filename = self.make_archive(root, [('file', 'file', b'original'), ('file', 'symlink', 'other'), ('copy', 'hardlink', 'file')])
            with self.assertRaisesRegex(ValueError, 'hardlink target must be a prior regular file'):
                extract_archive(filename, root / 'extract')

    def test_missing_prior_hardlink_target_rejected(self) -> None:
        """Reject forward hardlink fallback before any file is extracted, on hosts without symlink privileges too.
        在任何文件提取前拒绝前向硬链接回退，缺少符号链接权限的宿主也执行此检查。
        """
        with TemporaryDirectory() as temporary:
            # The target appears only later, so there is no prior archive authority for a hardlink.
            # 目标仅在后面出现，因此没有硬链接的先前归档权威。
            root = Path(temporary)
            filename = self.make_archive(root, [('copy', 'hardlink', 'file'), ('file', 'file', b'original')])
            with self.assertRaisesRegex(ValueError, 'hardlink target must be a prior regular file'):
                extract_archive(filename, root / 'extract')
            self.assertFalse((root / 'extract' / 'file').exists())

    def test_regular_files_and_directory_metadata_preserved(self) -> None:
        """Extract child bytes before applying original parent directory metadata.
        在应用原父目录元数据前提取子文件字节。
        """
        with TemporaryDirectory() as temporary:
            # Preserve an actual nested file and the original directory mtime under the production extractor.
            # 在生产提取器下保留实际嵌套文件及原目录修改时间。
            root = Path(temporary)
            filename = self.make_archive(root, [('folder', 'directory', ''), ('folder/file', 'file', b'original')])
            with self.trusted_extraction():
                extract_archive(filename, root / 'extract')
            self.assertEqual((root / 'extract' / 'folder' / 'file').read_bytes(), b'original')
            self.assertEqual(int((root / 'extract' / 'folder').stat().st_mtime), 123456789)

    def test_safe_relative_symlink_preflight_needs_no_os_privilege(self) -> None:
        """Accept the lawful parent-relative target in production preflight even without symlink privileges.
        即使缺少符号链接权限，生产预检也接受合法父目录相对目标。
        """
        with TemporaryDirectory() as temporary:
            # Preflight only inspects original archive entries, so this positive case must never be skipped.
            # 预检仅检查原归档成员，因此此正例不得跳过。
            root = Path(temporary)
            filename = self.make_archive(root, [('file', 'file', b'original'), ('folder/link', 'symlink', '../file')])
            with tarfile.open(filename) as archive:
                validate_tar_members(root / 'extract', archive)

    def test_hardlink_rechecks_actual_regular_target_before_yield(self) -> None:
        """Reject a vanished actual target after real extraction despite the prior regular archive authority.
        即使先前常规归档来源有效，也在真实提取后拒绝消失的实际目标。
        """
        with TemporaryDirectory() as temporary:
            # Run the first member through genuine extractall, then remove only that test-owned file.
            # 用真实 extractall 提取第一个成员，随后仅移除此测试拥有的文件。
            root = Path(temporary)
            filename = self.make_archive(root, [('file', 'file', b'original'), ('copy', 'hardlink', 'file')])
            destination = root / 'extract'
            with tarfile.open(filename) as archive:
                validate_tar_members(destination, archive)
                members = validated_tar_members(destination, archive)
                archive.extractall(destination, members=[next(members)])
                (destination / 'file').unlink()
                with self.assertRaisesRegex(ValueError, 'hardlink target is not an extracted regular file'):
                    next(members)
            self.assertFalse((destination / 'copy').exists())

    def test_real_regular_hardlink_preserved(self) -> None:
        """Keep a real hardlink to an already extracted regular file and its original bytes.
        保留指向已经提取的常规文件的真实硬链接及其原字节。
        """
        with TemporaryDirectory() as temporary:
            # Full preflight must not require the physical target before the real first member is extracted.
            # 完整预检不得在真实第一个成员提取前要求物理目标已存在。
            root = Path(temporary)
            filename = self.make_archive(root, [('file', 'file', b'original'), ('copy', 'hardlink', 'file')])
            with tarfile.open(filename) as archive:
                validate_tar_members(root / 'extract', archive)
            with self.trusted_extraction():
                extract_archive(filename, root / 'extract')
            self.assertEqual((root / 'extract' / 'copy').read_bytes(), b'original')
            self.assertTrue(os.path.samefile(root / 'extract' / 'file', root / 'extract' / 'copy'))

    def test_real_regular_hardlink_chain_preserved(self) -> None:
        """Preserve a real hardlink-to-hardlink-to-regular chain with the same inode and original bytes.
        保留真实硬链接到硬链接再到常规文件的链，维持相同 inode 及原字节。
        """
        with TemporaryDirectory() as temporary:
            # Each link captures its prior reference while genuine extraction establishes the physical chain.
            # 每个链接捕获先前引用，并通过真实提取建立物理链。
            root = Path(temporary)
            filename = self.make_archive(root, [('file', 'file', b'original'), ('first', 'hardlink', 'file'),
                                                ('second', 'hardlink', 'first')])
            with self.trusted_extraction():
                extract_archive(filename, root / 'extract')
            self.assertEqual((root / 'extract' / 'second').read_bytes(), b'original')
            self.assertTrue(os.path.samefile(root / 'extract' / 'file', root / 'extract' / 'first'))
            self.assertTrue(os.path.samefile(root / 'extract' / 'first', root / 'extract' / 'second'))

    def test_nested_hardlink_fallback_rejects_later_symbolic_override(self) -> None:
        """Reject later symbolic replacement of the original chain target, before any OS links are created.
        在创建任何系统链接前拒绝原链目标后来被符号链接替换的情况。
        """
        with TemporaryDirectory() as temporary:
            # The first link retains its original file reference; looking up only the final first name is insufficient.
            # 第一个链接保留原文件引用；仅查最终 first 名称并不足够。
            root = Path(temporary)
            filename = self.make_archive(root, [('file', 'file', b'original'), ('first', 'hardlink', 'file'),
                                                ('file', 'symlink', '.'), ('second', 'hardlink', 'first')])
            with self.assertRaisesRegex(ValueError, 'hardlink fallback target is no longer a regular file: file'):
                extract_archive(filename, root / 'extract')
            self.assertFalse((root / 'extract' / 'file').exists())

    def test_safe_relative_file_and_directory_symlinks_preserved(self) -> None:
        """Keep real directory and file symlinks, including a lawful parent-relative target inside the root.
        保留真实目录及文件符号链接，包括在根内的合法父目录相对目标。
        """
        with TemporaryDirectory() as temporary:
            # Both links must remain actual links rather than standard-library permission fallbacks to copies.
            # 两个链接必须保持真实链接，不能把标准库权限回退副本当成符号链接。
            root = Path(temporary)
            self.require_symlinks(root)
            filename = self.make_archive(root, [('folder', 'directory', ''), ('file', 'file', b'original'),
                                                ('folder/link', 'symlink', '../file'), ('alias', 'symlink', 'folder')])
            with self.trusted_extraction():
                extract_archive(filename, root / 'extract')
            self.assertTrue((root / 'extract' / 'folder' / 'link').is_symlink())
            self.assertTrue((root / 'extract' / 'alias').is_symlink())
            self.assertEqual((root / 'extract' / 'alias' / 'link').read_bytes(), b'original')

    def test_extraction_symlink_separator_copy_preserves_archive_metadata(self) -> None:
        """Normalize only the extraction symlink copy on Windows without modifying original archive metadata.
        仅在 Windows 规范化提取符号链接副本，不修改原归档元数据。
        """
        with TemporaryDirectory() as temporary:
            # Inspect the actual production iterator before OS extraction, so this regression needs no link privilege.
            # 在系统提取前检查实际生产迭代器，因此此回归不需要链接权限。
            root = Path(temporary)
            filename = self.make_archive(root, [('file', 'file', b'original'), ('folder/link', 'symlink', '../file')])
            with tarfile.open(filename) as archive:
                # Keep the original TarInfo identity and its metadata independently of the yielded extraction view.
                # 将原 TarInfo 身份及其元数据与交出的提取视图独立保存。
                # Select the declared link by its archive name rather than a member position that could move.
                # 按声明的归档名称选择链接，不绑定可能移动的成员位置。
                original = archive.getmember('folder/link')
                metadata = original.get_info()
                members = validated_tar_members(root / 'extract', archive)
                next(members)
                extracted = next(members)
                self.assertEqual(original.get_info(), metadata)
                self.assertEqual(original.linkname, '../file')
                self.assertEqual(extracted.name, original.name)
                self.assertEqual(extracted.type, original.type)
                self.assertEqual(extracted.mtime, original.mtime)
                if os.name == 'nt':
                    self.assertIsNot(extracted, original)
                    self.assertEqual(extracted.linkname, '..' + os.sep + 'file')
                else:
                    self.assertIs(extracted, original)
                    self.assertEqual(extracted.linkname, '../file')


if __name__ == '__main__':
    unittest.main()
