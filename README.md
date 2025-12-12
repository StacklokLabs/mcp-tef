# mcp-tef

Evaluation system for Model Context Protocol (MCP) tools. Verifies that MCP tools effectively trigger on relevant user queries.

## What it does

**Tool Evaluation**: Tests whether your MCP tool descriptions work:
- Does the LLM select the right tool for a given query?
- Are parameters extracted correctly?
- How confident is the LLM in its selection?
- Where can your tool descriptions be improved?

**Similarity Detection**: Find and fix overlapping tools:
- Detect tools with similar descriptions and capabilities
- Generate multi-dimensional similarity matrices
- Get AI-powered recommendations for improving differentiation
- Analyze capability overlap across tool portfolios

## Quick Start

```bash
# Install dependencies
uv sync

# Configure environment (optional - defaults work with Ollama)
cp .env.example .env

# Run the server (HTTPS with auto-generated certificate)
uv run python -m mcp_tef
# Server starts at https://localhost:8000

# API docs at https://localhost:8000/docs
```

> **📖 New to mcp-tef?** See the [**comprehensive quickstart guide**](docs/quickstart.md) for detailed tutorials, workflows, and troubleshooting.

### Key Configuration

**LLM Providers:**
- **Local Development**: Ollama (default) - no API key needed
- **Production**: OpenRouter - set `OPENROUTER_API_KEY` in `.env`

**Security:**
- **Default**: HTTPS with auto-generated self-signed certificate
- **Custom certs**: `--tls-cert-file` and `--tls-key-file` flags
- **Development**: `--tls-enabled=false` for HTTP (⚠️ not for production)

See [docs/testing-with-ollama.md](docs/testing-with-ollama.md) and [docs/tls-configuration.md](docs/tls-configuration.md) for details.

## Core Workflows

### Tool Evaluation
Test if your LLM correctly selects tools based on user queries:
- Create test case with expected tool and parameters
- Run test with fresh tool definitions from MCP server URLs
- Get classification (TP/FP/TN/FN), parameter validation, and confidence analysis
- Receive AI-powered recommendations for improving tool descriptions

