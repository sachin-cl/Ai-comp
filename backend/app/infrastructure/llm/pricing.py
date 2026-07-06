"""USD price per 1M tokens (prompt, completion). Unknown models cost 0 (e.g. local Ollama)."""

PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "text-embedding-3-small": (0.02, 0.0),
    # Anthropic
    "claude-sonnet-5": (3.00, 15.00),
    "claude-opus-4-8": (15.00, 75.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    # Gemini
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-pro": (1.25, 5.00),
}


def compute_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    prompt_price, completion_price = PRICES_PER_MTOK.get(model, (0.0, 0.0))
    return round(
        prompt_tokens / 1_000_000 * prompt_price
        + completion_tokens / 1_000_000 * completion_price,
        6,
    )
