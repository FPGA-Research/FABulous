#!/usr/bin/env python3
"""Download-and-exec wrapper for a pinned Verible release.

Downloads the pinned Verible tarball into a user cache on first call, then
execs the requested Verible tool with the remaining arguments.
"""

from __future__ import annotations

import fcntl
import os
import platform
import shutil
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

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

DOWNLOAD_ATTEMPTS = 5
DOWNLOAD_BACKOFF_SECONDS = 2.0
# HTTP status codes that indicate a transient failure worth retrying.
TRANSIENT_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


def cache_dir() -> Path:
    """Return the per-version cache directory for the pinned Verible release."""
    root = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(root) / "fabulous-verible" / VERIBLE_VERSION


def asset_name() -> str:
    """Return the release asset filename for the current platform/arch."""
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


def fetch_tarball(url: str, dest_dir: Path) -> Path:
    """Download ``url`` to a temp file under ``dest_dir``, retrying transient errors."""
    last_exc: Exception | None = None
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        msg = f"verible_wrapper: downloading {url} "
        msg += f"(attempt {attempt}/{DOWNLOAD_ATTEMPTS})\n"
        sys.stderr.write(msg)
        try:
            with (
                urllib.request.urlopen(url, timeout=60) as resp,
                tempfile.NamedTemporaryFile(
                    delete=False, dir=dest_dir, suffix=".tar.gz"
                ) as tmp,
            ):
                shutil.copyfileobj(resp, tmp)
                return Path(tmp.name)
        except urllib.error.HTTPError as e:
            last_exc = e
            if e.code not in TRANSIENT_STATUSES:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_exc = e
        time.sleep(DOWNLOAD_BACKOFF_SECONDS * (2 ** (attempt - 1)))
    raise RuntimeError(
        f"verible_wrapper: download failed after "
        f"{DOWNLOAD_ATTEMPTS} attempts: {last_exc}",
    )


def download(dest: Path) -> None:
    """Fetch the Verible tarball and extract it into ``dest`` atomically."""
    url = RELEASE_URL.format(asset=asset_name())
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = fetch_tarball(url, dest.parent)
    staging = Path(tempfile.mkdtemp(dir=dest.parent, prefix=".staging-"))
    try:
        with tarfile.open(tmp_path) as tar:
            tar.extractall(staging, filter="data")
        matches = list(staging.glob(f"verible-{VERIBLE_VERSION}*"))
        if not matches:
            sys.exit(
                f"verible_wrapper: extracted archive does not contain "
                f"verible-{VERIBLE_VERSION}*",
            )
        matches[0].rename(dest)
    finally:
        tmp_path.unlink(missing_ok=True)
        shutil.rmtree(staging, ignore_errors=True)


def ensure_bin(tool: str) -> Path:
    """Return the path to ``tool``, downloading and installing it if missing."""
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
    """Resolve the requested Verible tool then exec it with the remaining argv."""
    if len(sys.argv) < 2:
        sys.exit("verible_wrapper: expected tool name as first argument")
    tool, *rest = sys.argv[1:]
    binary = ensure_bin(tool)
    os.execv(str(binary), [str(binary), *rest])


if __name__ == "__main__":
    main()
