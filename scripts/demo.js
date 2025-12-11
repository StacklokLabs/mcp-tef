#!/usr/bin/env node

/**
 * MCP TEF API Demo Script (JavaScript/Node.js)
 * 
 * This script demonstrates all API endpoints with detailed explanations.
 * 
 * Usage: node scripts/demo.js
 * 
 * Prerequisites:
 * - API server running on https://localhost:8000 (or set BASE_URL env var)
 * - Node.js 18+ installed
 * - At least 2 running MCP servers for similarity analysis examples (optional)
 */

const https = require('https');
const http = require('http');

// Configuration
const BASE_URL = process.env.BASE_URL || 'https://localhost:8000';
const AUTO_MODE = process.env.AUTO_MODE === '1';

// Parse URL to get protocol, host, and port
const url = new URL(BASE_URL);
const client = url.protocol === 'https:' ? https : http;

// Colors for output
const colors = {
  BOLD: '\x1b[1m',
  GREEN: '\x1b[0;32m',
  BLUE: '\x1b[0;34m',
  CYAN: '\x1b[0;36m',
  YELLOW: '\x1b[1;33m',
  MAGENTA: '\x1b[0;35m',
  RED: '\x1b[0;31m',
  NC: '\x1b[0m'
};

// Helper function to make HTTP requests
function makeRequest(path, options = {}) {
  return new Promise((resolve, reject) => {
    const requestOptions = {
      hostname: url.hostname,
      port: url.port || (url.protocol === 'https:' ? 443 : 80),
      path: path,
      method: options.method || 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      },
      rejectUnauthorized: false // Accept self-signed certificates
    };

    const req = client.request(requestOptions, (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => {
        try {
          resolve(JSON.parse(data));
        } catch (e) {
          resolve(data);
        }
      });
    });

    req.on('error', reject);

    if (options.body) {
      req.write(JSON.stringify(options.body));
    }

    req.end();
  });
}

// Formatting helpers
function printHeader(text) {
  console.log('');
  console.log(`${colors.BOLD}${colors.CYAN}${'━'.repeat(80)}${colors.NC}`);
  console.log(`${colors.BOLD}${colors.CYAN}${text}${colors.NC}`);
  console.log(`${colors.BOLD}${colors.CYAN}${'━'.repeat(80)}${colors.NC}`);
}

function printSection(text) {
  console.log('');
  console.log(`${colors.BOLD}${colors.BLUE}▸ ${text}${colors.NC}`);
  console.log(`${colors.BLUE}${'─'.repeat(80)}${colors.NC}`);
}

function printEndpoint(method, path) {
  console.log('');
  console.log(`${colors.BOLD}${colors.GREEN}Endpoint:${colors.NC} ${colors.YELLOW}${method} ${path}${colors.NC}`);
}

function printExplanation(text) {
  console.log(`${colors.MAGENTA}Purpose:${colors.NC} ${text}`);
}

function printResponse(data) {
  console.log(`${colors.MAGENTA}Response:${colors.NC}`);
  console.log(JSON.stringify(data, null, 2));
}

function pause() {
  if (!AUTO_MODE) {
    return new Promise((resolve) => {
      console.log(`\n${colors.CYAN}Press Enter to continue...${colors.NC}`);
      process.stdin.once('data', () => resolve());
    });
  } else {
    return new Promise((resolve) => setTimeout(resolve, 500));
  }
}

