# Data Model: MCP Tool Evaluation System

**Generated**: 2025-11-10
**Status**: Consolidated from all specifications
**Git Commit**: 859d728254fc64586c05039908056c6b4bec1709

## Overview

This document defines all entities, relationships, and data structures for the MCP Tool Evaluation System, consolidating data models from all integrated specifications.

---

## Entity Relationship Diagram

```
┌─────────────────┐
│  mcp_servers    │
│─────────────────│
│ id (PK)         │
│ name (UNIQUE)   │
│ url (UNIQUE)    │
│ transport       │
│ status          │──────┐
│ last_connected  │      │
│ created_at      │      │
│ updated_at      │      │
└─────────────────┘      │
         ▲               │
         │               │ FK: mcp_server_id
         │               │
┌────────┴─────────┐     │
│ test_case_mcp_   │     │
│    servers       │     │
│──────────────────│     │
│ test_case_id(FK) │     │
│ mcp_server_id(FK)│     │
└──────────────────┘     │
         ▲               │
         │ FK            │
         │               │
┌─────────┴────────┐     │
│   test_cases     │     │
│──────────────────│     │
│ id (PK)          │     │
│ name             │     │
│ query            │     │
│ expected_server  │     │
│ expected_tool    │     │
│ expected_params  │     │
│ created_at       │     │
│ updated_at       │     │
└──────────────────┘     │
         ▲               │
         │ FK            │
         │               │
┌─────────┴────────┐     │
│   test_runs      │     │
│──────────────────│     │
│ id (PK)          │─────┼──┐
│ test_case_id(FK) │     │  │
│ model_settings_id│     │  │ FK: test_run_id
│ status           │     │  │
│ selected_tool_id │     │  │
│ confidence_score │     │  │
│ classification   │     │  │
│ execution_time   │     │  │
│ error_message    │     │  │
│ created_at       │     │  │
│ completed_at     │     │  │
└──────────────────┘     │  │
         ▲               │  │
         │               │  │
         └───────────────┼──┼─────┐
                         │  │     │
┌──────────────────┐     │  │     │
│ model_settings   │     │  │     │
│──────────────────│     │  │     │
│ id (PK)          │◄────┘  │     │
│ provider         │        │     │
│ model            │        │     │
│ timeout          │        │     │
│ temperature      │        │     │
│ max_retries      │        │     │
│ created_at       │        │     │
└──────────────────┘        │     │
                            │     │
┌─────────────────┐         │     │
│ tool_definitions│         │     │
│─────────────────│         │     │
│ id (PK)         │◄────────┘     │
│ name            │               │
│ description     │               │
│ input_schema    │               │
│ output_schema   │               │
│ mcp_server_id   │───────────────┘
│ test_run_id(FK) │◄──────────────┐
│ created_at      │               │
│ updated_at      │               │
└─────────────────┘               │
                                  │
         ┌────────────────────────┘
         │
┌──────────────────────┐
│ evaluation_results   │
│──────────────────────│
│ id (PK)              │
│ test_run_id (FK,UNQ) │
│ classification       │
│ tool_selection_ok    │
│ param_completeness   │
│ param_correctness    │
│ param_type_ok        │
│ hallucinated_params  │
│ confidence_category  │
│ reasoning            │
│ recommendations      │
│ created_at           │
└──────────────────────┘
```

---

## Core Entities

### 1. MCP Server

**Purpose**: Represents an external Model Context Protocol server

**Source**: 001-this-is-an, 004-decouple-tool-ingestion

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PK | UUID identifier |
| name | TEXT | NOT NULL, UNIQUE | Server name |
| url | TEXT | NOT NULL, UNIQUE | Server connection URL |
| transport | TEXT | NOT NULL | Connection type ('sse', 'streamable-http') |
| status | TEXT | NOT NULL, DEFAULT 'inactive' | Status ('active', 'failed', 'inactive') |
| last_connected_at | TIMESTAMP | NULL | Last successful connection |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW | Creation timestamp |
| updated_at | TIMESTAMP | NOT NULL, DEFAULT NOW | Update timestamp |

**Relationships**:
- One-to-many with `tool_definitions` (via mcp_server_id)
- Many-to-many with `test_cases` (via test_case_mcp_servers)

**Business Rules**:
- **004-decouple-tool-ingestion**: Status updated by connectivity check only (not tool ingestion)
- **004-decouple-tool-ingestion**: Server create/update completes in <2 seconds
- Tools are NOT ingested during server registration
- Status reflects last connectivity verification

**State Transitions**:
```
inactive → active (successful connectivity check)
inactive → failed (connectivity check failed)
active → failed (connectivity check failed on update)
failed → active (connectivity check succeeded on update)
```

