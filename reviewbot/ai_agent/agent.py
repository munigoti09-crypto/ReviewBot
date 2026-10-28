"""Main orchestration agent for ReviewBot AI Fix Agent (Work 3).

Exposes the primary integration function:
    generate_fix(issues, source_files, feedback=None) -> list[dict]
"""

import os
from typing import Any, Optional

from reviewbot.ai_agent.fix_generator import FixGenerator, FixParsingError, FixValidationError
from reviewbot.ai_agent.llm_client import BaseLLMClient, LLMError, get_llm_client
from reviewbot.ai_agent.patch_builder import PatchBuilder
from reviewbot.ai_agent.prompt_builder import PromptBuilder
from reviewbot.core.models import FixResult, FixStatus, Issue
from reviewbot.utils.logger import get_logger

logger = get_logger("reviewbot.ai_agent.agent")


def _is_safe_path(file_path: str) -> bool:
    """Validate that file path does not attempt path traversal or dangerous system access."""
    if not file_path or not isinstance(file_path, str):
        return False

    # Disallow path traversal components
    parts = file_path.replace("\\", "/").split("/")
    if ".." in parts:
        return False

    # Disallow absolute paths that target root/system directories outside the workspace
    # Windows drive letters or root slashes
    if os.path.isabs(file_path) and not file_path.startswith(("\\\\", "/")):
        # Check if it has suspicious traversal
        norm = os.path.normpath(file_path)
        if ".." in norm:
            return False

    return True


class AIAgent:
    """Orchestrates AI code fix generation for ReviewBot."""

    def __init__(self, llm_client: Optional[BaseLLMClient] = None) -> None:
        self._llm_client = llm_client

    def _get_client(self) -> BaseLLMClient:
        if self._llm_client is None:
            self._llm_client = get_llm_client()
        return self._llm_client

    def fix_file(
        self,
        file_path: str,
        issues: list[dict[str, Any]],
        original_code: str,
        feedback: Optional[str] = None,
    ) -> FixResult:
        """Process issues for a single file and return a FixResult.

        Args:
            file_path: Relative or canonical path of the file.
            issues: List of issue dictionaries for this file.
            original_code: The original source code of the file.
            feedback: Optional validation feedback from a prior attempt.

        Returns:
            FixResult object representing proposed, unchanged, or failed fix.
        """
        issue_codes = list(dict.fromkeys(
            str(i.get("code", "")).strip() for i in issues if i.get("code")
        ))

        # Security check: path traversal
        if not _is_safe_path(file_path):
            logger.warning("Unsafe file path detected and rejected: %s", file_path)
            return FixResult(
                file=file_path,
                issue_codes=issue_codes,
                explanation=f"Security violation: path traversal or invalid path '{file_path}' rejected.",
                original_code=original_code,
                fixed_code="",
                patch="",
                status=FixStatus.FAILED.value,
            )

        try:
            # 1. Build prompts
            system_prompt = PromptBuilder.build_system_prompt()
            user_prompt = PromptBuilder.build_user_prompt(
                file_path=file_path,
                source_code=original_code,
                issues=issues,
                feedback=feedback,
            )

            # 2. Call LLM
            client = self._get_client()
            raw_response = client.complete(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )

            # 3. Parse and validate response
            fixed_code, explanation = FixGenerator.parse_response(
                raw_response=raw_response,
                expected_file=file_path,
                original_code=original_code,
            )

            # 4. Generate unified diff patch
            patch, is_changed = PatchBuilder.create_patch(
                file_path=file_path,
                original_code=original_code,
                fixed_code=fixed_code,
            )

            # 5. Determine status
            status = FixStatus.PROPOSED.value if is_changed else FixStatus.UNCHANGED.value

            return FixResult(
                file=file_path,
                issue_codes=issue_codes,
                explanation=explanation or ("No changes required." if not is_changed else "Applied fix."),
                original_code=original_code,
                fixed_code=fixed_code,
                patch=patch,
                status=status,
            )

        except (FixParsingError, FixValidationError) as e:
            logger.error("Fix validation failed for %s: %s", file_path, e)
            return FixResult(
                file=file_path,
                issue_codes=issue_codes,
                explanation=f"Fix parsing/validation failed: {e}",
                original_code=original_code,
                fixed_code="",
                patch="",
                status=FixStatus.FAILED.value,
            )

        except LLMError as e:
            logger.error("LLM error while fixing %s: %s", file_path, e)
            return FixResult(
                file=file_path,
                issue_codes=issue_codes,
                explanation=f"LLM communication error: {e}",
                original_code=original_code,
                fixed_code="",
                patch="",
                status=FixStatus.FAILED.value,
            )

        except Exception as e:
            logger.exception("Unexpected error while fixing %s: %s", file_path, e)
            return FixResult(
                file=file_path,
                issue_codes=issue_codes,
                explanation=f"Unexpected error: {e}",
                original_code=original_code,
                fixed_code="",
                patch="",
                status=FixStatus.FAILED.value,
            )

    def generate_fix(
        self,
        issues: list[dict],
        source_files: dict[str, str],
        feedback: Optional[str] = None,
    ) -> list[dict]:
        """Main batch generation method."""
        if not issues:
            logger.info("No issues provided to generate_fix. Returning empty list.")
            return []

        # Group issues by target file
        files_to_issues: dict[str, list[dict]] = {}
        for idx, issue in enumerate(issues):
            if not isinstance(issue, dict):
                logger.warning("Skipping invalid issue item at index %d: not a dict.", idx)
                continue

            file_path = issue.get("file")
            if not file_path or not isinstance(file_path, str):
                logger.warning("Skipping issue without valid 'file' key at index %d.", idx)
                continue

            files_to_issues.setdefault(file_path, []).append(issue)

        results: list[dict] = []

        for file_path, file_issues in files_to_issues.items():
            issue_codes = list(dict.fromkeys(
                str(i.get("code", "")).strip() for i in file_issues if i.get("code")
            ))

            if file_path not in source_files:
                logger.error("Source content missing for file '%s'.", file_path)
                failed_res = FixResult(
                    file=file_path,
                    issue_codes=issue_codes,
                    explanation=f"Source content missing for file '{file_path}' in provided source_files.",
                    original_code="",
                    fixed_code="",
                    patch="",
                    status=FixStatus.FAILED.value,
                )
                results.append(failed_res.to_dict())
                continue

            original_code = source_files[file_path]
            fix_result = self.fix_file(
                file_path=file_path,
                issues=file_issues,
                original_code=original_code,
                feedback=feedback,
            )
            results.append(fix_result.to_dict())

        return results


def generate_fix(
    issues: list[dict],
    source_files: dict[str, str],
    feedback: Optional[str] = None,
) -> list[dict]:
    """Generate AI fixes for static analysis issues.

    Public integration function for ReviewBot CLI (Work 3).

    Args:
        issues: List of issue dictionaries from Work 2.
        source_files: Dictionary mapping file paths to their source contents.
        feedback: Optional feedback from Work 4 validation for retry iterations.

    Returns:
        List of structured fix proposal dictionaries for Work 4.
    """
    agent = AIAgent()
    return agent.generate_fix(issues=issues, source_files=source_files, feedback=feedback)
