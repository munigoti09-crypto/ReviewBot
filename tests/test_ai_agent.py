"""Unit and integration tests for Work 3 - ReviewBot AI Review & Fix Agent."""

import json
import os
import pytest

from reviewbot.ai_agent.agent import AIAgent, generate_fix, _is_safe_path
from reviewbot.ai_agent.fix_generator import FixGenerator, FixParsingError, FixValidationError
from reviewbot.ai_agent.llm_client import (
    BaseLLMClient,
    LLMAuthenticationError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    MockLLMClient,
)
from reviewbot.ai_agent.patch_builder import PatchBuilder
from reviewbot.ai_agent.prompt_builder import PromptBuilder
from reviewbot.core.config import LLMConfig
from reviewbot.core.models import FixStatus


# ---------------------------------------------------------------------------
# Test Fixtures & Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_client() -> MockLLMClient:
    return MockLLMClient()


@pytest.fixture
def agent(mock_client: MockLLMClient) -> AIAgent:
    return AIAgent(llm_client=mock_client)


# ---------------------------------------------------------------------------
# 1. Successful Fix Generation
# ---------------------------------------------------------------------------

def test_successful_fix_generation(agent: AIAgent, mock_client: MockLLMClient):
    issues = [
        {
            "file": "sample.py",
            "line": 2,
            "tool": "ruff",
            "code": "F821",
            "message": "Undefined name 'result'",
            "severity": "error",
        }
    ]
    source_files = {
        "sample.py": "value = 10\nprint(result)\n"
    }

    mock_client.set_response(json.dumps({
        "fixed_code": "value = 10\nprint(value)\n",
        "explanation": "Replaced undefined name 'result' with existing variable 'value'."
    }))

    results = agent.generate_fix(issues, source_files)

    assert len(results) == 1
    fix = results[0]
    assert fix["file"] == "sample.py"
    assert fix["issue_codes"] == ["F821"]
    assert fix["status"] == FixStatus.PROPOSED.value
    assert "value = 10\nprint(value)\n" in fix["fixed_code"]
    assert "--- a/sample.py" in fix["patch"]
    assert "+++ b/sample.py" in fix["patch"]
    assert "-print(result)" in fix["patch"]
    assert "+print(value)" in fix["patch"]
    assert "Replaced undefined" in fix["explanation"]


# ---------------------------------------------------------------------------
# 2. Multiple Issues in One File
# ---------------------------------------------------------------------------

def test_multiple_issues_in_one_file(agent: AIAgent, mock_client: MockLLMClient):
    issues = [
        {
            "file": "math_utils.py",
            "line": 1,
            "tool": "ruff",
            "code": "F401",
            "message": "'os' imported but unused",
            "severity": "warning",
        },
        {
            "file": "math_utils.py",
            "line": 4,
            "tool": "bandit",
            "code": "B101",
            "message": "Use of assert detected",
            "severity": "error",
        },
    ]
    source_files = {
        "math_utils.py": "import os\n\ndef check_positive(x):\n    assert x > 0\n    return x\n"
    }

    fixed_code = "def check_positive(x):\n    if x <= 0:\n        raise ValueError('x must be positive')\n    return x\n"
    mock_client.set_response(json.dumps({
        "fixed_code": fixed_code,
        "explanation": "Removed unused import 'os' and replaced unsafe assert with ValueError."
    }))

    results = agent.generate_fix(issues, source_files)

    assert len(results) == 1
    fix = results[0]
    assert fix["file"] == "math_utils.py"
    assert "F401" in fix["issue_codes"]
    assert "B101" in fix["issue_codes"]
    assert fix["status"] == FixStatus.PROPOSED.value
    assert "-import os" in fix["patch"]
    assert "-    assert x > 0" in fix["patch"]


# ---------------------------------------------------------------------------
# 3. Multiple Source Files
# ---------------------------------------------------------------------------

