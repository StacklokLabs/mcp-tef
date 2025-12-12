-- Schema for MCP Tool Evaluation System
-- SQLite Database Schema

-- Enable foreign key constraints
PRAGMA foreign_keys = ON;

-- Enable WAL mode for better concurrent read performance
PRAGMA journal_mode = WAL;

-- Model Settings (NEW - replaces providers/models tables)
-- Stores non-credential LLM configuration for audit trail
CREATE TABLE IF NOT EXISTS model_settings (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    timeout INTEGER NOT NULL CHECK (timeout > 0 AND timeout <= 300),
    temperature REAL NOT NULL CHECK (temperature >= 0 AND temperature <= 2),
    max_retries INTEGER NOT NULL CHECK (max_retries >= 0 AND max_retries <= 10),
    base_url TEXT,
    system_prompt TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_model_settings_provider ON model_settings(provider);
CREATE INDEX IF NOT EXISTS idx_model_settings_model ON model_settings(model);

-- Tool Definitions
CREATE TABLE IF NOT EXISTS tool_definitions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    input_schema TEXT NOT NULL,  -- JSON Schema as TEXT
    output_schema TEXT,          -- Optional JSON Schema as TEXT
    mcp_server_url TEXT NOT NULL,
    test_run_id TEXT NOT NULL,   -- Links tool to test run that ingested it
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (test_run_id) REFERENCES test_runs(id) ON DELETE CASCADE,
    UNIQUE(name, mcp_server_url, test_run_id)  -- Allow same tool per test run
);

CREATE INDEX IF NOT EXISTS idx_tool_name ON tool_definitions(name);
CREATE INDEX IF NOT EXISTS idx_tool_test_run ON tool_definitions(test_run_id);

-- Test Cases (MODIFIED - removed model_id FK, made expected_tool nullable, uses URL not name)
CREATE TABLE IF NOT EXISTS test_cases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    query TEXT NOT NULL,
    expected_mcp_server_url TEXT,  -- Can be NULL if no tool expected
    expected_tool_name TEXT,  -- Can be NULL if no tool expected
    expected_parameters TEXT,  -- JSON as TEXT, can be NULL
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((expected_mcp_server_url IS NULL AND expected_tool_name IS NULL AND expected_parameters IS NULL) OR
           (expected_mcp_server_url IS NOT NULL AND expected_tool_name IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_test_case_expected_server ON test_cases(expected_mcp_server_url);
CREATE INDEX IF NOT EXISTS idx_test_case_expected_tool ON test_cases(expected_tool_name);

-- Junction table for test case available MCP servers (many-to-many)
CREATE TABLE IF NOT EXISTS test_case_mcp_servers (
    test_case_id TEXT NOT NULL,
    server_url TEXT NOT NULL,
    transport TEXT NOT NULL DEFAULT 'streamable-http',
    PRIMARY KEY (test_case_id, server_url),
    FOREIGN KEY (test_case_id) REFERENCES test_cases(id) ON DELETE CASCADE,
    CHECK (transport IN ('sse', 'streamable-http'))
);

CREATE INDEX IF NOT EXISTS idx_test_case_mcp_servers_test_case ON test_case_mcp_servers(test_case_id);

-- Test Runs (MODIFIED - added model_settings_id FK, llm_confidence, parameter_correctness)
CREATE TABLE IF NOT EXISTS test_runs (
    id TEXT PRIMARY KEY,
    test_case_id TEXT NOT NULL,
    model_settings_id TEXT,  -- NEW: Link to model configuration used
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    llm_response_raw TEXT,  -- JSON as TEXT
    selected_tool_id TEXT,
    extracted_parameters TEXT,  -- JSON as TEXT
    llm_confidence TEXT CHECK (llm_confidence IS NULL OR llm_confidence IN ('high', 'low')),
    parameter_correctness REAL CHECK (parameter_correctness IS NULL OR (parameter_correctness >= 0 AND parameter_correctness <= 10)),
    confidence_score TEXT CHECK (confidence_score IS NULL OR confidence_score IN ('robust description', 'needs clarity', 'misleading description')),
    classification TEXT CHECK (classification IS NULL OR classification IN ('TP', 'FP', 'TN', 'FN')),
    execution_time_ms INTEGER CHECK (execution_time_ms IS NULL OR execution_time_ms > 0),
    error_message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (test_case_id) REFERENCES test_cases(id) ON DELETE CASCADE,
    FOREIGN KEY (model_settings_id) REFERENCES model_settings(id) ON DELETE SET NULL,
    FOREIGN KEY (selected_tool_id) REFERENCES tool_definitions(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_test_run_test_case ON test_runs(test_case_id);
CREATE INDEX IF NOT EXISTS idx_test_run_model_settings ON test_runs(model_settings_id);
CREATE INDEX IF NOT EXISTS idx_test_run_status ON test_runs(status);
CREATE INDEX IF NOT EXISTS idx_test_run_created_at ON test_runs(created_at);

-- Triggers to update updated_at timestamp

CREATE TRIGGER IF NOT EXISTS update_test_case_timestamp
AFTER UPDATE ON test_cases
FOR EACH ROW
BEGIN
    UPDATE test_cases SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;
