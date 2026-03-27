from app.core.config import settings
from langchain_openai import OpenAIEmbeddings
from langchain_community.embeddings import DashScopeEmbeddings


class EmbeddingsFactory:
    @staticmethod
    def create():
        """
        Factory method to create an embeddings instance based on .env config.
        """
        embeddings_provider = settings.EMBEDDINGS_PROVIDER.lower()

        if embeddings_provider == "openai":
            return OpenAIEmbeddings(
                openai_api_key=settings.OPENAI_API_KEY,
                openai_api_base=settings.OPENAI_API_BASE,
                model=settings.OPENAI_EMBEDDINGS_MODEL,
            )
        elif embeddings_provider == "dashscope":
            return DashScopeEmbeddings(
                model=settings.DASH_SCOPE_EMBEDDINGS_MODEL,
                dashscope_api_key=settings.DASH_SCOPE_API_KEY,
            )
        elif embeddings_provider == "openrouter":
            return OpenAIEmbeddings(
                openai_api_key=settings.OPENROUTER_API_KEY,
                openai_api_base=settings.OPENROUTER_API_BASE,
                model=settings.OPENROUTER_EMBEDDINGS_MODEL,
            )
        else:
            raise ValueError(f"Unsupported embeddings provider: {embeddings_provider}")
