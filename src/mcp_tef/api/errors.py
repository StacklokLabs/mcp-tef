"""Custom error classes and exception handlers for the API."""

from typing import Any

from fastapi import Request, status
from fastapi.responses import JSONResponse


class MCPEvalException(Exception):
    """Base exception for MCP Evaluation System."""

    def __init__(self, message: str, status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class ResourceNotFoundError(MCPEvalException):
    """Raised when a requested resource is not found."""

    def __init__(self, resource_type: str, resource_id: str):
        message = f"{resource_type} with id '{resource_id}' not found"
        super().__init__(message, status.HTTP_404_NOT_FOUND)
        self.resource_type = resource_type
        self.resource_id = resource_id


class ValidationError(MCPEvalException):
    """Raised when input validation fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, status.HTTP_422_UNPROCESSABLE_CONTENT)
        self.details = details or {}


class DuplicateResourceError(MCPEvalException):
    """Raised when attempting to create a resource that already exists."""

    def __init__(self, resource_type: str, field: str, value: str):
        message = f"{resource_type} with {field} '{value}' already exists"
        super().__init__(message, status.HTTP_409_CONFLICT)
        self.resource_type = resource_type
        self.field = field
        self.value = value


class DatabaseError(MCPEvalException):
    """Raised when database operations fail."""

    def __init__(self, message: str, original_error: Exception | None = None):
        super().__init__(f"Database error: {message}", status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.original_error = original_error


class LLMProviderError(MCPEvalException):
    """Raised when LLM provider requests fail."""

    def __init__(self, provider: str, message: str, original_error: Exception | None = None):
        super().__init__(
            f"LLM provider '{provider}' error: {message}",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.provider = provider
        self.original_error = original_error


class LLMProviderAPIKeyError(MCPEvalException):
    """Raised when LLM provider API key is missing or invalid."""

    def __init__(self, provider: str, message: str):
        super().__init__(
            f"LLM provider '{provider}' API key error: {message}",
            status.HTTP_400_BAD_REQUEST,
        )
        self.provider = provider


class TestRunIncompleteError(MCPEvalException):
    """Raised when attempting to access results of incomplete test run."""

    def __init__(self, test_run_id: str, current_status: str):
        super().__init__(
            f"Test run '{test_run_id}' is not completed (current status: {current_status})",
            status.HTTP_409_CONFLICT,
        )
        self.test_run_id = test_run_id
        self.current_status = current_status


class ConfigurationError(MCPEvalException):
    """Raised when configuration is invalid or missing."""

    def __init__(self, message: str):
        super().__init__(f"Configuration error: {message}", status.HTTP_500_INTERNAL_SERVER_ERROR)


class EmbeddingGenerationError(MCPEvalException):
    """Raised when embedding generation fails."""

    def __init__(self, message: str, original_error: Exception | None = None):
        super().__init__(
            f"Embedding generation error: {message}",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.original_error = original_error


class ToolIngestionError(MCPEvalException):
    """Raised when tool ingestion fails during test run execution."""

    def __init__(self, message: str, server_url: str, original_error: Exception | None = None):
        super().__init__(
            f"Tool ingestion failed for server '{server_url}': {message}",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.server_url = server_url
        self.original_error = original_error


class BadRequestError(MCPEvalException):
    """Raised when the client makes a bad request."""

    def __init__(self, message: str, original_error: Exception | None = None):
        super().__init__(
            f"Bad request: {message}",
            status.HTTP_400_BAD_REQUEST,
        )
        self.original_error = original_error


async def mcp_eval_exception_handler(request: Request, exc: MCPEvalException) -> JSONResponse:
    """Handle MCPEvalException and return appropriate JSON response.

    Args:
        request: FastAPI request object
        exc: The exception instance

    Returns:
        JSON response with error details
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.__class__.__name__,
            "message": exc.message,
            "details": getattr(exc, "details", None),
        },
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions.

    Args:
        request: FastAPI request object
        exc: The exception instance

    Returns:
        JSON response with error details
    """
    # Include exception details only in debug mode
    details = str(exc) if getattr(request.app.state, "debug", False) else None

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalServerError",
            "message": "An unexpected error occurred",
            "details": details,
        },
    )
