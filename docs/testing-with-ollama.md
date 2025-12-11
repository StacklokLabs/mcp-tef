# Testing with Ollama

Complete guide for running tests with optional Ollama integration for realistic LLM behavior.

## Quick Start

### Default: Mock Mode (Fast)

```bash
# Tests use mocked LLM responses by default
task test
```

- ✅ Fast (~37 seconds)
- ✅ Deterministic results
- ✅ No external dependencies

### Optional: Ollama Mode (Realistic)

```bash
# 1. Install and start Ollama
brew install ollama
ollama serve

# 2. Pull a lightweight model
ollama pull llama3.2:1b

# 3. Run tests with Ollama
USE_OLLAMA=true task test:ollama
```

- ✅ Realistic LLM behavior
- ✅ Tests actual prompt engineering
- ⏱️  Slower (~5-8 minutes)

## Architecture

### How It Works

Tests automatically detect the `USE_OLLAMA` environment variable and configure accordingly:

```python
# tests/conftest.py
if os.getenv("USE_OLLAMA") == "true":
    # Use real Ollama
    Settings(
        default_model=ModelSettings(
            name="llama3.2:1b",
            provider="ollama",
            base_url="http://localhost:11434/v1",  # Required for Ollama
            timeout=30,
            max_retries=3,
        )
    )
else:
    # Use mocks (default)
    Settings(
        default_model=ModelSettings(
            name="anthropic/claude-3.5-sonnet",
            provider="openrouter",
            # No base_url needed - OpenRouter has built-in support
            timeout=30,
            max_retries=3,
        )
    )
```

### Test Categories

| Category | Mock Mode | Ollama Mode | Marker |
|----------|-----------|-------------|--------|
| Integration | ✅ Fast | ✅ Realistic | `@pytest.mark.integration` |
| Contract | ✅ Fast | ✅ Realistic | `@pytest.mark.contract` |
| LLM-enhanced | ⚠️ Simplified | ✅ Full behavior | `@pytest.mark.ollama` |

## Task Commands

```bash
# Standard test modes
task test              # All tests with mocks (default)
task test:fast         # Skip slow tests
task test:integration  # Integration tests only
task test:contract     # Contract tests only

# Ollama modes
task test:ollama       # All tests with Ollama
task test:ollama-only  # Only tests marked as benefiting from Ollama
```

## CI/CD Integration

### Current Setup (Mock Mode)

`.github/workflows/code-quality.yml` runs on every PR:

```yaml
- name: Run Tests
  run: task test  # Uses mocks by default
```

**Result:** Fast, deterministic tests (~2-3 minutes total)

### Optional: Ollama Workflow

`.github/workflows/code-quality-with-ollama.yml` provides realistic LLM testing:

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    ports:
      - 11434:11434

steps:
  - name: Pull Ollama Model
    run: ollama pull llama3.2:1b
  
  - name: Run Tests
    env:
      USE_OLLAMA: "true"
    run: task test
