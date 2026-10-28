# ReviewBot CLI — Work 3: AI Review & Fix Agent

Production-oriented, modular AI code repair and fixing engine for **ReviewBot CLI**.

ReviewBot CLI automatically analyzes Python code, detects bugs and security vulnerabilities, generates AI-powered fixes, validates those fixes, and produces reports.

This module implements **Work 3 (AI Review & Fix Agent)**. It receives issues detected by static analysis (Work 2), uses an LLM to generate targeted code repairs, produces standard unified diff patches, and returns structured proposals to the validation engine (Work 4).

---

## 1. Folder Structure

```text
reviewbot/
├── __init__.py
├── ai_agent/                     # WORK 3 IMPLEMENTATION
│   ├── __init__.py               # Exports public interfaces
│   ├── agent.py                  # Main orchestration & generate_fix()
│   ├── fix_generator.py          # Response parsing, validation & ast syntax verification
│   ├── llm_client.py             # Isolated provider abstraction (OpenAI, Gemini, Mock)
│   ├── patch_builder.py          # Unified diff generation via difflib
│   └── prompt_builder.py         # Prompt engineering & untrusted context sanitation
├── core/
│   ├── __init__.py
│   ├── config.py                 # LLM configuration & env loader
│   └── models.py                 # Shared data contracts (Issue, FixResult, FixStatus)
└── utils/
    ├── __init__.py
    └── logger.py                 # Safe logging without credential leakage

tests/
├── __init__.py
└── test_ai_agent.py              # Comprehensive unit tests with mocked LLM responses
```

---

## 2. Integration Contract

Work 3 exposes the exact required public integration function:

```python
from reviewbot.ai_agent.agent import generate_fix

fixes = generate_fix(
    issues=issues,
    source_files=source_files,
    feedback=feedback  # Optional retry feedback from Work 4
)
```

### Input Contract (from Work 2)

```python
issues = [
    {
        "file": "sample.py",
        "line": 3,
        "tool": "ruff",
        "code": "F821",
        "message": "Undefined name 'result'",
        "severity": "error"
    }
]

source_files = {
    "sample.py": "value = 10\nprint(result)\n"
}
```

### Output Contract (to Work 4)

```python
[
    {
        "file": "sample.py",
        "issue_codes": ["F821"],
        "explanation": "Replaced the undefined variable with the existing variable.",
        "original_code": "value = 10\nprint(result)\n",
        "fixed_code": "value = 10\nprint(value)\n",
        "patch": "--- a/sample.py\n+++ b/sample.py\n@@ -1,2 +1,2 @@\n value = 10\n-print(result)\n+print(value)\n",
        "status": "proposed"  # "proposed" | "unchanged" | "failed"
    }
]
```

---

## 3. Key Design & Security Features

1. **Zero Execution of Untrusted Code:** Generated code is never executed inside Work 3. Syntax validity is checked purely via `ast.parse()`.
2. **Untrusted Data Sanitization:** Original source code, file contents, comments, and issue messages are strictly delimited and treated as passive untrusted data, preventing prompt injection attacks.
3. **No Direct Disk Writes:** Work 3 never modifies repository files directly on disk. All changes are represented as string patches and proposals.
4. **Path Traversal Protection:** Directory traversal attempts (e.g., `../`, `..\\`) are rejected before contacting any LLM.
5. **Provider Isolation:** LLM provider implementations (OpenAI, Google Gemini) are isolated behind a common `BaseLLMClient` interface with exponential backoff, rate-limit retries, and timeout controls.
6. **Graceful Batch Resilience:** A failure in fixing one file does not halt the processing of other files in the same batch.
7. **Work 4 Retry Support:** Accepts optional `feedback` string from Work 4 validation tests, incorporating test failure details into retry prompts.

---

## 4. Setup & Running Tests

### Installation

```bash
pip install -r requirements.txt
```

### Configuration

Copy `.env.example` to `.env` and set your credentials:

```bash
cp .env.example .env
```

Available environment variables:
- `LLM_PROVIDER`: `openai` (default) or `gemini`
- `OPENAI_API_KEY`: API key for OpenAI / OpenAI-compatible endpoint
- `OPENAI_MODEL`: Model name (default: `gpt-4o-mini`)
- `OPENAI_BASE_URL`: Optional custom base URL (Ollama, vLLM, Azure, OpenRouter)
- `GEMINI_API_KEY`: API key for Google Gemini
- `GEMINI_MODEL`: Model name (default: `gemini-2.5-flash`)
- `LLM_TIMEOUT`: Timeout in seconds (default: `30.0`)
- `LLM_MAX_RETRIES`: Retry attempts for transient errors (default: `3`)

### Running Tests

All unit tests run offline using `MockLLMClient` without consuming API credits:

```bash
python -m pytest tests/test_ai_agent.py -v
```
