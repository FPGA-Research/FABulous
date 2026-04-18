#!/usr/bin/env python3
"""Wrapper that downloads a pinned Verible release into a user cache on first
call, then execs the requested Verible tool with the remaining arguments.
"""

from __future__ import annotations

import fcntl
import os
import platform
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

VERIBLE_VERSION = "v0.0-4053-g89d4d98a"
RELEASE_URL = (
    "https://github.com/chipsalliance/verible/releases/download/"
    f"{VERIBLE_VERSION}/verible-{VERIBLE_VERSION}-{{asset}}"
)

ASSETS = {
    ("Linux", "x86_64"): "linux-static-x86_64.tar.gz",
    ("Linux", "aarch64"): "linux-static-arm64.tar.gz",
    ("Linux", "arm64"): "linux-static-arm64.tar.gz",
    ("Darwin", "x86_64"): "macOS.tar.gz",
    ("Darwin", "arm64"): "macOS.tar.gz",
}


def cache_dir() -> Path:
    root = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(root) / "fabulous-verible" / VERIBLE_VERSION


def asset_name() -> str:
    key = (platform.system(), platform.machine())
    if key not in ASSETS:
        sys.exit(f"verible_wrapper: unsupported platform {key}")
    return ASSETS[key]


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    """Serialize concurrent callers (e.g. parallel pre-commit hooks)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def download(dest: Path) -> None:
    url = RELEASE_URL.format(asset=asset_name())
    dest.parent.mkdir(parents=True, exist_ok=True)
    sys.stderr.write(f"verible_wrapper: downloading {url}\n")
    with (
        urllib.request.urlopen(url) as resp,
        tempfile.NamedTemporaryFile(
            delete=False, dir=dest.parent, suffix=".tar.gz"
        ) as tmp,
    ):
        shutil.copyfileobj(resp, tmp)
        tmp_path = Path(tmp.name)
    staging = Path(tempfile.mkdtemp(dir=dest.parent, prefix=".staging-"))
    try:
        with tarfile.open(tmp_path) as tar:
            tar.extractall(staging, filter="data")
        tmp_path.unlink()
        extracted = next(staging.glob(f"verible-{VERIBLE_VERSION}*"))
        extracted.rename(dest)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def ensure_bin(tool: str) -> Path:
    prefix = cache_dir() / "install"
    binary = prefix / "bin" / tool
    if binary.exists():
        return binary
    with file_lock(cache_dir() / ".lock"):
        if not binary.exists():
            download(prefix)
    if not binary.exists():
        sys.exit(f"verible_wrapper: {tool} not found after install in {prefix}")
    return binary


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("verible_wrapper: expected tool name as first argument")
    tool, *rest = sys.argv[1:]
    binary = ensure_bin(tool)
    os.execv(str(binary), [str(binary), *rest])


if __name__ == "__main__":
    main()
