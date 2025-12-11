#!/usr/bin/env python3

"""
MCP TEF API Demo Script (Python)

This script demonstrates all API endpoints with detailed explanations.

Usage: python scripts/demo.py

Prerequisites:
- API server running on https://localhost:8000 (or set BASE_URL env var)
- Python 3.8+ installed
- At least 2 running MCP servers for similarity analysis examples (optional)
"""

import json
import os
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Configuration
BASE_URL = os.environ.get("BASE_URL", "https://localhost:8000")
AUTO_MODE = os.environ.get("AUTO_MODE") == "1"

# Create SSL context that doesn't verify certificates (for self-signed certs)
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE


# Colors for output
class Colors:
    BOLD = "\033[1m"
    GREEN = "\033[0;32m"
    BLUE = "\033[0;34m"
    CYAN = "\033[0;36m"
    YELLOW = "\033[1;33m"
    MAGENTA = "\033[0;35m"
    RED = "\033[0;31m"
    NC = "\033[0m"  # No Color


def make_request(path: str, method: str = "GET", data: dict | None = None) -> dict | str:
    """Make an HTTP request to the API."""
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}

    if data:
        data_bytes = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    else:
        req = urllib.request.Request(url, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, context=ssl_context) as response:
            response_data = response.read().decode("utf-8")
            try:
                return json.loads(response_data)
            except json.JSONDecodeError:
                return response_data
    except urllib.error.HTTPError as e:
        error_data = e.read().decode("utf-8")
        print(f"{Colors.RED}HTTP Error {e.code}:{Colors.NC} {error_data}")
        raise
    except urllib.error.URLError as e:
        print(f"{Colors.RED}URL Error:{Colors.NC} {e.reason}")
        raise


def print_header(text: str) -> None:
    """Print a header with formatting."""
    print()
    print(f"{Colors.BOLD}{Colors.CYAN}{'━' * 80}{Colors.NC}")
    print(f"{Colors.BOLD}{Colors.CYAN}{text}{Colors.NC}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'━' * 80}{Colors.NC}")


def print_section(text: str) -> None:
    """Print a section header."""
    print()
    print(f"{Colors.BOLD}{Colors.BLUE}▸ {text}{Colors.NC}")
    print(f"{Colors.BLUE}{'─' * 80}{Colors.NC}")


def print_endpoint(method: str, path: str) -> None:
    """Print endpoint information."""
    print()
    print(
        f"{Colors.BOLD}{Colors.GREEN}Endpoint:{Colors.NC} {Colors.YELLOW}{method} {path}{Colors.NC}"
    )


def print_explanation(text: str) -> None:
    """Print explanation text."""
    print(f"{Colors.MAGENTA}Purpose:{Colors.NC} {text}")


def print_response(data: dict | str) -> None:
    """Print response data."""
    print(f"{Colors.MAGENTA}Response:{Colors.NC}")
    if isinstance(data, dict):
        print(json.dumps(data, indent=2))
    else:
        print(data)


def pause() -> None:
    """Pause for user input or auto-continue."""
    if not AUTO_MODE:
        print(f"\n{Colors.CYAN}Press Enter to continue...{Colors.NC}")
        input()
    else:
        time.sleep(0.5)


