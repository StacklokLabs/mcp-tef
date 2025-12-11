"""Embedding service with multi-backend support (fastembed, OpenAI, custom API)."""

import asyncio
from typing import Literal

import httpx
import structlog

from mcp_tef.api.errors import EmbeddingGenerationError

logger = structlog.get_logger(__name__)


class EmbeddingService:
    """Service for generating embeddings using multiple backends.

    Supports:
    - fastembed: Local embedding models (fast, no API costs)
    - openai: OpenAI embeddings API
    - custom: Self-hosted embedding API
    """

    def __init__(
        self,
        model_type: Literal["fastembed", "openai", "custom"],
        model_name: str,
        api_key: str = "",
        custom_api_url: str = "",
        timeout: int = 30,
    ):
        """Initialize embedding service.

        Args:
            model_type: Backend type ('fastembed', 'openai', or 'custom')
            model_name: Model identifier (e.g., 'BAAI/bge-small-en-v1.5', 'text-embedding-3-small')
            api_key: API key (required for OpenAI)
            custom_api_url: Custom API URL (required for custom backend)
            timeout: Request timeout in seconds
        """
        self.model_type = model_type
        self.model_name = model_name
        self.api_key = api_key
        self.custom_api_url = custom_api_url
        self.timeout = timeout

        # Initialize fastembed model if using local backend
        self._fastembed_model = None
        if model_type == "fastembed":
            self._init_fastembed()

    def _init_fastembed(self) -> None:
        """Initialize fastembed model (lazy loading)."""
        try:
            from fastembed import TextEmbedding

            logger.info(f"Initializing fastembed model: {self.model_name}")
            self._fastembed_model = TextEmbedding(model_name=self.model_name)
            logger.info("Fastembed model initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize fastembed: {e}")
            raise EmbeddingGenerationError(
                f"Failed to initialize fastembed model '{self.model_name}': {str(e)}"
            ) from e

    async def generate_embedding(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Input text to embed

        Returns:
            Embedding vector as list of floats

        Raises:
            EmbeddingGenerationError: If embedding generation fails
        """
        if self.model_type == "fastembed":
            return await self._fastembed_embed(text)
        if self.model_type == "openai":
            return await self._openai_embed(text)
        if self.model_type == "custom":
            return await self._custom_api_embed(text)
        raise EmbeddingGenerationError(f"Unknown model type: {self.model_type}")

    async def generate_embeddings_batch(self, texts: list[str]) -> list[list[float | int]]:
        """Generate embeddings for multiple texts concurrently.

        Args:
            texts: List of input texts to embed

        Returns:
            List of embedding vectors

        Raises:
            EmbeddingGenerationError: If any embedding generation fails
        """
        logger.info(f"Generating embeddings for {len(texts)} texts")

        if self.model_type == "fastembed":
            # Fastembed supports batch processing natively
            return await self._fastembed_embed_batch(texts)
        # For API backends, process concurrently
        tasks = [self.generate_embedding(text) for text in texts]
        results = await asyncio.gather(*tasks)
        return list(results)

    async def _fastembed_embed(self, text: str) -> list[float]:
        """Generate embedding using fastembed (local model).

        Args:
            text: Input text

        Returns:
            Embedding vector
        """
        try:
            if self._fastembed_model is None:
                self._init_fastembed()

            # Run in thread pool to avoid blocking async loop
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(
                None, lambda: list(self._fastembed_model.embed([text]))
            )
            return embeddings[0].tolist()

        except Exception as e:
            logger.error(f"Fastembed embedding failed: {e}")
            raise EmbeddingGenerationError(f"Fastembed embedding failed: {str(e)}") from e

    async def _fastembed_embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings in batch using fastembed.

        Args:
            texts: List of input texts

        Returns:
            List of embedding vectors
        """
        try:
            if self._fastembed_model is None:
                self._init_fastembed()

            # Run in thread pool to avoid blocking async loop
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(
                None, lambda: list(self._fastembed_model.embed(texts))
            )
            return [emb.tolist() for emb in embeddings]

        except Exception as e:
            logger.error(f"Fastembed batch embedding failed: {e}")
            raise EmbeddingGenerationError(f"Fastembed batch embedding failed: {str(e)}") from e

    async def _openai_embed(self, text: str) -> list[float]:
        """Generate embedding using OpenAI API.

        Args:
            text: Input text

        Returns:
            Embedding vector
        """
        if not self.api_key:
            raise EmbeddingGenerationError("OpenAI API key is required")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "input": text,
                        "model": self.model_name,
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data["data"][0]["embedding"]

        except httpx.HTTPStatusError as e:
            logger.error(f"OpenAI API error: {e.response.status_code} - {e.response.text}")
            raise EmbeddingGenerationError(f"OpenAI API error: {e.response.status_code}") from e
        except Exception as e:
            logger.error(f"OpenAI embedding failed: {e}")
            raise EmbeddingGenerationError(f"OpenAI embedding failed: {str(e)}") from e

    async def _custom_api_embed(self, text: str) -> list[float]:
        """Generate embedding using custom API.

        Args:
            text: Input text

        Returns:
            Embedding vector
        """
        if not self.custom_api_url:
            raise EmbeddingGenerationError("Custom API URL is required")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.custom_api_url,
                    json={"text": text},
                )
                response.raise_for_status()
                data = response.json()
                return data["embedding"]

        except httpx.HTTPStatusError as e:
            logger.error(f"Custom API error: {e.response.status_code} - {e.response.text}")
            raise EmbeddingGenerationError(f"Custom API error: {e.response.status_code}") from e
        except Exception as e:
            logger.error(f"Custom API embedding failed: {e}")
            raise EmbeddingGenerationError(f"Custom API embedding failed: {str(e)}") from e
