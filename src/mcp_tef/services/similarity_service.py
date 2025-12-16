"""Similarity analysis service with multi-method support."""

import asyncio
from datetime import UTC, datetime
from typing import Any

import numpy as np
import structlog
from mcp_tef_models.schemas import MCPServerConfig, NormalizedTool, ToolDefinition
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from mcp_tef.api.errors import ValidationError
from mcp_tef.services.embedding_service import EmbeddingService
from mcp_tef.services.mcp_loader import MCPLoaderService

logger = structlog.get_logger(__name__)


def calculate_cosine_similarity(embedding_a: list[float], embedding_b: list[float]) -> float:
    """Calculate cosine similarity between two embeddings.

    Args:
        embedding_a: First embedding vector
        embedding_b: Second embedding vector

    Returns:
        Cosine similarity score (0.0-1.0)
    """
    vec_a = np.array(embedding_a).reshape(1, -1)
    vec_b = np.array(embedding_b).reshape(1, -1)
    similarity = cosine_similarity(vec_a, vec_b)[0][0]
    return float(similarity)


def calculate_tfidf_similarity(descriptions: list[str]) -> np.ndarray:
    """Calculate TF-IDF similarity matrix for tool descriptions.

    Args:
        descriptions: List of tool descriptions

    Returns:
        2D numpy array of TF-IDF cosine similarity scores
    """
    if len(descriptions) < 2:
        return np.array([[1.0]])

    vectorizer = TfidfVectorizer(stop_words="english", max_features=1000)
    tfidf_matrix = vectorizer.fit_transform(descriptions)
    return cosine_similarity(tfidf_matrix, tfidf_matrix)