```

**When to use:**
- Manual trigger for critical PRs
- Before major releases
- Nightly/weekly scheduled runs

### Enabling Ollama in CI

To add Ollama tests to your PR workflow, update `.github/workflows/main-and-pr.yml`:

```yaml
jobs:
  # Standard mock tests (always run)
  code_checks:
    name: Code Checks
    uses: ./.github/workflows/code-checks.yml
  
  # Ollama tests (optional)
  code_checks_ollama:
    name: Code Checks (Ollama)
    uses: ./.github/workflows/code-quality-with-ollama.yml
    with:
      enable_ollama: true
      ollama_model: llama3.2:1b
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_OLLAMA` | `false` | Set to `true` to enable Ollama |
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Ollama API endpoint |
| `OLLAMA_MODEL` | `llama3.2:1b` | Model to use for testing |
| `OPENROUTER_API_KEY` | - | OpenRouter API key (optional, for `no_mock_agent` tests) |
| `ANTHROPIC_API_KEY` | - | Anthropic API key (optional, for `no_mock_agent` tests) |

### API Keys for Real LLM Tests

**Important:** Only tests marked with `@pytest.mark.no_mock_agent` make real LLM API calls. All other tests use mocked agents and don't require API keys.

#### Option 1: No API Keys (Most tests pass)

```bash
# Most tests use mocked LLM agents
task test
# ✅ Tests marked with no_mock_agent will skip without API keys
```

#### Option 2: With API Keys - Full Coverage

Create a `.env` file:
```bash
OPENROUTER_API_KEY=your-openrouter-key-here
ANTHROPIC_API_KEY=your-anthropic-key-here
```

```bash
task test:real-llm-keys
# ✅ All tests pass including real LLM API tests
# 🔄 Tests both OpenRouter and Anthropic integration
```

**Tests requiring real API keys** are marked with `@pytest.mark.no_mock_agent` and include:
- Tool quality evaluation endpoints
- Direct LLM provider integration tests

#### Why OpenRouter is Convenient

1. **Single API Key**: Access to 400+ models through one API key
2. **Cost Effective**: Competitive pricing across multiple providers
3. **Flexibility**: Easy to switch between different models and providers
4. **No Setup Required**: Built-in support in Pydantic AI (no `base_url` needed)

#### Test Skipping Behavior

Tests that require API keys will:
- ✅ **Skip gracefully** if the required key is not set
- 📝 **Show skip reason** in test output (e.g., "OPENROUTER_API_KEY not found in .env file")
- ⚠️ **Not fail** - they simply won't run

This allows developers to run tests with whatever API keys they have available.

### Application Settings

In `src/mcp_tef/config/settings.py`:

```python
default_model: ModelSettings = ModelSettings(
    name="llama3.2:3b",
    provider="ollama",
    base_url="http://localhost:11434/v1",
    timeout=30,
    max_retries=3,
)
```

You can also configure this via environment variables:
```bash
DEFAULT_MODEL__NAME=llama3.2:3b
DEFAULT_MODEL__PROVIDER=ollama
DEFAULT_MODEL__BASE_URL=http://localhost:11434/v1  # Required for Ollama
DEFAULT_MODEL__TIMEOUT=30
DEFAULT_MODEL__MAX_RETRIES=3
```

**Note:** For OpenRouter, `base_url` is optional since Pydantic AI has built-in support:
```python
default_model=ModelSettings(
    name="anthropic/claude-3.5-sonnet",
    provider="openrouter",
    # base_url not needed!
)
```

### Recommended Models

| Model | Size | Speed | Use Case |
|-------|------|-------|----------|
| `llama3.2:1b` | ~1GB | ⚡ Fast | CI/CD, quick local tests |
| `llama3.2:3b` | ~3GB | 🏃 Medium | Local development, realistic behavior |
| `llama3.1:8b` | ~8GB | 🚶 Slow | High-quality validation |
| `anthropic/claude-3.5-sonnet` | API | 🎯 Best | Production (via OpenRouter) |

**Recommendations:**
- **CI/Testing**: `llama3.2:1b` for speed
- **Development**: `llama3.2:3b` for quality/speed balance
- **Production**: `anthropic/claude-3.5-sonnet` via OpenRouter for best accuracy

## Local Development

### Using Docker

```bash
# Start Ollama in Docker
docker run -d -p 11434:11434 --name ollama ollama/ollama:latest

# Pull model
docker exec ollama ollama pull llama3.2:1b

# Run tests
USE_OLLAMA=true \
OLLAMA_BASE_URL=http://localhost:11434 \
OLLAMA_MODEL=llama3.2:1b \
task test
```

### Docker Compose

```yaml
# docker-compose.yml
services:
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_models:/root/.ollama

volumes:
  ollama_models:
```

```bash
docker-compose up -d
docker-compose exec ollama ollama pull llama3.2:1b
USE_OLLAMA=true task test
```

## Testing Strategy

### Daily Development

```bash
# TDD cycle - use mocks for fast feedback
task test

# Before committing
task format
task lint
task test
```

### Before PR

```bash
# Standard checks
task lint
task typecheck
task test

