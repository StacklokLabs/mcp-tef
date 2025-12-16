# Quickstart Guide: MCP Tool Evaluation System

**Last Updated**: 2025-11-10

This guide shows you how to use mcp-tef to evaluate and improve your MCP tools. Follow the workflows below based on your use case.

> **Note**: For historical specification files that were consolidated into this documentation, see commit [859d728](https://github.com/StacklokLabs/mcp-tef/tree/859d728254fc64586c05039908056c6b4bec1709/specs).

---

## Table of Contents

1. [Installation](#installation)
2. [Quick Start](#quick-start)
3. [Core Concepts](#core-concepts)
4. [Workflow 1: Tool Evaluation](#workflow-1-tool-evaluation)
5. [Workflow 2: Similarity Detection](#workflow-2-similarity-detection)
6. [Workflow 3: Tool Quality Analysis](#workflow-3-tool-quality-analysis)
7. [Advanced Usage](#advanced-usage)
8. [Development & Testing](#development--testing)
9. [Troubleshooting](#troubleshooting)

---

## Installation

### Prerequisites
- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- (Optional) [Ollama](https://ollama.ai/) for local LLM testing

### Setup

```bash
# Clone the repository
git clone https://github.com/StacklokLabs/mcp-tef.git
cd mcp-tef

# Install dependencies
uv sync

# Configure environment (optional - defaults work for Ollama)
cp .env.example .env
# Edit .env with your LLM provider credentials if using cloud providers
```

---

## Quick Start

### Start the Server

**Option 1: Run directly (Python)**

```bash
# Default: HTTPS with auto-generated self-signed certificate
uv run python -m mcp_tef

# OR: HTTP mode for development (insecure)
uv run python -m mcp_tef --tls-enabled=false
```

The server starts at `https://localhost:8000` (or `http://localhost:8000` with `--tls-enabled=false`).

**Option 2: Deploy with CLI (Docker)**

```bash
# Install the CLI
uv tool install "mtef @ git+https://github.com/StacklokLabs/mcp-tef.git#subdirectory=cli"

# Deploy the server
mtef deploy --health-check
```

> **💡 Tip**: The CLI deploys mcp-tef as a Docker container from GitHub Container Registry. See [CLI documentation](../cli/README.md) for details.

### Access API Documentation

Open your browser (accept the self-signed certificate warning if using HTTPS):
- **Interactive API docs**: https://localhost:8000/docs
- **OpenAPI spec**: https://localhost:8000/openapi.json

### Health Check

```bash
# HTTPS (default)
curl -k https://localhost:8000/health

# HTTP (with --tls-enabled=false)
curl http://localhost:8000/health
```

Expected response:
```json
{"status": "healthy"}
```

---

## Core Concepts

### 1. Test Case
A test scenario that defines:
- **Query**: User's natural language request
- **Expected Tool**: Which tool should be selected
- **Expected Parameters**: What parameters should be extracted
- **Available Servers**: List of MCP server URLs to fetch tools from

### 2. Test Run
An execution of a test case with:
- **Fresh Tool Ingestion**: Tools are loaded from servers at runtime (not cached)
- **LLM Evaluation**: The LLM selects a tool and extracts parameters
- **Validation**: System compares LLM output against expectations
- **Runtime Configuration**: API key and model settings provided per-run (not stored)

### 3. Evaluation Result
Analysis of test run including:
- **Classification**: TP (True Positive), FP (False Positive), TN (True Negative), FN (False Negative)
- **Parameter Metrics**: Completeness, correctness, type conformance
- **Confidence Category**: Robust, needs clarity, misleading
- **Recommendations**: Suggestions for improving tool descriptions

### 4. Similarity Analysis
Stateless analysis that:
- **Detects Overlap**: Finds tools with similar descriptions
- **Generates Matrices**: Visualizes similarity across tool sets
- **Provides Recommendations**: AI-powered suggestions for differentiation
- **No Persistence**: Analysis is performed on-demand, no database storage

---

## Workflow 1: Tool Evaluation

**Goal**: Test if your MCP tool descriptions work correctly with LLMs.

### Step 1: Create a Test Case

Use your actual MCP server URLs - no need to register servers first!

**Option A: Using the REST API (curl)**

```bash
curl -k -X POST https://localhost:8000/test-cases \
  -H "Content-Type: application/json" \
  -d '{
    "name": "GitHub repository search",
    "query": "Find repositories related to MCP tools",
    "expected_mcp_server_url": "http://localhost:8080/github/mcp",
    "expected_tool_name": "search_repositories",
    "expected_parameters": {
      "query": "mcp tool topic:mcp stars:>5",
      "sort": "stars"
    },
    "available_mcp_servers": [
      {
        "url": "http://localhost:8080/github/mcp",
        "transport": "streamable-http"
      }
    ]
  }'
```

**Option B: Using the CLI**

```bash
mtef test-case create \
  --name "GitHub repository search" \
  --query "Find repositories related to MCP tools" \
  --expected-server "http://localhost:8080/github/mcp" \
  --expected-tool "search_repositories" \
  --expected-params '{"query": "mcp tool topic:mcp stars:>5", "sort": "stars"}' \
  --servers "http://localhost:8080/github/mcp:streamable-http"
```

> **Note**: The `--servers` flag accepts comma-separated URLs. See [CLI documentation](../cli/README.md) for more examples.
```

> **💡 Tip**: The CLI provides a simpler interface for common operations. See [CLI documentation](../cli/README.md) for full details.

**Response**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "GitHub repository search",
  "query": "Find repositories related to MCP tools",
  "expected_mcp_server_url": "http://localhost:8080/github/mcp",
  "expected_tool_name": "search_repositories",
  "expected_parameters": {
    "query": "mcp tool topic:mcp stars:>5",
    "sort": "stars"
  },
  "available_mcp_servers": [
    {
      "url": "http://localhost:8080/github/mcp",
      "transport": "streamable-http"
    }
  ],
  "created_at": "2025-11-10T10:00:00Z",
  "updated_at": "2025-11-10T10:00:00Z"
}
```

**💡 Key Points**:
- `available_mcp_servers`: Tools will be fetched from these URLs at test execution time
- `expected_mcp_server_url` + `expected_tool_name`: What you expect the LLM to select
- `expected_parameters`: What parameters you expect to be extracted

### Step 2: Run the Test

Execute the test with runtime API key and model configuration:

**Option A: Using the REST API (curl)**

```bash
# Using OpenRouter (recommended for production testing with frontier models)
curl -k -X POST https://localhost:8000/test-cases/550e8400-e29b-41d4-a716-446655440000/run \
  -H "Content-Type: application/json" \
  -H "X-Model-API-Key: sk-or-v1-..." \
  -d '{
    "model_settings": {
      "provider": "openrouter",
      "model": "anthropic/claude-3.5-sonnet",
      "timeout": 30,
      "temperature": 0.4,
      "max_retries": 3
    }
  }'

# Using Ollama (local testing, no API key needed)
curl -k -X POST https://localhost:8000/test-cases/550e8400-e29b-41d4-a716-446655440000/run \
  -H "Content-Type: application/json" \
  -d '{
    "model_settings": {
      "provider": "ollama",
      "model": "llama3.2:3b",
      "timeout": 60,
      "temperature": 0.4,
      "max_retries": 2
    }
  }'
```

**Option B: Using the CLI**

```bash
# Using OpenRouter (recommended for production testing with frontier models)
mtef test-run execute 550e8400-e29b-41d4-a716-446655440000 \
  --model-provider openrouter \
  --model-name anthropic/claude-3.5-sonnet \
  --api-key sk-or-v1-...

# Using Ollama (local testing, no API key needed)
mtef test-run execute 550e8400-e29b-41d4-a716-446655440000 \
  --model-provider ollama \
  --model-name llama3.2:3b
```

**What Happens**:
1. **Tool Ingestion** (1-5s per server): Fresh tools loaded from all `available_mcp_servers`
2. **LLM Evaluation**: LLM receives query and all tool descriptions, selects one
3. **Parameter Extraction**: LLM extracts parameters from the query
4. **Validation**: System compares LLM output vs expectations
5. **Result**: Test run completes with classification and metrics

**Response**:
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "test_case_id": "550e8400-e29b-41d4-a716-446655440000",
  "model_settings": {
    "id": "770e8400-e29b-41d4-a716-446655440002",
    "provider": "openrouter",
    "model": "anthropic/claude-3.5-sonnet",
    "timeout": 30,
    "temperature": 0.4,
    "max_retries": 3,
    "created_at": "2025-11-10T10:05:00Z"
  },
  "status": "completed",
  "classification": "TP",
  "confidence_score": 0.92,
  "execution_time_ms": 2341,
  "created_at": "2025-11-10T10:05:00Z",
  "completed_at": "2025-11-10T10:05:02Z"
}
```

**💡 Security Note**: API keys are **never stored** - they're only used for the duration of the request.

### Step 3: View Detailed Results

**Option A: Using the REST API (curl)**

```bash
curl -k https://localhost:8000/test-runs/660e8400-e29b-41d4-a716-446655440001/result
```

**Option B: Using the CLI**

```bash
mtef test-run get 660e8400-e29b-41d4-a716-446655440001
```

**Response**:
```json
{
  "id": "880e8400-e29b-41d4-a716-446655440003",
  "test_run_id": "660e8400-e29b-41d4-a716-446655440001",
  "classification": "TP",
  "tool_selection_correct": true,
  "parameter_completeness": 1.0,
  "parameter_correctness": 1.0,
  "parameter_type_conformance": true,
  "hallucinated_parameters": [],
  "confidence_category": "robust",
  "reasoning": "The tool description clearly matches the user's intent...",
  "recommendations": [
    "Consider adding examples to the tool description",
    "Specify the expected format for location parameter"
  ],
  "created_at": "2025-11-10T10:05:02Z"
}
```

**Understanding the Results**:

| Field | Meaning |
|-------|---------|
| `classification` | **TP**: Correct tool selected<br>**FP**: Wrong tool selected<br>**TN**: Correctly selected nothing<br>**FN**: Should have selected tool but didn't |
| `parameter_completeness` | Ratio of expected params that were extracted (0.0-1.0) |
| `parameter_correctness` | Ratio of extracted params that are correct (0.0-1.0) |
| `parameter_type_conformance` | Whether all parameters match expected types |
| `confidence_category` | **robust**: High confidence + correct<br>**needs_clarity**: Low confidence + correct<br>**misleading**: High confidence + incorrect ⚠️ |

### Step 4: Get Aggregate Metrics

After running multiple tests:

**Using the REST API (curl)**

```bash
curl -k https://localhost:8000/metrics/summary
```

> **Note**: Aggregate metrics are currently only available via the REST API. CLI support may be added in future releases.

**Response**:
```json
{
  "total_tests": 50,
  "true_positives": 42,
  "false_positives": 3,
  "true_negatives": 4,
  "false_negatives": 1,
  "precision": 0.933,
  "recall": 0.977,
  "f1_score": 0.955,
  "parameter_accuracy": 0.891,
  "average_execution_time_ms": 2156.4,
  "confidence_distribution": {
    "robust": 40,
    "needs_clarity": 8,
    "misleading": 2
  }
}
```

**💡 Interpreting Metrics**:
- **Precision**: Of tools selected, how many were correct? (penalizes false positives)
- **Recall**: Of correct tools, how many were found? (penalizes false negatives)
- **F1 Score**: Harmonic mean of precision and recall
- **Parameter Accuracy**: How accurately parameters are extracted
- **Misleading**: High priority - fix these tool descriptions first! 🚨

---

## Workflow 2: Similarity Detection

**Goal**: Find and fix overlapping tool descriptions that confuse LLMs.

### Option A: Analyze Tools from MCP Server URLs (Recommended)

The easiest way - just provide your MCP server URLs:

**Using the REST API (curl)**

```bash
curl -k -X POST https://localhost:8000/similarity/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "url_list": [
      "http://localhost:8080/fetch/mcp:streamable-http",
      "http://localhost:8080/toolhive-doc-mcp/mcp:streamable-http",
      "http://localhost:8080/mcp-optimizer/mcp:streamable-http",
      "http://localhost:8080/github/mcp:streamable-http"
    ],
    "similarity_threshold": 0.85,
    "include_recommendations": true
  }'
```

**Using the CLI**

```bash
mtef similarity analyze \
  --server-urls "http://localhost:8080/fetch/mcp:streamable-http,http://localhost:8080/toolhive-doc-mcp/mcp:streamable-http,http://localhost:8080/mcp-optimizer/mcp:streamable-http,http://localhost:8080/github/mcp:streamable-http" \
  --threshold 0.85 \
  --recommendations
```

### Option B: Analyze Tools Directly (No Server Fetch)

If you already have tool definitions:

**Using the REST API (curl)**

```bash
curl -k -X POST https://localhost:8000/similarity/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "tool_list": [
      {
        "name": "search_documents",
        "description": "Search through user documents using keywords and filters",
        "parameter": {
          "query": "Search query string",
          "filters": "Optional filters"
        }
      },
      {
        "name": "find_files",
        "description": "Find files in the system by searching with patterns",
        "parameter": {
          "pattern": "File name pattern to match",
          "path": "Optional search path"
        }
      }
    ],
    "similarity_threshold": 0.85,
    "include_recommendations": true
  }'
```

> **Note**: Direct tool list analysis is currently only available via the REST API. CLI support requires MCP server URLs.

### Understanding Similarity Results

**Response**:
```json
{
  "tool_ids": ["search_documents", "find_files"],
  "matrix": [
    [1.0, 0.87],
    [0.87, 1.0]
  ],
  "threshold": 0.85,
  "flagged_pairs": [
    {
      "tool_a_id": "search_documents",
      "tool_b_id": "find_files",
      "similarity_score": 0.87,
      "method": "embedding",
      "flagged": true
    }
  ],
  "recommendations": [
    {
      "tool_pair": ["search_documents", "find_files"],
      "similarity_score": 0.87,
      "issues": [
        {
          "issue_type": "scope_clarity",
          "description": "Both tools describe searching/finding with unclear boundaries"
        }
      ],
      "recommendations": [
        {
          "issue": "scope_clarity",
          "tool_id": "search_documents",
          "recommendation": "Emphasize this tool searches CONTENT within documents, not filenames",
          "priority": "high",
          "revised_description": "Search document CONTENT using keywords and filters. Returns matching text passages with relevance scores."
        },
        {
          "issue": "scope_clarity",
          "tool_id": "find_files",
          "recommendation": "Emphasize this tool searches FILENAMES by pattern, not content",
          "priority": "high",
          "revised_description": "Find files by FILENAME pattern (glob/regex). Returns matching file paths and metadata."
        }
      ]
    }
  ],
  "generated_at": "2025-11-10T10:30:00Z"
}
```

**💡 Similarity Threshold Guide**:
- **0.95+**: Nearly identical (definitely problematic)
- **0.85-0.95**: Very similar (likely confusing)
- **0.70-0.85**: Moderately similar (review recommended)
- **<0.70**: Sufficiently distinct

### Specialized Similarity Endpoints

#### Generate Full Matrix

For visualization or analysis of all pairwise similarities:

**Using the REST API (curl)**

```bash
curl -k -X POST https://localhost:8000/similarity/matrix \
  -H "Content-Type: application/json" \
  -d '{
    "url_list": ["http://localhost:8080/github/mcp:streamable-http"],
    "similarity_threshold": 0.7
  }'
```

**Using the CLI**

```bash
mtef similarity matrix \
  --server-urls "http://localhost:8080/github/mcp:streamable-http" \
  --threshold 0.7
```

> **Note**: The `--server-urls` flag accepts comma-separated URLs for multiple servers.

#### Generate Overlap Matrix

Multi-dimensional analysis (semantic + parameters + description):

```bash
curl -k -X POST https://localhost:8000/similarity/overlap-matrix \
  -H "Content-Type: application/json" \
  -d '{
    "tool_list": [...],
    "similarity_threshold": 0.75
  }'
```

**Response** includes weighted overlap scores:
- **Semantic** (50%): Embedding-based meaning similarity
- **Parameters** (30%): Parameter name/type overlap
- **Description** (20%): TF-IDF keyword overlap

---

## Workflow 3: Tool Quality Analysis

**Goal**: Get AI-powered quality scores and improvement suggestions for your tool descriptions.

### Analyze Tools from MCP Server(s)

**Using the REST API (curl)**

```bash
# Single server (recommended: use frontier models for production testing)
curl -k "https://localhost:8000/mcp-servers/tools/quality?server_urls=http://localhost:8080/github/mcp:streamable-http&model_provider=openrouter&model_name=anthropic/claude-3.5-sonnet" \
  -H "X-Model-API-Key: sk-or-v1-..."

# Multiple servers at once
curl -k "https://localhost:8000/mcp-servers/tools/quality?server_urls=http://localhost:8080/fetch/mcp:streamable-http&server_urls=http://localhost:8080/github/mcp:streamable-http&model_provider=openrouter&model_name=anthropic/claude-3.5-sonnet" \
  -H "X-Model-API-Key: sk-or-v1-..."

# Using Ollama (local testing, no API key)
curl -k "https://localhost:8000/mcp-servers/tools/quality?server_urls=http://localhost:8080/github/mcp:streamable-http&model_provider=ollama&model_name=llama3.2:3b"
```

**Using the CLI**

```bash
# Single server with OpenRouter (recommended for production testing)
mtef tool-quality \
  --server-urls "http://localhost:8080/github/mcp:streamable-http" \
  --model-provider openrouter \
  --model-name anthropic/claude-3.5-sonnet \
  --api-key sk-or-v1-...

# Multiple servers (comma-separated)
mtef tool-quality \
  --server-urls "http://localhost:8080/fetch/mcp:streamable-http,http://localhost:8080/github/mcp:streamable-http" \
  --model-provider openrouter \
  --model-name anthropic/claude-3.5-sonnet \
  --api-key sk-or-v1-...

# Using Ollama (local testing, no API key)
mtef tool-quality \
  --server-urls "http://localhost:8080/github/mcp:streamable-http" \
  --model-provider ollama \
  --model-name llama3.2:3b
```

### Understanding Quality Results

**Response**:
```json
{
  "results": [
    {
      "tool_name": "search_documents",
      "tool_description": "Search through documents",
      "evaluation_result": {
        "clarity": {
          "score": 4,
          "explanation": "Description is vague. What kind of documents? What search capabilities?"
        },
        "completeness": {
          "score": 3,
          "explanation": "Missing: search syntax, supported file types, result format, filters"
        },
        "conciseness": {
          "score": 9,
          "explanation": "Very brief and to the point"
        },
        "suggested_description": "Search document content using keywords and boolean operators. Supports PDF, TXT, DOCX, and MD files. Returns ranked results with highlighted excerpts and relevance scores. Use filters for date range, file type, and tags."
      }
    }
  ]
}
```

**💡 Quality Scores (1-10)**:
- **Clarity**: How understandable is the description?
- **Completeness**: Does it include all necessary information?
- **Conciseness**: Is it succinct without being vague?

**Ideal Profile**: 8-9 clarity, 8-9 completeness, 7-8 conciseness

---

## Advanced Usage

### Custom Embedding Models

For similarity analysis, use different embedding models:

```bash
curl -k -X POST https://localhost:8000/similarity/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "tool_list": [...],
    "embedding_model": "BAAI/bge-large-en-v1.5",
    "similarity_threshold": 0.8
  }'
```

**Available Models** (via fastembed):
- `BAAI/bge-small-en-v1.5` (default) - Fast, good balance
- `BAAI/bge-base-en-v1.5` - More accurate, slower
- `BAAI/bge-large-en-v1.5` - Most accurate, slowest
- `sentence-transformers/all-MiniLM-L6-v2` - Very fast, lower accuracy

### Full Similarity (Include Parameters)

By default, similarity uses descriptions only. To include parameter schemas:

```bash
curl -k -X POST https://localhost:8000/similarity/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "tool_list": [...],
    "compute_full_similarity": true,
    "similarity_threshold": 0.85
  }'
```

This adds parameter names, types, and descriptions to the similarity calculation.

### Filtering Results

Get metrics for specific test cases or date ranges:

```bash
# Specific test cases
curl -k "https://localhost:8000/metrics/summary?test_case_ids=tc1,tc2,tc3"

# Date range
curl -k "https://localhost:8000/metrics/summary?from_date=2025-11-01T00:00:00Z&to_date=2025-11-10T23:59:59Z"
```

### Using Different LLM Providers

#### OpenRouter (Recommended)
```json
{
  "model_settings": {
    "provider": "openrouter",
    "model": "anthropic/claude-3.5-sonnet",
    "timeout": 30,
    "temperature": 0.4
  }
}
```
**Header**: `X-Model-API-Key: sk-or-v1-...`

#### OpenAI
```json
{
  "model_settings": {
    "provider": "openai",
    "model": "gpt-4-turbo",
    "timeout": 30,
    "temperature": 0.4
  }
}
```
**Header**: `X-Model-API-Key: sk-...`

#### Anthropic
```json
{
  "model_settings": {
    "provider": "anthropic",
    "model": "claude-3-5-sonnet-20241022",
    "timeout": 30,
    "temperature": 0.4
  }
}
```
**Header**: `X-Model-API-Key: sk-ant-...`

#### Ollama (Local)
```json
{
  "model_settings": {
    "provider": "ollama",
    "model": "llama3.2:3b",
    "timeout": 60,
    "temperature": 0.4
  }
}
```
**No API key required** (omit `X-Model-API-Key` header)

**💡 Model Recommendations**:
- **Production**: `anthropic/claude-3.5-sonnet` (via OpenRouter) - Best accuracy
- **Development**: `llama3.2:3b` (via Ollama) - Good balance of speed and quality
- **CI/Testing**: `llama3.2:1b` (via Ollama) - Fast, reliable for automated tests
- **Budget**: `meta-llama/llama-3.1-8b-instruct` (via OpenRouter) - Good balance

---

## Development & Testing

### Run Quality Checks

```bash
# Format code
task format

# Lint
task lint

# Type check
task typecheck

# Run all tests
task test

# Run specific test suite
uv run pytest tests/contract/
uv run pytest tests/integration/
```

### Using Mock Mode (No Real LLM)

For testing without LLM API calls:

```bash
# Set environment variable
export DEFAULT_MODEL__PROVIDER=mock

# Run tests
task test
```

### Using Ollama for Development

See [docs/testing-with-ollama.md](testing-with-ollama.md) for complete Ollama setup guide.

**Quick Setup**:
```bash
# Install Ollama
# https://ollama.ai/

# Pull a model
ollama pull llama3.2:3b

# Start mcp-tef (it will auto-detect Ollama)
uv run python -m mcp_tef
```

### Database Location

SQLite database is stored at: `./mcp_eval.db`

To reset:
```bash
rm mcp_eval.db mcp_eval.db-shm mcp_eval.db-wal
# Restart server - it will recreate the database
```

---

## Troubleshooting

### Issue: "SSL: CERTIFICATE_VERIFY_FAILED"

**Cause**: Self-signed certificate not trusted by curl/client

**Solution**:
```bash
# Option 1: Accept self-signed cert (curl)
curl -k https://localhost:8000/health

# Option 2: Disable TLS for development
uv run python -m mcp_tef --tls-enabled=false
# Then use http://localhost:8000
```

### Issue: "Connection refused"

**Check server is running**:
```bash
# Check process
ps aux | grep mcp_tef

# Check port
lsof -i :8000
```

**Start server with logs**:
```bash
uv run python -m mcp_tef
# Watch for startup errors
```

### Issue: "Tool ingestion failed"

**Cause**: MCP server unreachable or returns invalid data

**Debug**:
```bash
# Test MCP server directly (streamable-http transport, recommended)
curl http://localhost:8080/your-server/mcp

# Or test SSE transport (deprecated but still supported)
curl http://localhost:8080/your-server/sse

# Check test run error message
curl -k https://localhost:8000/test-runs/{run_id}
# Look at "error_message" field
```

**Common causes**:
- MCP server is down
- Wrong URL format (use `http://host:port/path/mcp:streamable-http` for streamable-http transport, or `/sse` for SSE transport)
- Server returns invalid MCP protocol response
- Network/firewall blocks connection

### Issue: "Missing API key"

**Symptom**: 401 Unauthorized when running test

**Solution**: Provide API key in header (for cloud providers):
```bash
curl ... -H "X-Model-API-Key: your-key-here"
```

**Note**: Ollama doesn't need API key - omit the header entirely.

### Issue: "LLM timeout"

**Cause**: LLM took too long to respond

**Solutions**:
1. Increase timeout:
   ```json
   {"model_settings": {"timeout": 60}}
   ```

2. Use faster model:
   ```json
   {"model_settings": {"model": "llama3.2:1b"}}
   ```

3. Reduce available tools (fewer servers in `available_mcp_servers`)

### Issue: "Ollama not detected"

**Check Ollama is running**:
```bash
# Should return version info
curl http://localhost:11434/api/version
```

**Check model is pulled**:
```bash
ollama list
# Should show your model (e.g., llama3.2:3b)
```

**Pull model if missing**:
```bash
ollama pull llama3.2:3b
```

### Issue: Low precision/recall scores

**Possible causes**:
1. **Vague tool descriptions** → Use tool quality analysis to improve
2. **Similar tools** → Use similarity detection to differentiate
3. **Wrong expected values** → Review test case expectations
4. **Inappropriate model** → Try more capable model (e.g., Claude 3.5 Sonnet)

**Debug workflow**:
1. Check individual test runs for patterns
2. Look at `reasoning` field in evaluation results
3. Run tool quality analysis on problematic tools
4. Run similarity detection to find overlaps

---

## Next Steps

1. **Explore API Documentation**: https://localhost:8000/docs
2. **Review Technology Decisions**: [docs/technology-decisions.md](technology-decisions.md)
3. **Check System Specification**: [docs/current-specification.md](current-specification.md)
4. **See OpenAPI Contract**: [docs/openapi.yaml](openapi.yaml)
5. **Understand Data Model**: [docs/data-model.md](data-model.md)
6. **Deep Dive: Ollama Testing**: [docs/testing-with-ollama.md](testing-with-ollama.md)
7. **Production TLS Setup**: [docs/tls-configuration.md](tls-configuration.md)
8. **Browse All Documentation**: [docs/README.md](README.md)

---

## Quick Reference

### Common Commands

```bash
# Start server (HTTPS)
uv run python -m mcp_tef

# Start server (HTTP)
uv run python -m mcp_tef --tls-enabled=false

# Run tests
task test

# Check code quality
task format && task lint && task typecheck

# View API docs
open https://localhost:8000/docs
```

### Key Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /test-cases` | Create test case |
| `POST /test-cases/{id}/run` | Execute test (fresh tool ingestion) |
| `GET /test-runs/{id}/result` | Get evaluation result |
| `GET /metrics/summary` | Get aggregate metrics |
| `POST /similarity/analyze` | Analyze tool similarity |
| `GET /mcp-servers/tools/quality` | Analyze tool quality |

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DEFAULT_MODEL__PROVIDER` | `ollama` | Default LLM provider |
| `DEFAULT_MODEL__NAME` | `llama3.2:3b` | Default model name |
| `DEFAULT_MODEL__BASE_URL` | `http://localhost:11434/v1` | Ollama base URL |
| `OPENROUTER_API_KEY` | - | OpenRouter API key |
| `DATABASE_URL` | `sqlite+aiosqlite:///./mcp_eval.db` | Database location |

---

## Choosing Between API and CLI

Both the REST API and CLI provide access to mcp-tef functionality:

| Use Case | Recommended Method |
|----------|-------------------|
| **Interactive exploration** | REST API (curl) - See examples in workflows above |
| **Scripting and automation** | CLI (`mtef`) - Better for shell scripts and CI/CD |
| **Docker deployment** | CLI (`mtef deploy`) - Simplifies container management |
| **Direct server control** | Python (`uv run python -m mcp_tef`) - Full control over configuration |

**CLI Installation:**

```bash
# Install from GitHub release
uv tool install https://github.com/StacklokLabs/mcp-tef/releases/download/cli-v0.1.0/mcp_tef_cli-0.1.0-py3-none-any.whl

# Or install from Git
uv tool install "mtef @ git+https://github.com/StacklokLabs/mcp-tef.git#subdirectory=cli"
```

See the [CLI documentation](../cli/README.md) for complete CLI usage and examples.

---

**Need help?** Check the [troubleshooting section](#troubleshooting) or review the [full documentation](README.md).

