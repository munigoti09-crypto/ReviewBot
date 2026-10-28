"""Configuration management for ReviewBot CLI."""

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass
class LLMConfig:
    """Configuration for LLM provider."""
    provider: str = "openai"
    api_key: str | None = None
    model: str = "gpt-4o-mini"
    base_url: str | None = None
    timeout: float = 30.0
    max_retries: int = 3
    temperature: float = 0.0

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Load LLM configuration from environment variables."""
        provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()

        if provider == "gemini":
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("LLM_API_KEY")
            model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
            base_url = os.getenv("GEMINI_BASE_URL")
        else:
            # Default to openai (or compatible)
            api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
            base_url = os.getenv("OPENAI_BASE_URL")

        try:
            timeout = float(os.getenv("LLM_TIMEOUT", "30.0"))
        except ValueError:
            timeout = 30.0

        try:
            max_retries = int(os.getenv("LLM_MAX_RETRIES", "3"))
        except ValueError:
            max_retries = 3

        try:
            temperature = float(os.getenv("LLM_TEMPERATURE", "0.0"))
        except ValueError:
            temperature = 0.0

        return cls(
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            temperature=temperature,
        )

    def mask_api_key(self) -> str:
        """Return masked key representation for safe logging."""
        if not self.api_key:
            return "<none>"
        if len(self.api_key) <= 8:
            return "***"
        return f"{self.api_key[:4]}...{self.api_key[-4:]}"
