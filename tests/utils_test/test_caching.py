"""Tests for FABulous caching utilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import yaml

from FABulous.caching import (
    _CACHE_MISS,
    Cache,
    DiscoveryHelper,
    HashHelper,
    cache_with,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Generator


@pytest.fixture(autouse=True)
def setup_cache(tmp_path: Path) -> Generator:
    """Set up and tear down the cache singleton for each test."""
    # Setup: Reset singleton and initialize with tmp_path
    # Check if instance exists and reset it
    if Cache._instance is not None:  # noqa: SLF001
        Cache._instance.reset()  # noqa: SLF001
    Cache(str(tmp_path / ".test_cache"))

    yield

    # Teardown: Reset singleton using the reset method
    if Cache._instance is not None:  # noqa: SLF001
        Cache._instance.reset()  # noqa: SLF001


class TestCacheSingleton:
    """Test singleton behavior of Cache."""

    def test_singleton_returns_same_instance(self) -> None:
        """Test that multiple instantiations return the same object."""
        cache1 = Cache()
        cache2 = Cache()
        assert cache1 is cache2

    def test_singleton_forbids_reinit_with_different_path(self, tmp_path: Path) -> None:
        """Test that reinitializing with a different path raises RuntimeError."""
        # Cache is already initialized by the fixture
        different_dir = tmp_path / "different"
        different_dir.mkdir()
        with pytest.raises(RuntimeError, match="Cache already initialized"):
            Cache(str(different_dir))

    def test_singleton_allows_reinit_with_same_path(self) -> None:
        """Test that reinitializing with the same path is allowed."""
        cache1 = Cache()
        # Reinit with same path should work
        cache2 = Cache(cache1.cache_dir)
        assert cache1 is cache2

    def test_singleton_creates_cache_dir(self) -> None:
        """Test that the cache directory is created on initialization."""
        cache = Cache()
        assert Path(cache.cache_dir).exists()


class TestSimpleCaching:
    """Test simple caching with Cache.get/set methods."""

    def test_cache_miss(self) -> None:
        """Test that a cache miss executes the function."""
        cache = Cache()
        call_count = 0

        def expensive_func(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        # Test cache miss BEFORE setting any value
        result = cache.get(expensive_func, (5,), {})
        assert result is _CACHE_MISS
        assert call_count == 0  # Function not called yet

        # Now execute and cache
        result1 = expensive_func(5)
        cache.set(expensive_func, (5,), {}, result1)
        assert result1 == 10
        assert call_count == 1

    def test_cache_hit(self) -> None:
        """Test that a cache hit returns the cached value without executing."""
        cache = Cache()
        call_count = 0

        def expensive_func(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call - execute and cache
        result1 = expensive_func(5)
        cache.set(expensive_func, (5,), {}, result1)
        assert result1 == 10
        assert call_count == 1

        # Second call - should get from cache
        result2 = cache.get(expensive_func, (5,), {})
        assert result2 == 10
        assert call_count == 1  # Only executed once

    def test_different_args_miss_cache(self) -> None:
        """Test that different arguments cause a cache miss."""
        cache = Cache()
        call_count = 0

        def expensive_func(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call with args1
        result1 = expensive_func(5)
        cache.set(expensive_func, (5,), {}, result1)
        assert result1 == 10
        assert call_count == 1

        # Different args - cache miss
        result2 = cache.get(expensive_func, (10,), {})
        assert result2 is _CACHE_MISS
        assert call_count == 1  # Still only executed once

        # Execute with different args
        result3 = expensive_func(10)
        cache.set(expensive_func, (10,), {}, result3)
        assert result3 == 20
        assert call_count == 2  # Now executed twice


class TestDependencyAwareCaching:
    """Test dependency-aware caching with cache_with."""

    def test_cache_with_on_class_method(self, tmp_path: Path) -> None:
        """Test cache_with decorator on class method with lambda self pattern."""
        test_file = tmp_path / "input.txt"
        test_file.write_text("initial content")

        class Worker:
            """Example worker class as shown in the usage documentation."""

            def __init__(self, path: Path) -> None:
                self.path = path
                self.call_count = 0

            @cache_with(files=lambda self: [self.path])
            def build(self) -> str:
                """Build method that should be cached based on file."""
                self.call_count += 1
                return f"built_{self.call_count}"

        # Create worker and call build
        worker = Worker(test_file)
        result1 = worker.build()
        assert result1 == "built_1"
        assert worker.call_count == 1

        # Second call should return None (cache hit, no re-execution)
        result2 = worker.build()
        assert result2 is None
        assert worker.call_count == 1  # Not called again

        # Modify the file
        test_file.write_text("modified content")

        # Should re-execute because file changed
        result3 = worker.build()
        assert result3 == "built_2"
        assert worker.call_count == 2

    def test_cache_with_on_class_method_with_return_cached(
        self, tmp_path: Path
    ) -> None:
        """Test cache_with with return_cached=True on class methods."""
        test_file = tmp_path / "data.txt"
        test_file.write_text("data")

        class Processor:
            def __init__(self, data_file: Path) -> None:
                self.data_file = data_file
                self.execution_count = 0

            @cache_with(files=lambda self: [self.data_file], return_cached=True)
            def process(self) -> str:
                self.execution_count += 1
                return f"result_{self.execution_count}"

        processor = Processor(test_file)

        # First call executes
        result1 = processor.process()
        assert result1 == "result_1"
        assert processor.execution_count == 1

        # Second call returns cached result
        result2 = processor.process()
        assert result2 == "result_1"  # Same cached result
        assert processor.execution_count == 1  # Not executed again

    def test_cache_with_files_up_to_date(self, tmp_path: Path) -> None:
        """Test cache_with returns None when files are unchanged."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        call_count = 0

        @cache_with(files=lambda: [test_file])
        def process_file() -> str:
            nonlocal call_count
            call_count += 1
            return "processed"

        result1 = process_file()
        assert result1 == "processed"
        assert call_count == 1

        # Second call should return None (cache hit)
        result2 = process_file()
        assert result2 is None
        assert call_count == 1  # Not executed again

    def test_cache_with_files_changed(self, tmp_path: Path) -> None:
        """Test cache_with re-executes when files change."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        call_count = 0

        @cache_with(files=lambda: [test_file])
        def process_file() -> str:
            nonlocal call_count
            call_count += 1
            return f"processed_{call_count}"

        result1 = process_file()
        assert result1 == "processed_1"
        assert call_count == 1

        # Modify the file
        test_file.write_text("new content")

        # Should re-execute because file changed
        result2 = process_file()
        assert result2 == "processed_2"
        assert call_count == 2

    def test_cache_with_params(self) -> None:
        """Test cache_with tracks parameter changes."""
        call_count = 0

        @cache_with(param=True)
        def process_with_params(x: int = 10) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = process_with_params(x=10)
        assert result1 == 20
        assert call_count == 1

        # Same params should return None (cache hit)
        result2 = process_with_params(x=10)
        assert result2 is None
        assert call_count == 1

        # Different params should re-execute
        result3 = process_with_params(x=20)
        assert result3 == 40
        assert call_count == 2

    def test_cache_with_return_cached_value(self, tmp_path: Path) -> None:
        """Test cache_with returns previous result when return_cached=True."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        call_count = 0

        @cache_with(files=lambda: [test_file], return_cached=True)
        def process_file() -> str:
            nonlocal call_count
            call_count += 1
            return "processed"

        # First call executes
        result1 = process_file()
        assert result1 == "processed"
        assert call_count == 1

        # Second call unchanged deps: returns cached value instead of None
        result2 = process_file()
        assert result2 == "processed"
        assert call_count == 1  # Not executed again

    def test_cache_with_non_serializable_params(self) -> None:
        """Test cache_with handles non-serializable params gracefully."""

        # Create a non-serializable object
        class NonSerializableObject:
            def __init__(self, value: int) -> None:
                self.value = value

        call_count = 0

        @cache_with(param=True)
        def process_with_object(obj: NonSerializableObject) -> str:
            nonlocal call_count
            call_count += 1
            return f"processed_{obj.value}"

        obj1 = NonSerializableObject(42)

        # First call should execute
        result1 = process_with_object(obj=obj1)
        assert result1 == "processed_42"
        assert call_count == 1

        # Second call with same object should re-execute
        # (no caching due to non-serializable param)
        result2 = process_with_object(obj=obj1)
        assert result2 == "processed_42"
        assert call_count == 2  # Executed again because params can't be cached

    def test_hash_params_with_non_serializable_returns_none(self) -> None:
        """Test that hash_params returns None for non-serializable params."""

        # Non-serializable object
        class CustomObject:
            pass

        params = {"obj": CustomObject()}
        result = HashHelper.hash_params(params)
        assert result is None  # Should return None instead of raising


