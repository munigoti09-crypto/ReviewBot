"""Fix generator and response parser for ReviewBot AI Fix Agent."""

import ast
import json
import re
from typing import Tuple

from reviewbot.utils.logger import get_logger

logger = get_logger("reviewbot.ai_agent.fix_generator")


class FixParsingError(Exception):
    """Raised when LLM response cannot be parsed as valid JSON."""
    pass


class FixValidationError(Exception):
    """Raised when LLM-generated fix fails validation constraints."""
    pass


class FixGenerator:
    """Parses and validates LLM responses to produce safe, syntactically valid code fixes."""

    @staticmethod
    def _extract_json_string(raw_text: str) -> str:
        """Extract a JSON substring from raw LLM output, handling markdown blocks."""
        text = raw_text.strip()

        # Check for ```json ... ``` or ``` ... ```
        code_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        if code_block_match:
            candidate = code_block_match.group(1).strip()
            if candidate.startswith("{") and candidate.endswith("}"):
                return candidate

        # Look for the first outer curly bracket block {...}
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            return text[first_brace : last_brace + 1]

        return text

    @classmethod
    def parse_response(
        cls,
        raw_response: str,
        expected_file: str,
        original_code: str,
    ) -> Tuple[str, str]:
        """Parse raw LLM response, validate JSON structure, and verify Python syntax.

        Args:
            raw_response: The raw string response returned by the LLM.
            expected_file: The target filename being fixed.
            original_code: The original source code of the file.

        Returns:
            Tuple of (fixed_code, explanation).

        Raises:
            FixParsingError: If response is empty or cannot be parsed as JSON.
            FixValidationError: If response structure is invalid, fixed code is empty,
                                or generated code has Python syntax errors.
        """
        if not raw_response or not raw_response.strip():
            raise FixParsingError("LLM response is empty.")

        json_text = cls._extract_json_string(raw_response)

        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON from LLM response: %s", e)
            raise FixParsingError(f"Malformed JSON in LLM response: {e}") from e

        if not isinstance(data, dict):
            raise FixValidationError("LLM response JSON must be an object/dict.")

        if "fixed_code" not in data:
            raise FixValidationError("Missing required 'fixed_code' field in LLM response.")

        fixed_code = data["fixed_code"]
        if not isinstance(fixed_code, str):
            raise FixValidationError("'fixed_code' field must be a string.")

        explanation = data.get("explanation", "")
        if not isinstance(explanation, str):
            explanation = str(explanation)

        # Validate that if the original code was non-empty, the fix is not completely empty
        if original_code.strip() and not fixed_code.strip():
            raise FixValidationError(
                "Proposed fixed code is empty, which would delete the entire file contents."
            )

        # Validate Python syntax using ast.parse without executing code
        try:
            ast.parse(fixed_code, filename=expected_file)
        except SyntaxError as e:
            logger.warning("Generated Python code failed syntax validation for %s: %s", expected_file, e)
            raise FixValidationError(
                f"Generated code contains Python syntax error on line {e.lineno}: {e.msg}"
            ) from e

        return fixed_code, explanation.strip()
