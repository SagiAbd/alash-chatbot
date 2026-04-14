from typing import Optional
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_deepseek import ChatDeepSeek
from app.core.config import settings


class LLMFactory:
    @staticmethod
    def default_model_for_provider(provider: str) -> str:
        """Return the default model name for a given supported provider."""
        provider = provider.lower()
        if provider == "openai":
            return settings.OPENAI_MODEL
        if provider == "deepseek":
            return settings.DEEPSEEK_MODEL
        if provider == "openrouter":
            return settings.OPENROUTER_MODEL
        raise ValueError(f"Unsupported LLM provider: {provider}")

    @staticmethod
    def create(
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0,
        streaming: bool = True,
    ) -> BaseChatModel:
        """
        Create a LLM instance based on the provider
        """
        # If no provider specified, use the one from settings
        provider = provider or settings.CHAT_PROVIDER
        model_name = model or LLMFactory.default_model_for_provider(provider)

        if provider.lower() == "openai":
            return ChatOpenAI(
                temperature=temperature,
                streaming=streaming,
                model=model_name,
                openai_api_key=settings.OPENAI_API_KEY,
                openai_api_base=settings.OPENAI_API_BASE,
            )
        elif provider.lower() == "deepseek":
            return ChatDeepSeek(
                temperature=temperature,
                streaming=streaming,
                model=model_name,
                api_key=settings.DEEPSEEK_API_KEY,
                api_base=settings.DEEPSEEK_API_BASE,
            )
        elif provider.lower() == "openrouter":
            headers = {}
            if settings.OPENROUTER_SITE_URL:
                headers["HTTP-Referer"] = settings.OPENROUTER_SITE_URL
            if settings.OPENROUTER_SITE_NAME:
                headers["X-OpenRouter-Title"] = settings.OPENROUTER_SITE_NAME

            return ChatOpenAI(
                temperature=temperature,
                streaming=streaming,
                model=model_name,
                openai_api_key=settings.OPENROUTER_API_KEY,
                openai_api_base=settings.OPENROUTER_API_BASE,
                default_headers=headers,
            )
        # Add more providers here as needed
        # elif provider.lower() == "anthropic":
        #     return ChatAnthropic(...)
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")