def test_multiple_source_files(agent: AIAgent, mock_client: MockLLMClient):
    issues = [
        {
            "file": "mod1.py",
            "line": 1,
            "tool": "ruff",
            "code": "E302",
            "message": "Expected 2 blank lines",
            "severity": "info",
        },
        {
            "file": "mod2.py",
            "line": 1,
            "tool": "ruff",
            "code": "F821",
            "message": "Undefined name 'foo'",
            "severity": "error",
        },
    ]
    source_files = {
        "mod1.py": "def f():\n    pass\n",
        "mod2.py": "print(foo)\n",
    }

    # First call will be for mod1, second for mod2
    responses = [
        json.dumps({
            "fixed_code": "\n\ndef f():\n    pass\n",
            "explanation": "Added blank lines.",
        }),
        json.dumps({
            "fixed_code": "foo = 'bar'\nprint(foo)\n",
            "explanation": "Defined variable foo.",
        }),
    ]

    multi_agent = AIAgent(llm_client=MockLLMClient(responses=responses))
    results = multi_agent.generate_fix(issues, source_files)

    assert len(results) == 2
    assert results[0]["file"] == "mod1.py"
    assert results[0]["status"] == FixStatus.PROPOSED.value
    assert results[1]["file"] == "mod2.py"
    assert results[1]["status"] == FixStatus.PROPOSED.value


# ---------------------------------------------------------------------------
# 4. Empty Issue Lists
# ---------------------------------------------------------------------------

def test_empty_issue_list(agent: AIAgent):
    results = agent.generate_fix(issues=[], source_files={"sample.py": "x = 1\n"})
    assert results == []


# ---------------------------------------------------------------------------
# 5. Missing Source Content
# ---------------------------------------------------------------------------

def test_missing_source_content(agent: AIAgent):
    issues = [
        {
            "file": "nonexistent.py",
            "line": 1,
            "tool": "ruff",
            "code": "E999",
            "message": "Syntax error",
            "severity": "error",
        }
    ]
    # source_files does NOT contain nonexistent.py
    results = agent.generate_fix(issues=issues, source_files={})

    assert len(results) == 1
    fix = results[0]
    assert fix["file"] == "nonexistent.py"
    assert fix["status"] == FixStatus.FAILED.value
    assert "Source content missing" in fix["explanation"]
    assert fix["patch"] == ""


# ---------------------------------------------------------------------------
# 6. Invalid Analysis Results
# ---------------------------------------------------------------------------

def test_invalid_analysis_results(agent: AIAgent, mock_client: MockLLMClient):
    issues = [
        "not a dict",
        {"missing_file_key": 123},
        {"file": "valid.py", "line": 1, "code": "W0611", "message": "Unused"},
    ]
    source_files = {"valid.py": "import sys\n"}
    mock_client.set_response(json.dumps({
        "fixed_code": "",
        "explanation": "Removed unused import.",
    }))

    # Should ignore malformed items and process the valid one
    results = agent.generate_fix(issues=issues, source_files=source_files)
    assert len(results) == 1
    assert results[0]["file"] == "valid.py"


# ---------------------------------------------------------------------------
# 7. Malformed LLM Output & Markdown Wrapped JSON
# ---------------------------------------------------------------------------

def test_malformed_llm_json(agent: AIAgent, mock_client: MockLLMClient):
    issues = [{"file": "calc.py", "code": "E001", "line": 1}]
    source_files = {"calc.py": "a = 1\n"}

    mock_client.set_response("This is definitely not JSON.")
    results = agent.generate_fix(issues, source_files)

    assert len(results) == 1
    assert results[0]["status"] == FixStatus.FAILED.value
    assert "Fix parsing/validation failed" in results[0]["explanation"]


def test_markdown_wrapped_json_parsed_properly(agent: AIAgent, mock_client: MockLLMClient):
    issues = [{"file": "calc.py", "code": "E001", "line": 1}]
    source_files = {"calc.py": "a = 1\n"}

    # Response wrapped in ```json ... ```
    wrapped = "Here is the fix:\n```json\n{\n  \"fixed_code\": \"a = 2\\n\",\n  \"explanation\": \"Updated constant.\"\n}\n```\nHope this helps!"
    mock_client.set_response(wrapped)

    results = agent.generate_fix(issues, source_files)
    assert len(results) == 1
    assert results[0]["status"] == FixStatus.PROPOSED.value
    assert "+a = 2" in results[0]["patch"]


