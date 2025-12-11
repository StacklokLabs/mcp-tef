<!--
SYNC IMPACT REPORT
==================
Version Change: 1.0.0 → 1.1.0
Modified Principles:
- II. Centralized Configuration - pyproject.toml: Expanded with explicit enforcement rules
- Testing Standards section: Expanded to emphasize feature-level testing over unit tests

Added Sections:
- VI. Code Quality Standards: New principle requiring formatting and linting compliance
- VII. Concurrency by Default: New principle mandating concurrent execution patterns
- VIII. No Hardcoded Constants: New principle requiring configuration through env vars and CLI
- IX. Configuration Hierarchy: New principle establishing env var + CLI parameter precedence

Removed Sections: None

Templates Status:
✅ plan-template.md - Constitution Check references constitution file, will auto-check new principles
✅ spec-template.md - No changes required (spec remains technology-agnostic)
✅ tasks-template.md - Aligns with testing and concurrency principles
✅ agent-file-template.md - Reviewed, no updates required

Follow-up TODOs:
- None. All placeholders filled with concrete values.
- Plan template will automatically enforce new principles via Constitution Check gate.
-->

# mcp-tef Constitution

## Core Principles

### I. Package Management - uv

All dependency management MUST use uv exclusively.

**Rules:**
- Add runtime dependencies: `uv add <package>`
- Add development dependencies: `uv add <package> --dev`
- Run commands in project environment: `uv run <command>`
- NEVER use `pip` or other package managers directly
- Always use `uv run python` instead of bare `python` to ensure correct environment

**Rationale:** Ensures consistent environment across all developers and CI/CD. The uv tool provides reproducible builds and proper Python version management (3.13+).

### II. Centralized Configuration - pyproject.toml

All project configuration MUST be centralized in `pyproject.toml`.

**Rules:**
- Linter configuration goes in `pyproject.toml`
- Type checker configuration goes in `pyproject.toml`
- Test framework configuration goes in `pyproject.toml`
- Build system configuration goes in `pyproject.toml`
- Package metadata goes in `pyproject.toml`
- Tool settings for ruff, mypy, pytest, etc. go in `pyproject.toml`
- NO separate config files (`.pylintrc`, `setup.py`, `setup.cfg`, etc.) unless tool explicitly requires it
- If a tool absolutely cannot read from `pyproject.toml`, document the exception in this constitution

**Rationale:** Single source of truth for all project settings. Reduces configuration sprawl and makes project setup transparent. Aligns with PEP 518 and modern Python tooling standards.

### III. Task Automation - Taskfile

All development operations MUST be executed via the Taskfile.

**Standard Commands:**
- `task format` - Run code formatters (auto-fix formatting issues)
- `task lint` - Run linters (check code quality)
- `task typecheck` - Run type checkers (validate type annotations)
- `task test` - Run test suite

**Rules:**
- DO NOT run linters/formatters/tests directly via CLI
- All commands MUST be defined in Taskfile
- Taskfile commands MUST use `uv run` internally
- Document custom tasks in project README

**Rationale:** Standardizes developer workflow. New contributors run `task <command>` without learning project-specific tool invocations.

### IV. Structured Data Validation - Pydantic

All structured data MUST be validated using Pydantic models.

**Rules:**
- Define Pydantic models for all data structures with validation requirements
- Use Pydantic for configuration parsing
- Use Pydantic for API request/response schemas
- Use Pydantic for file format parsing (JSON, YAML, etc.)
- MUST validate external inputs (user input, API responses, file contents)

**Rationale:** Pydantic provides runtime type checking, clear validation errors, and automatic serialization. Catches data issues early and provides clear error messages to users.

### V. Modern Type Hints

All type annotations MUST use native Python types (PEP 585+).

**Rules:**
- Use `list` instead of `typing.List`
- Use `dict` instead of `typing.Dict`
- Use `set` instead of `typing.Set`
- Use `tuple` instead of `typing.Tuple`
- Use `type` instead of `typing.Type`
- Use union operator `|` instead of `typing.Union` (e.g., `str | None` instead of `Optional[str]`)
- Only import from `typing` when native equivalent doesn't exist

**Rationale:** Python 3.9+ native types are cleaner, more readable, and reduce import overhead. Project targets Python 3.13+, so legacy typing imports are unnecessary.

### VI. Code Quality Standards

All code MUST adhere to formatting and linting standards before commit.

**Rules:**
- Code MUST pass `task format` without manual intervention
- Code MUST pass `task lint` with zero violations
- Code MUST pass `task typecheck` with zero errors
- Pre-commit hooks SHOULD auto-run formatting
- CI/CD pipeline MUST enforce all quality checks
- Pull requests MUST NOT be merged with failing quality checks
- Use ruff for formatting and linting (fast, modern, all-in-one)
- Configuration for all tools MUST be in `pyproject.toml` (see Principle II)

**Rationale:** Consistent code quality prevents bikeshedding, reduces review time, catches bugs early, and maintains codebase health. Automated enforcement ensures compliance without manual oversight.

### VII. Concurrency by Default

Code MUST be designed for concurrent execution wherever possible.

**Rules:**
- Identify independent operations that can run in parallel
- Use `asyncio` for I/O-bound concurrency (API calls, file operations, database queries)
- Use `concurrent.futures` or similar for CPU-bound parallelism when needed
- Support batch execution of independent tasks
- Functions that can be parallelized MUST document this capability
- CLI commands MUST support batch mode for processing multiple inputs
- Avoid sequential execution when parallel execution is feasible
- Design APIs to accept collections and process them concurrently

**Rationale:** Maximizes performance and throughput. Modern applications often involve multiple I/O operations (API calls, database queries) that benefit greatly from concurrency. Batch processing enables efficient large-scale operations.