def calculate_jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Calculate Jaccard similarity between two sets.

    Args:
        set_a: First set
        set_b: Second set

    Returns:
        Jaccard similarity score (0.0-1.0)
    """
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0

    intersection = len(set_a.intersection(set_b))
    union = len(set_a.union(set_b))
    return intersection / union if union > 0 else 0.0


class SimilarityService:
    """Service for analyzing tool similarity using multiple methods.

    Supports:
    - Embedding-based similarity (cosine similarity of embeddings)
    - TF-IDF analysis (distinctive term overlap)
    - Parameter overlap (Jaccard + semantic similarity)
    """

    def __init__(
        self,
        embedding_service: EmbeddingService,
        mcp_loader_service: MCPLoaderService | None = None,
    ):
        """Initialize similarity service.

        Args:
            embedding_service: Service for generating embeddings
            mcp_loader_service: Optional service for loading tools from URLs
        """
        self.embedding_service = embedding_service
        self.mcp_loader_service = mcp_loader_service

    def _build_similarity_matrix_from_embeddings(
        self,
        embeddings: list[list[float]],
    ) -> np.ndarray:
        """Build a similarity matrix from embeddings using cosine similarity.

        Args:
            embeddings: List of embedding vectors

        Returns:
            2D numpy array of cosine similarity scores
        """
        n = len(embeddings)
        matrix = np.zeros((n, n))

        for i in range(n):
            for j in range(i, n):
                if i == j:
                    matrix[i][j] = 1.0
                else:
                    similarity = calculate_cosine_similarity(embeddings[i], embeddings[j])
                    matrix[i][j] = similarity
                    matrix[j][i] = similarity

        return matrix

    async def extract_and_normalize_tools(
        self,
        server_configs: list[MCPServerConfig],
        tool_names: list[str] | None = None,
    ) -> list[NormalizedTool]:
        """Extract and normalize tools from MCP server configurations.

        Args:
            server_configs: Array of MCPServerConfig objects to fetch tools from
            tool_names: Optional list of tool names to filter. If provided, only tools
                with matching names will be included.

        Returns:
            List of normalized tool definitions with temporary IDs

        Raises:
            ValidationError: If input is invalid or yields fewer than 2 tools
        """
        if not self.mcp_loader_service:
            raise ValidationError("MCPLoaderService is required")

        logger.info(f"Fetching tools from {len(server_configs)} servers")
        if tool_names:
            logger.info(f"Filtering tools by names: {tool_names}")

        # Fetch tools concurrently
        fetch_tasks = [
            self._fetch_tools_from_server(server.url, server.transport) for server in server_configs
        ]
        fetch_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        # Process results
        normalized_tools = []
        tool_names_set = set(tool_names) if tool_names else None

        for server, tools in zip(server_configs, fetch_results, strict=False):
            url = server.url
            if isinstance(tools, Exception):
                logger.warning(f"Failed to fetch tools from {url}: {tools}")
                continue

            for tool in tools:
                # Filter by tool name if specified
                if tool_names_set is not None and tool.name not in tool_names_set:
                    continue

                normalized_tools.append(
                    NormalizedTool(
                        id=f"{url}:{tool.name}",
                        name=tool.name,
                        description=tool.description,
                        input_schema=tool.input_schema,
                        parameters=tool.parameters,
                        server_url=url,
                    )
                )

        # Validate minimum tool count
        if len(normalized_tools) < 2:
            if tool_names:
                error_msg = (
                    f"At least 2 tools required for similarity analysis, "
                    f"got {len(normalized_tools)}. Requested tool names: {tool_names}. "
                    "Make sure the specified tools exist on the provided server(s)."
                )
                raise ValidationError(error_msg)
            raise ValidationError(
                f"At least 2 tools required for similarity analysis, got {len(normalized_tools)}"
            )

        logger.info(f"Extracted and normalized {len(normalized_tools)} tools")
        return normalized_tools

    async def _fetch_tools_from_server(self, url: str, transport: str) -> list[ToolDefinition]:
        """Fetch tools from a single MCP server.

        Args:
            url: MCP server URL
            transport: Transport protocol ('sse' or 'streamable-http')

        Returns:
            List of tool definitions

        Raises:
            Exception: If fetching fails
        """
        # Fetch tools using MCPLoaderService
        if not self.mcp_loader_service:
            raise ValidationError("MCPLoaderService is required")
        return await self.mcp_loader_service.load_tools_from_server(url, transport)

    def construct_embedding_text(
        self,
        tool: NormalizedTool,
        include_parameters: bool = False,
    ) -> str:
        """Construct text for embedding generation.

        Args:
            tool: Normalized tool definition
            include_parameters: Whether to include parameter info in embedding

        Returns:
            Text string for embedding
        """
        name = tool.name
        description = tool.description

        if not include_parameters:
            # Description-only (primary for tool selection confusion)
            return f"{name} {description}"

        # Full embedding (including parameters)
        parameters = tool.parameters
        if not parameters:
            return f"{name} {description}"

        param_names = ", ".join(parameters.keys())
        param_descriptions = " ".join(parameters.values())

        return f"{name} {description} {param_names} {param_descriptions}"

    async def calculate_embedding_similarity(
        self,
        tools: list[NormalizedTool],
        compute_full_similarity: bool = False,
    ) -> tuple[np.ndarray, np.ndarray | None]:
        """Calculate embedding-based similarity for all tool pairs.

        Args:
            tools: List of normalized tool definitions
            compute_full_similarity: Whether to compute full similarity (including parameters)

        Returns:
            Tuple of (description_only_matrix, full_similarity_matrix or None)
        """
        logger.info(f"Calculating embedding similarity for {len(tools)} tools")

        # Generate description-only embeddings (always)
        description_texts = [
            self.construct_embedding_text(tool, include_parameters=False) for tool in tools
        ]
        description_embeddings = await self.embedding_service.generate_embeddings_batch(
            description_texts
        )

        # Calculate description-only similarity matrix
        desc_matrix = self._build_similarity_matrix_from_embeddings(description_embeddings)

        # Optionally generate full embeddings (including parameters)
        full_matrix = None
        if compute_full_similarity:
            full_texts = [
                self.construct_embedding_text(tool, include_parameters=True) for tool in tools
            ]
            full_embeddings = await self.embedding_service.generate_embeddings_batch(full_texts)
            full_matrix = self._build_similarity_matrix_from_embeddings(full_embeddings)

        return desc_matrix, full_matrix

    def calculate_description_overlap(
        self,
        tools: list[NormalizedTool],
    ) -> np.ndarray:
        """Calculate TF-IDF based description overlap.

        Args:
            tools: List of normalized tool definitions

        Returns:
            2D similarity matrix
        """
        logger.info(f"Calculating TF-IDF description overlap for {len(tools)} tools")
        descriptions = [tool.description for tool in tools]
        return calculate_tfidf_similarity(descriptions)

    def calculate_parameter_overlap(
        self,
        tool_a: NormalizedTool,
        tool_b: NormalizedTool,
    ) -> float:
        """Calculate parameter overlap between two tools.

        Uses Jaccard similarity of parameter names.

        Args:
            tool_a: First tool
            tool_b: Second tool

        Returns:
            Parameter overlap score (0.0-1.0)
        """
        params_a = set(tool_a.parameters.keys())
        params_b = set(tool_b.parameters.keys())
        return calculate_jaccard_similarity(params_a, params_b)

    def calculate_parameter_overlap_matrix(
        self,
        tools: list[NormalizedTool],
    ) -> np.ndarray:
        """Calculate parameter overlap matrix for all tool pairs.

        Args:
            tools: List of normalized tool definitions

        Returns:
            2D numpy array of parameter overlap scores
        """
        logger.info(f"Calculating parameter overlap matrix for {len(tools)} tools")
        n = len(tools)
        param_matrix = np.zeros((n, n))

        for i in range(n):
            for j in range(n):
                if i == j:
                    param_matrix[i][j] = 1.0
                else:
                    param_matrix[i][j] = self.calculate_parameter_overlap(tools[i], tools[j])

        return param_matrix

    def build_similarity_matrix(
        self,
        tools: list[NormalizedTool],
        embedding_matrix: np.ndarray,
        threshold: float,
    ) -> dict[str, Any]:
        """Build similarity matrix response.

        Args:
            tools: List of normalized tools
            embedding_matrix: Similarity matrix from embeddings
            threshold: Threshold for flagging pairs

        Returns:
            Similarity matrix response dict
        """
        tool_ids = [tool.id for tool in tools]
        matrix = embedding_matrix.tolist()

        # Find flagged pairs
        flagged_pairs = []
        for i in range(len(tools)):
            for j in range(i + 1, len(tools)):
                similarity = embedding_matrix[i][j]
                if similarity >= threshold:
                    flagged_pairs.append(
                        {
                            "tool_a_id": tool_ids[i],
                            "tool_b_id": tool_ids[j],
                            "similarity_score": float(similarity),
                        }
                    )

        return {
            "tool_ids": tool_ids,
            "matrix": matrix,
            "threshold": threshold,
            "flagged_pairs": flagged_pairs,
            "generated_at": datetime.now(UTC).isoformat(),
        }

    def calculate_overlap_matrix(
        self,
        tools: list[NormalizedTool],
        semantic_matrix: np.ndarray,
        description_matrix: np.ndarray,
        parameter_matrix: np.ndarray,
    ) -> dict[str, Any]:
        """Calculate capability overlap matrix with dimension breakdown.

        Weighted average:
        - Semantic: 0.5
        - Parameters: 0.3
        - Description: 0.2

        Args:
            tools: List of normalized tools
            semantic_matrix: Semantic similarity matrix (from embeddings)
            description_matrix: Description overlap matrix (from TF-IDF)
            parameter_matrix: Parameter overlap matrix (from Jaccard similarity)

        Returns:
            Overlap matrix response dict
        """
        logger.info(f"Calculating overlap matrix for {len(tools)} tools")

        # Weighted average
        weights = {"semantic": 0.5, "parameters": 0.3, "description": 0.2}
        overlap_matrix = (
            weights["semantic"] * semantic_matrix
            + weights["parameters"] * parameter_matrix
            + weights["description"] * description_matrix
        )

        tool_ids = [tool.id for tool in tools]

        return {
            "tool_ids": tool_ids,
            "matrix": overlap_matrix.tolist(),
            "dimensions": weights,
            "generated_at": datetime.now(UTC).isoformat(),
        }