class TestConfigFileExpansion:
    """Test configuration file path extraction."""

    @pytest.mark.parametrize(
        ("config_format", "config_content", "expected_files"),
        [
            (
                "json",
                lambda tmp_path: json.dumps(
                    {
                        "data_path": str(tmp_path / "data.txt"),
                        "model": {
                            "path": str(tmp_path / "model.bin"),
                            "version": "1.0",
                        },
                        "other": "not a path",
                    }
                ),
                ["data.txt", "model.bin"],
            ),
            (
                "yaml",
                lambda tmp_path: yaml.dump(
                    {
                        "input": str(tmp_path / "input.csv"),
                        "output": str(tmp_path / "output.json"),
                        "settings": {"debug": True, "max_size": 100},
                    }
                ),
                ["input.csv", "output.json"],
            ),
        ],
    )
    def test_extract_paths_from_config_files(
        self,
        tmp_path: Path,
        config_format: str,
        config_content: Callable[[Path], str],
        expected_files: list[str],
    ) -> None:
        """Test extracting file paths from JSON and YAML config files."""
        # Create referenced files
        for filename in expected_files:
            file_path = tmp_path / filename
            if filename.endswith(".json"):
                file_path.write_text("{}")  # Valid JSON content
            else:
                file_path.write_text(f"{filename} content")

        # Create config file
        config_filename = f"config.{config_format}"
        config = tmp_path / config_filename
        config.write_text(config_content(tmp_path))

        paths = DiscoveryHelper.extract_paths_from_config(config)

        # Should find all expected files
        for filename in expected_files:
            expected_path = tmp_path / filename
            assert expected_path in paths

    def test_nested_config_files(self, tmp_path: Path) -> None:
        """Test recursive extraction from nested config files."""
        # Create a data file
        data_file = tmp_path / "data.txt"
        data_file.write_text("data")

        # Create a nested config that references the data file
        nested_config = tmp_path / "nested.json"
        nested_config.write_text(json.dumps({"data": str(data_file)}))

        # Create a main config that references the nested config
        main_config = tmp_path / "main.yaml"
        main_config.write_text(f"config_file: {nested_config}\n")

        paths = DiscoveryHelper.extract_paths_from_config(main_config)

        # Should find both the nested config and the data file
        assert nested_config in paths
        assert data_file in paths

    def test_prevents_infinite_loops(self, tmp_path: Path) -> None:
        """Test that circular references don't cause infinite loops."""
        config_a = tmp_path / "config_a.json"
        config_b = tmp_path / "config_b.json"

        # Create circular references
        config_a.write_text(json.dumps({"next": str(config_b)}))
        config_b.write_text(json.dumps({"next": str(config_a)}))

        # Should not hang or crash
        paths = DiscoveryHelper.extract_paths_from_config(config_a)

        # Should find config_b but not get stuck in a loop
        assert config_b in paths
        assert len(paths) < 10  # Reasonable upper bound

    def test_relative_paths_in_config(self, tmp_path: Path) -> None:
        """Test that relative paths in config files are resolved correctly."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        # Create a data file in subdir
        data_file = subdir / "data.txt"
        data_file.write_text("data")

        # Create config with relative path
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"data": "subdir/data.txt"}))

        paths = DiscoveryHelper.extract_paths_from_config(config)

        # Should resolve relative path correctly
        assert data_file in paths

    def test_expand_config_files(self, tmp_path: Path) -> None:
        """Test _expand_config_files method."""
        # Create files
        data_file = tmp_path / "data.txt"
        data_file.write_text("data")

        regular_file = tmp_path / "regular.txt"
        regular_file.write_text("regular")

        # Create config that references data_file
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"data": str(data_file)}))

        expanded = DiscoveryHelper.expand_config_files([regular_file, config])

        # Should include regular file, config, and data file
        assert regular_file in expanded
        assert config in expanded
        assert data_file in expanded

    def test_cache_with_config_file_dependency(self, tmp_path: Path) -> None:
        """Test cache_with decorator with config file dependencies."""
        # Create a data file
        data_file = tmp_path / "data.txt"
        data_file.write_text("initial data")

        # Create a config file
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"data_path": str(data_file)}))

        call_count = 0

        @cache_with(files=lambda: [config])
        def process_config() -> str:
            nonlocal call_count
            call_count += 1
            return "processed"

        # First call
        result1 = process_config()
        assert result1 == "processed"
        assert call_count == 1

        # Second call - should be cached
        result2 = process_config()
        assert result2 is None
        assert call_count == 1

        # Modify the data file (which is referenced in config)
        data_file.write_text("modified data")

        # Should re-execute because referenced file changed
        result3 = process_config()
        assert result3 == "processed"
        assert call_count == 2

    def test_non_existent_paths_ignored(self, tmp_path: Path) -> None:
        """Test that non-existent paths in configs are ignored."""
        config = tmp_path / "config.json"
        config.write_text(
            json.dumps(
                {
                    "existing": str(tmp_path / "file.txt"),  # doesn't exist
                    "also_fake": "/path/to/nowhere/file.dat",
                }
            )
        )

        paths = DiscoveryHelper.extract_paths_from_config(config)

        # Should return empty list (no valid files found)
        assert len(paths) == 0


class TestHashHelper:
    """Test HashHelper utility methods."""

    def test_hash_file_content_existing_file(self, tmp_path: Path) -> None:
        """Test hashing content of an existing file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        hash1 = HashHelper.hash_file_content(test_file)
        assert isinstance(hash1, str)
        assert len(hash1) == 64  # SHA256 produces 64 hex characters

        # Same content should produce same hash
        hash2 = HashHelper.hash_file_content(test_file)
        assert hash1 == hash2

    def test_hash_file_content_missing_file(self, tmp_path: Path) -> None:
        """Test hashing content of a non-existent file raises FileNotFoundError."""
        missing_file = tmp_path / "missing.txt"
        with pytest.raises(FileNotFoundError, match=f"File not found: {missing_file}"):
            HashHelper.hash_file_content(missing_file)

    def test_hash_file_content_changed_file(self, tmp_path: Path) -> None:
        """Test that hash changes when file content changes."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("original content")

        hash1 = HashHelper.hash_file_content(test_file)

        # Modify the file
        test_file.write_text("modified content")
        hash2 = HashHelper.hash_file_content(test_file)

        assert hash1 != hash2

    def test_hash_files_multiple_files(self, tmp_path: Path) -> None:
        """Test hashing multiple files together."""
        file1 = tmp_path / "file1.txt"
        file1.write_text("content 1")

        file2 = tmp_path / "file2.txt"
        file2.write_text("content 2")

        hash1 = HashHelper.hash_files([file1, file2])
        assert isinstance(hash1, str)
        assert len(hash1) == 64

        # Same files should produce same hash
        hash2 = HashHelper.hash_files([file1, file2])
        assert hash1 == hash2

    def test_hash_files_order_independent(self, tmp_path: Path) -> None:
        """Test that hash_files produces same hash regardless of order."""
        file1 = tmp_path / "file1.txt"
        file1.write_text("content 1")

        file2 = tmp_path / "file2.txt"
        file2.write_text("content 2")

        # Hash should be same regardless of order (sorted internally)
        hash1 = HashHelper.hash_files([file1, file2])
        hash2 = HashHelper.hash_files([file2, file1])
        assert hash1 == hash2

    def test_hash_files_duplicates_removed(self, tmp_path: Path) -> None:
        """Test that duplicate files are handled correctly."""
        file1 = tmp_path / "file1.txt"
        file1.write_text("content 1")

        # With duplicates
        hash1 = HashHelper.hash_files([file1, file1, file1])
        # Without duplicates
        hash2 = HashHelper.hash_files([file1])

        assert hash1 == hash2

    @pytest.mark.parametrize(
        ("params", "expected_result", "description"),
        [
            (
                {"key1": "value1", "key2": 42, "key3": [1, 2, 3]},
                "hash_exists",
                "serializable params",
            ),
            (None, None, "None params"),
            ({}, None, "empty params"),
        ],
    )
    def test_hash_params_various_inputs(
        self,
        tmp_path: Path,
        params: dict[str, Any] | None,
        expected_result: str | None,
        description: str,
    ) -> None:
        """Test hash_params with various parameter types."""
        if "path" in description or (
            params and any(isinstance(v, Path) for v in params.values())
        ):
            # Add path to params for path test
            test_path = tmp_path / "test.txt"
            params = {"path": test_path, "value": 10}

        result = HashHelper.hash_params(params)

        if expected_result == "hash_exists":
            assert isinstance(result, str)
            assert len(result) == 64
            # Same params should produce same hash
            result2 = HashHelper.hash_params(params)
            assert result == result2
        else:
            assert result is expected_result

    def test_hash_params_with_path(self, tmp_path: Path) -> None:
        """Test hashing parameters containing Path objects."""
        test_path = tmp_path / "test.txt"
        params = {"path": test_path, "value": 10}

        hash1 = HashHelper.hash_params(params)
        assert isinstance(hash1, str)

    def test_hash_params_order_independent(self) -> None:
        """Test that parameter order doesn't affect hash."""
        params1 = {"a": 1, "b": 2, "c": 3}
        params2 = {"c": 3, "a": 1, "b": 2}

        hash1 = HashHelper.hash_params(params1)
        hash2 = HashHelper.hash_params(params2)
        assert hash1 == hash2