# If touching LLM features, also test with Ollama
USE_OLLAMA=true task test:ollama-only
```

### CI/CD Recommendations

**Tier 1 - Every PR (Required)**
- Mock mode tests via standard workflow
- Fast execution (~2-3 minutes)
- Catches 95% of issues

**Tier 2 - Important PRs (Manual)**
- Trigger Ollama workflow manually
- For PRs touching similarity, confusion, or recommendation features
- More thorough validation

**Tier 3 - Scheduled (Nightly/Weekly)**
- Automated Ollama test runs
- Catches edge cases and LLM drift
- Quality gate before releases

## Performance Comparison

| Aspect | Mock Mode | Ollama Mode |
|--------|-----------|-------------|
| **Execution Time** | ~37 seconds | ~5-8 minutes |
| **Setup Time** | None | ~30s (pull model) |
| **Per Test** | ~0.3s avg | ~3-5s avg |
| **Deterministic** | ✅ Yes | ⚠️ Mostly |
| **Coverage** | 95% of issues | 99% of issues |
| **Dependencies** | None | Ollama service |
| **Cost** | Free | Free (local) |

## Troubleshooting

### Ollama Not Responding

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Restart Ollama
ollama serve
```

### Model Not Found

```bash
# List available models
ollama list

# Pull required model
ollama pull llama3.2:1b

# Verify
curl http://localhost:11434/api/tags
```

### Tests Timing Out

**Solutions:**
1. Use smaller model: `llama3.2:1b` instead of larger models
2. Increase timeout in `src/mcp_tef/config/settings.py`:
   ```python
   default_model: ModelSettings = ModelSettings(
       name="llama3.2:1b",
       provider="ollama",
       base_url="http://localhost:11434/v1",
       timeout=60,  # Increase from 30
       max_retries=3,
   )
   ```
   Or via environment variable: `DEFAULT_MODEL__TIMEOUT=60`
3. Reduce test data size
4. Check system resources (CPU/memory)

### Non-Deterministic Test Failures

**This is normal with real LLMs!** They have natural variance in outputs.

**Handling strategies:**
1. Use `temperature=0` for more consistent output
2. Make assertions flexible (check structure, not exact content)
3. Add retry logic for flaky tests:
   ```python
   @pytest.mark.flaky(reruns=2)
   async def test_with_llm(...):
   ```

### Mock vs Ollama Behavior Differs

**Expected!** Mocks are simplified. If tests fail with Ollama but pass with mocks:

1. **Check LLM response format** - May need more flexible parsing
2. **Improve prompts** - For more consistent structured output
3. **Update assertions** - To handle valid LLM variations
4. **Review mock behavior** - Ensure mocks reflect realistic responses

## Examples

### Running Specific Tests

```bash
# Single test file
pytest tests/integration/test_similarity_analysis.py

# Single test function
pytest tests/integration/test_similarity_analysis.py::test_analyze_similarity_with_server_list

# Tests by marker
pytest -m integration
pytest -m "ollama and integration"
pytest -m "not slow"

# With Ollama
USE_OLLAMA=true pytest -m ollama

# Verbose output
pytest -vv -s
```

### Debugging

```bash
# Show print statements
pytest -s

# Drop into debugger on failure
pytest --pdb

# Show local variables on failure
pytest --showlocals

# Only show failing tests
pytest --tb=short
```

## Best Practices

### ✅ DO

- Use mock mode for TDD and rapid iteration
- Use Ollama before merging LLM feature PRs
- Keep models lightweight in CI (llama3.2:1b)
- Make test assertions flexible for LLM variance
- Document expected LLM behavior in tests
- Run both modes locally before important PRs

### ❌ DON'T

- Don't rely only on mocks for LLM features
- Don't use Ollama for every local test run
- Don't expect identical LLM outputs on each run
- Don't use large models (>8B) in CI
- Don't ignore differences between mock and Ollama results

## Related Resources

- [Ollama Documentation](https://github.com/ollama/ollama)
- [Ollama API Reference](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [Available Models](https://ollama.ai/library)
- [Pytest Documentation](https://docs.pytest.org/)

## Summary

**Default behavior:** Tests use mocked LLM responses for speed and determinism.

**Optional Ollama:** Set `USE_OLLAMA=true` for realistic LLM testing when needed.

**When to use Ollama:**
- Before merging LLM-related PRs
- For confusion testing validation
- For differentiation recommendation features
- Pre-release quality gates

**Current test status:**
- ✅ 105 total tests collected
- ✅ Most tests use mocked LLMs (no API keys required)
- ✅ Tests marked with `no_mock_agent` require real API keys
- ✅ All tests compatible with Ollama mode
- ✅ CI runs mock mode by default (~37-68 seconds)
- ✅ Ollama workflow available for thorough testing (~5-8 minutes)

