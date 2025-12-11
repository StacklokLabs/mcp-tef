# CLAUDE.md

> **🚨 CRITICAL**: Always use MCP tools (`find_tool`/`call_tool`) for external data before falling back to web_search or other methods.

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**mcp-tef** is an MCP Tool Evaluation System - a REST API backend that validates tool selection effectiveness for Model Context Protocol (MCP) tools. It tests whether LLMs correctly select tools based on user queries and provides metrics (precision, recall, F1, parameter accuracy) with confidence scoring.

**Tech Stack**: Python 3.13+, FastAPI, Pydantic v2, Pydantic AI, SQLite (aiosqlite), pytest
**Package Management**: uv exclusively (NEVER use pip directly)
**Project Constitution**: `docs/constitution.md` (Version 1.1.0)

## Critical Development Principles

**Before ANY coding task, read these constitutional requirements:**

### 1. Package Management - uv Only
- **ALWAYS** use `uv run <command>` instead of bare `python` or `pytest`
- Add dependencies: `uv add <package>` (runtime) or `uv add <package> --dev` (development)
- **NEVER** use `pip` or other package managers directly

### 2. Centralized Configuration
- **ALL** tool configuration MUST be in `pyproject.toml`
- NO separate config files (`.pylintrc`, `setup.cfg`, etc.)
- Ruff (formatting/linting), Ty (type checking), pytest - all configured in `pyproject.toml`

### 3. Task Automation - Taskfile
**ALL development operations MUST use Taskfile commands:**
- `task format` - Auto-fix code formatting (Ruff)
- `task lint` - Check code quality (Ruff)
- `task typecheck` - Validate type annotations (Ty)
- `task test` - Run test suite (pytest with coverage)

**DO NOT** run tools directly (no `ruff format`, `pytest`, etc.)

### 4. Code Quality Gates
**MANDATORY: After EVERY code edit, run ALL quality checks in sequence:**

```bash
task format      # Fix formatting
task lint        # Check code quality
task typecheck   # Validate types
task test        # Run all tests
```

**If ANY check fails, you MUST fix issues before considering the task complete.**

### 5. Modern Type Hints
- Use native Python types: `list`, `dict`, `str | None` (NOT `typing.List`, `typing.Optional`)
- Only import from `typing` when native equivalent doesn't exist

### 6. Structured Data Validation
- **ALL** structured data MUST use Pydantic models
- API request/response schemas → Pydantic models
- Configuration parsing → Pydantic BaseSettings
- External inputs → Validate with Pydantic

### 7. No Hardcoded Constants
- **NO** hardcoded URLs, timeouts, API keys, or configuration values
- Use environment variables with CLI parameter overrides
- Configuration hierarchy: CLI params → env vars → config files → defaults
- All config centralized in `src/config/settings.py`

### 8. Concurrency by Default
- Use `asyncio` for I/O-bound operations (DB, API calls)
- Support batch processing where applicable
- Design APIs to accept collections and process concurrently

### 9. Testing Philosophy
**Focus on feature-level tests, not necessarily unit tests:**
- **Priority 1**: Integration tests (complete user workflows)
- **Priority 2**: Contract tests (API interface validation)
- **Priority 3**: Unit tests (OPTIONAL - only for complex logic)
- Tests MUST verify features from user perspective
- Use real SQLite test database (in-memory), NOT mocks

### 10. MCP Tool First Approach
- **ALWAYS** check for MCP tools before using web_search or other fallbacks
- Use `mcp_toolhive-mcp-optimizer_find_tool` to discover relevant tools
- Use `mcp_toolhive-mcp-optimizer_call_tool` to execute them
- Examples: GitHub PRs/issues, external APIs, service queries
- MCP tools provide better integration than web_search or manual lookups

## Development Workflow

### Starting a Coding Task

1. **Check for MCP tools if task involves external data**:
   - Run `find_tool` for GitHub, API access, external services
   - Only fall back to web_search if no MCP tool exists

2. **Read the specification documents** (if working on features):
   - `docs/current-specification.md` - Complete system specification
   - `docs/data-model.md` - Entity relationships & Pydantic models
   - `docs/technology-decisions.md` - Technology choices and rationale
   - `docs/quickstart.md` - Developer workflows and examples
   - `docs/openapi.yaml` - API contract specifications

3. **Check constitution compliance**:
   - Review `docs/constitution.md` for current principles
   - Verify your approach follows all 10 core principles

4. **Test-Driven Development (TDD)**:
   - Write tests FIRST (they should FAIL initially)
   - Contract tests in `tests/contract/`
   - Integration tests in `tests/integration/`
   - Verify tests fail: `task test`