---

### 2. Tool Definition

**Purpose**: Represents a tool's schema and metadata at a specific point in time

**Source**: 001-this-is-an, 004-decouple-tool-ingestion

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PK | UUID identifier |
| name | TEXT | NOT NULL | Tool name |
| description | TEXT | NOT NULL | Tool description (used by LLM) |
| input_schema | TEXT | NOT NULL | JSON Schema for inputs |
| output_schema | TEXT | NULL | Optional JSON Schema for outputs |
| mcp_server_id | TEXT | FK to mcp_servers, NOT NULL | Server that provided tool |
| test_run_id | TEXT | FK to test_runs, NOT NULL | Test run that ingested tool |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW | Creation timestamp |
| updated_at | TIMESTAMP | NOT NULL, DEFAULT NOW | Update timestamp |

**Relationships**:
- Many-to-one with `mcp_servers`
- **004-decouple-tool-ingestion**: Many-to-one with `test_runs` (point-in-time snapshot)
- One-to-many with `test_runs` (via selected_tool_id)

**Business Rules**:
- **004-decouple-tool-ingestion**: All tools MUST be linked to a test run (NOT NULL test_run_id)
- **004-decouple-tool-ingestion**: Tools ingested at test execution time, not server registration
- Multiple records can exist for same logical tool across different test runs
- Deleting test run cascades to tool definitions (removes snapshot)

**Validation**:
- name: Non-empty string
- description: Non-empty string
- input_schema: Valid JSON (MCP format)
- output_schema: Valid JSON or NULL

---

### 3. Test Case

**Purpose**: Query-based test scenario with expected tool selection

**Source**: 001-this-is-an, 003-remove-api-key

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PK | UUID identifier |
| name | TEXT | NOT NULL | Test case name |
| query | TEXT | NOT NULL | User query to evaluate |
| expected_mcp_server_name | TEXT | NOT NULL | Expected server selection |
| expected_tool_name | TEXT | NOT NULL | Expected tool selection |
| expected_parameters | TEXT | NULL | Expected parameters (JSON) |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW | Creation timestamp |
| updated_at | TIMESTAMP | NOT NULL, DEFAULT NOW | Update timestamp |

**Relationships**:
- Many-to-many with `mcp_servers` (via test_case_mcp_servers)
- One-to-many with `test_runs`

**Business Rules**:
- **003-remove-api-key**: No model_id foreign key (removed for simplification)
- Model configuration provided at runtime during test execution
- Test case is model-agnostic (can be executed with any LLM provider)

**Validation**:
- query: Non-empty string
- expected_mcp_server_name: Non-empty string
- expected_tool_name: Non-empty string
- expected_parameters: Valid JSON or NULL

---

### 4. Test Case MCP Servers (Junction Table)

**Purpose**: Many-to-many relationship between test cases and MCP servers

**Source**: 001-this-is-an, 004-decouple-tool-ingestion

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| test_case_id | TEXT | FK to test_cases, PK | Test case reference |
| mcp_server_id | TEXT | FK to mcp_servers, PK | MCP server reference |

**Business Rules**:
- Composite primary key prevents duplicate associations
- Cascading delete from both sides
- **004-decouple-tool-ingestion**: Servers used to fetch tools at test execution time

---

### 5. Model Settings

**Purpose**: Non-credential LLM configuration for audit trail

**Source**: 003-remove-api-key

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PK | UUID identifier |
| provider | TEXT | NOT NULL | Provider name (e.g., "openai", "anthropic") |
| model | TEXT | NOT NULL | Model name (e.g., "gpt-4") |
| timeout | INTEGER | NOT NULL, CHECK (1-300) | Request timeout (seconds) |
| temperature | REAL | NOT NULL, CHECK (0.0-2.0) | Sampling temperature |
| max_retries | INTEGER | NOT NULL, CHECK (0-10) | Maximum retry attempts |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW | Creation timestamp |

**Relationships**:
- One-to-many with `test_runs` (one settings record used by multiple runs)

**Business Rules**:
- **003-remove-api-key**: Created per test run with runtime configuration
- **003-remove-api-key**: API keys NEVER stored (request-scoped only)
- Immutable (no updates after creation)
- Provides audit trail for historical analysis

**Validation**:
- provider: min_length=1, max_length=100
- model: min_length=1, max_length=100
- timeout: 1-300 seconds
- temperature: 0.0-2.0
- max_retries: 0-10

**Default Values**:
- timeout: 30 seconds
- temperature: 0.4 (semi-deterministic)
- max_retries: 3

---

### 6. Test Run

**Purpose**: Execution instance of a test case

