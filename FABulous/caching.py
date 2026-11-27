"""Caching utilities for FABulous.

Provides:
- Cache: singleton file-backed cache (implemented via __new__)
- cache_with: dependency-aware caching decorator

Usage:
    # Initialize the cache directory
    Cache("/path/to/cache")

    # Use the decorator to cache a function
    @cache_with(files=lambda self: [self.config_path])
    def build(self):
        ...
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import pickle
from contextlib import contextmanager
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

import yaml
from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

# Sentinel value to distinguish cache misses from cached None
_CACHE_MISS = object()


class HashHelper:
    """Helper class for hashing files and parameters."""

    @staticmethod
    def hash_file_content(file_path: Path) -> str:
        """Return a SHA256 hash of a file's contents.

        Uses hashlib.file_digest() for efficient file hashing without
        loading the entire file into memory.

        Parameters
        ----------
        file_path : Path
            The path to the file to hash.

        Returns
        -------
        str
            The SHA256 hash as a hexadecimal string.

        Raises
        ------
        FileNotFoundError
            If the file does not exist.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with file_path.open("rb") as f:
            digest = hashlib.file_digest(f, "sha256")
        return digest.hexdigest()

    @staticmethod
    def hash_files(files: list[Path]) -> str:
        """Return a combined hash for a list of files.

        The files are sorted by path to ensure stable ordering.

        Parameters
        ----------
        files : list[Path]
            List of file paths to hash.

        Returns
        -------
        str
            The combined SHA256 hash as a hexadecimal string.
        """
        # unique files, stable order
        seen = set()
        unique: list[Path] = []
        for p in files:
            if p not in seen:
                seen.add(p)
                unique.append(p)

        h = hashlib.sha256()
        for p in sorted(unique, key=lambda x: str(x)):
            h.update(str(p).encode())
            h.update(HashHelper.hash_file_content(p).encode())
        return h.hexdigest()

    @staticmethod
    def hash_params(params: dict[str, Any] | None) -> str | None:
        """Return a stable hash for the provided params mapping.

        Returns None if params cannot be serialized, and emits a warning.

        Parameters
        ----------
        params : dict[str, Any] | None
            The parameters to hash.

        Returns
        -------
        str | None
            The SHA256 hash as a hexadecimal string, or None if serialization fails.
        """
        if not params:
            return None

        def serialize(v: Any) -> Any:  # noqa: ANN401
            """Normalize serializable parameter values for hashing."""
            if isinstance(v, Path):
                return str(v)
            if isinstance(v, dict):
                return {k: serialize(val) for k, val in v.items()}
            if isinstance(v, list | tuple):
                return [serialize(i) for i in v]
            return v

        try:
            serial = {k: serialize(v) for k, v in params.items()}
            json_str = json.dumps(serial, sort_keys=True)
            return hashlib.sha256(json_str.encode()).hexdigest()
        except (TypeError, ValueError) as e:
            logger.warning(
                "Parameters contain non-serializable values and cannot be cached. "
                f"Function will be treated as non-cacheable. Error: {e}",
            )
            return None