# ---------------------------------------------------------------------------
# 8. Invalid Python Syntax in Generated Code
# ---------------------------------------------------------------------------

def test_invalid_python_syntax_rejected(agent: AIAgent, mock_client: MockLLMClient):
    issues = [{"file": "syntax.py", "code": "F821", "line": 1}]
    source_files = {"syntax.py": "print(x)\n"}

    # Fixed code with intentional syntax error: def without closing paren
    mock_client.set_response(json.dumps({
        "fixed_code": "def broken(:\n    pass\n",
        "explanation": "Tried fixing but created bad syntax",
    }))

    results = agent.generate_fix(issues, source_files)
    assert len(results) == 1
    assert results[0]["status"] == FixStatus.FAILED.value
    assert "syntax error" in results[0]["explanation"].lower()


# ---------------------------------------------------------------------------
# 9. LLM Connection & Authentication Failures
# ---------------------------------------------------------------------------

def test_llm_auth_failure(agent: AIAgent, mock_client: MockLLMClient):
    issues = [{"file": "test.py", "code": "F821", "line": 1}]
    source_files = {"test.py": "x = 1\n"}

    mock_client.set_exception(LLMAuthenticationError("Invalid API key provided."))
    results = agent.generate_fix(issues, source_files)

    assert len(results) == 1
    assert results[0]["status"] == FixStatus.FAILED.value
    assert "LLM communication error" in results[0]["explanation"]


def test_llm_timeout_failure(agent: AIAgent, mock_client: MockLLMClient):
    issues = [{"file": "test.py", "code": "F821", "line": 1}]
    source_files = {"test.py": "x = 1\n"}

    mock_client.set_exception(LLMTimeoutError("Request timed out."))
    results = agent.generate_fix(issues, source_files)

    assert len(results) == 1
    assert results[0]["status"] == FixStatus.FAILED.value
    assert "timed out" in results[0]["explanation"]


def test_llm_rate_limit_failure(agent: AIAgent, mock_client: MockLLMClient):
    issues = [{"file": "test.py", "code": "F821", "line": 1}]
    source_files = {"test.py": "x = 1\n"}

    mock_client.set_exception(LLMRateLimitError("Rate limit exceeded."))
    results = agent.generate_fix(issues, source_files)

    assert len(results) == 1
    assert results[0]["status"] == FixStatus.FAILED.value
    assert "rate limit" in results[0]["explanation"].lower()


# ---------------------------------------------------------------------------
# 10. Patch Generation
# ---------------------------------------------------------------------------

def test_patch_builder_unified_diff():
    orig = "def add(a, b):\n    return a - b\n"
    fixed = "def add(a, b):\n    return a + b\n"

    patch, is_changed = PatchBuilder.create_patch("math/calc.py", orig, fixed)
    assert is_changed is True
    assert "--- a/math/calc.py" in patch
    assert "+++ b/math/calc.py" in patch
    assert "-    return a - b" in patch
    assert "+    return a + b" in patch


# ---------------------------------------------------------------------------
# 11. No-Change Responses (Status: Unchanged)
# ---------------------------------------------------------------------------

def test_no_change_response(agent: AIAgent, mock_client: MockLLMClient):
    issues = [{"file": "same.py", "code": "W291", "line": 1}]
    source_files = {"same.py": "x = 42\n"}

    # Fixed code is identical to original code
    mock_client.set_response(json.dumps({
        "fixed_code": "x = 42\n",
        "explanation": "No modification needed.",
    }))

    results = agent.generate_fix(issues, source_files)
    assert len(results) == 1
    assert results[0]["status"] == FixStatus.UNCHANGED.value
    assert results[0]["patch"] == ""


# ---------------------------------------------------------------------------
# 12. Feedback-Based Retry Requests
# ---------------------------------------------------------------------------

