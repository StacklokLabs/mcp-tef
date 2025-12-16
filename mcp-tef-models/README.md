# mcp-tef-models

Shared Pydantic models for the mcp-tef server and CLI.

This package provides a single source of truth for all shared data models, preventing model drift between the server and CLI packages.

## Installation

This package is used as a local path dependency in the monorepo:

```toml
dependencies = [
    "mcp-tef-models @ {path = '../mcp-tef-models', editable = true}",
]
```

## Usage

```python
from mcp_tef_models import (
    TestCaseCreate,
    TestCaseResponse,
    MCPServerConfig,
    SimilarityMethod,
    EmbeddingModelType,
)
```

## Dependencies

This package has minimal dependencies:
- `pydantic>=2.12.5` - For data validation

The CLI can depend on this package without pulling in heavy server dependencies like FastAPI, pydantic-ai, etc.