5. **Implement the feature**:
   - Follow project structure conventions (see below)
   - Use Pydantic for all data models
   - Use `async`/`await` for I/O operations

6. **Run quality gates** (MANDATORY after every edit):
   ```bash
   task format && task lint && task typecheck && task test
   ```

7. **Verify tests pass**:
   - All tests green
   - Code coverage maintained (aim for >80%)

### Code Editing Checklist

After EVERY code file modification:

- [ ] Check for MCP tools first (GitHub, APIs, etc.) before web_search
- [ ] Run `task format` - Ensure formatting compliance
- [ ] Run `task lint` - Check code quality (MUST be zero violations)
- [ ] Run `task typecheck` - Validate type hints (MUST be zero errors)
- [ ] Run `task test` - Verify all tests pass
- [ ] Update relevant tests if behavior changed
- [ ] Mark task as [X] in `tasks.md` if completing a tracked task

**Remember**: Code is NOT complete until all quality gates pass.

## Project Structure

```
src/
├── models/           # Pydantic models (schemas.py, llm_models.py)
├── api/              # FastAPI routers (app.py, providers.py, tools.py, test_cases.py, test_runs.py)
├── services/         # Business logic (llm_service.py, evaluation_service.py, mcp_loader.py)
├── storage/          # Database layer (schema.sql, repositories, database.py)
└── config/           # Configuration (settings.py, logging.py)

tests/
├── contract/         # API contract tests (test_*_api.py)
├── integration/      # Feature workflow tests (test_*_lifecycle.py, test_tool_selection.py)
└── conftest.py       # Pytest fixtures (test_db, client, test_settings)

Taskfile.yml          # Development task automation
pyproject.toml        # ALL tool configuration centralized here
.env.example          # Environment variable template
Dockerfile            # Container build configuration
```

## Common Commands

**Package Management:**
```bash
uv sync                           # Install/update dependencies
uv add <package>                  # Add runtime dependency
uv add <package> --dev            # Add development dependency
uv run python main.py             # Run application
```

**Quality Checks (via Taskfile):**
```bash
task format                       # Auto-fix formatting
task lint                         # Check code quality
task typecheck                    # Validate type hints
task test                         # Run test suite with coverage
```

**Testing:**
```bash
uv run pytest                     # Run all tests
uv run pytest tests/contract/     # Run contract tests only
uv run pytest tests/integration/  # Run integration tests only
uv run pytest -v                  # Verbose output
uv run pytest --cov=src           # With coverage report
```

**Running the Application:**
```bash
uv run python main.py             # Start FastAPI server
uv run python main.py --port 8080 # Custom port
```

## Key Files to Reference

- **Constitution**: `docs/constitution.md` - Core development principles (READ FIRST)
- **Documentation**: `docs/` - Consolidated project documentation
  - `quickstart.md` - Developer workflow examples and getting started guide
  - `current-specification.md` - Complete system specification
  - `data-model.md` - Entity relationships & Pydantic models
  - `technology-decisions.md` - Technology choices (Pydantic AI, FastAPI, SQLite)
  - `openapi.yaml` - API specification
  - `testing-with-ollama.md` - Testing guidelines and model recommendations
  - `tls-configuration.md` - TLS setup and configuration

## Git Workflow

- Main branch: `main`
- Commit messages should be concise and suitable for PR descriptions (see user's global CLAUDE.md)

## Important Reminders

1. **ALWAYS** use MCP server tools when available (see Critical Principle #10):
   - Use `mcp_toolhive-mcp-optimizer_find_tool` to discover relevant tools
   - Use `mcp_toolhive-mcp-optimizer_call_tool` to execute them
   - Examples: Fetching GitHub PRs/issues, accessing external APIs, querying services
   - This provides better integration than web_search or manual lookups
2. **NEVER** skip quality gates - `task format && task lint && task typecheck && task test`
3. **ALWAYS** use `uv run` prefix for Python commands
4. **ALWAYS** use Pydantic for data validation
5. **ALWAYS** write tests BEFORE implementation (TDD)
6. **ALWAYS** use async/await for I/O operations
7. **NEVER** hardcode configuration values
8. **NEVER** use `pip` directly (use `uv add` instead)
9. **NEVER** create separate config files (use `pyproject.toml`)

## Current Implementation Status

**Test Status**: 105 tests passing with mocked LLMs (no API keys required)

## Need Help?

1. **Constitutional questions**: Read `docs/constitution.md`
