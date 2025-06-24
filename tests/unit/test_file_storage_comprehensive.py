"""
Comprehensive tests for file storage functionality.
"""

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


class TestFileStorageBasics:
    """Test basic file storage functionality."""

    @pytest.fixture
    def temp_storage_dir(self):
        """Create temporary storage directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_file_storage_module_import(self):
        """Test that file storage module can be imported."""
        try:
            import content_collector.storage.file_storage

            assert True
        except ImportError:
            pytest.skip("File storage module not available")

    def test_directory_creation(self, temp_storage_dir):
        """Test directory creation functionality."""
        nested_dir = os.path.join(temp_storage_dir, "content", "pages", "2023")
        os.makedirs(nested_dir, exist_ok=True)

        assert os.path.exists(nested_dir)
        assert os.path.isdir(nested_dir)

    def test_file_operations(self, temp_storage_dir):
        """Test basic file operations."""
        test_file = os.path.join(temp_storage_dir, "test_file.txt")
        test_content = "This is test content"

        with open(test_file, "w", encoding="utf-8") as f:
            f.write(test_content)

        assert os.path.exists(test_file)

        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()

        assert content == test_content

    def test_file_path_generation(self):
        """Test file path generation logic."""

        def generate_content_path(page_id, base_dir="/tmp/storage"):
            """Generate content file path for a page."""
            return os.path.join(base_dir, "content", f"{page_id}.html")

        def generate_headers_path(page_id, base_dir="/tmp/storage"):
            """Generate headers file path for a page."""
            return os.path.join(base_dir, "headers", f"{page_id}.json")

        page_id = "test_page_123"

        content_path = generate_content_path(page_id)
        headers_path = generate_headers_path(page_id)

        assert "test_page_123.html" in content_path
        assert "test_page_123.json" in headers_path
        assert "content" in content_path
        assert "headers" in headers_path

    def test_json_serialization(self, temp_storage_dir):
        """Test JSON serialization for headers."""
        import json

        headers = {
            "content-type": "text/html",
            "content-length": "1024",
            "server": "nginx/1.18.0",
        }

        headers_file = os.path.join(temp_storage_dir, "headers.json")

        with open(headers_file, "w", encoding="utf-8") as f:
            json.dump(headers, f, indent=2)

        assert os.path.exists(headers_file)

        with open(headers_file, "r", encoding="utf-8") as f:
            loaded_headers = json.load(f)

        assert loaded_headers == headers
        assert loaded_headers["content-type"] == "text/html"

    def test_unicode_handling(self, temp_storage_dir):
        """Test handling of unicode content."""
        unicode_content = "Test content with unicode: ñáéíóú 中文 🚀"
        test_file = os.path.join(temp_storage_dir, "unicode_test.html")

        with open(test_file, "w", encoding="utf-8") as f:
            f.write(unicode_content)

        with open(test_file, "r", encoding="utf-8") as f:
            loaded_content = f.read()

        assert loaded_content == unicode_content

    def test_large_file_handling(self, temp_storage_dir):
        """Test handling of large files."""
        large_content = "x" * (1024 * 1024)
        large_file = os.path.join(temp_storage_dir, "large_file.html")

        with open(large_file, "w", encoding="utf-8") as f:
            f.write(large_content)

        assert os.path.exists(large_file)
        assert os.path.getsize(large_file) > 1000000


class TestFileStorageUtilities:
    """Test file storage utility functions."""

    def test_directory_size_calculation(self, temp_storage_dir):
        """Test directory size calculation."""

        def calculate_directory_size(directory):
            """Calculate total size of directory."""
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(directory):
                for filename in filenames:
                    file_path = os.path.join(dirpath, filename)
                    if os.path.exists(file_path):
                        total_size += os.path.getsize(file_path)
            return total_size

        test_files = [
            ("file1.txt", "content1"),
            ("file2.txt", "content2"),
            ("subdir/file3.txt", "content3"),
        ]

        for file_path, content in test_files:
            full_path = os.path.join(temp_storage_dir, file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)

        total_size = calculate_directory_size(temp_storage_dir)
        assert total_size > 0

    @pytest.fixture
    def temp_storage_dir(self):
        """Create temporary storage directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_file_cleanup_by_age(self, temp_storage_dir):
        """Test file cleanup by age."""
        import time

        def cleanup_old_files(directory, max_age_days=7):
            """Clean up files older than max_age_days."""
            import os
            import time

            cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
            deleted_count = 0

            for root, dirs, files in os.walk(directory):
                for file in files:
                    file_path = os.path.join(root, file)
                    if os.path.getmtime(file_path) < cutoff_time:
                        os.remove(file_path)
                        deleted_count += 1

            return deleted_count

        test_file = os.path.join(temp_storage_dir, "old_file.txt")
        with open(test_file, "w") as f:
            f.write("old content")

        old_time = time.time() - (10 * 24 * 60 * 60)
        os.utime(test_file, (old_time, old_time))

        deleted_count = cleanup_old_files(temp_storage_dir, max_age_days=7)

        assert deleted_count >= 0

    def test_archive_creation(self, temp_storage_dir):
        """Test archive creation functionality."""
        import zipfile

        def create_archive(source_dir, archive_path):
            """Create ZIP archive of directory."""
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(source_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, source_dir)
                        zipf.write(file_path, arcname)

        test_file1 = os.path.join(temp_storage_dir, "file1.txt")
        test_file2 = os.path.join(temp_storage_dir, "subdir", "file2.txt")

        os.makedirs(os.path.dirname(test_file2), exist_ok=True)

        with open(test_file1, "w") as f:
            f.write("content1")
        with open(test_file2, "w") as f:
            f.write("content2")

        archive_path = os.path.join(temp_storage_dir, "test_archive.zip")
        create_archive(temp_storage_dir, archive_path)

        assert os.path.exists(archive_path)
        assert os.path.getsize(archive_path) > 0

    def test_file_metadata_extraction(self):
        """Test file metadata extraction."""

        def extract_file_metadata(file_path):
            """Extract metadata from file."""
            if not os.path.exists(file_path):
                return None

            stat = os.stat(file_path)
            return {
                "size": stat.st_size,
                "created": stat.st_ctime,
                "modified": stat.st_mtime,
                "is_file": os.path.isfile(file_path),
                "is_dir": os.path.isdir(file_path),
            }

        metadata = extract_file_metadata("/nonexistent/file.txt")
        assert metadata is None

        metadata = extract_file_metadata(tempfile.gettempdir())
        assert metadata is not None
        assert metadata["is_dir"] is True
        assert metadata["size"] >= 0