class TestDiscoveryHelper:
    """Test DiscoveryHelper utility methods."""

    @pytest.mark.parametrize(
        ("filename", "expected_is_config"),
        [
            ("config.json", True),
            ("config.yaml", True),
            ("config.yml", True),
            ("config.JSON", True),  # Case insensitive
            ("config.YAML", True),  # Case insensitive
            ("file.txt", False),
            ("script.py", False),
            ("data.csv", False),
        ],
    )
    def test_is_config_file_various_extensions(
        self, tmp_path: Path, filename: str, expected_is_config: bool
    ) -> None:
        """Test is_config_file with various file extensions."""
        test_file = tmp_path / filename
        test_file.write_text("content")

        result = DiscoveryHelper.is_config_file(test_file)
        assert result is expected_is_config


class TestCacheReset:
    """Test cache reset functionality."""

    def test_reset_clears_cache_files(self) -> None:
        """Test that reset removes all cache files."""
        cache = Cache()

        # Add some cached values
        def test_func(x: int) -> int:
            return x * 2

        cache.set(test_func, (5,), {}, 10)
        cache.set(test_func, (10,), {}, 20)

        # Verify files exist
        cache_dir = Path(cache.cache_dir)
        files_before = list(cache_dir.iterdir())
        assert len(files_before) > 0

        # Reset cache
        cache.reset()

        # Verify files are removed
        files_after = list(cache_dir.iterdir())
        assert len(files_after) == 0

    def test_reset_clears_singleton(self) -> None:
        """Test that reset clears the singleton instance."""
        cache1 = Cache()
        cache1_dir = cache1.cache_dir

        # Add some data
        def test_func(x: int) -> int:
            return x * 2

        cache1.set(test_func, (5,), {}, 10)

        # Reset cache
        cache1.reset()

        # After reset, should be able to create new instance with different path
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            cache2 = Cache(tmpdir)
            assert cache2.cache_dir != cache1_dir

            # Verify old data is not accessible
            result = cache2.get(test_func, (5,), {})
            assert result is _CACHE_MISS

    def test_reset_clears_locks(self) -> None:
        """Test that reset clears the locks dictionary."""
        cache = Cache()

        # Add some cached values to create locks
        def test_func(x: int) -> int:
            return x * 2

        cache.set(test_func, (5,), {}, 10)
        cache.set(test_func, (10,), {}, 20)

        # Verify locks were created (access private attribute for testing)
        assert len(cache._locks) > 0  # noqa: SLF001

        # Reset cache
        cache.reset()

        # Create new cache instance
        new_cache = Cache()

        # Verify locks dictionary is empty in new instance
        assert len(new_cache._locks) == 0  # noqa: SLF001

    def test_reset_allows_reinitialization(self) -> None:
        """Test that reset allows cache to be reinitialized with new path."""
        import tempfile

        cache1 = Cache()
        original_dir = cache1.cache_dir

        # Add some data
        def test_func(x: int) -> int:
            return x * 2

        cache1.set(test_func, (5,), {}, 10)

        # Reset
        cache1.reset()

        # Should be able to initialize with a different path
        with tempfile.TemporaryDirectory() as tmpdir:
            cache2 = Cache(tmpdir)
            assert cache2.cache_dir == tmpdir
            assert cache2.cache_dir != original_dir

            # Old data should not exist
            result = cache2.get(test_func, (5,), {})
            assert result is _CACHE_MISS

    def test_reset_with_metadata_files(self, tmp_path: Path) -> None:
        """Test that reset also clears metadata JSON files."""
        cache = Cache()

        # Create a metadata file using the cache_with decorator
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        call_count = 0

        @cache_with(files=lambda: [test_file])
        def process_file() -> str:
            nonlocal call_count
            call_count += 1
            return "processed"

        # Execute to create metadata
        result = process_file()
        assert result == "processed"

        # Verify metadata files exist
        cache_dir = Path(cache.cache_dir)
        json_files = list(cache_dir.glob("*.json"))
        assert len(json_files) > 0

        # Reset
        cache.reset()

        # Create new cache and verify metadata is gone
        new_cache = Cache(str(tmp_path / ".new_cache"))
        new_cache_dir = Path(new_cache.cache_dir)
        json_files_after = list(new_cache_dir.glob("*.json"))
        assert len(json_files_after) == 0

    def test_reset_async_method(self) -> None:
        """Test the async reset method directly."""
        import asyncio

        cache = Cache()

        # Add some cached values
        def test_func(x: int) -> int:
            return x * 2

        cache.set(test_func, (5,), {}, 10)

        # Verify files exist
        cache_dir = Path(cache.cache_dir)
        assert len(list(cache_dir.iterdir())) > 0

        # Reset using async method
        asyncio.run(cache.reset_async())

        # Verify files are removed
        assert len(list(cache_dir.iterdir())) == 0

        # Verify singleton is reset
        assert Cache._instance is None  # noqa: SLF001
        assert Cache._initialized is False  # noqa: SLF001

    def test_multiple_resets(self) -> None:
        """Test that multiple resets work correctly."""
        import tempfile

        # First initialization
        cache1 = Cache()
        cache1.set(lambda x: x, (1,), {}, 1)
        cache1.reset()

        # Second initialization
        with tempfile.TemporaryDirectory() as tmpdir1:
            cache2 = Cache(tmpdir1)
            cache2.set(lambda x: x, (2,), {}, 2)
            cache2.reset()

            # Third initialization
            with tempfile.TemporaryDirectory() as tmpdir2:
                cache3 = Cache(tmpdir2)
                assert cache3.cache_dir == tmpdir2

                # Should be completely clean
                result = cache3.get(lambda x: x, (1,), {})
                assert result is _CACHE_MISS
                result = cache3.get(lambda x: x, (2,), {})
                assert result is _CACHE_MISS