def test_feedback_included_in_prompt(agent: AIAgent, mock_client: MockLLMClient):
    issues = [{"file": "retry.py", "code": "F821", "line": 2}]
    source_files = {"retry.py": "a = 1\nprint(b)\n"}
    feedback = "Fix failed unit test test_add(): Expected b to be string, not int."

    mock_client.set_response(json.dumps({
        "fixed_code": "a = 1\nb = 'hello'\nprint(b)\n",
        "explanation": "Defined b as string based on validation feedback.",
    }))

    results = agent.generate_fix(issues, source_files, feedback=feedback)

    assert len(results) == 1
    assert results[0]["status"] == FixStatus.PROPOSED.value

    # Verify that the feedback was included in the user prompt sent to LLM
    assert len(mock_client.calls) == 1
    _, user_prompt = mock_client.calls[0]
    assert "VALIDATION FEEDBACK FROM PREVIOUS ATTEMPT" in user_prompt
    assert feedback in user_prompt


# ---------------------------------------------------------------------------
# 13. Security & Path Validation
# ---------------------------------------------------------------------------

def test_path_traversal_detection():
    assert _is_safe_path("src/app.py") is True
    assert _is_safe_path("app.py") is True
    assert _is_safe_path("../etc/passwd") is False
    assert _is_safe_path("foo/../../bar.py") is False
    assert _is_safe_path("..\\windows\\system32") is False


def test_path_traversal_rejected_in_agent(agent: AIAgent, mock_client: MockLLMClient):
    issues = [{"file": "../../secret.py", "code": "F821", "line": 1}]
    source_files = {"../../secret.py": "secret = 'pass'\n"}

    results = agent.generate_fix(issues, source_files)
    assert len(results) == 1
    assert results[0]["status"] == FixStatus.FAILED.value
    assert "Security violation" in results[0]["explanation"]
    # LLM should not even be called
    assert len(mock_client.calls) == 0


def test_empty_fix_rejection_when_original_nonempty():
    with pytest.raises(FixValidationError, match="would delete the entire file"):
        FixGenerator.parse_response(
            raw_response=json.dumps({"fixed_code": "", "explanation": "Deleted everything"}),
            expected_file="test.py",
            original_code="print('important code')\n",
        )


# ---------------------------------------------------------------------------
# 14. Public Integration Function Contract
# ---------------------------------------------------------------------------

def test_public_generate_fix_contract(monkeypatch):
    """Verify that `from reviewbot.ai_agent.agent import generate_fix` adheres to exact signature."""
    # Monkeypatch get_llm_client to return a Mock client
    mock = MockLLMClient(response_text=json.dumps({
        "fixed_code": "val = 20\n",
        "explanation": "Updated value"
    }))
    monkeypatch.setattr("reviewbot.ai_agent.agent.get_llm_client", lambda: mock)

    issues = [{"file": "mod.py", "code": "C0103", "line": 1}]
    sources = {"mod.py": "val = 10\n"}

    res = generate_fix(issues=issues, source_files=sources)
    assert isinstance(res, list)
    assert len(res) == 1
    assert res[0]["file"] == "mod.py"
    assert res[0]["status"] == "proposed"


# ---------------------------------------------------------------------------
# 15. Optional Manual Live LLM Integration Test
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY") and not os.getenv("GEMINI_API_KEY"),
    reason="Live LLM tests require OPENAI_API_KEY or GEMINI_API_KEY environment variable.",
)
def test_live_llm_manual_integration():
    """Manual integration test verifying connection to real configured LLM provider."""
    issues = [
        {
            "file": "live_test.py",
            "line": 2,
            "tool": "ruff",
            "code": "F821",
            "message": "Undefined name 'foo'",
            "severity": "error",
        }
    ]
    source_files = {
        "live_test.py": "bar = 42\nprint(foo)\n"
    }

    results = generate_fix(issues=issues, source_files=source_files)
    assert len(results) == 1
    fix = results[0]
    assert fix["file"] == "live_test.py"
    assert fix["status"] in ("proposed", "unchanged")
    if fix["status"] == "proposed":
        assert len(fix["patch"]) > 0
        assert "live_test.py" in fix["patch"]