class DiscoveryHelper:
    """Helper class for discovering file dependencies in config files."""

    @staticmethod
    def is_config_file(file_path: Path) -> bool:
        """Check if a file is a configuration file.

        Supported formats are JSON and YAML.

        Parameters
        ----------
        file_path : Path
            The path to the file to check.

        Returns
        -------
        bool
            True if the file is a config file, False otherwise.
        """
        return file_path.suffix.lower() in {".json", ".yaml", ".yml"}

    @staticmethod
    def expand_config_files(files: list[Path]) -> list[Path]:
        """Expand list of files by recursively extracting paths from config files.

        For each configuration file in the input list, this method will:
        1. Include the config file itself
        2. Recursively extract and include any file paths referenced within it
        3. Cache the expansion results to avoid recomputation

        Parameters
        ----------
        files : list[Path]
            List of file paths, may include config files.

        Returns
        -------
        list[Path]
            Expanded list including all referenced files.
        """
        expanded: list[Path] = []
        visited: set[Path] = set()

        for file_path in files:
            # If it's a config file, extract referenced files first
            if DiscoveryHelper.is_config_file(file_path) and file_path.exists():
                # _extract_paths_from_config will mark the config and
                # its refs as visited
                referenced = DiscoveryHelper.extract_paths_from_config(
                    file_path, visited
                )
                # Add config file if not already in expanded
                if file_path not in expanded:
                    expanded.append(file_path)
                # Add all referenced files
                for ref_path in referenced:
                    if ref_path not in expanded:
                        expanded.append(ref_path)
            else:
                # Regular file - just add it if not already there
                if file_path not in visited:
                    expanded.append(file_path)
                    visited.add(file_path)

        return expanded

    @staticmethod
    def extract_file_paths_from_value(
        value: Any,  # noqa: ANN401
        base_dir: Path,
        visited: set[Path],
    ) -> list[Path]:
        """Recursively extract file paths from a configuration value.

        Parameters
        ----------
        value : Any
            The value to extract paths from.
        base_dir : Path
            Base directory for resolving relative paths.
        visited : set[Path]
            Set of already visited paths to prevent loops.

        Returns
        -------
        list[Path]
            List of Path objects found in the value.
        """
        paths: list[Path] = []

        if isinstance(value, str):
            # Check if the string represents a file path
            potential_path = Path(value)
            # Try both absolute and relative (to base_dir)
            if potential_path.is_absolute():
                resolved = potential_path
            else:
                resolved = (base_dir / potential_path).resolve()

            # Check if it exists and is a file, and not already visited
            if resolved.exists() and resolved.is_file() and resolved not in visited:
                # If it's a config file, recursively extract from it
                if DiscoveryHelper.is_config_file(resolved):
                    # Recurse first (it will mark itself as visited)
                    paths.extend(
                        DiscoveryHelper.extract_paths_from_config(resolved, visited)
                    )
                    # Also include the config file itself
                    paths.append(resolved)
                else:
                    # Non-config file, just add it
                    paths.append(resolved)
                    visited.add(resolved)

        elif isinstance(value, dict):
            for v in value.values():
                paths.extend(
                    DiscoveryHelper.extract_file_paths_from_value(v, base_dir, visited)
                )

        elif isinstance(value, list | tuple):
            for item in value:
                paths.extend(
                    DiscoveryHelper.extract_file_paths_from_value(
                        item, base_dir, visited
                    )
                )

        return paths

    @staticmethod
    def extract_paths_from_config(
        config_file: Path, visited: set[Path] | None = None
    ) -> list[Path]:
        """Extract all file paths referenced in a configuration file.

        Recursively searches through JSON/YAML config files for string values
        that represent valid file paths. Prevents infinite loops by tracking
        visited files.

        Parameters
        ----------
        config_file : Path
            Path to the configuration file.
        visited : set[Path] | None
            Set of already visited config files (for loop prevention).

        Returns
        -------
        list[Path]
            List of Path objects found in the configuration.
        """
        if visited is None:
            visited = set()

        # Prevent processing the same file twice
        if config_file in visited:
            return []

        visited.add(config_file)
        paths: list[Path] = []

        content = config_file.read_text()
        base_dir = config_file.parent

        # Parse based on file extension
        if config_file.suffix.lower() == ".json":
            data = json.loads(content)
        elif config_file.suffix.lower() in {".yaml", ".yml"}:
            data = yaml.safe_load(content)
        else:
            return []

        # Extract paths from the parsed data
        if data is not None:
            paths.extend(
                DiscoveryHelper.extract_file_paths_from_value(data, base_dir, visited)
            )

        return paths


