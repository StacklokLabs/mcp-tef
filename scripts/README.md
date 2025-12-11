# MCP Malt Scripts

Utility scripts for working with the MCP Malt API.

## analyze_similarity.sh

Run similarity analysis between tools from multiple MCP servers using their URLs directly.

### Prerequisites

Before using this script, ensure:

1. **MCP servers are running** and accessible at their URLs
2. **ToolHive (optional)** - Install `thv` for auto-detection of running servers

**Note:** MCP server registration has been removed from the API. The script now loads tools directly from server URLs without requiring pre-registration in the database.

### Usage

```bash
# Basic usage - compare two server URLs
./scripts/analyze_similarity.sh http://localhost:3000 http://localhost:3001

# Auto-detect running servers from ToolHive
./scripts/analyze_similarity.sh --auto

# Get a summary view instead of full JSON
./scripts/analyze_similarity.sh --summary http://localhost:3000 http://localhost:3001

# Set a higher threshold to find very similar tools (85%+)
./scripts/analyze_similarity.sh --threshold 0.85 --summary http://localhost:3000 http://localhost:3001

# Include AI-powered differentiation recommendations
./scripts/analyze_similarity.sh --recommendations http://localhost:3000 http://localhost:3001

# Compare multiple servers
./scripts/analyze_similarity.sh --summary http://localhost:3000 http://localhost:3001 http://localhost:3002

# Use with custom API URL
./scripts/analyze_similarity.sh --url https://remote-host:8000 http://localhost:3000 http://localhost:3001
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `-t, --threshold FLOAT` | Similarity threshold (0.0-1.0) | 0.9 |
| `-r, --recommendations` | Include AI recommendations | false |
| `-s, --summary` | Show summary instead of JSON | false |
| `-u, --url URL` | API base URL | https://localhost:8000 |
| `-a, --auto` | Auto-detect servers using `thv ls` | false |
| `-h, --help` | Show help message | - |

### Environment Variables

- `MCP_TEF_API_URL` - Override default API URL

### Examples

#### Auto-detect and analyze all running servers

```bash
$ ./scripts/analyze_similarity.sh --auto --summary

Auto-detecting servers from 'thv ls'...
Found 3 running servers:
  http://localhost:3000
  http://localhost:3001
  http://localhost:3002

=== Similarity Analysis Summary ===

Total tools analyzed: 57
Total tool pairs: 1596
Pairs above threshold: 14

Top 10 Most Similar Pairs:
  github:search_issues ↔ github:search_pull_requests: 0.91
  github:create_pull_request ↔ github:update_pull_request: 0.9
  github:add_sub_issue ↔ github:remove_sub_issue: 0.9
  github:create_issue ↔ github:update_issue: 0.9
  ...

Similarity Distribution:
  0.9-1.0: 2 pairs
  0.8-0.9: 12 pairs

Full results saved to: similarity_results.json
```

#### Compare specific server URLs

```bash
$ ./scripts/analyze_similarity.sh --summary --threshold 0.85 http://localhost:3000 http://localhost:3001
```

#### Get JSON output for programmatic use

```bash
$ ./scripts/analyze_similarity.sh --threshold 0.90 http://localhost:3000 http://localhost:3001 > results.json
$ jq '.flagged_pairs | length' results.json
2
```

#### Generate recommendations for improvements

```bash
$ ./scripts/analyze_similarity.sh --recommendations --threshold 0.90 http://localhost:3000 http://localhost:3001
```

The recommendations will include:
- Analysis of why tools are similar
- Suggestions for differentiating tool descriptions
- Specific wording improvements

### Output Files

When using `--summary`, the script saves full JSON results to `similarity_results.json` in the current directory.

### Troubleshooting

**"At least 2 server URLs required"**

You need to provide at least two server URLs to compare. Either:
- Use `--auto` to auto-detect servers from ToolHive
- Specify server URLs manually: `./scripts/analyze_similarity.sh http://localhost:3000 http://localhost:3001`

