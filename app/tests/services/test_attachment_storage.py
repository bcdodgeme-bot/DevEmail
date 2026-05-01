"""
Tests for app/services/attachment_storage.py.

Pure-Python: no DB. Each test gets a fresh tmp directory via the standard
tmp_path fixture, with settings.ATTACHMENT_STORAGE_DIR monkey-patched to
that directory.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture
def storage_dir(tmp_path, monkeypatch):
    """Fresh isolated storage root per test, plumbed via settings."""
    from app.config import settings
    monkeypatch.setattr(settings, "ATTACHMENT_STORAGE_DIR", str(tmp_path))
    return tmp_path


class TestSaveBytes:
    async def test_writes_file_and_returns_relative_path(self, storage_dir):
        from app.services.attachment_storage import save_bytes

        rec = await save_bytes(b"hello world", content_type="text/plain", filename="hi.txt")

        assert rec.size_bytes == len(b"hello world")
        assert rec.content_type == "text/plain"
        assert rec.filename == "hi.txt"
        # storage_path is relative — no leading slash, no '..'.
        assert not os.path.isabs(rec.storage_path)
        assert ".." not in rec.storage_path

        on_disk = storage_dir / rec.storage_path
        assert on_disk.exists()
        assert on_disk.read_bytes() == b"hello world"

    async def test_creates_storage_dir_on_first_write(self, tmp_path, monkeypatch):
        from app.config import settings
        from app.services.attachment_storage import save_bytes

        new_dir = tmp_path / "deep" / "nested" / "attachments"
        assert not new_dir.exists()
        monkeypatch.setattr(settings, "ATTACHMENT_STORAGE_DIR", str(new_dir))

        await save_bytes(b"x", content_type="text/plain", filename="x.txt")
        assert new_dir.exists()

    async def test_each_save_uses_unique_uuid_path(self, storage_dir):
        from app.services.attachment_storage import save_bytes

        a = await save_bytes(b"a", content_type="text/plain", filename="a.txt")
        b = await save_bytes(b"b", content_type="text/plain", filename="b.txt")
        assert a.storage_path != b.storage_path

    async def test_bytes_required(self, storage_dir):
        from app.services.attachment_storage import save_bytes
        with pytest.raises(TypeError):
            await save_bytes("not bytes", content_type="text/plain", filename="x.txt")  # type: ignore[arg-type]

    async def test_default_content_type_when_blank(self, storage_dir):
        from app.services.attachment_storage import save_bytes
        rec = await save_bytes(b"x", content_type="", filename="x.bin")
        assert rec.content_type == "application/octet-stream"


class TestSanitization:
    @pytest.mark.parametrize("dirty,expected", [
        ("../../etc/passwd",          "passwd"),
        ("subdir/file.txt",           "file.txt"),
        ("..\\..\\winnt\\sys.dll",    "sys.dll"),
        ("file\x00name.txt",          "filename.txt"),
        ("with\rcontrol\nchars.pdf",  "withcontrolchars.pdf"),
        ("",                          "attachment"),
        (None,                        "attachment"),
        ("...",                       "attachment"),  # only dots -> default
        ("/",                         "attachment"),
        ("\\",                        "attachment"),
    ])
    async def test_sanitize(self, storage_dir, dirty, expected):
        from app.services.attachment_storage import save_bytes
        rec = await save_bytes(b"x", content_type="text/plain", filename=dirty)
        assert rec.filename == expected

    async def test_long_filename_truncated_with_extension(self, storage_dir):
        from app.services.attachment_storage import save_bytes
        long_stem = "a" * 300
        rec = await save_bytes(
            b"x", content_type="text/plain", filename=f"{long_stem}.pdf",
        )
        assert len(rec.filename) <= 255
        assert rec.filename.endswith(".pdf")


class TestReadBytes:
    async def test_round_trip(self, storage_dir):
        from app.services.attachment_storage import save_bytes, read_bytes
        rec = await save_bytes(b"payload", content_type="text/plain", filename="x.txt")
        assert await read_bytes(rec.storage_path) == b"payload"

    async def test_path_traversal_refused(self, storage_dir):
        from app.services.attachment_storage import read_bytes
        with pytest.raises(ValueError):
            await read_bytes("../../../etc/passwd")


class TestDelete:
    async def test_removes_file(self, storage_dir):
        from app.services.attachment_storage import save_bytes, delete
        rec = await save_bytes(b"x", content_type="text/plain", filename="x.txt")
        on_disk = storage_dir / rec.storage_path
        assert on_disk.exists()

        await delete(rec.storage_path)
        assert not on_disk.exists()

    async def test_silently_ignores_missing(self, storage_dir):
        from app.services.attachment_storage import delete
        # Should not raise even though the file doesn't exist.
        await delete("nonexistent-uuid")

    async def test_empty_path_is_noop(self, storage_dir):
        from app.services.attachment_storage import delete
        await delete(None)
        await delete("")

    async def test_path_traversal_refused_silently(self, storage_dir, caplog):
        from app.services.attachment_storage import delete
        # Should not raise (caller transactions stay safe), but should not
        # touch the filesystem outside the storage root.
        with caplog.at_level("WARNING"):
            await delete("../../etc/passwd")
        assert any("Refusing" in r.message for r in caplog.records)