class Cache:
    """Singleton file-backed cache for function results.

    The first instantiation may specify cache_dir. Subsequent instantiations return the
    same instance; if cache_dir is provided it updates the path.

    Caching can be globally enabled/disabled using enable() and disable() methods, or
    temporarily controlled using the temporarily_disabled() context manager.

    Parameters
    ----------
    cache_dir : str | None
        The cache directory path.
    """

    _instance: Self | None = None
    _initialized: bool = False
    _enabled: bool = True  # Global cache enable/disable flag
    _cache_dir: str
    _locks_lock: asyncio.Lock
    _lock: dict[str, asyncio.Lock]

    def __new__(cls, cache_dir: str | None = None) -> Self:
        """Create or return the singleton Cache instance.

        Parameters
        ----------
        cache_dir : str | None
            The cache directory path. If provided on first call, sets the cache dir.

        Returns
        -------
        Self
            The singleton instance.

        Raises
        ------
        RuntimeError
            If attempting to reinitialize with a different cache_dir.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            return cls._instance

        # If already instantiated and initialized, forbid reinitializing with a
        # different path
        if (
            cache_dir is not None
            and str(Path(cache_dir).expanduser()) != cls._instance.cache_dir
        ):
            raise RuntimeError("Cache already initialized with a different path")

        return cls._instance

    def __init__(self, cache_dir: str | None = None) -> None:
        # use class attribute to track initialization
        if Cache._initialized:
            # do not change cache_dir after initialization
            return

        if cache_dir is None:
            cache_dir = str(Path.cwd() / ".fab_cache")

        # Per-key locks for fine-grained concurrency
        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_lock = asyncio.Lock()  # Protects the locks dictionary itself
        p = Path(cache_dir).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        self._cache_dir = str(p)
        Cache._initialized = True

    @property
    def cache_dir(self) -> str:
        """The cache directory path.

        Returns
        -------
        str
            The path to the cache directory.
        """
        return self._cache_dir

    async def _get_lock_for_key(self, key: str) -> asyncio.Lock:
        """Get or create a lock for a specific cache key.

        Parameters
        ----------
        key : str
            The cache key.

        Returns
        -------
        asyncio.Lock
            The lock for the key.
        """
        async with self._locks_lock:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            return self._locks[key]

    def _key_for(self, fn: Callable, args: tuple, kwargs: dict) -> str:
        """Return a stable key for a function and its call arguments.

        Parameters
        ----------
        fn : Callable
            The function.
        args : tuple
            Positional arguments.
        kwargs : dict
            Keyword arguments.

        Returns
        -------
        str
            The cache key.
        """
        h = hashlib.sha256()
        h.update(fn.__module__.encode("utf-8"))
        h.update(b".")
        h.update(fn.__name__.encode("utf-8"))
        try:
            h.update(pickle.dumps((args, kwargs)))
        except (TypeError, AttributeError, pickle.PicklingError):
            # If pickling fails, use repr as fallback
            h.update(repr((args, kwargs)).encode("utf-8"))
        return h.hexdigest()

    def _path_for_key(self, key: str) -> str:
        """Return filesystem path for a cache key file.

        Parameters
        ----------
        key : str
            The cache key.

        Returns
        -------
        str
            The path to the cache file.
        """
        return str(Path(self.cache_dir) / key)

    @classmethod
    async def get_async(cls, fn: Callable, args: tuple, kwargs: dict) -> Any:  # noqa: ANN401
        """Get cached result or return _CACHE_MISS sentinel.

        Parameters
        ----------
        fn : Callable
            The function.
        args : tuple
            Positional arguments.
        kwargs : dict
            Keyword arguments.

        Returns
        -------
        Any
            The cached result or _CACHE_MISS.
        """
        instance = cls()
        key = instance._key_for(fn, args, kwargs)
        p = Path(instance._path_for_key(key))
        lock = await instance._get_lock_for_key(key)
        async with lock:
            if not p.exists():
                return _CACHE_MISS
            return pickle.loads(p.read_bytes())

    @classmethod
    def get(cls, fn: Callable, args: tuple, kwargs: dict) -> Any:  # noqa: ANN401
        """Get cached result or return _CACHE_MISS sentinel.

        Parameters
        ----------
        fn : Callable
            The function.
        args : tuple
            Positional arguments.
        kwargs : dict
            Keyword arguments.

        Returns
        -------
        Any
            The cached result or _CACHE_MISS.
        """
        return asyncio.run(cls.get_async(fn, args, kwargs))

    @classmethod
    async def set_async(
        cls,
        fn: Callable,
        args: tuple,
        kwargs: dict,
        value: Any,  # noqa: ANN401
    ) -> None:
        """Store a pickled cached value for the given function call.

        Parameters
        ----------
        fn : Callable
            The function.
        args : tuple
            Positional arguments.
        kwargs : dict
            Keyword arguments.
        value : Any
            The value to cache.
        """
        instance = cls()
        key = instance._key_for(fn, args, kwargs)
        path = Path(instance._path_for_key(key))
        tmp = (
            path.with_suffix(path.suffix + ".tmp")
            if path.suffix
            else Path(str(path) + ".tmp")
        )
        lock = await instance._get_lock_for_key(key)
        async with lock:
            tmp.write_bytes(pickle.dumps(value))
            tmp.replace(path)

    @classmethod
    def set(cls, fn: Callable, args: tuple, kwargs: dict, value: Any) -> None:  # noqa: ANN401
        """Store a pickled cached value for the given function call.

        Parameters
        ----------
        fn : Callable
            The function.
        args : tuple
            Positional arguments.
        kwargs : dict
            Keyword arguments.
        value : Any
            The value to cache.
        """
        asyncio.run(cls.set_async(fn, args, kwargs, value))

    @classmethod
    async def reset_async(cls) -> None:
        """Clear all cached entries and reset the singleton state."""
        instance = cls()
        async with instance._locks_lock:
            cache_path = Path(instance.cache_dir)
            if cache_path.exists():
                for item in cache_path.iterdir():
                    if item.is_file():
                        item.unlink()
            instance._locks.clear()
            Cache._instance = None
            Cache._initialized = False

    @classmethod
    def reset(cls) -> None:
        """Clear all cached entries and reset the singleton state."""
        asyncio.run(cls.reset_async())

    @classmethod
    def update(
        cls, cache_key: str, files: list[Path], params: dict[str, Any] | None = None
    ) -> None:
        """Write metadata for a cache key.

        Parameters
        ----------
        cache_key : str
            The cache key.
        files : list[Path]
            List of dependent files.
        params : dict[str, Any] | None
            Parameters.
        """
        instance = cls()
        meta = Path(instance.cache_dir) / f"{cache_key}.json"
        data = {
            "file_hash": HashHelper.hash_files(files),
            "param_hash": HashHelper.hash_params(params),
            "timestamp": datetime.now().isoformat(),
            "dependencies": [str(p) for p in files],
            "params": params,
        }
        meta.write_text(json.dumps(data, indent=2, default=str))

    @classmethod
    def enable(cls) -> None:
        """Enable caching globally."""
        cls._enabled = True

    @classmethod
    def disable(cls) -> None:
        """Disable caching globally.

        When disabled, all cache checks will return cache miss, forcing functions to re-
        execute every time.
        """
        cls._enabled = False

    @classmethod
    def is_enabled(cls) -> bool:
        """Check if caching is currently enabled.

        Returns
        -------
        bool
            True if enabled, False otherwise.
        """
        return cls._enabled

    @classmethod
    @contextmanager
    def cache_disabled(cls) -> Generator[None, None, None]:
        """Context manager to temporarily disable caching.

        Yields
        ------
        None

        Examples
        --------
        >>> # Caching is normally enabled
        >>> result1 = cached_function()  # Uses cache
        >>> with Cache.cache_disabled():
        ...     result2 = cached_function()  # Bypasses cache
        >>> result3 = cached_function()  # Uses cache again
        """
        previous_state = cls._enabled
        cls._enabled = False
        try:
            yield
        finally:
            cls._enabled = previous_state

    @classmethod
    @contextmanager
    def cache_enabled(cls) -> Generator[None, None, None]:
        """Context manager to temporarily enable caching.

        Useful when caching is globally disabled but you want to
        enable it for a specific code block.

        Yields
        ------
        None

        Examples
        --------
        >>> Cache.disable()  # Disable globally
        >>> with Cache.cache_enabled():
        ...     result = cached_function()  # Uses cache
        """
        previous_state = cls._enabled
        cls._enabled = True
        try:
            yield
        finally:
            cls._enabled = previous_state

    def is_cache_hit(
        self, cache_key: str, files: list[Path], params: dict[str, Any] | None = None
    ) -> bool:
        """Return True when stored metadata indicates dependencies are unchanged.

        Parameters
        ----------
        cache_key: str
            Unique key identifying the cached function call
        files: list[Path]
            List of file paths that the function depends on
        params: dict[str, Any] | None
            Optional dictionary of parameters affecting the function

        Returns
        -------
        bool
            True if the cache is valid (hit), False if a cache miss
        """
        # If caching is disabled, always return False (cache miss)
        if not Cache._enabled:
            return False

        meta = Path(self.cache_dir) / f"{cache_key}.json"
        if not meta.exists():
            return False

        data = json.loads(meta.read_text())
        current_files = HashHelper.hash_files(files)
        if data.get("file_hash") != current_files:
            return False
        if params:
            current_params = HashHelper.hash_params(params)
            # If params can't be serialized, treat as cache miss
            if current_params is None:
                return False
            if data.get("param_hash") != current_params:
                return False
        return True


def cache_with(
    *,
    param: bool = True,
    files: Callable[..., list[Path | str]] | None = None,
    return_cached: bool = False,
) -> Callable[[Callable], Callable]:
    """Return a dependency-aware caching decorator.

    Parameters
    ----------
    param : bool
        Whether to include parameters in cache key. Defaults to True.
    files : Callable[..., list[Path | str]] | None
        Function to get file dependencies.
    return_cached : bool
        Whether to return cached value. Defaults to False.

    Returns
    -------
    Callable[[Callable], Callable]
        The decorator function.

    Examples
    --------
    >>> class Worker:
    ...     def __init__(self, path: Path):
    ...         self.path = path
    ...
    ...     @cache_with(files=lambda self: [self.path])
    ...     def build(self):
    ...         ...
    """

    def make_decorator(func: Callable) -> Callable:
        """Create a decorator for the provided function.

        Parameters
        ----------
        func : Callable
            The function to decorate.

        Returns
        -------
        Callable
            The decorated function.
        """

        @wraps(func)
        def wrapped(*args: tuple, **kwargs: dict) -> Callable:
            """Handle dependency-aware caching for the function.

            Parameters
            ----------
            *args : tuple
                Positional arguments.
            **kwargs : dict
                Keyword arguments.

            Returns
            -------
            Callable
                The function result.
            """
            cache_key = (
                func.__module__
                + "."
                + func.__name__
                + "_"
                + hashlib.sha256(repr((args, kwargs)).encode()).hexdigest()
            )
            files_source = files
            params_ = kwargs if param else {}

            # resolve files
            if callable(files_source):
                resolved = files_source(*args, **kwargs)
            else:
                resolved = files_source or []
            if not isinstance(resolved, list | tuple):
                resolved = [resolved]
            file_paths: list[Path] = []
            for f in resolved:
                if isinstance(f, Path):
                    file_paths.append(f)
                else:
                    file_paths.append(Path(str(f)))

            # Expand config files to include their referenced files
            file_paths = DiscoveryHelper.expand_config_files(file_paths)

            # Helper async function to handle cache operations
            async def _check_and_update_cache() -> Any:  # noqa: ANN401
                # Use the singleton instance for is_up_to_date
                cache = Cache()
                if cache.is_cache_hit(cache_key, file_paths, params_):
                    if return_cached:
                        cached_val = await Cache.get_async(func, args, kwargs)
                        if cached_val is not _CACHE_MISS:
                            return cached_val
                    return None

                result = func(*args, **kwargs)

                # Only store results if caching is enabled
                if Cache.is_enabled():
                    Cache.update(cache_key, file_paths, params_)
                    # Store the result for potential return on cache hits
                    await Cache.set_async(func, args, kwargs, result)

                return result

            # Run the async function synchronously
            try:
                _loop = asyncio.get_running_loop()
                # We're already in an async context, but we need to run synchronously
                # Create a new event loop in a thread
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, _check_and_update_cache())
                    return future.result()
            except RuntimeError:
                # No event loop running, create one and run
                return asyncio.run(_check_and_update_cache())

        return wrapped

    return make_decorator
