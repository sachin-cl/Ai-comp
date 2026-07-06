"""Import all adapters so they self-register with the provider registry."""
from app.infrastructure.llm.adapters import (  # noqa: F401
    anthropic_adapter,
    gemini_adapter,
    mock_adapter,
    ollama_adapter,
    openai_adapter,
)
