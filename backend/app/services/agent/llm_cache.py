"""LLM instance cache — avoids recreating LLM objects on every request.

Keys are (provider, model, temperature, streaming) tuples.
"""

from app.services.llm.llm_factory import LLMFactory


class _LLMCache(dict):
    """Dict subclass that auto-creates LLM instances on first access."""

    def __missing__(self, key):
        provider, model, temperature, streaming = key
        llm = LLMFactory.create(
            provider=provider,
            model=model,
            temperature=temperature,
            streaming=streaming,
        )
        self[key] = llm
        return llm


_llm_cache = _LLMCache()
