import os
from typing import List

class PyFileTool:
    """Handles safe file operations for Python projects."""

    @staticmethod
    def list_python_files(directory: str) -> List[str]:
        """Return all .py files in a directory (recursively)."""
        py_files = []
        for root, _, files in os.walk(directory):
            for f in files:
                if f.endswith(".py"):
                    py_files.append(os.path.join(root, f))
        return py_files

    @staticmethod
    def read_file(file_path: str) -> str:
        """Safely read a file's content."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"{file_path} not found")
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
