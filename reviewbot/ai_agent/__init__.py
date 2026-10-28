"""AI Review & Fix Agent module for ReviewBot CLI (Work 3)."""

from reviewbot.ai_agent.agent import AIAgent, generate_fix
from reviewbot.ai_agent.fix_generator import FixGenerator, FixParsingError, FixValidationError
from reviewbot.ai_agent.llm_client import (
    BaseLLMClient,
    GeminiLLMClient,
    LLMAuthenticationError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    MockLLMClient,
    OpenAILLMClient,
    get_llm_client,
)
from reviewbot.ai_agent.patch_builder import PatchBuilder
from reviewbot.ai_agent.prompt_builder import PromptBuilder

__all__ = [
    "generate_fix",
    "AIAgent",
    "BaseLLMClient",
    "OpenAILLMClient",
    "GeminiLLMClient",
    "MockLLMClient",
    "get_llm_client",
    "LLMError",
    "LLMAuthenticationError",
    "LLMTimeoutError",
    "LLMRateLimitError",
    "PromptBuilder",
    "FixGenerator",
    "FixParsingError",
    "FixValidationError",
    "PatchBuilder",
]