class TestAsyncMethods:
    """Test async cache methods."""

    @pytest.mark.parametrize(
        ("operation", "expected_value"),
        [
            ("cache_miss", _CACHE_MISS),
            ("cache_hit", 10),
        ],
    )
    def test_async_get_operations(self, operation: str, expected_value: object) -> None:
        """Test async get operations with cache miss and cache hit."""
        import asyncio

        cache = Cache()

        def test_func(x: int) -> int:
            return x * 2

        async def test_async() -> None:
            if operation == "cache_hit":
                # Set value first for cache hit test
                await cache.set_async(test_func, (5,), {}, 10)

            result = await cache.get_async(test_func, (5,), {})
            assert result is expected_value

        asyncio.run(test_async())

    def test_set_async_stores_value(self) -> None:
        """Test async set stores values correctly."""
        import asyncio

        cache = Cache()

        def test_func(x: int) -> int:
            return x * 2

        async def test_async() -> None:
            await cache.set_async(test_func, (5,), {}, 10)

            # Verify value was stored
            result = await cache.get_async(test_func, (5,), {})
            assert result == 10

        asyncio.run(test_async())


class TestCacheEnableDisable:
    """Test cache enable/disable functionality."""

    def test_cache_enabled_by_default(self) -> None:
        """Test that caching is enabled by default."""
        assert Cache.is_enabled() is True

    def test_disable_prevents_caching(self, tmp_path: Path) -> None:
        """Test that disabling cache prevents caching."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        call_count = 0

        @cache_with(files=lambda: [test_file])
        def test_func() -> int:
            nonlocal call_count
            call_count += 1
            return call_count

        # Ensure cache is enabled
        Cache.enable()

        # First call with cache enabled
        result1 = test_func()
        assert result1 == 1
        assert call_count == 1

        # Second call should not execute (cache hit)
        result2 = test_func()
        assert result2 is None
        assert call_count == 1

        # Disable caching
        Cache.disable()

        try:
            # Third call should execute (cache disabled)
            result3 = test_func()
            assert result3 == 2
            assert call_count == 2

            # Fourth call should also execute (still disabled)
            result4 = test_func()
            assert result4 == 3
            assert call_count == 3
        finally:
            # Re-enable for other tests
            Cache.enable()

    def test_enable_restores_caching(self, tmp_path: Path) -> None:
        """Test that enabling cache after disable restores caching."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        call_count = 0

        @cache_with(files=lambda: [test_file])
        def test_func() -> int:
            nonlocal call_count
            call_count += 1
            return call_count

        # Disable cache
        Cache.disable()

        try:
            # Call executes
            result1 = test_func()
            assert result1 == 1
            assert call_count == 1

            # Call executes again (cache disabled)
            result2 = test_func()
            assert result2 == 2
            assert call_count == 2

            # Re-enable cache
            Cache.enable()

            # Call executes (first time with cache enabled)
            result3 = test_func()
            assert result3 == 3
            assert call_count == 3

            # Second call with cache enabled should not execute
            result4 = test_func()
            assert result4 is None
            assert call_count == 3  # Not called again
        finally:
            Cache.enable()

    def test_is_enabled_reflects_state(self) -> None:
        """Test that is_enabled() correctly reflects the cache state."""
        original_state = Cache.is_enabled()

        try:
            Cache.enable()
            assert Cache.is_enabled() is True

            Cache.disable()
            assert Cache.is_enabled() is False

            Cache.enable()
            assert Cache.is_enabled() is True
        finally:
            # Restore original state
            if original_state:
                Cache.enable()
            else:
                Cache.disable()

    def test_temporarily_disabled_context(self, tmp_path: Path) -> None:
        """Test temporarily_disabled() context manager."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        call_count = 0

        @cache_with(files=lambda: [test_file])
        def test_func() -> int:
            nonlocal call_count
            call_count += 1
            return call_count

        # Ensure cache is enabled
        Cache.enable()

        # First call with cache enabled
        result1 = test_func()
        assert result1 == 1
        assert call_count == 1

        # Second call uses cache
        result2 = test_func()
        assert result2 is None
        assert call_count == 1

        # Temporarily disable
        with Cache.cache_disabled():
            assert Cache.is_enabled() is False

            # Should execute (cache disabled)
            result3 = test_func()
            assert result3 == 2
            assert call_count == 2

            # Should execute again (still disabled)
            result4 = test_func()
            assert result4 == 3
            assert call_count == 3

        # After context, cache is re-enabled
        assert Cache.is_enabled() is True

        # Should not execute (cache re-enabled, but already has cached data)
        result5 = test_func()
        assert result5 is None
        assert call_count == 3

    def test_temporarily_enabled_context(self, tmp_path: Path) -> None:
        """Test temporarily_enabled() context manager."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        call_count = 0

        @cache_with(files=lambda: [test_file])
        def test_func() -> int:
            nonlocal call_count
            call_count += 1
            return call_count

        # Disable cache globally
        Cache.disable()

        try:
            # First call executes (cache disabled)
            result1 = test_func()
            assert result1 == 1
            assert call_count == 1

            # Second call also executes (cache still disabled)
            result2 = test_func()
            assert result2 == 2
            assert call_count == 2

            # Temporarily enable
            with Cache.cache_enabled():
                assert Cache.is_enabled() is True

                # Should execute (first time with cache enabled)
                result3 = test_func()
                assert result3 == 3
                assert call_count == 3

                # Should not execute (cache enabled)
                result4 = test_func()
                assert result4 is None
                assert call_count == 3

            # After context, cache is disabled again
            assert Cache.is_enabled() is False

            # Should execute (cache disabled again)
            result5 = test_func()
            assert result5 == 4
            assert call_count == 4
        finally:
            Cache.enable()

    def test_nested_context_managers(self) -> None:
        """Test nested context managers restore state correctly."""
        Cache.enable()

        assert Cache.is_enabled() is True

        with Cache.cache_disabled():
            assert Cache.is_enabled() is False

            with Cache.cache_enabled():
                assert Cache.is_enabled() is True

            # Inner context exited, should be disabled again
            assert Cache.is_enabled() is False

        # Outer context exited, should be enabled again
        assert Cache.is_enabled() is True

    def test_disable_with_return_cached(self, tmp_path: Path) -> None:
        """Test that return_cached=True works with disable/enable."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        call_count = 0

        @cache_with(files=lambda: [test_file], return_cached=True)
        def test_func() -> int:
            nonlocal call_count
            call_count += 1
            return call_count

        # Enable cache and execute
        Cache.enable()

        # First call with cache enabled
        result1 = test_func()
        assert result1 == 1
        assert call_count == 1

        # Second call returns cached value
        result2 = test_func()
        assert result2 == 1
        assert call_count == 1

        # Disable cache
        Cache.disable()

        try:
            # Should execute and return new value
            result3 = test_func()
            assert result3 == 2
            assert call_count == 2

            # Should execute again (cache disabled)
            result4 = test_func()
            assert result4 == 3
            assert call_count == 3
        finally:
            Cache.enable()

    def test_disable_with_file_dependencies(self, tmp_path: Path) -> None:
        """Test that disable works with file dependencies."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("v1")

        call_count = 0

        @cache_with(files=lambda: [test_file])
        def process_file() -> str:
            nonlocal call_count
            call_count += 1
            return test_file.read_text()

        # Ensure cache is enabled
        Cache.enable()

        # First call
        result1 = process_file()
        assert result1 == "v1"
        assert call_count == 1

        # Modify file
        test_file.write_text("v2")

        # Should detect change and re-execute
        result2 = process_file()
        assert result2 == "v2"
        assert call_count == 2

        # Disable cache
        Cache.disable()

        try:
            # Should always execute when disabled
            result3 = process_file()
            assert result3 == "v2"
            assert call_count == 3

            # Modify file again
            test_file.write_text("v3")

            # Should execute again (cache disabled)
            result4 = process_file()
            assert result4 == "v3"
            assert call_count == 4
        finally:
            Cache.enable()

    def test_disable_with_params(self) -> None:
        """Test that disable works with parameter tracking."""
        call_count = 0

        @cache_with(param=True)
        def func_with_params(x: int = 10) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        # Enable cache
        Cache.enable()

        # First call
        result1 = func_with_params(x=10)
        assert result1 == 20
        assert call_count == 1

        # Same params - cache hit
        result2 = func_with_params(x=10)
        assert result2 is None
        assert call_count == 1

        # Disable cache
        Cache.disable()

        try:
            # Same params but cache disabled - should execute
            result3 = func_with_params(x=10)
            assert result3 == 20  # Returns x * 2 = 10 * 2 = 20
            assert call_count == 2  # Executed again

            # Different params - should execute
            result4 = func_with_params(x=20)
            assert result4 == 40  # Returns x * 2 = 20 * 2 = 40
            assert call_count == 3
        finally:
            Cache.enable()


