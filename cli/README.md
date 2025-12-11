# mcp-tef CLI

Command-line interface for deploying and managing the mcp-tef MCP Tool Evaluation System.

## Overview

The mcp-tef CLI is a standalone tool that simplifies deploying and managing mcp-tef Docker containers. It pulls pre-built images from GitHub Container Registry (GHCR) and provides a streamlined interface for container lifecycle management.

**Features:**
- Deploy mcp-tef from GHCR with a single command
- Support for environment variable configuration
- Health check validation
- Volume mounting and network configuration
- Custom image support for local testing

## Installation

### Primary Method: uv tool from GitHub Release (Recommended)

Install directly from a GitHub release wheel:

```bash
uv tool install https://github.com/StacklokLabs/mcp-tef/releases/download/cli-v0.1.0/mcp_tef_cli-0.1.0-py3-none-any.whl
```

Replace `0.1.0` with the desired version. See [releases](https://github.com/StacklokLabs/mcp-tef/releases) for available versions.

This installs the CLI in an isolated environment and makes it available globally as `mcp-tef-cli`.

### Alternative: Install from Git Repository

```bash
uv tool install "mcp-tef-cli @ git+https://github.com/StacklokLabs/mcp-tef.git@cli-v0.1.0#subdirectory=cli"
```

Or install the latest from main branch:

```bash
uv tool install "mcp-tef-cli @ git+https://github.com/StacklokLabs/mcp-tef.git#subdirectory=cli"
```

### Development: Install from Source

```bash
git clone https://github.com/StacklokLabs/mcp-tef.git
cd mcp-tef/cli
uv tool install --editable .
```

## Quick Start

### Deploy mcp-tef Server

```bash
# Deploy latest version
mcp-tef-cli deploy

# Deploy with API keys and health check
mcp-tef-cli deploy \
  --env OPENROUTER_API_KEY=sk-xxx \
  --env ANTHROPIC_API_KEY=sk-xxx \
  --health-check

# Deploy specific version
mcp-tef-cli deploy --version v0.2.1
```

### Evaluate Tool Quality

```bash
# Evaluate tool description quality from an MCP server
mcp-tef-cli tool-quality \
  --server-urls http://localhost:3000/sse \
  --model-provider openrouter \
  --model-name anthropic/claude-sonnet-4-5-20250929
```

### Manage Test Cases

```bash
# Create a test case
mcp-tef-cli test-case create \
  --name "Weather lookup" \
  --query "What is the weather in San Francisco?" \
  --expected-server "http://localhost:3000/sse" \
  --expected-tool "get_weather" \
  --servers "http://localhost:3000/sse"

# Create test cases from a JSON file with variable substitution
# Example test-cases.json:
#   [
#     {
#       "name": "Weather lookup",
#       "query": "What is the weather in San Francisco?",
#       "available_mcp_servers": ["${MCP_SERVER_URL}"],
#       "expected_mcp_server_url": "${MCP_SERVER_URL}",
#       "expected_tool_name": "get_weather"
#     }
#   ]
mcp-tef-cli test-case create \
  --from-file test-cases.json \
  --set MCP_SERVER_URL=http://localhost:3000/sse

# List all test cases
mcp-tef-cli test-case list

# Get test case details
mcp-tef-cli test-case get <test-case-id>
```

### Execute Test Runs

```bash
# Execute a test case with an LLM
mcp-tef-cli test-run execute <test-case-id> \
  --model-provider openrouter \
  --model-name anthropic/claude-sonnet-4-5-20250929 \
  --api-key sk-xxx

# List test runs
mcp-tef-cli test-run list

# Get test run results
mcp-tef-cli test-run get <test-run-id>
```

### Analyze Tool Similarity

```bash
# Run similarity analysis across MCP servers
mcp-tef-cli similarity analyze \
  --server-urls http://localhost:3000/sse

# Generate similarity matrix
mcp-tef-cli similarity matrix \
  --server-urls http://localhost:3000/sse

# Get differentiation recommendations for similar tools
mcp-tef-cli similarity recommend \
  --server-urls http://localhost:3000/sse
```

### Stop the Server

```bash
# Stop and remove the container
mcp-tef-cli stop
```

## Usage

### `mcp-tef-cli deploy`

Deploy mcp-tef as a Docker container from GitHub Container Registry.

```bash
mcp-tef-cli deploy [OPTIONS]
```

#### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--version TEXT` | `latest` | Image version/tag to pull from GHCR (e.g., `v0.2.1`, `latest`) |
| `--image TEXT` | None | Full image reference (overrides `--version`, useful for local testing) |
| `--name TEXT` | `mcp-tef` | Container name |
| `--port INTEGER` | `8000` | Host port to bind (maps to container port 8000) |
| `--env TEXT` | - | Environment variable in `KEY=value` format (can be specified multiple times) |
| `--env-file PATH` | None | Path to `.env` file with environment variables |
| `--detach/--no-detach` | `--detach` | Run container in background |
| `--remove` | True | Remove container on exit (only if `--no-detach`) |
| `--health-check` | False | Wait for health check to pass after deployment |
| `--health-timeout INTEGER` | `30` | Health check timeout in seconds |
| `--volume TEXT` | - | Volume mount in `host:container` or `host:container:mode` format |
| `--network TEXT` | None | Docker network to attach container to |
| `--restart TEXT` | `no` | Restart policy: `no`, `always`, `on-failure`, `unless-stopped` |
| `--insecure` | False | Skip SSL certificate verification for health checks (for self-signed certs) |

### `mcp-tef-cli stop`

Stop and remove a deployed mcp-tef container.

```bash
mcp-tef-cli stop [OPTIONS]
```

#### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--name TEXT` | `mcp-tef` | Container name to stop |
| `--remove-image` | False | Also remove the Docker image after stopping |
| `--force` | False | Force stop (SIGKILL instead of SIGTERM) |
| `--timeout INTEGER` | `10` | Seconds to wait for container to stop before killing |

**Examples:**

```bash
# Stop the default mcp-tef container
mcp-tef-cli stop

# Stop a named container
mcp-tef-cli stop --name mcp-tef-dev

# Stop and remove the image to free disk space
mcp-tef-cli stop --remove-image

# Force stop (immediate kill)
mcp-tef-cli stop --force
```

## Usage Examples

### Local Development

Deploy for local development with debug logging:

```bash
mcp-tef-cli deploy \
  --env LOG_LEVEL=DEBUG \
  --env OPENROUTER_API_KEY=sk-xxx \
  --health-check
```

### Custom Port

Deploy on a different port:

```bash
mcp-tef-cli deploy --port 9000
```

### Environment File

Create a `.env` file:

```env
OPENROUTER_API_KEY=sk-xxx
ANTHROPIC_API_KEY=sk-xxx
OPENAI_API_KEY=sk-xxx
LOG_LEVEL=INFO
DATABASE_URL=sqlite:///./data/mcp-tef.db
```

Deploy with environment file:

```bash
mcp-tef-cli deploy --env-file .env --health-check
```

### Volume Mounting

Mount a local database directory:

```bash
mcp-tef-cli deploy \
  --volume ./data:/app/data:rw \
  --env DATABASE_URL=sqlite:///./data/mcp-tef.db
```

### Production Deployment

Deploy with restart policy and health check:

```bash
mcp-tef-cli deploy \
  --name mcp-tef-production \
  --port 8000 \
  --env-file .env.prod \
  --restart unless-stopped \
  --health-check \
  --health-timeout 60
```

### Local Testing

Deploy a locally built image for testing:

```bash
# First build the image
docker build -t mcp-tef:test .

# Deploy local image
mcp-tef-cli deploy --image mcp-tef:test --port 9000
```

## CI/CD Integration

### GitHub Actions: Direct Environment Variables

Pass secrets directly as environment variables:

```yaml
name: Deploy mcp-tef for Testing

on:
  pull_request:
  workflow_dispatch:

jobs:
  test-with-mcp-tef:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Install mcp-tef CLI
        run: uv tool install "mcp-tef-cli @ git+https://github.com/StacklokLabs/mcp-tef.git#subdirectory=cli"

      - name: Deploy mcp-tef server
        run: |
          mcp-tef-cli deploy \
            --version latest \
            --port 8000 \
            --env OPENROUTER_API_KEY=${{ secrets.OPENROUTER_API_KEY }} \
            --env ANTHROPIC_API_KEY=${{ secrets.ANTHROPIC_API_KEY }} \
            --env LOG_LEVEL=INFO \
            --health-check

      - name: Run integration tests
        run: |
          pytest tests/integration/

      - name: Stop mcp-tef container
        if: always()
        run: docker stop mcp-tef
```

### GitHub Actions: Environment File

Create environment file from secrets:

```yaml
- name: Create .env file with secrets
  run: |
    cat << EOF > .env.ci
    OPENROUTER_API_KEY=${{ secrets.OPENROUTER_API_KEY }}
    ANTHROPIC_API_KEY=${{ secrets.ANTHROPIC_API_KEY }}
    LOG_LEVEL=INFO
    EOF
    chmod 600 .env.ci

- name: Deploy mcp-tef server
  run: |
    mcp-tef-cli deploy \
      --version latest \
      --port 8000 \
      --env-file .env.ci \
      --health-check

- name: Cleanup
  if: always()
  run: |
    docker stop mcp-tef || true
    rm -f .env.ci
```

### GitLab CI

```yaml
test:
  image: python:3.13
  services:
    - docker:dind
  before_script:
    - pip install uv
    - uv tool install "mcp-tef-cli @ git+https://github.com/StacklokLabs/mcp-tef.git#subdirectory=cli"
  script:
    - |
      mcp-tef-cli deploy \
        --env OPENROUTER_API_KEY=$OPENROUTER_API_KEY \
        --env ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
        --health-check
    - pytest tests/integration/
  after_script:
    - docker stop mcp-tef || true
```

## Environment Variables

### Required Variables

At least one LLM provider API key is required:

- `OPENROUTER_API_KEY` - OpenRouter API key (recommended)
- `ANTHROPIC_API_KEY` - Anthropic API key
- `OPENAI_API_KEY` - OpenAI API key

### Optional Variables

- `LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR) [default: INFO]
- `DATABASE_URL` - SQLite database URL [default: sqlite:///./data/mcp-tef.db]
- `TLS_ENABLED` - Enable TLS/HTTPS [default: false]
- `PORT` - Server port [default: 8000]
- `EMBEDDING_MODEL_NAME` - Embedding model name [default: BAAI/bge-small-en-v1.5]

See the [main documentation](https://github.com/StacklokLabs/mcp-tef) for complete configuration details.

## Troubleshooting

### Docker Not Running

**Error:**
```
✗ Docker daemon not available
  Ensure Docker is installed and running
```

**Solution:**
1. Check Docker is installed: `docker --version`
2. Start Docker Desktop (macOS/Windows) or Docker daemon (Linux)
3. Verify: `docker ps`

### Port Already in Use

**Error:**
```
✗ Port 8000 already in use
  Try a different port with --port
```

**Solution:**
1. Use a different port: `mcp-tef-cli deploy --port 9000`
2. Or stop the conflicting container: `docker ps` and `docker stop <container>`

### Image Not Found

**Error:**
```
✗ Image not found: ghcr.io/stackloklabs/mcp-tef:v99.99.99
  Available versions: https://github.com/StacklokLabs/mcp-tef/pkgs/container/mcp-tef
```

**Solution:**
1. Check available versions at the GHCR link
2. Use `--version latest` or specify a valid version tag

### Health Check Timeout

**Error:**
```
✗ Health check timeout
```

**Solution:**
1. Increase timeout: `--health-timeout 60`
2. Check container logs: `docker logs mcp-tef`
3. Verify API keys are correct
4. Ensure sufficient resources (memory, CPU)

### Local Image Not Found

**Error:**
```
✗ Local image not found: mcp-tef:test
  Build the image first with: docker build -t mcp-tef:test .
```

**Solution:**
Build the image first:
```bash
cd /path/to/mcp-tef
docker build -t mcp-tef:test .
```

## Container Lifecycle Notes

### Auto-Removal Behavior

By default, containers are deployed in detached mode (`--detach`). In this mode:

- Containers are **not** automatically removed when stopped
- Stopped containers persist and can accumulate over time
- Use `mcp-tef-cli stop` to clean up containers when done

To manually list and clean up stopped containers:
```bash
# List all mcp-tef containers (including stopped)
docker ps -a --filter "name=mcp-tef"

# Remove stopped containers
docker container prune -f
```

For non-detached mode (`--no-detach`), containers are automatically removed when the process exits.

### Volume Mount Permissions

When mounting host directories that don't exist, Docker creates them with root ownership. This can cause permission issues if the container process runs as non-root.

**Best practice:** Create host directories before mounting:
```bash
mkdir -p ./data
mcp-tef-cli deploy --volume ./data:/app/data:rw
```

## Development

### Running Tests

The CLI has its own test suite separate from the main mcp-tef server:

```bash
# Install CLI dev dependencies
cd cli/
uv sync --dev

# Run unit tests (no Docker required)
uv run pytest -m "not docker"

# Run all tests (requires Docker)
uv run pytest

# Run with coverage
uv run pytest --cov=src/mcp_tef_cli --cov-report=html
```

### Building from Source

```bash
cd cli/
uv build
```

This creates distribution packages in `cli/dist/`.

### Local Development Installation

```bash
cd cli/
uv tool install --editable .
```

Changes to the source code will be immediately reflected in the installed CLI.

## Links

- **Repository:** https://github.com/StacklokLabs/mcp-tef
- **CLI Specification:** [docs/cli-specification.md](../docs/cli-specification.md)
- **API Documentation:** https://github.com/StacklokLabs/mcp-tef#api-documentation
- **Issue Tracker:** https://github.com/StacklokLabs/mcp-tef/issues
- **Container Registry:** https://github.com/StacklokLabs/mcp-tef/pkgs/container/mcp-tef

## License

Apache License 2.0 - see the [LICENSE](../LICENSE) file for details.