**Source**: All features (001, 003, 004)

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PK | UUID identifier |
| test_case_id | TEXT | FK to test_cases, NOT NULL | Associated test case |
| model_settings_id | TEXT | FK to model_settings, NULL | LLM configuration used |
| status | TEXT | NOT NULL, DEFAULT 'pending' | Execution status |
| llm_response_raw | TEXT | NULL | Raw LLM response (JSON) |
| selected_tool_id | TEXT | FK to tool_definitions, NULL | Tool selected by LLM |
| extracted_parameters | TEXT | NULL | Parameters extracted (JSON) |
| confidence_score | REAL | NULL, CHECK (0.0-1.0) | LLM confidence score |
| classification | TEXT | NULL, CHECK IN ('TP','FP','TN','FN') | Evaluation result |
| execution_time_ms | INTEGER | NULL, CHECK (> 0) | Execution duration |
| error_message | TEXT | NULL | Error details if failed |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW | Creation timestamp |
| completed_at | TIMESTAMP | NULL | Completion timestamp |

**Relationships**:
- Many-to-one with `test_cases`
- **003-remove-api-key**: Many-to-one with `model_settings`
- Many-to-one with `tool_definitions` (via selected_tool_id)
- **004-decouple-tool-ingestion**: One-to-many with `tool_definitions` (via test_run_id)
- One-to-one with `evaluation_results`

**Business Rules**:
- **004-decouple-tool-ingestion**: Creating test run triggers tool ingestion from all associated servers
- **003-remove-api-key**: API key provided at runtime via header (not stored)
- Status set to 'failed' if any tool ingestion fails
- **004-decouple-tool-ingestion**: All ingested tools linked via test_run_id for point-in-time snapshot

**State Transitions**:
```
pending → running → completed (success)
pending → running → failed (error)
```

**Status Values**:
- `pending`: Test run created, awaiting execution
- `running`: Currently executing (tool ingestion + LLM evaluation)
- `completed`: Successfully completed with results
- `failed`: Failed (tool ingestion error, LLM error, or validation error)

---

### 7. Evaluation Result

**Purpose**: Detailed evaluation analysis for a completed test run

**Source**: 001-this-is-an

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | TEXT | PK | UUID identifier |
| test_run_id | TEXT | FK to test_runs, UNIQUE | One-to-one with test run |
| classification | TEXT | NOT NULL, CHECK | Result ('TP', 'FP', 'TN', 'FN') |
| tool_selection_correct | INTEGER | NOT NULL | Boolean (0/1) |
| parameter_completeness | REAL | NOT NULL, CHECK (0.0-1.0) | Completeness score |
| parameter_correctness | REAL | NOT NULL, CHECK (0.0-1.0) | Correctness score |
| parameter_type_conformance | INTEGER | NOT NULL | Boolean (0/1) |
| hallucinated_parameters | TEXT | NULL | JSON array of invalid params |
| confidence_category | TEXT | NULL, CHECK | Category ('robust', 'needs_clarity', 'misleading') |
| reasoning | TEXT | NOT NULL | Why tool was/wasn't selected |
| recommendations | TEXT | NOT NULL | JSON array of improvement suggestions |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW | Creation timestamp |

**Relationships**:
- One-to-one with `test_runs`

**Business Rules**:
- Created after test run completes successfully
- Classification determined by comparing expected vs actual tool selection
- Parameter validation only performed if tool selection was correct

**Classification Logic**:
- **TP (True Positive)**: expected_tool == selected_tool (both not None)
- **FP (False Positive)**: expected_tool == None, selected_tool != None
- **TN (True Negative)**: expected_tool == None, selected_tool == None
- **FN (False Negative)**: expected_tool != None, selected_tool != expected_tool

**Confidence Categories**:
- **robust**: High confidence + correct selection
- **needs_clarity**: Low confidence + correct selection
- **misleading**: High confidence + incorrect selection (critical issue)

---

## Similarity Analysis Models (002)

**Note**: Similarity analysis is stateless and does NOT persist to database. These are request/response models only.

### Similarity Analysis Request

**Purpose**: Input format for similarity analysis

**Fields**:
- `server_list`: Array of MCP servers with embedded tools (optional)
- `tool_list`: Array of tool definitions (optional)
- `url_list`: Array of MCP server URLs to fetch from (optional)
- `embedding_model`: Embedding model identifier (optional)
- `similarity_threshold`: Threshold for flagging (default 0.85)
- `compute_full_similarity`: Include parameters in similarity (default false)
- `include_recommendations`: Generate recommendations (default false)

**Validation**:
- Exactly one of server_list, tool_list, url_list must be provided
- Minimum 2 tools required after extraction
- similarity_threshold: 0.0-1.0