class TestAsyncContextCaching:
    """Test cache_with decorator behavior in async and non-async contexts."""

    def test_cache_with_in_sync_context(self, tmp_path: Path) -> None:
        """Test cache_with decorator works correctly in sync context."""
        test_file = tmp_path / "sync_test.txt"
        test_file.write_text("content")

        call_count = 0

        @cache_with(files=lambda: [test_file])
        def process_file() -> str:
            nonlocal call_count
            call_count += 1
            return f"processed_{call_count}"

        # Test in regular (sync) context
        # First call - should execute
        result1 = process_file()
        assert result1 == "processed_1"
        assert call_count == 1

        # Second call - should return None (cache hit)
        result2 = process_file()
        assert result2 is None
        assert call_count == 1

        # Modify file - should re-execute
        test_file.write_text("modified content")
        result3 = process_file()
        assert result3 == "processed_2"
        assert call_count == 2

    def test_cache_with_in_async_context(self, tmp_path: Path) -> None:
        """Test cache_with decorator works correctly in async context."""
        import asyncio

        test_file = tmp_path / "async_test.txt"
        test_file.write_text("async content")

        call_count = 0

        @cache_with(files=lambda: [test_file])
        def async_process_file() -> str:
            nonlocal call_count
            call_count += 1
            return f"async_processed_{call_count}"

        async def run_async_test() -> None:
            # First call in async context - should execute
            result1 = async_process_file()
            assert result1 == "async_processed_1"
            assert call_count == 1

            # Second call - should return None (cache hit)
            result2 = async_process_file()
            assert result2 is None
            assert call_count == 1

            # Modify file - should re-execute
            test_file.write_text("modified async content")
            result3 = async_process_file()
            assert result3 == "async_processed_2"
            assert call_count == 2

        # Run the async test
        asyncio.run(run_async_test())