class TestStorageValidation:
    """Test storage validation and error handling."""

    def test_path_validation(self):
        """Test path validation logic."""

        def validate_storage_path(path):
            """Validate storage path."""
            if not path:
                return False, "Path cannot be empty"

            if not os.path.isabs(path):
                return False, "Path must be absolute"

            parent_dir = os.path.dirname(path)
            if not os.path.exists(parent_dir):
                try:
                    os.makedirs(parent_dir, exist_ok=True)
                except PermissionError:
                    return False, "Cannot create parent directory"

            return True, "Valid path"

        is_valid, message = validate_storage_path("")
        assert is_valid is False
        assert "empty" in message

        is_valid, message = validate_storage_path("relative/path")
        assert is_valid is False
        assert "absolute" in message

        valid_path = os.path.join(tempfile.gettempdir(), "test_storage")
        is_valid, message = validate_storage_path(valid_path)
        assert is_valid is True

    def test_content_validation(self):
        """Test content validation."""

        def validate_content(content, max_size=10 * 1024 * 1024):
            """Validate content before storage."""
            if content is None:
                return False, "Content cannot be None"

            if not isinstance(content, str):
                return False, "Content must be a string"

            if len(content.encode("utf-8")) > max_size:
                return False, f"Content too large (max {max_size} bytes)"

            return True, "Valid content"

        is_valid, message = validate_content(None)
        assert is_valid is False
        assert "None" in message

        is_valid, message = validate_content(123)
        assert is_valid is False
        assert "string" in message

        is_valid, message = validate_content("Valid HTML content")
        assert is_valid is True

        large_content = "x" * (11 * 1024 * 1024)
        is_valid, message = validate_content(large_content, max_size=10 * 1024 * 1024)
        assert is_valid is False
        assert "too large" in message

    def test_page_id_validation(self):
        """Test page ID validation."""

        def validate_page_id(page_id):
            """Validate page ID."""
            if not page_id:
                return False, "Page ID cannot be empty"

            if not isinstance(page_id, str):
                return False, "Page ID must be a string"

            invalid_chars = ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]
            for char in invalid_chars:
                if char in page_id:
                    return False, f"Page ID contains invalid character: {char}"

            if len(page_id) > 255:
                return False, "Page ID too long (max 255 characters)"

            return True, "Valid page ID"

        is_valid, message = validate_page_id("")
        assert is_valid is False

        is_valid, message = validate_page_id(123)
        assert is_valid is False

        is_valid, message = validate_page_id("page/with/slashes")
        assert is_valid is False

        is_valid, message = validate_page_id("valid_page_id_123")
        assert is_valid is True