### Similarity Score

**Purpose**: Pairwise similarity between two tools

**Fields**:
- `tool_a_id`: First tool ID
- `tool_b_id`: Second tool ID
- `similarity_score`: Description-only cosine similarity (0.0-1.0)
- `full_similarity_score`: Optional full similarity with parameters (0.0-1.0)
- `method`: Analysis method ('embedding', 'description_overlap')
- `flagged`: Whether similarity exceeds threshold

### Overlap Matrix

**Purpose**: Multi-dimensional capability overlap

**Fields**:
- `tool_ids`: Ordered list of tool IDs
- `matrix`: 2D matrix of overlap scores (0.0-1.0)
- `dimensions`: Weights (semantic: 0.5, parameters: 0.3, description: 0.2)
- `generated_at`: Timestamp

### Differentiation Recommendation

**Purpose**: Actionable guidance for improving tool differentiation

**Fields**:
- `tool_pair`: [tool_a_id, tool_b_id]
- `similarity_score`: Overall similarity
- `issues`: Array of DifferentiationIssue
- `recommendations`: Array of RecommendationItem

**Issue Types**:
- `scope_clarity`: Unclear scope boundaries
- `example_distinctiveness`: Similar examples
- `parameter_uniqueness`: Overlapping parameters
- `naming_clarity`: Ambiguous naming
- `terminology_overlap`: Shared terminology

**Recommendation Item**:
- `issue`: Issue this addresses
- `tool_id`: Tool to modify (None if both)
- `recommendation`: Specific action
- `rationale`: Why this matters
- `priority`: high/medium/low
- `revised_description`: LLM-generated improved description
- `apply_commands`: Executable commands/JSON patches

---

## Pydantic Models

All entities have corresponding Pydantic models for API validation:

### API Models (Request/Response)

**From 001-this-is-an**:
- `TestCaseCreate`, `TestCaseResponse`
- `TestRunResponse`
- `EvaluationResultResponse`
- `MetricsSummaryResponse`

**From 002-inter-tool-similarity**:
- `SimilarityAnalysisRequest`
- `SimilarityScoreResponse`
- `OverlapMatrixResponse`
- `DifferentiationRecommendationResponse`

**From 003-remove-api-key**:
- `ModelSettingsCreate`, `ModelSettingsResponse`
- `TestRunExecuteRequest` (with inline model_config)

**From 004-decouple-tool-ingestion**:
- `MCPServerCreate`, `MCPServerResponse` (no tools array)
- `ToolDefinitionCreate`, `ToolDefinitionResponse` (with test_run_id)

### Configuration Hierarchy

**003-remove-api-key**: Runtime configuration follows:
1. CLI params (test execution request body)
2. Environment variables (defaults)
3. Pydantic defaults

**API Key**: Request header only (no defaults, fails fast if missing for cloud providers)

---

## Schema Features

### Indexes
- `mcp_servers`: name, url
- `tool_definitions`: name, mcp_server_id, test_run_id
- `test_cases`: expected_mcp_server_name, expected_tool_name
- `test_runs`: test_case_id, status, created_at, model_settings_id
- `test_case_mcp_servers`: composite (test_case_id, mcp_server_id)

### Constraints
- Foreign keys: ON DELETE CASCADE for dependent records
- CHECK constraints: status enums, score ranges (0.0-1.0), timeout limits
- UNIQUE constraints: server names/URLs, test_run_id in evaluation_results

### Triggers
- `updated_at` auto-update on mcp_servers, test_cases, tool_definitions

### Concurrency
- SQLite WAL mode: Concurrent reads supported
- Write operations: Serialized by SQLite (appropriate for evaluation workload)
- Batch operations: Use transactions for atomicity

---

## Summary of Changes by Feature

### 001-this-is-an (Base)
- Core entities: test_cases, test_runs, evaluation_results
- Metrics aggregation
- Parameter validation

### 002-inter-tool-similarity
- No database persistence (stateless analysis)
- Request/response models only
- Multi-format input support (server_list, tool_list, url_list)

### 003-remove-api-key
- **Removed**: providers table, models table
- **Removed**: test_cases.model_id column
- **Added**: model_settings table
- **Added**: test_runs.model_settings_id column
- API key handling: Runtime only, never persisted

### 004-decouple-tool-ingestion
- **Added**: tool_definitions.test_run_id column (NOT NULL)
- **Modified**: MCP server status reflects connectivity only
- **Modified**: Tools ingested at test execution, not server registration
- Point-in-time tool snapshots per test run

---

**Document Version**: 1.0  
**Last Updated**: 2025-11-10  
**Git Commit**: 859d728254fc64586c05039908056c6b4bec1709

