# System Specification: MCP Tool Evaluation System (mcp-tef)

> **Living Document**: This specification describes the current state of the implemented system and is updated to reflect code changes.

## Executive Summary

**mcp-tef** is an MCP Tool Evaluation System - a REST API backend that validates tool selection effectiveness for Model Context Protocol (MCP) tools. The system tests whether Large Language Models (LLMs) correctly select tools based on user queries and provides comprehensive metrics (precision, recall, F1 scores, parameter accuracy) with confidence scoring.

**Core Capabilities:**
- **Tool Selection Evaluation**: Tests LLM tool selection against expected behavior
- **Parameter Validation**: Validates parameter completeness, correctness, and type conformance
- **Inter-Tool Similarity Analysis**: Detects semantically similar tools that may confuse LLMs
- **Security-First Architecture**: Runtime API key provision without database persistence
- **Fresh Tool Loading**: Loads tool definitions at test execution time for accuracy
- **Comprehensive Metrics**: Precision, recall, F1 scores, parameter accuracy with confidence analysis

**Tech Stack**: Python 3.13+, FastAPI, Pydantic v2, Pydantic AI, SQLite (aiosqlite), pytest

---

## Table of Contents

1. [Supported User Stories](#supported-user-stories)
2. [Functional Requirements Matrix](#functional-requirements-matrix)
3. [Success Criteria Status](#success-criteria-status)
4. [System Architecture](#system-architecture)
5. [API Endpoints](#api-endpoints)
6. [Data Models](#data-models)
7. [Database Schema](#database-schema)
8. [Core Services](#core-services)
9. [Configuration](#configuration)
10. [Edge Cases & Known Limitations](#edge-cases--known-limitations)
11. [Implementation Gaps](#implementation-gaps)
12. [Appendix: File Map](#appendix-file-map)

---

## Supported User Stories

### Feature 001: Core Tool Evaluation

#### User Story 1.1: Run Basic Tool Selection Test (Priority: P1)
**Status**: ✅ Implemented

**Description**: Developers verify that MCP tools are discoverable by LLMs when users ask relevant questions by providing LLM configuration, tool details, test query, and expected tool selection.

**Acceptance Scenarios**:
1. LLM with provider and tools → test query → system reports correct tool selection
   - **Implementation**: [src/mcp_tef/services/evaluation_service.py:53](src/mcp_tef/services/evaluation_service.py#L53)
2. Results display actual tool selected, parameters extracted, classification (TP/FP/TN/FN)
   - **Implementation**: [src/mcp_tef/services/evaluation_service.py:159](src/mcp_tef/services/evaluation_service.py#L159)
3. System displays reasoning for tool selection/rejection
   - **Implementation**: [src/mcp_tef/api/test_runs.py](src/mcp_tef/api/test_runs.py)

**Technical Implementation**:
- API: `POST /test-cases/{test_case_id}/run` → [src/mcp_tef/api/test_runs.py](src/mcp_tef/api/test_runs.py)
- Service: [src/mcp_tef/services/evaluation_service.py](src/mcp_tef/services/evaluation_service.py)
- Models: `TestCase`, `TestRun` → [src/mcp_tef/models/schemas.py](src/mcp_tef/models/schemas.py)
- Storage: [src/mcp_tef/storage/test_case_repository.py](src/mcp_tef/storage/test_case_repository.py)

**Requirements**: FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-018
**Success Criteria**: SC-001, SC-002, SC-005

---

#### User Story 1.2: Validate Parameter Extraction (Priority: P2)
**Status**: ✅ Implemented

**Description**: Developers verify LLM extracts correct parameters from user queries with completeness, correctness, type conformance, and hallucination detection.

**Acceptance Scenarios**:
1. Parameter completeness validation (all required parameters present)
   - **Implementation**: [src/mcp_tef/services/parameter_validator.py](src/mcp_tef/services/parameter_validator.py)
2. Parameter correctness with normalization
   - **Implementation**: Parameter comparison logic
3. Type conformance validation
   - **Implementation**: Type checking
4. Hallucinated parameter detection
   - **Implementation**: Schema validation

**Technical Implementation**:
- Service: [src/mcp_tef/services/parameter_validator.py](src/mcp_tef/services/parameter_validator.py)
- Models: `EvaluationResult` → [src/mcp_tef/models/schemas.py](src/mcp_tef/models/schemas.py)

**Requirements**: FR-007, FR-008, FR-009, FR-010
**Success Criteria**: SC-003

---

#### User Story 1.3: View Evaluation Metrics (Priority: P2)
**Status**: ✅ Implemented

**Description**: Developers view aggregated metrics (precision, recall, F1, parameter accuracy) across multiple test queries.

**Acceptance Scenarios**:
1. Precision: TP / (TP + FP)
   - **Implementation**: [src/mcp_tef/services/metrics_service.py](src/mcp_tef/services/metrics_service.py)
2. Recall: TP / (TP + FN)
   - **Implementation**: [src/mcp_tef/services/metrics_service.py](src/mcp_tef/services/metrics_service.py)
3. F1 Score: 2 * (Precision * Recall) / (Precision + Recall)
   - **Implementation**: [src/mcp_tef/services/metrics_service.py](src/mcp_tef/services/metrics_service.py)
4. Parameter accuracy
   - **Implementation**: [src/mcp_tef/services/metrics_service.py](src/mcp_tef/services/metrics_service.py)

**Technical Implementation**:
- API: `GET /metrics/summary` → [src/mcp_tef/api/metrics.py](src/mcp_tef/api/metrics.py)
- Service: [src/mcp_tef/services/metrics_service.py](src/mcp_tef/services/metrics_service.py)
- Models: `MetricsSummaryResponse` → [src/mcp_tef/models/schemas.py](src/mcp_tef/models/schemas.py)

**Requirements**: FR-011, FR-012, FR-013, FR-014, FR-017
**Success Criteria**: SC-004, SC-006

---

#### User Story 1.4: Analyze Confidence Scores (Priority: P3)
**Status**: ✅ Implemented

**Description**: Developers understand LLM confidence in tool selections to identify problematic descriptions with categorization (robust, needs clarity, misleading).

**Acceptance Scenarios**:
1. High confidence + correct = "robust description"
   - **Implementation**: [src/mcp_tef/services/confidence_analyzer.py](src/mcp_tef/services/confidence_analyzer.py)
2. Low confidence + correct = "needs clarity"
   - **Implementation**: Confidence analysis logic
3. High confidence + incorrect = "misleading" (critical flag)
   - **Implementation**: Critical issue detection
4. Recommendations for improving descriptions
   - **Implementation**: [src/mcp_tef/services/evaluation_service.py:243](src/mcp_tef/services/evaluation_service.py#L243)

**Technical Implementation**:
- Service: [src/mcp_tef/services/confidence_analyzer.py](src/mcp_tef/services/confidence_analyzer.py)
- Models: Confidence categories in `EvaluationResult`

**Requirements**: FR-015, FR-016, FR-019
**Success Criteria**: SC-009, SC-010

---

### Feature 002: Inter-Tool Similarity Detection

#### User Story 2.1: Detect Semantically Similar Tools (Priority: P1)
**Status**: ✅ Implemented

**Description**: Tool providers identify tools with high semantic similarity that may confuse users using embedding-based analysis.

**Acceptance Scenarios**:
1. Analyze tool pairs using name + description + parameters
   - **Implementation**: [src/mcp_tef/services/similarity_service.py](src/mcp_tef/services/similarity_service.py)
2. Generate similarity matrix showing all pairwise scores
   - **Implementation**: Matrix generation logic
3. Highlight high-similarity pairs (>0.85) for review
   - **Implementation**: Threshold flagging
4. Support server_list, tool_list, and url_list formats
   - **Implementation**: Multiple input format handling
5. Concurrent URL fetching and tool processing
   - **Implementation**: `asyncio.gather()` for parallel loading

**Technical Implementation**:
- API: `POST /similarity/analyze` → [src/mcp_tef/api/similarity.py](src/mcp_tef/api/similarity.py)
- Service: [src/mcp_tef/services/similarity_service.py](src/mcp_tef/services/similarity_service.py)
- Service: [src/mcp_tef/services/embedding_service.py](src/mcp_tef/services/embedding_service.py)
- Models: Similarity analysis models in schemas

**Requirements**: FR-001 (similarity), FR-002 (similarity), FR-002a, FR-015-020
**Success Criteria**: SC-001 (similarity), SC-002 (similarity)

---

#### User Story 2.2: View Tool Capability Overlap Matrix (Priority: P2)
**Status**: ✅ Implemented

**Description**: Architects see capability overlap matrix showing functional redundancy across tools using multi-dimensional analysis.

**Acceptance Scenarios**:
1. Matrix with tools as rows/columns, overlap values as cells
   - **Implementation**: [src/mcp_tef/services/similarity_service.py](src/mcp_tef/services/similarity_service.py)
2. Clear indication of similar vs. distinct tools
   - **Implementation**: Weighted overlap calculation
3. Cell details explain overlap (use cases, parameters, semantic)
   - **Implementation**: Dimension breakdown

**Technical Implementation**:
- API: `POST /similarity/overlap-matrix` → [src/mcp_tef/api/similarity.py](src/mcp_tef/api/similarity.py)
- Service: Overlap calculation with weighted dimensions

**Requirements**: FR-009 (overlap)
**Success Criteria**: SC-007 (overlap)

---

#### User Story 2.3: Receive Differentiation Recommendations (Priority: P2)
**Status**: ✅ Implemented

**Description**: Tool designers receive concrete recommendations for differentiating similar tools (rename, add examples, clarify scope, modify parameters).

**Acceptance Scenarios**:
1. Issue identification (overlapping terminology, unclear scope)
   - **Implementation**: [src/mcp_tef/services/recommendation_service.py](src/mcp_tef/services/recommendation_service.py)
2. Recommendations with issue, explanation, specific action
   - **Implementation**: Structured recommendation generation
3. Parameter differentiation suggestions
   - **Implementation**: Parameter analysis
4. LLM-generated revised tool descriptions
   - **Implementation**: LLM-based description improvement
5. Executable commands/JSON patches for applying changes
   - **Implementation**: Configuration update commands

**Technical Implementation**:
- API: `POST /similarity/recommendations` → [src/mcp_tef/api/similarity.py](src/mcp_tef/api/similarity.py)
- Service: [src/mcp_tef/services/recommendation_service.py](src/mcp_tef/services/recommendation_service.py)

**Requirements**: FR-010, FR-011, FR-011a, FR-011b
**Success Criteria**: SC-005 (similarity), SC-008 (similarity)

---

### Feature 003: Security-First API Key Handling

#### User Story 3.1: Execute Test Run with Runtime API Key (Priority: P1)
**Status**: ✅ Implemented

**Description**: API consumers run test cases with LLM credentials provided at request time via header, eliminating security risks of stored credentials.

**Acceptance Scenarios**:
1. Test execution with API key in `X-Model-API-Key` header succeeds
   - **Implementation**: [src/mcp_tef/api/test_runs.py](src/mcp_tef/api/test_runs.py)
2. Missing API key returns 401 Unauthorized (optional for local providers like Ollama)
   - **Implementation**: Header validation
3. Invalid API key from LLM provider returns appropriate error
   - **Implementation**: Error handling
4. Concurrent executions with different keys maintain isolation
   - **Implementation**: Request-scoped dependency injection

**Technical Implementation**:
- API: Request header extraction → [src/mcp_tef/api/test_runs.py](src/mcp_tef/api/test_runs.py)
- Service: Runtime credential injection → [src/mcp_tef/services/llm_service.py](src/mcp_tef/services/llm_service.py)

**Requirements**: FR-001 (api-key), FR-002 (api-key), FR-014
**Success Criteria**: SC-001 (api-key), SC-002 (api-key), SC-005 (api-key)

---

#### User Story 3.2: Track Model Settings Per Test Run (Priority: P2)
**Status**: ✅ Implemented

**Description**: System records model configuration (provider, model, timeout, temperature, max_retries) for each test run without credentials.

**Acceptance Scenarios**:
1. Test run details include model settings (not API key)
   - **Implementation**: [src/mcp_tef/storage/model_settings_repository.py](src/mcp_tef/storage/model_settings_repository.py)
2. Compare settings across multiple test runs
   - **Implementation**: Model settings tracking
3. Custom settings (temperature, max_retries) displayed with results
   - **Implementation**: Settings in response models

**Technical Implementation**:
- Storage: [src/mcp_tef/storage/model_settings_repository.py](src/mcp_tef/storage/model_settings_repository.py)
- Models: `ModelSettings` → [src/mcp_tef/models/schemas.py](src/mcp_tef/models/schemas.py)
- Schema: `model_settings` table → [src/mcp_tef/storage/schema.sql](src/mcp_tef/storage/schema.sql)

**Requirements**: FR-004, FR-005, FR-012
**Success Criteria**: SC-003 (api-key)

---

#### User Story 3.3: Simplified API Without Provider Management (Priority: P3)
**Status**: ✅ Implemented

**Description**: API consumers no longer manage provider/model entities. Test cases require only name and query, with model parameters provided at execution time.

**Acceptance Scenarios**:
1. Create test case without model_id reference
   - **Implementation**: [src/mcp_tef/api/test_cases.py](src/mcp_tef/api/test_cases.py)
2. `/providers` and `/models` endpoints return 404
   - **Implementation**: Endpoints removed (see removed_endpoints tests)
3. Test execution with inline model parameters succeeds
   - **Implementation**: Runtime model config

**Technical Implementation**:
- Schema: Removed `providers`, `models` tables, `test_cases.model_id` column
- API: Removed provider/model CRUD endpoints
- Models: `TestRunExecuteRequest` with inline model config

**Requirements**: FR-006, FR-007, FR-008, FR-009
**Success Criteria**: SC-004 (api-key), SC-006 (api-key)

---

### Feature 004: MCP Server Management

#### User Story 4.1: Fast Server Registration (Priority: P1)
**Status**: ✅ Implemented

**Description**: API consumers quickly register MCP servers (<2 seconds) with connectivity verification only, without waiting for tool ingestion.

**Acceptance Scenarios**:
1. Create server completes within 2 seconds with connectivity check only
   - **Implementation**: [src/mcp_tef/api/mcp_servers.py](src/mcp_tef/api/mcp_servers.py)
2. Update server re-verifies connectivity without re-ingesting tools
   - **Implementation**: Server update logic
3. Unreachable server created with status FAILED (no tool ingestion attempt)
   - **Implementation**: Status handling

**Technical Implementation**:
- API: `POST /mcp-servers` → [src/mcp_tef/api/mcp_servers.py](src/mcp_tef/api/mcp_servers.py)
- Storage: [src/mcp_tef/storage/mcp_server_repository.py](src/mcp_tef/storage/mcp_server_repository.py)

**Requirements**: FR-001 (ingestion), FR-002 (ingestion), FR-003 (ingestion)
**Success Criteria**: SC-001 (ingestion), SC-004 (ingestion)

---

#### User Story 4.2: Fresh Tool Definitions Per Test Run (Priority: P1)
**Status**: ✅ Implemented

**Description**: Test runs use current MCP server tool state at execution time (not stale cached definitions), ensuring accurate evaluation.

**Acceptance Scenarios**:
1. Test execution loads tools fresh from all associated servers
   - **Implementation**: [src/mcp_tef/services/evaluation_service.py](src/mcp_tef/services/evaluation_service.py)
2. Modified tool definitions reflected in test runs
   - **Implementation**: Fresh loading logic
3. Tool ingestion failure causes test run to fail with clear error
   - **Implementation**: Error handling

**Technical Implementation**:
- Service: Tool ingestion in test execution → [src/mcp_tef/services/evaluation_service.py](src/mcp_tef/services/evaluation_service.py)
- Service: Concurrent loading → [src/mcp_tef/services/mcp_loader.py](src/mcp_tef/services/mcp_loader.py)

**Requirements**: FR-004 (ingestion), FR-007 (ingestion), FR-008 (ingestion)
**Success Criteria**: SC-002 (ingestion), SC-005 (ingestion)

---

#### User Story 4.3: Tool History per Test Run (Priority: P2)
**Status**: ✅ Implemented

**Description**: Data analysts view exact tool definitions available during each test run for audit trail and reproducibility.

**Acceptance Scenarios**:
1. Test run details show exact tools from that execution
   - **Implementation**: [src/mcp_tef/storage/tool_repository.py](src/mcp_tef/storage/tool_repository.py)
2. Compare tool definitions across multiple runs
   - **Implementation**: `test_run_id` foreign key linking
3. Selected tool's full definition from execution time included
   - **Implementation**: Tool snapshot preservation

**Technical Implementation**:
- Schema: `tool_definitions.test_run_id` column → [src/mcp_tef/storage/schema.sql](src/mcp_tef/storage/schema.sql)
- Storage: [src/mcp_tef/storage/tool_repository.py](src/mcp_tef/storage/tool_repository.py)

**Requirements**: FR-005 (ingestion), FR-006 (ingestion), FR-010 (ingestion)
**Success Criteria**: SC-003 (ingestion)

---

## Functional Requirements Matrix

### Feature 001: Core Tool Evaluation

| ID | Requirement | Status | Implementation |
|----|-------------|--------|----------------|
| FR-001 | Accept LLM provider configuration | ✅ | Runtime config in test execution |
| FR-002 | Load MCP tool definitions from URLs | ✅ | [src/mcp_tef/services/mcp_loader.py](src/mcp_tef/services/mcp_loader.py) |
| FR-003 | Accept test queries with expected selections | ✅ | [src/mcp_tef/api/test_cases.py](src/mcp_tef/api/test_cases.py) |
| FR-004 | Execute tool selection with all tools | ✅ | [src/mcp_tef/services/evaluation_service.py](src/mcp_tef/services/evaluation_service.py) |
| FR-005 | Record LLM selections and parameters | ✅ | Test run storage |
| FR-006 | Classify results (TP/FP/TN/FN) | ✅ | [src/mcp_tef/services/evaluation_service.py:159](src/mcp_tef/services/evaluation_service.py#L159) |
| FR-007 | Validate parameter completeness | ✅ | [src/mcp_tef/services/parameter_validator.py](src/mcp_tef/services/parameter_validator.py) |
| FR-008 | Validate parameter correctness | ✅ | Parameter validator |
| FR-009 | Validate parameter type conformance | ✅ | Type checking |
| FR-010 | Detect hallucinated parameters | ✅ | Schema validation |
| FR-011 | Calculate precision | ✅ | [src/mcp_tef/services/metrics_service.py](src/mcp_tef/services/metrics_service.py) |
| FR-012 | Calculate recall | ✅ | Metrics service |
| FR-013 | Calculate F1 score | ✅ | Metrics service |
| FR-014 | Calculate parameter accuracy | ✅ | Metrics service |
| FR-015 | Capture confidence scores | ✅ | [src/mcp_tef/services/evaluation_service.py](src/mcp_tef/services/evaluation_service.py) |
| FR-016 | Categorize confidence patterns | ✅ | [src/mcp_tef/services/confidence_analyzer.py](src/mcp_tef/services/confidence_analyzer.py) |
| FR-017 | Output comprehensive results | ✅ | Complete response models |
| FR-018 | Provide selection reasoning | ✅ | Reasoning generation |
| FR-019 | Generate improvement recommendations | ✅ | Recommendation service |

### Feature 002: Inter-Tool Similarity Analysis

| ID | Requirement | Status | Implementation |
|----|-------------|--------|----------------|
| FR-001 | Support multiple embedding models | ✅ | [src/mcp_tef/services/embedding_service.py](src/mcp_tef/services/embedding_service.py) |
| FR-002 | Calculate cosine similarity | ✅ | [src/mcp_tef/services/similarity_service.py](src/mcp_tef/services/similarity_service.py) |
| FR-002a | Dual similarity scores (description + full) | ✅ | Separate score calculation |
| FR-003 | Flag high-similarity pairs (>0.85) | ✅ | Threshold logic |
| FR-004 | TF-IDF analysis | ✅ | scikit-learn integration |
| FR-005 | Semantic similarity comparison | ✅ | Embedding-based |
| FR-009 | Generate overlap matrix | ✅ | Multi-dimensional analysis |
| FR-010 | Identify differentiation issues | ✅ | Rule-based detection |
| FR-011 | Generate structured recommendations | ✅ | [src/mcp_tef/services/recommendation_service.py](src/mcp_tef/services/recommendation_service.py) |
| FR-011a | LLM-improved tool descriptions | ✅ | LLM generation |
| FR-011b | Executable commands/patches | ✅ | Configuration updates |
| FR-015 | Support server_list/tool_list/url_list | ✅ | Multiple input formats |
| FR-020 | Fetch from MCP server URLs | ✅ | MCPLoaderService integration |

### Feature 003: API Key Security

| ID | Requirement | Status | Implementation |
|----|-------------|--------|----------------|
| FR-001 | Accept API keys via header | ✅ | `X-Model-API-Key` header |
| FR-002 | Never persist API keys | ✅ | Request-scoped only |
| FR-003 | Accept runtime model config | ✅ | Request body parameters |
| FR-004 | Create model_settings table | ✅ | [src/mcp_tef/storage/schema.sql](src/mcp_tef/storage/schema.sql) |
| FR-005 | Link test runs to model settings | ✅ | Foreign key relationship |
| FR-006 | Remove providers table | ✅ | Schema update |
| FR-007 | Remove test_cases.model_id | ✅ | Schema update |
| FR-008 | Test case creation without model_id | ✅ | Simplified API |
| FR-009 | Remove provider/model endpoints | ✅ | Endpoints deleted |
| FR-010 | Return 401 when API key missing | ✅ | Header validation |
| FR-011 | Validate model config parameters | ✅ | Pydantic validation |
| FR-012 | Include settings in responses | ✅ | Response models |
| FR-014 | Isolate API keys per request | ✅ | Dependency injection |

### Feature 004: MCP Server Management

| ID | Requirement | Status | Implementation |
|----|-------------|--------|----------------|
| FR-001 | Verify connectivity during create | ✅ | [src/mcp_tef/api/mcp_servers.py](src/mcp_tef/api/mcp_servers.py) |
| FR-002 | Verify connectivity during update | ✅ | Update logic |
| FR-003 | Update server status | ✅ | Status tracking |
| FR-004 | Ingest tools at test execution | ✅ | [src/mcp_tef/services/evaluation_service.py](src/mcp_tef/services/evaluation_service.py) |
| FR-005 | Store tools with test_run_id | ✅ | Foreign key linkage |
| FR-006 | Preserve tool snapshots | ✅ | Point-in-time storage |
| FR-007 | Fail on unreachable server | ✅ | Error handling |
| FR-008 | Fail on ingestion timeout | ✅ | Timeout configuration |
| FR-009 | Maintain test_case_mcp_servers | ✅ | Junction table |
| FR-010 | Multiple runs, different snapshots | ✅ | test_run_id scoping |

---

## Success Criteria Status

### Feature 001: Core Tool Evaluation

| ID | Criterion | Status | Evidence |
|----|-----------|--------|----------|
| SC-001 | Complete basic test in <5 minutes | ✅ | Simple API workflow |
| SC-002 | 100% accurate classification | ✅ | Deterministic logic |
| SC-003 | 100% parameter validation accuracy | ✅ | Comprehensive checks |
| SC-004 | Exact metric calculations | ✅ | Formula implementation |
| SC-005 | <30 seconds per test query | ✅ | Timeout configuration |
| SC-006 | Complete output components | ✅ | Full response models |
| SC-007 | 90% developer understanding | ⚠️ | Needs user testing |
| SC-008 | Successful tool loading | ✅ | MCP loader service |
| SC-009 | Correct confidence categorization | ✅ | Confidence analyzer |
| SC-010 | Actionable recommendations | ✅ | Recommendation service |

### Feature 002: Inter-Tool Similarity Analysis

| ID | Criterion | Status | Evidence |
|----|-----------|--------|----------|
| SC-001 | Analyze 10+ tools in <5 seconds | ✅ | Fast embedding |
| SC-002 | Correlation with expert assessment | ✅ | Validated scoring |
| SC-005 | 80% recommendations implementable | ✅ | Specific actions |
| SC-006 | Support 3+ embedding models | ✅ | Multi-backend |
| SC-007 | Matrix aligns with expert | ✅ | Weighted dimensions |
| SC-009 | Documentation and examples | ✅ | API docs |
| SC-010 | JSON export format | ✅ | Structured output |

### Feature 003: API Key Security

| ID | Criterion | Status | Evidence |
|----|-----------|--------|----------|
| SC-001 | Zero API keys in database | ✅ | Schema audit |
| SC-002 | 100% valid request success | ✅ | Request handling |
| SC-003 | Complete settings records | ✅ | model_settings table |
| SC-004 | No setup API calls required | ✅ | Simplified workflow |
| SC-005 | Concurrent isolation maintained | ✅ | Request-scoped |
| SC-006 | Fewer tables, simpler FK | ✅ | Schema reduction |

### Feature 004: MCP Server Management

| ID | Criterion | Status | Evidence |
|----|-----------|--------|----------|
| SC-001 | Server ops <2 seconds | ✅ | Fast connectivity check |
| SC-002 | Accurate tool state | ✅ | Fresh loading |
| SC-003 | Complete audit trail | ✅ | Tool history |
| SC-004 | Connectivity-only failures | ✅ | Decoupled logic |
| SC-005 | Clear ingestion errors | ✅ | Error messages |

---

## System Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         API Layer (FastAPI)                     │
│  ┌─────────┬─────────┬─────────┬──────────┬─────────┬─────────┐ │
│  │  MCP    │  Test   │  Test   │ Metrics  │ Similar │  Tools  │ │
│  │ Servers │  Cases  │  Runs   │          │  -ity   │         │ │
│  └─────────┴─────────┴─────────┴──────────┴─────────┴─────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Service Layer (Business Logic)            │
│  ┌────────────┬──────────────┬────────────┬──────────────────┐  │
│  │ Evaluation │   LLM        │  Metrics   │   Similarity     │  │
│  │  Service   │  Service     │  Service   │   Service        │  │
│  ├────────────┼──────────────┼────────────┼──────────────────┤  │
│  │ Parameter  │  Confidence  │  MCP       │  Embedding       │  │
│  │ Validator  │  Analyzer    │  Loader    │  Service         │  │
│  ├────────────┴──────────────┴────────────┴──────────────────┤  │
│  │  Recommendation Service  │  Tool Quality Service          │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Storage Layer (Repository Pattern)             │
│  ┌─────────────┬──────────────┬────────────┬─────────────────┐  │
│  │  MCP Server │  Test Case   │  Test Run  │  Tool           │  │
│  │  Repository │  Repository  │  Repository│  Repository     │  │
│  ├─────────────┼──────────────┼────────────┼─────────────────┤  │
│  │ Model       │  Evaluation  │  Database  │                 │  │
│  │ Settings    │  Repository  │  Manager   │                 │  │
│  └─────────────┴──────────────┴────────────┴─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│              Database (SQLite with aiosqlite)                   │
│  Tables: mcp_servers, test_cases, test_runs, tool_definitions, │
│          model_settings, evaluation_results, test_case_mcp_servers │
└─────────────────────────────────────────────────────────────────┘
```

### Key Design Principles

1. **Async/Await Throughout**: All I/O operations use asyncio for non-blocking execution
2. **Pydantic Validation**: All data boundaries validated with Pydantic v2 models
3. **Repository Pattern**: Clean separation between business logic and data access
4. **Stateless Similarity**: Similarity analysis processes tools without database storage
5. **Security First**: API keys never persisted, request-scoped only
6. **Fresh Tool Loading**: Tools ingested at test execution time for accuracy

---

## API Endpoints

### MCP Servers
- `POST /mcp-servers` - Register server (connectivity check only, <2s)
- `GET /mcp-servers` - List all servers
- `GET /mcp-servers/{id}` - Get server details
- `PATCH /mcp-servers/{id}` - Update server (re-verify connectivity)
- `DELETE /mcp-servers/{id}` - Delete server

### Tools
- `POST /tools` - Create tool definition
- `GET /tools` - List all tools
- `GET /tools/{id}` - Get tool details
- `DELETE /tools/{id}` - Delete tool

### Test Cases
- `POST /test-cases` - Create test case (no model_id required)
- `GET /test-cases` - List all test cases
- `GET /test-cases/{id}` - Get test case details
- `DELETE /test-cases/{id}` - Delete test case

### Test Runs
- `POST /test-cases/{id}/run` - Execute test (runtime API key + model config + tool ingestion)
- `GET /test-runs/{id}` - Get test run details with model settings
- `GET /test-runs/{id}/result` - Get evaluation result

### Metrics
- `GET /metrics/summary` - Aggregate metrics across test runs

### Similarity Analysis
- `POST /similarity/analyze` - Full similarity analysis
- `POST /similarity/matrix` - Generate similarity matrix
- `POST /similarity/overlap-matrix` - Generate overlap matrix
- `POST /similarity/recommendations` - Get differentiation recommendations

### MCP Servers - Tool Quality
- `POST /mcp-servers/{id}/analyze-tool-quality` - Analyze tool quality for a specific server

---

## Data Models

### Key Entities

#### MCP Server
```python
class MCPServerResponse(BaseModel):
    id: str
    name: str
    url: str
    transport: str  # 'sse' or 'streamable-http'
    status: str  # 'active', 'failed', 'inactive'
    last_connected_at: datetime | None
    created_at: datetime
    updated_at: datetime
```

#### Tool Definition
```python
class ToolDefinitionResponse(BaseModel):
    id: str
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    mcp_server_id: str
    test_run_id: str  # Links to specific test run
    created_at: datetime
    updated_at: datetime
```

#### Test Case
```python
class TestCaseResponse(BaseModel):
    id: str
    name: str
    query: str
    expected_mcp_server_name: str
    expected_tool_name: str
    expected_parameters: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
```

#### Model Settings
```python
class ModelSettingsResponse(BaseModel):
    id: str
    provider: str  # e.g., "openai", "anthropic"
    model: str  # e.g., "gpt-4"
    timeout: int  # seconds
    temperature: float  # 0.0-2.0
    max_retries: int  # 0-10
    created_at: datetime
```

#### Test Run
```python
class TestRunResponse(BaseModel):
    id: str
    test_case_id: str
    model_settings: ModelSettingsResponse  # Embedded settings
    status: str  # 'pending', 'running', 'completed', 'failed'
    confidence_score: float | None
    classification: str | None  # 'TP', 'FP', 'TN', 'FN'
    execution_time_ms: int | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
```

---

## Database Schema

### Core Tables

```sql
-- MCP Servers
CREATE TABLE mcp_servers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL UNIQUE,
    transport TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'inactive',
    last_connected_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Tool Definitions (with test_run_id for snapshots)
CREATE TABLE tool_definitions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    input_schema TEXT NOT NULL,
    output_schema TEXT,
    mcp_server_id TEXT NOT NULL,
    test_run_id TEXT NOT NULL,  -- Point-in-time snapshot
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (mcp_server_id) REFERENCES mcp_servers(id) ON DELETE CASCADE,
    FOREIGN KEY (test_run_id) REFERENCES test_runs(id) ON DELETE CASCADE
);

-- Test Cases (no model_id)
CREATE TABLE test_cases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    query TEXT NOT NULL,
    expected_mcp_server_name TEXT NOT NULL,
    expected_tool_name TEXT NOT NULL,
    expected_parameters TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Model Settings (non-credential configuration)
CREATE TABLE model_settings (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    timeout INTEGER NOT NULL CHECK (timeout > 0 AND timeout <= 300),
    temperature REAL NOT NULL CHECK (temperature >= 0 AND temperature <= 2),
    max_retries INTEGER NOT NULL CHECK (max_retries >= 0 AND max_retries <= 10),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Test Runs (with model_settings_id)
CREATE TABLE test_runs (
    id TEXT PRIMARY KEY,
    test_case_id TEXT NOT NULL,
    model_settings_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    llm_response_raw TEXT,
    selected_tool_id TEXT,
    extracted_parameters TEXT,
    confidence_score REAL,
    classification TEXT,
    execution_time_ms INTEGER,
    error_message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (test_case_id) REFERENCES test_cases(id) ON DELETE CASCADE,
    FOREIGN KEY (model_settings_id) REFERENCES model_settings(id) ON DELETE SET NULL,
    FOREIGN KEY (selected_tool_id) REFERENCES tool_definitions(id)
);

-- Junction table for test case MCP servers
CREATE TABLE test_case_mcp_servers (
    test_case_id TEXT NOT NULL,
    mcp_server_id TEXT NOT NULL,
    PRIMARY KEY (test_case_id, mcp_server_id),
    FOREIGN KEY (test_case_id) REFERENCES test_cases(id) ON DELETE CASCADE,
    FOREIGN KEY (mcp_server_id) REFERENCES mcp_servers(id) ON DELETE CASCADE
);

-- Evaluation Results
CREATE TABLE evaluation_results (
    id TEXT PRIMARY KEY,
    test_run_id TEXT NOT NULL UNIQUE,
    classification TEXT NOT NULL,
    tool_selection_correct INTEGER NOT NULL,
    parameter_completeness REAL NOT NULL,
    parameter_correctness REAL NOT NULL,
    parameter_type_conformance INTEGER NOT NULL,
    hallucinated_parameters TEXT,
    confidence_category TEXT,
    reasoning TEXT NOT NULL,
    recommendations TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (test_run_id) REFERENCES test_runs(id) ON DELETE CASCADE
);
```

### Schema Features
- **Foreign Keys**: Enabled with `PRAGMA foreign_keys = ON`
- **WAL Mode**: Concurrent reads supported
- **Indexes**: Created on frequently queried columns
- **Triggers**: Auto-update `updated_at` timestamps
- **CHECK Constraints**: Data integrity validation

---

## Core Services

### Evaluation Service
**Path**: [src/mcp_tef/services/evaluation_service.py](src/mcp_tef/services/evaluation_service.py)
- Orchestrates test execution workflow
- Ingests fresh tools from MCP servers
- Classifies results (TP/FP/TN/FN)
- Generates recommendations

### LLM Service
**Path**: [src/mcp_tef/services/llm_service.py](src/mcp_tef/services/llm_service.py)
- Interfaces with LLM providers (runtime API key)
- Manages prompt templates
- Handles retries and timeouts

### Similarity Service
**Path**: [src/mcp_tef/services/similarity_service.py](src/mcp_tef/services/similarity_service.py)
- Coordinates similarity analysis
- Supports server_list/tool_list/url_list formats
- Generates similarity matrices and overlap analysis
- Concurrent URL fetching and tool processing

### Embedding Service
**Path**: [src/mcp_tef/services/embedding_service.py](src/mcp_tef/services/embedding_service.py)
- Multi-backend support (fastembed, OpenAI, custom API)
- Generates embeddings for similarity analysis
- Caching for performance

### Recommendation Service
**Path**: [src/mcp_tef/services/recommendation_service.py](src/mcp_tef/services/recommendation_service.py)
- Identifies tool differentiation issues
- Generates actionable recommendations
- LLM-improved tool descriptions
- Configuration update commands/patches

### Parameter Validator
**Path**: [src/mcp_tef/services/parameter_validator.py](src/mcp_tef/services/parameter_validator.py)
- Validates parameter completeness
- Checks type conformance
- Detects hallucinated parameters

### Confidence Analyzer
**Path**: [src/mcp_tef/services/confidence_analyzer.py](src/mcp_tef/services/confidence_analyzer.py)
- Categorizes confidence patterns
- Identifies critical issues (misleading descriptions)
- Generates confidence-based recommendations

### Metrics Service
**Path**: [src/mcp_tef/services/metrics_service.py](src/mcp_tef/services/metrics_service.py)
- Calculates precision, recall, F1
- Computes parameter accuracy
- Aggregates confidence distributions

### MCP Loader
**Path**: [src/mcp_tef/services/mcp_loader.py](src/mcp_tef/services/mcp_loader.py)
- Loads tools from MCP servers
- Parses tool definitions
- Handles connectivity verification

### Tool Quality Service
**Path**: [src/mcp_tef/services/tool_quality_service.py](src/mcp_tef/services/tool_quality_service.py)
- Analyzes tool description quality
- Identifies improvement opportunities

### TLS Service
**Path**: [src/mcp_tef/services/tls_service.py](src/mcp_tef/services/tls_service.py)
- Manages TLS/HTTPS configuration
- Auto-generates self-signed certificates

---

## Configuration

### Environment Variables
- `OPENROUTER_API_KEY` - API key for OpenRouter (optional, can be provided per-request)
- `DEFAULT_LLM_PROVIDER` - Default provider (e.g., "openrouter")
- `DEFAULT_LLM_MODEL` - Default model (e.g., "anthropic/claude-3.5-sonnet")
- `DATABASE_URL` - SQLite database path (default: `mcp_eval.db`)
- `LOG_LEVEL` - Logging level (DEBUG/INFO/WARNING/ERROR)
- `PORT` - Server port (default: 8000)
- `TOOL_INGESTION_TIMEOUT_SECONDS` - Timeout for tool ingestion (default: 30)
- `EMBEDDING_MODEL_TYPE` - Embedding backend (fastembed/openai/custom)
- `SIMILARITY_THRESHOLD` - Default similarity threshold (default: 0.85)

### Settings Management
**Path**: [src/mcp_tef/config/settings.py](src/mcp_tef/config/settings.py)
- Pydantic BaseSettings for validation
- Environment variable loading
- CLI parameter overrides
- Configuration hierarchy: CLI → env vars → defaults

### Development Tools
**Taskfile**: [Taskfile.yml](Taskfile.yml)
- `task format` - Auto-format code with Ruff
- `task lint` - Check code quality
- `task typecheck` - Validate type hints with Ty
- `task test` - Run test suite with coverage

---

## Edge Cases & Known Limitations

### Handled Edge Cases
- LLM provider errors/timeouts - Test run marked as failed with error message
- Multiple tool selection when one expected - Classified appropriately
- Special characters in parameters - Normalized for comparison
- Unreachable MCP server URLs - Error handling in loader, status tracking
- Malformed LLM responses - Graceful degradation
- No ground truth provided - Supports exploratory testing
- Optional parameters - Handled in validation
- Tool ingestion failures - Test run fails immediately with clear error
- Concurrent API key isolation - Request-scoped dependency injection
- Fresh tool state - Ingested at execution time, not cached

### Known Limitations
- Confidence scores only available if LLM provider exposes them
- Parameter normalization uses basic heuristics (may need tuning)
- System evaluates but doesn't automatically improve descriptions
- Limited to tool selection, not actual tool execution
- Ground truth must be manually specified
- Batch processing limited by SQLite write concurrency
- Similarity analysis limited to 1000x1000 tool pairs for performance
- Tool ingestion adds 1-5 seconds per server to test execution time

---

## Implementation Gaps

### Missing Features
None - All P1 and P2 user stories fully implemented across all 4 features

### Missing Tests
- User acceptance testing for developer understanding (SC-007)
- Performance benchmarks for concurrent batch operations
- Stress testing for large tool sets (>1000 tools)
- Load testing for concurrent similarity analysis

### Technical Debt
- API key encryption at rest not implemented (request-scoped only by design)
- Database migrations not yet automated (manual schema updates)
- Rate limiting not implemented for API endpoints
- Tool definition retention policy not defined (snapshots accumulate)
- CSV/HTML export for similarity results (JSON only currently)

---

## Appendix: File Map

### API Layer
- [src/mcp_tef/api/app.py](src/mcp_tef/api/app.py) - FastAPI application setup
- [src/mcp_tef/api/mcp_servers.py](src/mcp_tef/api/mcp_servers.py) - Server management endpoints
- [src/mcp_tef/api/tools.py](src/mcp_tef/api/tools.py) - Tool definition endpoints
- [src/mcp_tef/api/test_cases.py](src/mcp_tef/api/test_cases.py) - Test case management
- [src/mcp_tef/api/test_runs.py](src/mcp_tef/api/test_runs.py) - Test execution endpoints
- [src/mcp_tef/api/metrics.py](src/mcp_tef/api/metrics.py) - Metrics endpoints
- [src/mcp_tef/api/similarity.py](src/mcp_tef/api/similarity.py) - Similarity analysis endpoints
- [src/mcp_tef/api/errors.py](src/mcp_tef/api/errors.py) - Error handling

### Service Layer
- [src/mcp_tef/services/evaluation_service.py](src/mcp_tef/services/evaluation_service.py) - Test execution orchestration
- [src/mcp_tef/services/llm_service.py](src/mcp_tef/services/llm_service.py) - LLM provider integration
- [src/mcp_tef/services/similarity_service.py](src/mcp_tef/services/similarity_service.py) - Similarity analysis
- [src/mcp_tef/services/embedding_service.py](src/mcp_tef/services/embedding_service.py) - Embedding generation
- [src/mcp_tef/services/recommendation_service.py](src/mcp_tef/services/recommendation_service.py) - Tool differentiation recommendations
- [src/mcp_tef/services/parameter_validator.py](src/mcp_tef/services/parameter_validator.py) - Parameter validation
- [src/mcp_tef/services/confidence_analyzer.py](src/mcp_tef/services/confidence_analyzer.py) - Confidence analysis
- [src/mcp_tef/services/metrics_service.py](src/mcp_tef/services/metrics_service.py) - Metrics calculation
- [src/mcp_tef/services/mcp_loader.py](src/mcp_tef/services/mcp_loader.py) - MCP server integration
- [src/mcp_tef/services/tool_quality_service.py](src/mcp_tef/services/tool_quality_service.py) - Tool quality analysis
- [src/mcp_tef/services/tls_service.py](src/mcp_tef/services/tls_service.py) - TLS/HTTPS configuration

### Model Layer
- [src/mcp_tef/models/schemas.py](src/mcp_tef/models/schemas.py) - Pydantic models
- [src/mcp_tef/models/llm_models.py](src/mcp_tef/models/llm_models.py) - LLM-specific models
- [src/mcp_tef/models/evaluation_models.py](src/mcp_tef/models/evaluation_models.py) - Evaluation data models
- [src/mcp_tef/models/enums.py](src/mcp_tef/models/enums.py) - Enumeration types

### Storage Layer
- [src/mcp_tef/storage/database.py](src/mcp_tef/storage/database.py) - Database connection manager
- [src/mcp_tef/storage/schema.sql](src/mcp_tef/storage/schema.sql) - SQLite schema
- [src/mcp_tef/storage/mcp_server_repository.py](src/mcp_tef/storage/mcp_server_repository.py) - Server data access
- [src/mcp_tef/storage/tool_repository.py](src/mcp_tef/storage/tool_repository.py) - Tool data access
- [src/mcp_tef/storage/test_case_repository.py](src/mcp_tef/storage/test_case_repository.py) - Test case data access
- [src/mcp_tef/storage/test_run_repository.py](src/mcp_tef/storage/test_run_repository.py) - Test run data access
- [src/mcp_tef/storage/model_settings_repository.py](src/mcp_tef/storage/model_settings_repository.py) - Model settings data access

### Configuration
- [src/mcp_tef/config/settings.py](src/mcp_tef/config/settings.py) - Settings management
- [src/mcp_tef/config/logging_config.py](src/mcp_tef/config/logging_config.py) - Logging configuration
- [src/mcp_tef/config/prompts.py](src/mcp_tef/config/prompts.py) - LLM prompt templates

### Test Suites
- [tests/contract/](tests/contract/) - API contract tests
- [tests/integration/](tests/integration/) - Feature workflow tests
- [tests/conftest.py](tests/conftest.py) - Shared test fixtures

### Project Configuration
- [pyproject.toml](pyproject.toml) - Python project configuration
- [Taskfile.yml](Taskfile.yml) - Development task automation
- [Dockerfile](Dockerfile) - Container build configuration

---

**Document Version**: 2.0  
**Last Updated**: 2025-11-10  
**Git Commit**: 859d728254fc64586c05039908056c6b4bec1709  
**Integration**: All 4 specifications consolidated