def run_demo() -> None:
    """Run the main demo."""
    print(f"{Colors.BOLD}{Colors.CYAN}")
    print("╔═══════════════════════════════════════════════════════════════════════════╗")
    print("║                                                                           ║")
    print("║                    MCP TEF API COMPREHENSIVE DEMO                        ║")
    print("║                                                                           ║")
    print("║                   Model Context Protocol - TEF System                    ║")
    print("║              (MCP Analysis, Learning, and Testing Platform)               ║")
    print("║                                                                           ║")
    print("╚═══════════════════════════════════════════════════════════════════════════╝")
    print(Colors.NC)
    print()
    print(f"Base URL: {Colors.YELLOW}{BASE_URL}{Colors.NC}")
    print()

    try:
        # ============================================================================
        # SECTION 1: BASIC ENDPOINTS
        # ============================================================================

        print_header("SECTION 1: BASIC ENDPOINTS")

        # Root Endpoint
        print_section("Root Endpoint")
        print_endpoint("GET", "/")
        print_explanation(
            "Returns basic information about the API service including name, version, and status."
        )
        root_response = make_request("/")
        print_response(root_response)
        pause()

        # Health Check
        print_section("Health Check")
        print_endpoint("GET", "/health")
        print_explanation(
            "Simple health check endpoint to verify the API is running and responsive."
        )
        health_response = make_request("/health")
        print_response(health_response)
        pause()

        # ============================================================================
        # SECTION 2: MCP SERVER TOOLS
        # ============================================================================

        print_header("SECTION 2: MCP SERVER TOOLS")

        print(
            f"{Colors.YELLOW}Note: MCP server persistence has been removed in favor of URL-based operations.{Colors.NC}"
        )
        print(
            f"{Colors.YELLOW}The API loads tools directly from server URLs without requiring registration.{Colors.NC}"
        )
        print()
        pause()

        # Get MCP server URLs from thv (ToolHive), environment, or use defaults
        def get_mcp_servers_from_thv():
            """Get running MCP servers from ToolHive (thv list)."""
            try:
                result = subprocess.run(
                    ["thv", "list"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    # Parse the output to extract URLs
                    urls = []
                    for line in result.stdout.split("\n"):
                        if "http" in line and "://" in line:
                            # Extract URL from the line
                            parts = line.split()
                            for part in parts:
                                if part.startswith(("http://", "https://")):
                                    urls.append(part)
                                    break
                    return urls
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
            return []

        # Try to get servers from thv, then environment, then defaults
        thv_servers = get_mcp_servers_from_thv()
        if len(thv_servers) >= 2:
            SERVER_URL_1 = thv_servers[0]
            SERVER_URL_2 = thv_servers[1]
            print(
                f"{Colors.GREEN}✓ Found {len(thv_servers)} MCP servers from ToolHive (thv list){Colors.NC}"
            )
        else:
            SERVER_URL_1 = os.environ.get("MCP_SERVER_1", "http://localhost:3000")
            SERVER_URL_2 = os.environ.get("MCP_SERVER_2", "http://localhost:3001")
            print(
                f"{Colors.YELLOW}Note: No servers found via 'thv list'. Using defaults.{Colors.NC}"
            )
            print(f"{Colors.YELLOW}To use your servers, either:{Colors.NC}")
            print(f"{Colors.YELLOW}  1. Run MCP servers with ToolHive (thv), or{Colors.NC}")
            print(
                f"{Colors.YELLOW}  2. Set MCP_SERVER_1 and MCP_SERVER_2 environment variables{Colors.NC}"
            )

        print(f"\n{Colors.CYAN}Using MCP Servers:{Colors.NC}")
        print(f"  Server 1: {SERVER_URL_1}")
        print(f"  Server 2: {SERVER_URL_2}")
        if len(thv_servers) > 2:
            print(f"  ({len(thv_servers) - 2} more servers available)")
        print()

        DEMO_SERVER_URL = SERVER_URL_1

        # Get Server Tools
        print_section("Get Tools from a Specific Server URL")
        print_endpoint("GET", "/mcp-servers/tools?server_url={url}")
        print_explanation(
            "Lists all tools provided by an MCP server. Loads tools directly from the server URL."
        )
        print(
            f"\n{Colors.YELLOW}Example: GET /mcp-servers/tools?server_url={DEMO_SERVER_URL}{Colors.NC}"
        )
        print(f"{Colors.YELLOW}Note: Requires a running MCP server. Skipped in demo.{Colors.NC}")
        pause()

        # Tool Quality Metrics (COMMENTED OUT - USES LLM)
        print_section("Get Tool Quality Metrics (LLM-based - COMMENTED OUT)")
        print_endpoint("GET", "/mcp-servers/tools/quality")
        print_explanation(
            "Analyzes tool quality using LLM. SLOW - typically commented out in demos."
        )
        print(
            f"{Colors.YELLOW}This endpoint uses LLM analysis and is slow. Skipped in demo.{Colors.NC}"
        )
        pause()

        # ============================================================================
        # SECTION 3: SIMILARITY ANALYSIS
        # ============================================================================

        print_header("SECTION 3: SIMILARITY ANALYSIS")

        print(
            f"{Colors.YELLOW}Note: Similarity analysis works directly with server URLs.{Colors.NC}"
        )
        print(
            f"{Colors.YELLOW}You provide MCP server URLs via the mcp_server_urls parameter.{Colors.NC}"
        )
        print()
        pause()

        # Basic Similarity Analysis
        print_section("Basic Similarity Analysis (Fast - uses embeddings)")
        print_endpoint("POST", "/similarity/analyze")
        print_explanation(
            "Analyzes similarity between tools to find potential overlaps. Uses embeddings (fast)."
        )
        print(f"\n{Colors.YELLOW}Request Body:{Colors.NC}")
        similarity_request = {
            "mcp_server_urls": [SERVER_URL_1, SERVER_URL_2],
            "similarity_threshold": 0.7,
            "compute_full_similarity": False,
        }
        print(json.dumps(similarity_request, indent=2))
        print(f"\n{Colors.YELLOW}Attempting similarity analysis...{Colors.NC}")
        try:
            similarity_response = make_request(
                "/similarity/analyze", method="POST", data=similarity_request
            )
            print_response(similarity_response)
        except Exception as e:
            print(
                f"{Colors.YELLOW}Note: Requires running MCP servers at the URLs above.{Colors.NC}"
            )
            print(f"{Colors.YELLOW}Error: {e}{Colors.NC}")
        pause()

        # Similarity Analysis with Recommendations (COMMENTED OUT - USES LLM)
        print_section("Similarity Analysis with LLM Recommendations (COMMENTED OUT)")
        print_endpoint("POST", "/similarity/analyze")
        print_explanation("Includes AI-generated recommendations. SLOW - uses LLM.")
        print(f"{Colors.YELLOW}Example with include_recommendations: true{Colors.NC}")
        print(
            json.dumps(
                {
                    "mcp_server_urls": [SERVER_URL_1, SERVER_URL_2],
                    "similarity_threshold": 0.7,
                    "include_recommendations": True,
                },
                indent=2,
            )
        )
        print(
            f"\n{Colors.YELLOW}This uses LLM analysis and is slow. Typically commented out.{Colors.NC}"
        )
        pause()

        # Similarity Matrix
        print_section("Generate Similarity Matrix (Fast - uses embeddings)")
        print_endpoint("POST", "/similarity/matrix")
        print_explanation(
            "Generates a full N×N similarity matrix showing relationships. Uses embeddings (fast)."
        )
        print(f"\n{Colors.YELLOW}Request Body:{Colors.NC}")
        matrix_request = {
            "mcp_server_urls": [SERVER_URL_1, SERVER_URL_2],
            "similarity_threshold": 0.7,
        }
        print(json.dumps(matrix_request, indent=2))
        print(f"\n{Colors.YELLOW}Attempting matrix generation...{Colors.NC}")
        try:
            matrix_response = make_request("/similarity/matrix", method="POST", data=matrix_request)
            print_response(matrix_response)
        except Exception as e:
            print(
                f"{Colors.YELLOW}Note: Requires running MCP servers at the URLs above.{Colors.NC}"
            )
            print(f"{Colors.YELLOW}Error: {e}{Colors.NC}")
        pause()

        # Overlap Matrix
        print_section("Generate Overlap Matrix with Dimensions (Fast - uses embeddings)")
        print_endpoint("POST", "/similarity/overlap-matrix")
        print_explanation(
            "Advanced matrix with dimensional analysis of overlaps. Uses embeddings (fast)."
        )
        print(f"\n{Colors.YELLOW}Request Body:{Colors.NC}")
        overlap_request = {
            "mcp_server_urls": [SERVER_URL_1, SERVER_URL_2],
            "similarity_threshold": 0.7,
        }
        print(json.dumps(overlap_request, indent=2))
        print(f"\n{Colors.YELLOW}Attempting overlap matrix generation...{Colors.NC}")
        try:
            overlap_response = make_request(
                "/similarity/overlap-matrix", method="POST", data=overlap_request
            )
            print_response(overlap_response)
        except Exception as e:
            print(
                f"{Colors.YELLOW}Note: Requires running MCP servers at the URLs above.{Colors.NC}"
            )
            print(f"{Colors.YELLOW}Error: {e}{Colors.NC}")
        pause()

        # ============================================================================
        # SECTION 4: TEST CASE MANAGEMENT (LLM-BASED - COMMENTED OUT)
        # ============================================================================

        print_header("SECTION 4: TEST CASE MANAGEMENT (LLM-based)")

        print_section("Create a Test Case")
        print_endpoint("POST", "/test-cases")
        print_explanation("Creates a test case to evaluate tool selection using LLM.")
        print(f"\n{Colors.YELLOW}Request Body Example:{Colors.NC}")
        print(
            json.dumps(
                {
                    "name": "Test tool selection",
                    "query": "Example query for demonstration",
                    "expected_mcp_server_name": "example-server",
                    "expected_tool_name": "example_tool",
                    "expected_parameters": {"param": "value"},
                    "available_mcp_servers": [DEMO_SERVER_URL],
                },
                indent=2,
            )
        )
        print(
            f"\n{Colors.YELLOW}Note: Test case execution requires LLM. Skipped in demo.{Colors.NC}"
        )
        pause()

        # ============================================================================
        # SECTION 5: METRICS
        # ============================================================================

        print_header("SECTION 5: METRICS & ANALYTICS")

        # Get Metrics Summary
        print_section("Get Metrics Summary")
        print_endpoint("GET", "/metrics/summary")
        print_explanation("Retrieves aggregated metrics across test runs.")
        metrics_response = make_request("/metrics/summary")
        print_response(metrics_response)
        pause()

        # ============================================================================
        # FINALE
        # ============================================================================

        print_header("DEMO COMPLETE!")

        print()
        print(f"{Colors.GREEN}✓ All API endpoints have been demonstrated{Colors.NC}")
        print()
        print(f"{Colors.BOLD}{Colors.CYAN}Quick Reference Summary:{Colors.NC}")
        print()
        print(f"{Colors.BOLD}Basic Endpoints:{Colors.NC}")
        print("  GET  /              - API info")
        print("  GET  /health        - Health check")
        print()
        print(f"{Colors.BOLD}MCP Servers & Tools:{Colors.NC}")
        print("  GET    /mcp-servers/tools?server_url={url}                - Load tools from URL")
        print(
            "  GET    /mcp-servers/tools/quality?server_urls={urls}...   - Tool quality (LLM-based, SLOW)"
        )
        print()
        print(f"{Colors.BOLD}Similarity Analysis:{Colors.NC}")
        print("  POST /similarity/analyze        - Analyze tool similarities")
        print("  POST /similarity/matrix         - Generate similarity matrix")
        print("  POST /similarity/overlap-matrix - Generate overlap matrix")
        print()
        print(f"{Colors.BOLD}Test Cases (LLM-based):{Colors.NC}")
        print("  POST   /test-cases              - Create test case")
        print("  POST   /test-cases/{id}/run     - Execute test run (SLOW)")
        print()
        print(f"{Colors.BOLD}Metrics:{Colors.NC}")
        print("  GET  /metrics/summary           - Get metrics summary")
        print()
        print(f"{Colors.BOLD}Documentation:{Colors.NC}")
        print(f"  Swagger UI: {Colors.YELLOW}{BASE_URL}/docs{Colors.NC}")
        print(f"  ReDoc:      {Colors.YELLOW}{BASE_URL}/redoc{Colors.NC}")
        print()
        print(f"{Colors.GREEN}Happy building! 🚀{Colors.NC}")
        print()

    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Demo interrupted by user.{Colors.NC}")
        sys.exit(0)
    except Exception as error:
        print(f"{Colors.RED}Error:{Colors.NC} {error}")
        sys.exit(1)


if __name__ == "__main__":
    run_demo()
