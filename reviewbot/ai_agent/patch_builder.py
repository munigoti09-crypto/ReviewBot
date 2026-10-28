"""Patch builder for ReviewBot AI Fix Agent.

Generates standard unified diff patches using Python's difflib without modifying files on disk.
"""

import difflib
from typing import Tuple


class PatchBuilder:
    """Builds unified diff patches comparing original and corrected code."""

    @staticmethod
    def _normalize_path(file_path: str) -> str:
        """Normalize file path to POSIX style (forward slashes) for standard diff compatibility."""
        return file_path.replace("\\", "/").lstrip("/")

    @classmethod
    def create_patch(
        cls,
        file_path: str,
        original_code: str,
        fixed_code: str,
    ) -> Tuple[str, bool]:
        """Generate a standard unified diff patch for a modified file.

        Args:
            file_path: Path of the file being modified.
            original_code: Original file content.
            fixed_code: Fixed file content.

        Returns:
            Tuple of (patch_string, is_changed).
            If no changes exist, returns ("", False).
        """
        # Exact string match check
        if original_code == fixed_code:
            return "", False

        # Split into lines preserving line endings
        orig_lines = original_code.splitlines(keepends=True)
        fixed_lines = fixed_code.splitlines(keepends=True)

        # Standard diff headers: a/path and b/path
        clean_path = cls._normalize_path(file_path)
        from_file = f"a/{clean_path}"
        to_file = f"b/{clean_path}"

        diff = list(
            difflib.unified_diff(
                orig_lines,
                fixed_lines,
                fromfile=from_file,
                tofile=to_file,
                lineterm="",
            )
        )

        if not diff:
            return "", False

        # Assemble patch string
        # Standard difflib lines include existing newlines if keepends=True,
        # but the header lines from difflib don't have newlines.
        # So we ensure every line has a consistent newline.
        patch_lines = []
        for line in diff:
            if not line.endswith("\n"):
                patch_lines.append(line + "\n")
            else:
                patch_lines.append(line)

        patch_str = "".join(patch_lines)
        return patch_str, True