### VIII. No Hardcoded Constants

Code MUST NOT contain hardcoded configuration values.

**Rules:**
- All configuration MUST be externalized to environment variables or CLI parameters
- NO hardcoded URLs, timeouts, limits, API keys, or domain-specific values
- If a value might need to change across environments (dev/staging/prod), it MUST be configurable
- Use Pydantic Settings models for environment variable management
- Every environment variable MUST have a CLI parameter equivalent for override
- Configuration MUST be centrally defined (see Principle IX)
- Include sensible defaults with clear documentation

**Rationale:** Enables environment-specific configuration without code changes. Supports testing, deployment flexibility, and operational requirements. Prevents accidental hardcoding of secrets or environment-specific values.

### IX. Configuration Hierarchy

Configuration MUST follow a clear precedence hierarchy.

**Precedence (highest to lowest):**
1. CLI parameters (explicit user override)
2. Environment variables (runtime configuration)
3. Configuration files (if applicable, e.g., `.env` files)
4. Default values (defined in code)

**Rules:**
- Define ALL configuration in a single centralized module/class
- Use Pydantic BaseSettings for automatic env var parsing
- CLI parameter names MUST match environment variable names (lowercase with underscores)
- Example: `--llm-provider` CLI flag matches `LLM_PROVIDER` env var
- Configuration module MUST be imported by all code requiring config values
- NO duplicate configuration definitions across multiple files
- Configuration MUST fail fast with clear errors for missing required values
- Document all configuration options in README or dedicated config documentation

**Rationale:** Prevents configuration conflicts and confusion. Single source of truth for all configuration. Predictable override behavior enables flexible deployment and testing scenarios. Centralization prevents drift and inconsistency.

## Development Workflow

### Code Quality Gates

All code MUST pass quality gates before committing:

1. **Format Check**: `task format` - Auto-fixes formatting issues
2. **Lint Check**: `task lint` - Code quality and best practices
3. **Type Check**: `task typecheck` - Type annotation validation
4. **Test Check**: `task test` - All tests must pass

**Enforcement:**
- Pre-commit hooks SHOULD run format + lint
- CI/CD MUST run all four checks
- Pull requests MUST pass all checks before merge

### Environment Consistency

All development and execution MUST use uv-managed environments:

**Developer Workflow:**
```bash
uv sync                          # Install/update dependencies
uv run python script.py          # Run scripts
uv run pytest                    # Run tests
uv add requests                  # Add dependency
uv add --dev pytest-cov          # Add dev dependency
```

**CI/CD Workflow:**
```bash
uv sync --frozen                 # Install exact versions from lockfile
uv run task lint                 # Run checks via Taskfile
```

**Rules:**
- NEVER activate virtual environments manually
- NEVER use system Python directly
- ALWAYS prefix commands with `uv run`

## Testing Standards

### Test Philosophy

Tests MUST focus on feature-level validation, not necessarily unit tests.

**Priorities:**
1. **Feature Tests**: Verify complete user-facing functionality works end-to-end
2. **Integration Tests**: Verify components work together correctly
3. **Contract Tests**: Verify external interface contracts are maintained
4. **Unit Tests**: OPTIONAL - include only when valuable for complex logic

**Rules:**
- Tests MUST verify features from user perspective
- Tests SHOULD cover complete user scenarios from spec.md
- Tests MAY skip testing individual functions if feature tests provide coverage
- Complex algorithms or business logic MAY benefit from unit tests
- Simple functions (getters, setters, formatters) DO NOT require dedicated unit tests
- Focus on "Does the feature work?" not "Does this function work?"

**Rationale:** Feature-level tests provide more value with less maintenance overhead. They verify actual user requirements rather than implementation details. Unit tests can become brittle and costly to maintain when implementation changes, while feature tests remain stable as long as behavior is consistent.

### Test Organization

Tests MUST be organized by type:

- `tests/contract/` - Contract tests (external interfaces, API contracts)
- `tests/integration/` - Integration tests (system components, feature flows)
- `tests/unit/` - Unit tests (isolated functions, OPTIONAL unless complexity justifies)

### Test Execution

- Contract tests: MUST verify external interface contracts
- Integration tests: SHOULD run in <5 seconds per test
- Unit tests (if present): MUST run in <1 second per test
- All tests: MUST be deterministic (no flaky tests)
- Tests MUST be runnable concurrently (see Principle VII)

### Test Coverage

- SHOULD aim for >80% coverage on business logic
- MUST test all public APIs and user-facing features
- MUST test error handling paths
- Feature coverage MORE IMPORTANT than line coverage
- Focus on covering user scenarios from spec.md

## Governance

### Amendment Process

1. **Propose**: Document the principle change with rationale
2. **Review**: Team reviews impact on existing code and workflows
3. **Approve**: Requires consensus or majority vote (define based on team size)
4. **Update**: Update constitution with version bump
5. **Migrate**: Update templates, code, and documentation to comply

### Version Semantics

- **MAJOR (X.0.0)**: Backward-incompatible changes (principle removal, redefinition)
- **MINOR (0.X.0)**: New principles or material expansions
- **PATCH (0.0.X)**: Clarifications, wording, typo fixes

### Compliance

- All new code MUST comply with current constitution
- All PRs MUST verify constitution compliance
- Existing code SHOULD be updated to comply during refactoring
- Complexity violations MUST be justified in `plan.md` Complexity Tracking section

### Runtime Guidance

This constitution supersedes all other development practices. For implementation-specific guidance during feature development, refer to `plan.md` and `tasks.md` in the feature's spec directory.

**Version**: 1.1.0 | **Ratified**: 2025-10-15 | **Last Amended**: 2025-10-15
