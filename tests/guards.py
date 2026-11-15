"""Test helpers that turn privacy claims into checks: no network connections, no file writes."""
import builtins
import contextlib
import io
import os
import socket
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

IGNORED_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules"}
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC


class ForbiddenOperation(AssertionError):
    pass


def _ignorable(path: object) -> bool:
    text = str(path)
    return text.endswith(".pyc") or "__pycache__" in text or text == os.devnull


@contextlib.contextmanager
def forbid_network() -> Iterator[list[str]]:
    """Any attempt to open a network connection is recorded and raises."""
    attempts: list[str] = []

    def blocked(self, address, *args):
        attempts.append(str(address))
        raise ForbiddenOperation(f"network connection attempted: {address}")

    with (
        mock.patch.object(socket.socket, "connect", blocked),
        mock.patch.object(socket.socket, "connect_ex", blocked),
    ):
        yield attempts


@contextlib.contextmanager
def forbid_file_writes() -> Iterator[list[str]]:
    """Any attempt to open a file for writing is recorded and raises. Bytecode caches are ignored."""
    attempts: list[str] = []
    real_open = builtins.open
    real_os_open = os.open

    def guarded_open(file, mode="r", *args, **kwargs):
        writing = any(flag in str(mode) for flag in "wax+")
        if writing and not isinstance(file, int) and not _ignorable(file):
            attempts.append(str(file))
            raise ForbiddenOperation(f"file write attempted: {file}")
        return real_open(file, mode, *args, **kwargs)

    def guarded_os_open(path, flags, *args, **kwargs):
        if flags & WRITE_FLAGS and not isinstance(path, int) and not _ignorable(path):
            attempts.append(str(path))
            raise ForbiddenOperation(f"file write attempted: {path}")
        return real_os_open(path, flags, *args, **kwargs)

    with (
        mock.patch.object(builtins, "open", guarded_open),
        mock.patch.object(io, "open", guarded_open),
        mock.patch.object(os, "open", guarded_os_open),
    ):
        yield attempts


def tree_snapshot(root: Path) -> dict[str, tuple[int, int]]:
    """Modification time and size of every file under root (ignoring caches), to detect any change."""
    snapshot: dict[str, tuple[int, int]] = {}
    for current, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if name not in IGNORED_DIRS]
        for name in files:
            path = Path(current) / name
            try:
                stat = path.stat()
            except OSError:
                continue
            snapshot[str(path)] = (stat.st_mtime_ns, stat.st_size)
    return snapshot