[→ See detailed workflow in quickstart guide](docs/quickstart.md#workflow-1-tool-evaluation)

### Tool Quality Analysis
Evaluate and improve tool descriptions with AI-powered quality scoring:
- Get clarity, completeness, and conciseness scores (1-10)
- Receive detailed explanations and suggested improvements
- Analyze multiple tools across servers simultaneously

[→ See detailed workflow in quickstart guide](docs/quickstart.md#workflow-3-tool-quality-analysis)

### Similarity Detection
Find and fix overlapping tool descriptions that confuse LLMs:
- Detect semantically similar tools using embeddings
- Generate multi-dimensional similarity and overlap matrices
- Get AI-powered differentiation recommendations
- Support multiple input formats (URLs, tool lists, or server groups)

[→ See detailed workflow in quickstart guide](docs/quickstart.md#workflow-2-similarity-detection)

### Metrics & Analytics
Track evaluation performance across multiple tests:
- Precision, recall, and F1 scores
- Parameter accuracy metrics
- Confidence distribution analysis
- Batch testing for concurrent evaluation

[→ See API documentation](https://localhost:8000/docs)

## Development

```bash
# Format code
task format

# Lint
task lint

# Type check
task typecheck

# Run tests
task test
```

### Making a Release

Releases are automated via GitHub Actions when you push a version tag. Git tags are the single source of truth for versions.

```bash
# 1. Ensure main branch is clean and all tests pass
git checkout main
git pull origin main
task format && task lint && task typecheck && task test

# 2. Create and push a version tag
git tag v1.2.3
git push origin v1.2.3

# For pre-release versions (won't update 'latest' tag):
git tag v1.2.3-beta.1
git push origin v1.2.3-beta.1
```

**Note:** The version in `pyproject.toml` stays at `0.1.0` as a placeholder. Git tags serve as the canonical version source for container releases.

**What happens automatically:**
- ✅ Runs all code quality checks (format, lint, typecheck, test)
- ✅ Builds multi-platform container images (linux/amd64, linux/arm64)
- ✅ Publishes to GitHub Container Registry with appropriate tags
- ✅ Generates SBOM and provenance attestations
- ✅ Signs all images with Cosign (keyless signing)
- ✅ Creates GitHub release with auto-generated notes

**Version Tag Format:**
- Stable releases: `v1.2.3` → Creates tags: `1.2.3`, `1.2`, `latest`
- Pre-releases: `v1.2.3-beta.1` → Creates tag: `1.2.3-beta.1` (no `latest`)
- Release candidates: `v1.2.3-rc.1` → Creates tag: `1.2.3-rc.1` (no `latest`)

**Verify the release:**
```bash
# Check workflow status
gh run list --workflow=release.yml

# Authenticate to GitHub Container Registry (images are private)
# Create a Personal Access Token with 'read:packages' scope at:
# https://github.com/settings/tokens/new?scopes=read:packages
echo "$GITHUB_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin

# Pull and test the image
docker pull ghcr.io/stackloklabs/mcp-tef:1.2.3
docker run --rm ghcr.io/stackloklabs/mcp-tef:1.2.3 --help

# Verify signature
cosign verify \
  --certificate-identity-regexp="https://github.com/StacklokLabs/mcp-tef" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com" \
  ghcr.io/stackloklabs/mcp-tef:1.2.3
```

### Making a CLI Release

CLI releases are published to GitHub Releases when you push a `cli-v*` tag:

```bash
# 1. Ensure CLI tests pass
cd cli/
uv sync --dev
uv run ruff format --check .
uv run ruff check .
uv run ty check src/
uv run pytest -m "not docker"

# 2. Create and push a CLI version tag
git tag cli-v0.1.0
git push origin cli-v0.1.0
```

**Supported version formats (PEP 440):**

| Tag | Type |
|-----|------|
| `cli-v1.0.0` | Release |
| `cli-v1.0.0.post1` | Release (post) |
| `cli-v1.0.0a1` | Pre-release (alpha) |
| `cli-v1.0.0b1` | Pre-release (beta) |
| `cli-v1.0.0rc1` | Pre-release (release candidate) |
| `cli-v1.0.0.dev1` | Pre-release (development) |

**What happens automatically:**
- Runs CLI code quality checks (format, lint, typecheck, test)
- Builds Python package (wheel + sdist)
- Creates GitHub Release with package artifacts

**Note:** CLI versions use a separate tag prefix (`cli-v*`) from server versions (`v*`).

## Tech Stack

- **Python 3.13+** with uv package manager
- **FastAPI** (async REST API)
- **Pydantic v2** (validation) + **Pydantic AI** (LLM interface)
- **SQLite + aiosqlite** (async storage)
- **pytest** (testing with 105 tests, 77% coverage)

[→ See detailed architecture in docs](docs/technology-decisions.md)

## Use Cases

- ✅ Validate tool descriptions before deploying MCP servers
- ✅ Identify and fix similar/overlapping tools
- ✅ Test tools across different LLM providers
- ✅ Get AI-powered improvement recommendations
- ✅ Track evaluation metrics across test suites

## Deployment

### CLI Tool (Recommended)

The easiest way to deploy mcp-tef is using the CLI tool:

```bash
# Install the CLI
uv tool install mtef

# Deploy latest version
mtef deploy

# Deploy with API keys and health check
mtef deploy \
  --env OPENROUTER_API_KEY=sk-xxx \
  --health-check
```

See the [CLI documentation](cli/README.md) for full usage details.

### Using Pre-built Container Images

Pre-built, signed container images are available from GitHub Container Registry.

**Authentication Required:**
Images are currently private and require authentication. Create a [Personal Access Token](https://github.com/settings/tokens/new?scopes=read:packages) with `read:packages` scope:

```bash
# Authenticate to GHCR
echo "$GITHUB_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

**Pull and Run:**
```bash
# Pull the latest stable release
docker pull ghcr.io/stackloklabs/mcp-tef:latest

# Or pull a specific version
docker pull ghcr.io/stackloklabs/mcp-tef:1.2.3

# Run the container
docker run -d \
  -p 8000:8000 \
  -e OPENROUTER_API_KEY=your-key \
  -v $(pwd)/data:/app/data \
  ghcr.io/stackloklabs/mcp-tef:latest
```

**Available Image Tags:**
- `latest` - Latest stable release (excludes pre-releases)
- `X.Y.Z` - Specific version (e.g., `1.2.3`)
- `X.Y` - Latest patch version (e.g., `1.2`)
- `X.Y.Z-beta.N` - Pre-release versions (e.g., `1.2.3-beta.1`)

**Verify Image Signatures:**

All images are signed with [Cosign](https://github.com/sigstore/cosign) for supply chain security:

```bash
# Install cosign (if not already installed)
# See: https://docs.sigstore.dev/cosign/installation/

# Verify image signature using keyless signing
cosign verify \
  --certificate-identity-regexp="https://github.com/StacklokLabs/mcp-tef" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com" \
  ghcr.io/stackloklabs/mcp-tef:latest

# Inspect SBOM (Software Bill of Materials)
cosign download sbom ghcr.io/stackloklabs/mcp-tef:latest
```

### Building from Source

```bash
# Build locally
docker build -t mcp-tef .

# Run locally built image
docker run -d -p 8000:8000 -e OPENROUTER_API_KEY=your-key mcp-tef
```

## License

[License TBD]
