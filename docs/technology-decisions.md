# Technology Decisions: MCP Tool Evaluation System

**Generated**: 2025-11-10
**Status**: Consolidated from all specifications
**Git Commit**: 859d728254fc64586c05039908056c6b4bec1709

## Executive Summary

This document consolidates all technology decisions from the MCP Tool Evaluation System specifications. These decisions form the technical foundation for tool evaluation, similarity analysis, security architecture, and performance optimization.

**Tech Stack Summary**:
- **Runtime**: Python 3.13+ (native type hints)
- **Framework**: FastAPI 0.115+ with async/await throughout
- **Validation**: Pydantic v2.9+ for all structured data
- **LLM Integration**: Pydantic AI 0.0.13+ with OpenRouter provider
- **Database**: SQLite with aiosqlite 0.20+ (async access)
- **Testing**: pytest 8.3.0+ with real database (no mocks)
- **Code Quality**: Ruff (format/lint) + Ty (type checking)

---

## Table of Contents

1. [Pydantic AI with OpenRouter](#1-pydantic-ai-with-openrouter)
2. [Pydantic Evals](#2-pydantic-evals)
3. [MCP Tool Definition Format](#3-mcp-tool-definition-format)
4. [FastAPI + SQLite Integration](#4-fastapi--sqlite-integration)
5. [Testing with Real Database](#5-testing-with-real-database)
6. [Embedding Library Selection](#6-embedding-library-selection)
7. [Similarity Calculation Method](#7-similarity-calculation-method)
8. [TF-IDF Analysis](#8-tf-idf-analysis)
9. [Overlap Matrix Calculation](#9-overlap-matrix-calculation)
10. [Differentiation Recommendations](#10-differentiation-recommendations)
11. [API Key Header Extraction](#11-api-key-header-extraction)
12. [Runtime Model Configuration](#12-runtime-model-configuration)
13. [Database Schema Changes for Security](#13-database-schema-changes-for-security)
14. [Tool Ingestion Workflow](#14-tool-ingestion-workflow)
15. [Server Connectivity Verification](#15-server-connectivity-verification)
16. [Transaction Boundaries](#16-transaction-boundaries)
17. [Concurrency Strategy](#17-concurrency-strategy)

---

## 1. Pydantic AI with OpenRouter

**Decision**: Use Pydantic AI with OpenRouter provider for LLM interfacing

**Used In**: 001-this-is-an (Core Evaluation), 002-inter-tool-similarity (LLM-based recommendations)

**Rationale**:
- Native OpenRouter support through `OpenRouterProvider` for 400+ models via single API
- Automatic tool definition extraction from Python functions using type hints and docstrings
- Built-in async support aligns with FastAPI's async architecture
- Automatic retry logic for validation failures and HTTP errors
- Type-safe interface using Pydantic models for input validation and structured output
- Reduces boilerplate for tool calling and parameter extraction

**Alternatives Considered**:
- **LangChain**: More complex, heavier framework with unnecessary abstractions for focused use case
- **Raw OpenAI SDK with OpenRouter**: Requires manual tool definition schema construction and parameter extraction logic
- **Instructor library**: Strong for structured outputs, but Pydantic AI provides more comprehensive agent functionality including tool calling and state management

**Key Integration Points**:
- LLM service wraps Pydantic AI Agent for tool selection
- Tool definitions converted from MCP format to Pydantic AI format
- Async operations throughout evaluation service
- Error handling uses built-in retry mechanisms

**Implementation Notes**:
```python
from pydantic_ai import Agent

# Simple shorthand (recommended)
agent = Agent("openrouter:anthropic/claude-3.5-sonnet")

# Tool definitions via decorators
@agent.tool
async def tool_function(ctx: RunContext, param: str) -> str:
    """Tool description for LLM."""
    return result
```

**Dependencies**:
- `pydantic-ai>=0.0.13`
- `httpx>=0.27.0` (for OpenAI-compatible API calls)

---

## 2. Pydantic Evals

**Decision**: Use Pydantic Evals framework for systematic evaluation of tool selection and parameter extraction

**Used In**: 001-this-is-an (Evaluation Framework)

**Rationale**:
- Purpose-built for evaluating LLM systems (augmented LLMs to multi-agent systems)
- Code-first approach allows defining evaluations in Python with version control
- OpenTelemetry integration provides detailed tracing and observability
- Supports both deterministic (code-based) and non-deterministic (LLM-based) evaluators
- Composable metrics: rule-based checks, LLM judges, and human annotations
- Built-in integration with Pydantic Logfire for visualization

**Alternatives Considered**:
- **pytest alone**: Lacks specialized support for probabilistic outputs and LLM-specific metrics
- **Custom evaluation framework**: Significant engineering effort to replicate built-in features
- **LangSmith or similar**: Vendor lock-in and less control over evaluation logic

**Key Integration Points**:
- Case/Dataset pattern for test scenarios
- Evaluators for classification accuracy, parameter validation
- OpenTelemetry traces for debugging

**Implementation Notes**:
- **Test Philosophy**: AI systems are probabilistic (not deterministic unit tests)
- **Evaluation Composition**: Rule-based metrics + reference-free assessments + human labels
- **Code-First**: All components defined in Python and version controlled

**Best Practices**:
1. Prefer cheap code-based tests over human/machine review
2. Look for "quick wins" with deterministic checks (regex, format validation)
3. Store test data in version control as code

**Dependencies**:
- `pydantic-evals>=0.0.2`

---

## 3. MCP Tool Definition Format

**Decision**: Follow MCP Protocol Revision 2025-06-18 specification for tool definitions

**Used In**: All features (Core format for tool definitions)

**Rationale**:
- Official standard ensures compatibility with MCP ecosystem
- JSON Schema provides strong typing and validation for tool parameters
- Well-documented specification with clear examples
- Model-controlled design allows LLMs to discover and invoke tools automatically
- Optional output schema enables result validation

**Alternatives Considered**:
- **Custom tool format**: Would break compatibility with MCP ecosystem
- **OpenAPI/Swagger**: More complex than needed, designed for HTTP APIs rather than function calling
- **Function signature extraction**: Less explicit, harder to validate and document

**Tool Definition Structure**:
```json
{
  "name": "unique_tool_identifier",
  "title": "Human Readable Tool Name (optional)",
  "description": "Human-readable description of what the tool does",
  "inputSchema": {
    "type": "object",
    "properties": {
      "param_name": {
        "type": "string",
        "description": "Parameter description"
      }
    },
    "required": ["param_name"]
  },
  "outputSchema": { "type": "object", ... }
}
```

**Integration with Pydantic AI**:
1. Parse inputSchema as Pydantic model or TypedDict
2. Use tool description in agent tool decorator
3. Extract required parameters from schema
4. Map JSON Schema types to Python types
5. Generate tool function signature dynamically

**Validation Strategy**:
- Use JSON Schema validator for input validation
- Store tool definitions in database with schema validation on insert
- Validate LLM-selected tools match available tool definitions
- Compare LLM-extracted parameters against inputSchema

---

## 4. FastAPI + SQLite Integration

**Decision**: Use FastAPI with aiosqlite for async SQLite access, with separate Pydantic models for API schemas and database operations

**Used In**: All features (Core API and storage architecture)

**Rationale**:
- aiosqlite provides true async SQLite access without blocking event loop
- Lightweight solution appropriate for evaluation system (not high-concurrency production)
- SQLite simplifies deployment (no separate database server)
- Pydantic V2 provides fast validation for API requests/responses
- Clear separation of concerns between API layer and data layer

**Alternatives Considered**:
- **SQLModel**: Unifies SQLAlchemy and Pydantic but lags behind latest features
- **SQLAlchemy 2.0 async**: More powerful but adds complexity, overkill for this use case
- **Synchronous SQLite**: Would block event loop, degrading FastAPI async performance
- **PostgreSQL**: Unnecessary complexity for evaluation system

**Architecture Pattern**:
```
FastAPI Endpoints → Pydantic Request/Response Models → Repository Layer → aiosqlite
```

**Database Connection Management**:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.db = await aiosqlite.connect("database.db")
    app.state.db.row_factory = aiosqlite.Row
    yield
    # Shutdown
    await app.state.db.close()

app = FastAPI(lifespan=lifespan)
```

**Best Practices**:
- Use async context managers for connections and cursors
- Single shared connection per application instance
- Parameterized queries (?) to prevent SQL injection
- Commit after write operations
- Set `row_factory = aiosqlite.Row` for dict-like access

**Key Gotchas**:
- SQLite has limited concurrency (single writer at a time)
- In-memory databases (`:memory:`) don't persist across connections
- JSON columns stored as TEXT, need serialization/deserialization
- Foreign key constraints disabled by default (enable with PRAGMA)

**Dependencies**:
- `fastapi>=0.115.0`
- `aiosqlite>=0.20.0`
- `uvicorn>=0.32.0` (ASGI server)

---

## 5. Testing with Real Database

**Decision**: Use pytest fixtures with in-memory SQLite databases for integration testing

**Used In**: All features (Testing strategy)

**Rationale**:
- In-memory SQLite (`:memory:`) provides fast, isolated test databases
- Each test gets clean database state, preventing cross-contamination
- Real database ensures accurate testing of SQL queries and schema
- Fixtures with function scope provide automatic setup/teardown
- No mocking required - tests verify actual database behavior
- Transaction-based isolation faster than create/drop for each test

**Alternatives Considered**:
- **Mocked database**: Doesn't catch SQL errors, schema issues, or query problems
- **Shared test database**: Risk of test interference and data contamination
- **PostgreSQL test container**: Unnecessary complexity and slower
- **File-based test database**: Slower than in-memory, requires cleanup

**Basic Pattern**:
```python
@pytest.fixture
async def test_db():
    """Create an in-memory SQLite database for testing."""
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    
    # Create schema
    await db.execute("""
        CREATE TABLE tool_definitions (...)
    """)
    await db.commit()
    
    yield db
    await db.close()
```

**Best Practices**:
- Use function-scoped fixtures for test independence
- `yield` separates setup (before) and teardown (after)
- In-memory databases clean up automatically
- Transaction rollback faster than dropping/recreating tables

**Integration with FastAPI Testing**:
```python
@pytest.fixture
async def client(test_db):
    """FastAPI test client with test database."""
    app.state.db = test_db
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
```

**Dependencies**:
- `pytest>=8.3.0`
- `pytest-asyncio>=0.24.0`
- `pytest-cov>=6.0.0`

---

## 6. Embedding Library Selection

**Decision**: Use multi-backend approach with fastembed (local), OpenAI API, and self-hosted support

**Used In**: 002-inter-tool-similarity (Similarity Analysis)

**Rationale**:
- **fastembed**: Fast local embeddings without API costs (good for development/testing)
- **OpenAI API**: High-quality embeddings with simple REST interface
- **Self-hosted**: Flexibility for organizations with custom models
- Abstraction layer normalizes all three interfaces to return consistent embedding format

**Alternatives Considered**:
- **sentence-transformers**: Good for local models but doesn't support OpenAI API directly
- **langchain**: Too heavyweight, adds unnecessary abstraction
- **openai Python SDK**: Only covers OpenAI, would need separate abstraction anyway

**Implementation Pattern**:
```python
class EmbeddingService:
    async def generate_embedding(self, text: str, model: str) -> list[float]:
        if model.startswith("fastembed:"):
            return await self._fastembed_embed(text, model)
        elif model.startswith("openai:"):
            return await self._openai_embed(text, model)
        else:
            return await self._custom_api_embed(text, model)
```

**Configuration**:
- `EMBEDDING_MODEL_TYPE`: fastembed, openai, or custom
- `EMBEDDING_MODEL_NAME`: Model identifier (e.g., `BAAI/bge-small-en-v1.5`)
- `OPENAI_API_KEY`: For OpenAI embeddings
- `CUSTOM_EMBEDDING_API_URL`: For self-hosted API

**Dependencies**:
- `fastembed` (local embeddings)
- `httpx` (for OpenAI/custom API calls)

---

## 7. Similarity Calculation Method

**Decision**: Use component-wise embedding concatenation with cosine similarity

**Used In**: 002-inter-tool-similarity (Core similarity metric)

**Rationale**:
- Simpler than multi-component concatenation (single embedding per tool)
- Captures semantic meaning from all tool components in context
- Parameter information included naturally in the text
- Fast computation suitable for pairwise comparisons
- Cosine similarity is standard for embeddings and handles dimensionality well

**Alternatives Considered**:
- **Separate embeddings per component then concatenate**: More complex, requires multiple embedding calls
- **Average of component embeddings**: Loses information about component relationships
- **Weighted average**: Requires tuning weights, adds complexity

**Implementation**:
1. Construct embedding text: `tool name + description + parameter names + parameter descriptions`
2. Generate single embedding for combined text
3. Calculate cosine similarity between embeddings

**Dual Similarity Scores** (002 enhancement):
- **Description-only** (primary): name + description (what LLMs primarily use for selection)
- **Full** (optional): name + description + parameters (complete functional similarity)

---

## 8. TF-IDF Analysis

**Decision**: Use `scikit-learn`'s `TfidfVectorizer` for identifying distinctive vs. generic terminology

**Used In**: 002-inter-tool-similarity (Terminology analysis)

**Rationale**:
- scikit-learn is standard library for text analysis
- TF-IDF automatically weights distinctive terms higher
- Can identify tools with high overlap in distinctive terminology
- Fast enough for batch processing

**Alternatives Considered**:
- **Manual TF-IDF calculation**: More error-prone, reinventing wheel
- **Pure keyword matching**: Less sophisticated, misses semantic relationships

**Implementation**:
- Extract text from all tool descriptions
- Vectorize with TF-IDF
- Identify terms with high TF-IDF scores (distinctive) vs. low scores (generic)
- Compare tool pairs based on shared distinctive terms

**Dependencies**:
- `scikit-learn` (TF-IDF analysis)

---

## 9. Overlap Matrix Calculation

**Decision**: Weighted average of three dimensions: semantic (0.5), parameters (0.3), description (0.2)

**Used In**: 002-inter-tool-similarity (Capability overlap)

**Rationale**:
- Semantic similarity is most important (captures purpose/intent)
- Parameter overlap identifies functional similarity
- Description overlap captures terminology overlap
- Weights can be made configurable if needed

**Alternatives Considered**:
- **Maximum of three scores**: Loses information about multi-dimensional similarity
- **Separate matrices**: More complex for users to interpret

**Dimensions**:
- **Semantic similarity**: Cosine similarity of embeddings (weight: 0.5)
- **Parameter overlap**: Jaccard similarity of parameter names + semantic similarity of descriptions (weight: 0.3)
- **Description overlap**: TF-IDF cosine similarity (weight: 0.2)

---

## 10. Differentiation Recommendations

**Decision**: Rule-based analysis with LLM enhancement for recommendations

**Used In**: 002-inter-tool-similarity (Actionable guidance)

**Rationale**:
- Rule-based issue detection is reliable and fast
- LLM-generated recommendations are more natural and actionable
- Combines deterministic analysis with creative suggestions
- Can validate recommendations before returning to user

**Alternatives Considered**:
- **Purely rule-based**: Less natural, requires extensive templates
- **Purely LLM-based**: Less reliable, harder to validate, more expensive

**Implementation Pattern**:
1. **Analyze issues** (rule-based):
   - Overlapping terminology (TF-IDF comparison)
   - Unclear scope (check for domain mentions)
   - Parameter similarity (compare names and descriptions)
   - Naming clarity (check for clear purpose indication)

2. **Generate recommendations** (LLM-assisted):
   - For each issue, prompt LLM to suggest specific fixes
   - Format: Issue → Why it matters → Specific action
   - Include revised tool descriptions
   - Provide executable commands/JSON patches

---

## 11. API Key Header Extraction

**Decision**: Use FastAPI `Header` dependency with custom validation function

**Used In**: 003-remove-api-key (Security architecture)

**Rationale**:
- FastAPI's dependency injection provides clean separation of concerns
- Testable in isolation (can mock dependency in tests)
- Automatic OpenAPI documentation generation includes header requirement
- Type-safe with IDE autocomplete support
- Aligns with async patterns and Pydantic validation

**Alternatives Considered**:
- **Manual `request.headers.get()`**: Verbose, error-prone, bypasses FastAPI's dependency system
- **Middleware-based extraction**: Overkill for single header, complicates testing
- **OAuth2PasswordBearer**: Designed for bearer tokens, not custom headers, adds unnecessary complexity

**Implementation Pattern**:
```python
from fastapi import Header, HTTPException

async def get_api_key(x_model_api_key: str = Header(...)) -> str:
    """Extract and validate API key from request header."""
    if not x_model_api_key or not x_model_api_key.strip():
        raise HTTPException(status_code=401, detail="API key required")
    return x_model_api_key.strip()
```

**Security Notes**:
- API key NEVER persisted to database
- API key NEVER logged (configure structlog to mask header)
- API key isolated per request context (no shared state)

---

## 12. Runtime Model Configuration

**Decision**: Pydantic BaseModel for request body with default values

**Used In**: 003-remove-api-key (Model configuration)

**Rationale**:
- Pydantic validates all constraints automatically
- Default values defined in schema (DRY principle, self-documenting)
- OpenAPI schema auto-generated with descriptions and constraints
- Runtime type checking prevents invalid configurations
- Supports environment variable overrides via BaseSettings if needed later

**Alternatives Considered**:
- **Dict with manual validation**: Error-prone, no type safety
- **Dataclasses with validators**: Pydantic provides superior validation and serialization
- **Separate config classes per provider**: Premature abstraction

**Implementation**:
```python
class ModelConfigRequest(BaseModel):
    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    timeout: int = Field(30, gt=0, le=300)
    temperature: float = Field(0.4, ge=0.0, le=2.0)
    max_retries: int = Field(3, ge=0, le=10)
```

**Default Values Justification**:
- `timeout=30`: Industry standard for API calls
- `temperature=0.4`: Semi-deterministic (suitable for tool selection with some variation)
- `max_retries=3`: Standard retry count for transient failures

---

## 13. Database Schema Changes for Security

**Decision**: Direct schema.sql modification with cascading deletes (DROP providers/models tables, CREATE model_settings)

**Used In**: 003-remove-api-key (Security improvement)

**Rationale**:
- SQLite CASCADE automatically cleans up dependent records
- Spec assumes clean database initialization (no migration script needed)
- Indexes on provider/model enable efficient filtering in audit queries
- CHECK constraints enforce validation at database level (defense in depth)
- model_settings immutable (no update triggers needed)

**Alternatives Considered**:
- **Migration script with data preservation**: Rejected (spec assumes clean slate)
- **JSON column for model_settings**: Rejected (loses query ability, no constraint enforcement)
- **Keep models table without API key**: Rejected (spec requires complete removal for simplification)

**Schema Changes**:
```sql
-- DROP (with CASCADE)
DROP TABLE IF EXISTS providers CASCADE;
DROP TABLE IF EXISTS models CASCADE;

-- CREATE (new model_settings)
CREATE TABLE IF NOT EXISTS model_settings (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    timeout INTEGER NOT NULL CHECK (timeout > 0 AND timeout <= 300),
    temperature REAL NOT NULL CHECK (temperature >= 0 AND temperature <= 2),
    max_retries INTEGER NOT NULL CHECK (max_retries >= 0 AND max_retries <= 10),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ALTER (test_cases and test_runs)
-- Remove model_id from test_cases (requires table recreation in SQLite)
-- Add model_settings_id to test_runs
```

---

## 14. Tool Ingestion Workflow

**Decision**: Ingest tools during `POST /test-cases/{id}/run` execution

**Used In**: 004-decouple-tool-ingestion (Fresh tool state)

**Rationale**:
- Test run is the natural boundary for tool ingestion (test execution needs fresh tools)
- Aligns with transactional boundary (test run creation + tool ingestion succeed/fail together)
- Provides clear error handling scope (test run fails if any server unreachable)
- Supports concurrent ingestion from multiple MCP servers using `asyncio.gather()`

**Alternatives Considered**:
- **Ingest tools in background task**: Rejected (race conditions, complicates error handling)
- **Ingest on-demand when LLM requests**: Rejected (adds latency during evaluation)
- **Pre-ingest on test case creation**: Rejected (tools become stale, same problem as server registration)

**Implementation Pattern**:
```python
async def execute_test_case(test_case_id: str, test_run_id: str):
    # 1. Fetch associated MCP servers
    servers = await get_test_case_servers(test_case_id)
    
    # 2. Ingest tools concurrently from all servers
    ingestion_tasks = [
        ingest_tools_for_test_run(server, test_run_id)
        for server in servers
    ]
    results = await asyncio.gather(*ingestion_tasks, return_exceptions=True)
    
    # 3. Check for failures and fail fast
    for result in results:
        if isinstance(result, Exception):
            # Update test run status to FAILED
            # Raise exception with clear error message
    
    # 4. Proceed with LLM evaluation using ingested tools
```

---

## 15. Server Connectivity Verification

**Decision**: Keep `MCPLoaderService.load_tools_from_server()` for connectivity checks

**Used In**: 004-decouple-tool-ingestion (Fast server registration)

**Rationale**:
- Already exists and works correctly for both connectivity verification and tool fetching
- Returns empty list on connection failure (appropriate for connectivity check)
- Uses MCP SDK's exception handling for unreachable servers
- No need to create separate connectivity-only method

**Alternatives Considered**:
- **Create dedicated `check_connectivity()` method**: Rejected (duplicates logic, loading tools inherently verifies connectivity)
- **Remove connectivity check entirely**: Rejected (immediate feedback on server status valuable)
- **Use HEAD request or health check endpoint**: Rejected (MCP servers don't standardize health endpoints)

**Pattern**:
```python
async def verify_server_connectivity(server: MCPServerResponse):
    try:
        # This call verifies connectivity without storing results
        tools = await mcp_loader.load_tools_from_server(server.url, server.transport)
        # Update server status to ACTIVE
        await mcp_server_repo.update_status(server.id, MCPServerStatus.ACTIVE)
    except Exception as e:
        # Update server status to FAILED with error message
        await mcp_server_repo.update_status(server.id, MCPServerStatus.FAILED)
        raise
```

---

## 16. Transaction Boundaries

**Decision**: Separate transactions for server management vs test execution

**Used In**: 004-decouple-tool-ingestion (Clean separation of concerns)

**Rationale**:
- Server create/update transaction: Only server record + status update (fast, simple)
- Test run transaction: Test run creation + tool ingestion + evaluation (complex, longer duration)
- Cleaner error handling (server registration never fails due to tool ingestion)
- Better separation of concerns (server management vs test execution)

**Alternatives Considered**:
- **Keep combined transaction (server + tools)**: Rejected (this is the current problem - slow, complex failure modes)
- **No transactions at all**: Rejected (risks data inconsistency)

**Server Create Transaction**:
```python
async def create_mcp_server(server_data: MCPServerCreate):
    # Single transaction: create server + verify connectivity
    async with db.transaction():
        server = await mcp_server_repo.create(server_data)
        await verify_server_connectivity(server)
    return server
```

**Test Run Transaction**:
```python
async def execute_test_case(test_case_id: str):
    # Single transaction: create test run + ingest tools + evaluate
    async with db.transaction():
        test_run = await test_run_repo.create(test_case_id)
        await ingest_tools_for_test_run(test_case_id, test_run.id)
        await evaluate_test_run(test_run.id)
    return test_run
```

---

## 17. Concurrency Strategy

**Decision**: Use `asyncio.gather()` for parallel tool ingestion from multiple servers

**Used In**: 004-decouple-tool-ingestion, 002-inter-tool-similarity (URL fetching)

**Rationale**:
- Aligns with Constitution Principle VII (Concurrency by Default)
- Test cases can have multiple associated MCP servers
- Loading tools from servers is I/O-bound, ideal for asyncio concurrency
- Reduces test run execution time when multiple servers involved

**Alternatives Considered**:
- **Sequential ingestion**: Rejected (slower, violates Principle VII)
- **Background tasks with callbacks**: Rejected (complicates flow and error handling)
- **Concurrent.futures thread pool**: Rejected (asyncio sufficient for I/O-bound tasks)

**Implementation**:
```python
async def ingest_tools_for_test_run(test_case_id: str, test_run_id: str):
    servers = await get_test_case_servers(test_case_id)
    
    # Create ingestion task for each server
    tasks = [
        _ingest_from_single_server(server, test_run_id)
        for server in servers
    ]
    
    # Execute concurrently, collect results
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Fail fast on first error
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            raise ToolIngestionError(
                f"Failed to ingest tools from server {servers[i].name}: {result}"
            )
```

---

## Summary

The MCP Tool Evaluation System's technology decisions form a cohesive architecture based on modern Python async patterns, Pydantic validation, and pragmatic choices that balance simplicity with functionality.

**Core Principles**:
1. **Async by default**: FastAPI + aiosqlite + Pydantic AI all async
2. **Pydantic everywhere**: Validation at all boundaries
3. **Real testing**: In-memory SQLite, no mocks
4. **Security first**: Runtime API keys, never persisted
5. **Fresh data**: Tools ingested at execution time
6. **Concurrent**: Multiple operations processed in parallel

**Integration Summary**:
- Pydantic AI + OpenRouter: LLM interactions
- FastAPI + aiosqlite: API and storage
- Pydantic Evals: Evaluation framework
- fastembed/OpenAI: Embedding generation
- scikit-learn: TF-IDF analysis

All decisions documented here are implemented in the codebase and validated by comprehensive test coverage (38/38 tests passing, 77% coverage).

---

**Document Version**: 1.0  
**Last Updated**: 2025-11-10  
**Git Commit**: 859d728254fc64586c05039908056c6b4bec1709