**"No running servers found from 'thv ls'"**

When using `--auto`, the script found no running MCP servers. Start your MCP servers first, or specify URLs manually.

**Network connection errors**

Check that:
1. The MCP Malt API is running: `curl -k https://localhost:8000/health`
2. Your MCP servers are accessible at their URLs

---

## Other Scripts

### demo.sh

Comprehensive demonstration script (Bash) showing all API endpoints and functionality.

**Usage:**
```bash
# Run full interactive demo
./scripts/demo.sh

# Run in non-interactive mode (no pauses)
AUTO_MODE=1 ./scripts/demo.sh

# Use custom API URL
BASE_URL=https://remote-host:8000 ./scripts/demo.sh

# Use your own MCP servers for similarity analysis
export MCP_SERVER_1="http://localhost:3000"
export MCP_SERVER_2="http://localhost:3001"
./scripts/demo.sh
```

**Features:**
- Health check and basic endpoints
- MCP server tools and quality evaluation (URL-based)
- Similarity analysis with multiple options
- Test case management and evaluation
- Metrics and analytics
- Advanced usage patterns for UI developers

### demo.js

Comprehensive demonstration script (JavaScript/Node.js) showing all API endpoints and functionality. JavaScript version of `demo.sh`.

**Usage:**
```bash
# Run full interactive demo
node scripts/demo.js

# Run in non-interactive mode (no pauses)
AUTO_MODE=1 node scripts/demo.js

# Use custom API URL
BASE_URL=https://remote-host:8000 node scripts/demo.js

# Use your own MCP servers for similarity analysis
export MCP_SERVER_1="http://localhost:3000"
export MCP_SERVER_2="http://localhost:3001"
node scripts/demo.js
```

**Features:**
- Health check and basic endpoints
- MCP server tools demonstration
- Similarity analysis endpoints
- Test case management (LLM-based features commented out)
- Metrics and analytics
- Clean, readable JavaScript/Node.js implementation

**Note:** LLM-based operations (tool quality analysis, recommendations, test runs) are commented out in the demo as they are slow. Uncomment to test them.

### demo.py

Comprehensive demonstration script (Python) showing all API endpoints and functionality. Python version of `demo.sh`.

**Usage:**
```bash
# Run full interactive demo
python scripts/demo.py

# Run in non-interactive mode (no pauses)
AUTO_MODE=1 python scripts/demo.py

# Use custom API URL
BASE_URL=https://remote-host:8000 python scripts/demo.py

# Use your own MCP servers for similarity analysis
export MCP_SERVER_1="http://localhost:3000"
export MCP_SERVER_2="http://localhost:3001"
python scripts/demo.py
```

**Features:**
- Health check and basic endpoints
- MCP server tools demonstration
- Similarity analysis endpoints
- Test case management (LLM-based features commented out)
- Metrics and analytics
- Clean, readable Python implementation

**Note:** LLM-based operations (tool quality analysis, recommendations, test runs) are commented out in the demo as they are slow. Uncomment to test them.

### register_and_analyze.sh

Auto-detect running MCP servers from ToolHive and run similarity analysis.

**Usage:**
```bash
# Auto-detect and analyze all running servers
./scripts/register_and_analyze.sh

# Use custom API URL
API_BASE=https://remote-host:8000 ./scripts/register_and_analyze.sh
```

**Note:** This script has been renamed from its original purpose. It no longer registers servers (that feature was removed), but instead focuses on auto-detection and analysis of running servers.

### test_api.sh

API testing script for development. Tests all similarity analysis endpoints with various configurations using test data files.

**Usage:**
```bash
./scripts/test_api.sh
```

Tests 16 different scenarios including:
- Basic similarity analysis (5, 10, 25 tools)
- Similarity matrices
- Overlap matrices
- Recommendations
- Custom embedding models
- Different analysis methods

### split_test_data.py

Python utility script for splitting test data into smaller samples for testing.

