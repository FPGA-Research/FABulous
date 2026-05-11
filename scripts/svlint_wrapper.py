#!/usr/bin/env python3
"""Download-and-exec wrapper for a pinned svlint release.

Downloads the pinned svlint archive into a user cache on first call, then execs
svlint with the original arguments.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

if platform.system() != "Windows":
    import fcntl
else:
    fcntl = None  # type: ignore[assignment]

SVLINT_VERSION = "v0.9.5"
RELEASE_API_URL = (
    "https://api.github.com/repos/dalance/svlint/releases/tags/" + SVLINT_VERSION
)

PLATFORM_TOKENS = {
    "Linux": ("lnx",),
    "Darwin": ("mac",),
    "Windows": ("win",),
}

ARCH_TOKENS = {
    "x86_64": ("x86_64", "amd64"),
    "AMD64": ("x86_64", "amd64"),
    "aarch64": ("aarch64", "arm64"),
    "arm64": ("aarch64", "arm64"),
}

DOWNLOAD_ATTEMPTS = 5
DOWNLOAD_BACKOFF_SECONDS = 2.0
# HTTP status codes that indicate a transient failure worth retrying.
TRANSIENT_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


def cache_dir() -> Path:
    """Return the per-version cache directory for the pinned svlint release."""
    root = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(root) / "fabulous-svlint" / SVLINT_VERSION


def platform_asset_tokens() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return platform and architecture tokens for the current machine."""
    system = platform.system()
    machine = platform.machine()
    if system not in PLATFORM_TOKENS:
        sys.exit(f"svlint_wrapper: unsupported platform {system}")
    if machine not in ARCH_TOKENS:
        sys.exit(f"svlint_wrapper: unsupported architecture {machine}")
    return PLATFORM_TOKENS[system], ARCH_TOKENS[machine]


def pick_asset(assets: list[dict[str, object]]) -> str:
    """Choose the release asset matching the current platform and architecture."""
    platform_tokens, arch_tokens = platform_asset_tokens()
    for asset in assets:
        name = str(asset.get("name", "")).lower()
        url = asset.get("browser_download_url")
        if not isinstance(url, str):
            continue
        if "svlint" not in name:
            continue
        if not any(token in name for token in platform_tokens):
            continue
        if not any(token in name for token in arch_tokens):
            continue
        if name.endswith((".zip", ".tar.gz", ".tgz")):
            return url
    sys.exit("svlint_wrapper: no release asset matches this platform")


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    """Serialize concurrent callers (e.g. parallel pre-commit hooks)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if fcntl is None:
        # Windows: skip locking. Concurrent first-run installs may race, but
        # the atomic rename in download() keeps the installed tree consistent.
        yield
        return
    with path.open("w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def fetch_json(url: str) -> dict[str, object]:
    """Fetch a JSON document, retrying transient errors."""
    last_exc: Exception | None = None
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        msg = f"svlint_wrapper: fetching {url} "
        msg += f"(attempt {attempt}/{DOWNLOAD_ATTEMPTS})\n"
        sys.stderr.write(msg)
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_exc = e
            if e.code not in TRANSIENT_STATUSES:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_exc = e
        time.sleep(DOWNLOAD_BACKOFF_SECONDS * (2 ** (attempt - 1)))
    raise RuntimeError(
        f"svlint_wrapper: fetch failed after {DOWNLOAD_ATTEMPTS} attempts: {last_exc}",
    )


def fetch_archive(url: str, dest_dir: Path) -> Path:
    """Download ``url`` to a temp file under ``dest_dir``, retrying transient errors."""
    last_exc: Exception | None = None
    suffix = ".zip" if url.endswith(".zip") else ".tar.gz"
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        msg = f"svlint_wrapper: downloading {url} "
        msg += f"(attempt {attempt}/{DOWNLOAD_ATTEMPTS})\n"
        sys.stderr.write(msg)
        try:
            with (
                urllib.request.urlopen(url, timeout=60) as resp,
                tempfile.NamedTemporaryFile(
                    delete=False, dir=dest_dir, suffix=suffix
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
        f"svlint_wrapper: download failed after "
        f"{DOWNLOAD_ATTEMPTS} attempts: {last_exc}",
    )


def extract_archive(archive: Path, dest: Path) -> None:
    """Extract a release archive into ``dest``."""
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest)
    else:
        with tarfile.open(archive) as tar:
            tar.extractall(dest, filter="data")


def download(dest: Path) -> None:
    """Fetch the svlint release archive and extract it into ``dest`` atomically."""
    release = fetch_json(RELEASE_API_URL)
    assets = release.get("assets")
    if not isinstance(assets, list):
        sys.exit("svlint_wrapper: release response does not contain assets")
    url = pick_asset(assets)
    dest.parent.mkdir(parents=True, exist_ok=True)
    archive = fetch_archive(url, dest.parent)
    staging = Path(tempfile.mkdtemp(dir=dest.parent, prefix=".staging-"))
    try:
        extract_archive(archive, staging)
        staging.rename(dest)
    finally:
        archive.unlink(missing_ok=True)
        shutil.rmtree(staging, ignore_errors=True)


def find_cached_binary(prefix: Path) -> Path | None:
    """Return the cached svlint binary if it exists."""
    binary_name = "svlint.exe" if platform.system() == "Windows" else "svlint"
    direct = prefix / "bin" / binary_name
    if direct.exists():
        return direct
    matches = list(prefix.glob(f"**/bin/{binary_name}")) + list(
        prefix.glob(f"**/{binary_name}")
    )
    return matches[0] if matches else None


def ensure_executable(binary: Path) -> Path:
    """Restore execute permission on a cached binary before running it."""
    if platform.system() != "Windows":
        binary.chmod(binary.stat().st_mode | 0o111)
    return binary


def ensure_bin() -> Path:
    """Return the path to svlint, downloading and installing it if missing."""
    system = shutil.which("svlint")
    if system:
        return Path(system)
    prefix = cache_dir() / "install"
    binary = find_cached_binary(prefix)
    if binary:
        return ensure_executable(binary)
    with file_lock(cache_dir() / ".lock"):
        binary = find_cached_binary(prefix)
        if not binary:
            download(prefix)
            binary = find_cached_binary(prefix)
    if not binary:
        sys.exit(f"svlint_wrapper: svlint not found after install in {prefix}")
    return ensure_executable(binary)


def main() -> None:
    """Resolve svlint then exec it with the original argv."""
    binary = ensure_bin()
    os.execv(str(binary), [str(binary), *sys.argv[1:]])


if __name__ == "__main__":
    main()