// Main demo function
async function runDemo() {
  console.log(`${colors.BOLD}${colors.CYAN}`);
  console.log('╔═══════════════════════════════════════════════════════════════════════════╗');
  console.log('║                                                                           ║');
  console.log('║                    MCP TEF API COMPREHENSIVE DEMO                        ║');
  console.log('║                                                                           ║');
  console.log('║                   Model Context Protocol - TEF System                    ║');
  console.log('║              (MCP Analysis, Learning, and Testing Platform)               ║');
  console.log('║                                                                           ║');
  console.log('╚═══════════════════════════════════════════════════════════════════════════╝');
  console.log(colors.NC);
  console.log('');
  console.log(`Base URL: ${colors.YELLOW}${BASE_URL}${colors.NC}`);
  console.log('');

  try {
    // ============================================================================
    // SECTION 1: BASIC ENDPOINTS
    // ============================================================================

    printHeader('SECTION 1: BASIC ENDPOINTS');

    // Root Endpoint
    printSection('Root Endpoint');
    printEndpoint('GET', '/');
    printExplanation('Returns basic information about the API service including name, version, and status.');
    const rootResponse = await makeRequest('/');
    printResponse(rootResponse);
    await pause();

    // Health Check
    printSection('Health Check');
    printEndpoint('GET', '/health');
    printExplanation('Simple health check endpoint to verify the API is running and responsive.');
    const healthResponse = await makeRequest('/health');
    printResponse(healthResponse);
    await pause();

    // ============================================================================
    // SECTION 2: MCP SERVER TOOLS
    // ============================================================================

    printHeader('SECTION 2: MCP SERVER TOOLS');

    console.log(`${colors.YELLOW}Note: MCP server persistence has been removed in favor of URL-based operations.${colors.NC}`);
    console.log(`${colors.YELLOW}The API loads tools directly from server URLs without requiring registration.${colors.NC}`);
    console.log('');
    await pause();

    // Get MCP server URLs from thv (ToolHive), environment, or use defaults
    function getMCPServersFromThv() {
      /**Get running MCP servers from ToolHive (thv list).*/
      try {
        const result = require('child_process').execSync('thv list', {
          encoding: 'utf8',
          timeout: 5000,
          stdio: ['pipe', 'pipe', 'ignore']
        });
        
        // Parse the output to extract URLs
        const urls = [];
        const lines = result.split('\n');
        for (const line of lines) {
          if (line.includes('http') && line.includes('://')) {
            // Extract URL from the line
            const parts = line.split(/\s+/);
            for (const part of parts) {
              if (part.startsWith('http://') || part.startsWith('https://')) {
                urls.push(part);
                break;
              }
            }
          }
        }
        return urls;
      } catch (error) {
        // thv not found or command failed
        return [];
      }
    }

    // Try to get servers from thv, then environment, then defaults
    const thvServers = getMCPServersFromThv();
    let SERVER_URL_1, SERVER_URL_2;
    
    if (thvServers.length >= 2) {
      SERVER_URL_1 = thvServers[0];
      SERVER_URL_2 = thvServers[1];
      console.log(`${colors.GREEN}✓ Found ${thvServers.length} MCP servers from ToolHive (thv list)${colors.NC}`);
    } else {
      SERVER_URL_1 = process.env.MCP_SERVER_1 || 'http://localhost:3000';
      SERVER_URL_2 = process.env.MCP_SERVER_2 || 'http://localhost:3001';
      console.log(`${colors.YELLOW}Note: No servers found via 'thv list'. Using defaults.${colors.NC}`);
      console.log(`${colors.YELLOW}To use your servers, either:${colors.NC}`);
      console.log(`${colors.YELLOW}  1. Run MCP servers with ToolHive (thv), or${colors.NC}`);
      console.log(`${colors.YELLOW}  2. Set MCP_SERVER_1 and MCP_SERVER_2 environment variables${colors.NC}`);
    }

    console.log(`\n${colors.CYAN}Using MCP Servers:${colors.NC}`);
    console.log(`  Server 1: ${SERVER_URL_1}`);
    console.log(`  Server 2: ${SERVER_URL_2}`);
    if (thvServers.length > 2) {
      console.log(`  (${thvServers.length - 2} more servers available)`);
    }
    console.log();

    const DEMO_SERVER_URL = SERVER_URL_1;

    // Get Server Tools
    printSection('Get Tools from a Specific Server URL');
    printEndpoint('GET', '/mcp-servers/tools?server_url={url}');
    printExplanation('Lists all tools provided by an MCP server. Loads tools directly from the server URL.');
    console.log(`\n${colors.YELLOW}Example: GET /mcp-servers/tools?server_url=${DEMO_SERVER_URL}${colors.NC}`);
    console.log(`${colors.YELLOW}Note: Requires a running MCP server. Skipped in demo.${colors.NC}`);
    await pause();

    // Tool Quality Metrics (COMMENTED OUT - USES LLM)
    printSection('Get Tool Quality Metrics (LLM-based - COMMENTED OUT)');
    printEndpoint('GET', '/mcp-servers/tools/quality');
    printExplanation('Analyzes tool quality using LLM. SLOW - typically commented out in demos.');
    console.log(`${colors.YELLOW}This endpoint uses LLM analysis and is slow. Skipped in demo.${colors.NC}`);
    await pause();

    // ============================================================================
    // SECTION 3: SIMILARITY ANALYSIS
    // ============================================================================

    printHeader('SECTION 3: SIMILARITY ANALYSIS');

    console.log(`${colors.YELLOW}Note: Similarity analysis works directly with server URLs.${colors.NC}`);
    console.log(`${colors.YELLOW}You provide MCP server URLs via the mcp_server_urls parameter.${colors.NC}`);
    console.log('');
    await pause();

    // Basic Similarity Analysis
    printSection('Basic Similarity Analysis (Fast - uses embeddings)');
    printEndpoint('POST', '/similarity/analyze');
    printExplanation('Analyzes similarity between tools to find potential overlaps. Uses embeddings (fast).');
    console.log(`\n${colors.YELLOW}Request Body:${colors.NC}`);
    const similarityRequest = {
      mcp_server_urls: [SERVER_URL_1, SERVER_URL_2],
      similarity_threshold: 0.7,
      compute_full_similarity: false
    };
    console.log(JSON.stringify(similarityRequest, null, 2));
    console.log(`\n${colors.YELLOW}Attempting similarity analysis...${colors.NC}`);
    try {
      const similarityResponse = await makeRequest('/similarity/analyze', {
        method: 'POST',
        body: similarityRequest
      });
      printResponse(similarityResponse);
    } catch (error) {
      console.log(`${colors.YELLOW}Note: Requires running MCP servers at the URLs above.${colors.NC}`);
      console.log(`${colors.YELLOW}Error: ${error.message}${colors.NC}`);
    }
    await pause();

    // Similarity Analysis with Recommendations (COMMENTED OUT - USES LLM)
    printSection('Similarity Analysis with LLM Recommendations (COMMENTED OUT)');
    printEndpoint('POST', '/similarity/analyze');
    printExplanation('Includes AI-generated recommendations. SLOW - uses LLM.');
    console.log(`${colors.YELLOW}Example with include_recommendations: true${colors.NC}`);
    console.log(JSON.stringify({
      mcp_server_urls: [SERVER_URL_1, SERVER_URL_2],
      similarity_threshold: 0.7,
      include_recommendations: true
    }, null, 2));
    console.log(`\n${colors.YELLOW}This uses LLM analysis and is slow. Typically commented out.${colors.NC}`);
    await pause();

    // Similarity Matrix
    printSection('Generate Similarity Matrix (Fast - uses embeddings)');
    printEndpoint('POST', '/similarity/matrix');
    printExplanation('Generates a full N×N similarity matrix showing relationships. Uses embeddings (fast).');
    console.log(`\n${colors.YELLOW}Request Body:${colors.NC}`);
    const matrixRequest = {
      mcp_server_urls: [SERVER_URL_1, SERVER_URL_2],
      similarity_threshold: 0.7
    };
    console.log(JSON.stringify(matrixRequest, null, 2));
    console.log(`\n${colors.YELLOW}Attempting matrix generation...${colors.NC}`);
    try {
      const matrixResponse = await makeRequest('/similarity/matrix', {
        method: 'POST',
        body: matrixRequest
      });
      printResponse(matrixResponse);
    } catch (error) {
      console.log(`${colors.YELLOW}Note: Requires running MCP servers at the URLs above.${colors.NC}`);
      console.log(`${colors.YELLOW}Error: ${error.message}${colors.NC}`);
    }
    await pause();

    // Overlap Matrix
    printSection('Generate Overlap Matrix with Dimensions (Fast - uses embeddings)');
    printEndpoint('POST', '/similarity/overlap-matrix');
    printExplanation('Advanced matrix with dimensional analysis of overlaps. Uses embeddings (fast).');
    console.log(`\n${colors.YELLOW}Request Body:${colors.NC}`);
    const overlapRequest = {
      mcp_server_urls: [SERVER_URL_1, SERVER_URL_2],
      similarity_threshold: 0.7
    };
    console.log(JSON.stringify(overlapRequest, null, 2));
    console.log(`\n${colors.YELLOW}Attempting overlap matrix generation...${colors.NC}`);
    try {
      const overlapResponse = await makeRequest('/similarity/overlap-matrix', {
        method: 'POST',
        body: overlapRequest
      });
      printResponse(overlapResponse);
    } catch (error) {
      console.log(`${colors.YELLOW}Note: Requires running MCP servers at the URLs above.${colors.NC}`);
      console.log(`${colors.YELLOW}Error: ${error.message}${colors.NC}`);
    }
    await pause();

    // ============================================================================
    // SECTION 4: TEST CASE MANAGEMENT (LLM-BASED - COMMENTED OUT)
    // ============================================================================

    printHeader('SECTION 4: TEST CASE MANAGEMENT (LLM-based)');

    printSection('Create a Test Case');
    printEndpoint('POST', '/test-cases');
    printExplanation('Creates a test case to evaluate tool selection using LLM.');
    console.log(`\n${colors.YELLOW}Request Body Example:${colors.NC}`);
    console.log(JSON.stringify({
      name: "Test tool selection",
      query: "Example query for demonstration",
      expected_mcp_server_name: "example-server",
      expected_tool_name: "example_tool",
      expected_parameters: { param: "value" },
      available_mcp_servers: [DEMO_SERVER_URL]
    }, null, 2));
    console.log(`\n${colors.YELLOW}Note: Test case execution requires LLM. Skipped in demo.${colors.NC}`);
    await pause();

    // ============================================================================
    // SECTION 5: METRICS
    // ============================================================================

    printHeader('SECTION 5: METRICS & ANALYTICS');

    // Get Metrics Summary
    printSection('Get Metrics Summary');
    printEndpoint('GET', '/metrics/summary');
    printExplanation('Retrieves aggregated metrics across test runs.');
    const metricsResponse = await makeRequest('/metrics/summary');
    printResponse(metricsResponse);
    await pause();

    // ============================================================================
    // FINALE
    // ============================================================================

    printHeader('DEMO COMPLETE!');

    console.log('');
    console.log(`${colors.GREEN}✓ All API endpoints have been demonstrated${colors.NC}`);
    console.log('');
    console.log(`${colors.BOLD}${colors.CYAN}Quick Reference Summary:${colors.NC}`);
    console.log('');
    console.log(`${colors.BOLD}Basic Endpoints:${colors.NC}`);
    console.log('  GET  /              - API info');
    console.log('  GET  /health        - Health check');
    console.log('');
    console.log(`${colors.BOLD}MCP Servers & Tools:${colors.NC}`);
    console.log('  GET    /mcp-servers/tools?server_url={url}                - Load tools from URL');
    console.log('  GET    /mcp-servers/tools/quality?server_urls={urls}...   - Tool quality (LLM-based, SLOW)');
    console.log('');
    console.log(`${colors.BOLD}Similarity Analysis:${colors.NC}`);
    console.log('  POST /similarity/analyze        - Analyze tool similarities');
    console.log('  POST /similarity/matrix         - Generate similarity matrix');
    console.log('  POST /similarity/overlap-matrix - Generate overlap matrix');
    console.log('');
    console.log(`${colors.BOLD}Test Cases (LLM-based):${colors.NC}`);
    console.log('  POST   /test-cases              - Create test case');
    console.log('  POST   /test-cases/{id}/run     - Execute test run (SLOW)');
    console.log('');
    console.log(`${colors.BOLD}Metrics:${colors.NC}`);
    console.log('  GET  /metrics/summary           - Get metrics summary');
    console.log('');
    console.log(`${colors.BOLD}Documentation:${colors.NC}`);
    console.log(`  Swagger UI: ${colors.YELLOW}${BASE_URL}/docs${colors.NC}`);
    console.log(`  ReDoc:      ${colors.YELLOW}${BASE_URL}/redoc${colors.NC}`);
    console.log('');
    console.log(`${colors.GREEN}Happy building! 🚀${colors.NC}`);
    console.log('');

  } catch (error) {
    console.error(`${colors.RED}Error:${colors.NC}`, error.message);
    process.exit(1);
  }
}

// Enable stdin for interactive mode
if (!AUTO_MODE) {
  process.stdin.setRawMode(true);
  process.stdin.resume();
  process.stdin.setEncoding('utf8');
}

// Run the demo
runDemo().then(() => {
  if (!AUTO_MODE) {
    process.stdin.setRawMode(false);
    process.stdin.pause();
  }
  process.exit(0);
}).catch((error) => {
  console.error(`${colors.RED}Fatal error:${colors.NC}`, error);
  process.exit(1);
});

