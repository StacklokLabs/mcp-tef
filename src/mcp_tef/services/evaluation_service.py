"""Evaluation service for tool selection tests."""

from __future__ import annotations

import asyncio
import time

import structlog

from mcp_tef.api.errors import ResourceNotFoundError, ToolIngestionError
from mcp_tef.config.settings import Settings
from mcp_tef.models.llm_models import ConfidenceLevel, LLMToolCall
from mcp_tef.models.schemas import (
    ModelSettingsCreate,
    TestRunResponse,
    ToolDefinitionCreate,
)
from mcp_tef.services.confidence_analyzer import ConfidenceAnalyzer
from mcp_tef.services.llm_service import LLMService
from mcp_tef.services.mcp_loader import MCPLoaderService
from mcp_tef.services.parameter_validator import ParameterValidator
from mcp_tef.storage.model_settings_repository import ModelSettingsRepository
from mcp_tef.storage.test_case_repository import TestCaseRepository
from mcp_tef.storage.test_run_repository import TestRunRepository
from mcp_tef.storage.tool_repository import ToolRepository

logger = structlog.get_logger(__name__)


class EvaluationService:
    """Service for executing and evaluating tool selection tests."""

    def __init__(
        self,
        test_case_repo: TestCaseRepository,
        test_run_repo: TestRunRepository,
        model_settings_repo: ModelSettingsRepository,
        tool_repo: ToolRepository,
        mcp_loader: MCPLoaderService,
        settings: Settings,
    ):
        """Initialize evaluation service.

        Args:
            test_case_repo: Test case repository
            test_run_repo: Test run repository
            model_settings_repo: Model settings repository
            tool_repo: Tool repository
            mcp_loader: MCP loader service for live tool discovery
            settings: Application settings
        """
        self.test_case_repo = test_case_repo
        self.test_run_repo = test_run_repo
        self.model_settings_repo = model_settings_repo
        self.tool_repo = tool_repo
        self.mcp_loader = mcp_loader
        self.settings = settings
        self.parameter_validator = ParameterValidator()
        self.confidence_analyzer = ConfidenceAnalyzer()

    async def create_test(
        self, test_case_id: str, model_settings: ModelSettingsCreate
    ) -> TestRunResponse:
        """Creates a 'pending' test run in the repository

        Args:
            test_case_id: test case to run
            model_settings: model settings to use with the test run

        Returns:
            'pending' test run
        """
        # Create model_settings record first (for audit trail)
        model_settings_record = await self.model_settings_repo.create(model_settings)

        # Create test run with model_settings_id
        return await self.test_run_repo.create(
            test_case_id=test_case_id, model_settings_id=model_settings_record.id
        )

    async def execute_pending_test(
        self,
        test_run: TestRunResponse,
        api_key: str | None,
    ) -> TestRunResponse:
        """Execute a tool selection test.

        Args:
            test_run: pending test run (already created in the repo)
            api_key: Optional runtime API key for LLM provider

        Returns:
            Test run with results and model_settings persisted

        Raises:
            ResourceNotFoundError: If test case not found
            DatabaseError: If database operation fails or LLM authentication fails
            LLMProviderError: If LLM provider authentication fails
        """

        if test_run.status != "pending":
            raise ValueError(f"Test run {test_run.id} is not 'pending'")

        if not test_run.model_settings:
            raise ValueError(f"Test run {test_run.id} does not have model_settings")

        start_time = time.time()

        try:
            # Ingest fresh tools before test execution
            await self.ingest_tools_for_test_run(
                test_case_id=test_run.test_case_id,
                test_run_id=test_run.id,
                commit=True,
            )
        except Exception as e:
            # Tool ingestion failed - create failed test run directly
            execution_time_ms = max(1, int((time.time() - start_time) * 1000))
            logger.error(f"Tool ingestion failed for test run {test_run.id}: {e}")

            return await self.test_run_repo.update_status(
                test_run_id=test_run.id,
                status="failed",
                error_message=f"Tool ingestion failed: {str(e)}",
                execution_time_ms=execution_time_ms,
            )

        try:
            model_settings = await self.model_settings_repo.get(test_run.model_settings.id)
            # Update status to running
            await self.test_run_repo.update_status(test_run.id, "running")

            # Get test case
            test_case = await self.test_case_repo.get(test_run.test_case_id)

            # MCP server URLs are already in test_case.available_mcp_servers
            mcp_server_urls = test_case.available_mcp_servers

            # Create LLM service with optional runtime API key and model settings
            # If API key is None, pass empty string (will fail gracefully during authentication)
            llm_service = LLMService(
                provider=model_settings.provider,
                model=model_settings.model,
                api_key=api_key,
                timeout=model_settings.timeout,
                max_retries=model_settings.max_retries,
                base_url=model_settings.base_url,
                settings=self.settings,
            )

            # Connect to MCP servers with system prompt
            system_prompt = (
                model_settings.system_prompt or self.settings.default_system_prompt_tool_selection
            )
            await llm_service.connect_to_mcp_servers(mcp_server_urls, system_prompt)

            # Query LLM with tool mapping
            llm_response = await llm_service.select_tool(test_case.query)

            # Extract selected tool and parameters from LLM response
            selected_tool: LLMToolCall | None = None
            selected_tool_id: str | None = None
            extracted_parameters: dict | None = None

            if len(llm_response.tool_calls) > 0:
                candidate_tool_calls = [
                    tool_call
                    for tool_call in llm_response.tool_calls
                    if tool_call.name == test_case.expected_tool_name
                ]

                if len(candidate_tool_calls) == 0:
                    candidate_tool_calls = llm_response.tool_calls

                if len(candidate_tool_calls) > 1:
                    logger.warning(
                        f"LLM returned multiple tool calls, using the first one: "
                        f"{candidate_tool_calls}"
                    )

                selected_tool = candidate_tool_calls[0]
                extracted_parameters = selected_tool.parameters

                # Resolve selected tool ID from tool name and test run ID
                try:
                    tool_def = await self.tool_repo.get_by_name_and_test_run(
                        selected_tool.name, test_run.id
                    )
                    selected_tool_id = tool_def.id
                except ResourceNotFoundError as e:
                    logger.warning(
                        "Failed to resolve selected tool ID",
                        tool_name=selected_tool.name,
                        test_run_id=test_run.id,
                        error=str(e),
                    )

            # Resolve expected tool ID from MCP server URL, tool name, and test run ID
            expected_tool_id: str | None = None
            if test_case.expected_mcp_server_url is not None:
                try:
                    expected_tool_def = await self.tool_repo.get_by_server_url_and_test_run(
                        test_case.expected_mcp_server_url, test_case.expected_tool_name, test_run.id
                    )
                    expected_tool_id = expected_tool_def.id
                except ResourceNotFoundError as e:
                    logger.warning(
                        "Failed to resolve expected tool ID",
                        server_url=test_case.expected_mcp_server_url,
                        tool_name=test_case.expected_tool_name,
                        test_run_id=test_run.id,
                        error=str(e),
                    )

            # Classify result
            classification = self._classify_result(expected_tool_id, selected_tool_id)

            # Evaluate parameter correctness if expected_tool and expected_parameters exist
            parameter_correctness = self._evaluate_parameters(
                expected_params=test_case.expected_parameters,
                actual_params=extracted_parameters,
            )

            # Calculate confidence_score description based on
            # llm_confidence and parameter_correctness
            confidence_score = None
            if llm_response.confidence_level and parameter_correctness is not None:
                if (
                    llm_response.confidence_level == ConfidenceLevel.HIGH
                    and parameter_correctness == 10
                ):
                    confidence_score = "robust description"
                elif (
                    llm_response.confidence_level == ConfidenceLevel.HIGH
                    and parameter_correctness == 0
                ):
                    confidence_score = "misleading description"
                else:
                    confidence_score = "needs clarity"

            # Calculate execution time (ensure it's at least 1ms to satisfy CHECK constraint)
            execution_time_ms = max(1, int((time.time() - start_time) * 1000))

            # Update test run with results
            test_run = await self.test_run_repo.update_status(
                test_run.id,
                status="completed",
                llm_response_raw=llm_response.raw_response,
                selected_tool_id=selected_tool_id,
                extracted_parameters=extracted_parameters,
                llm_confidence=llm_response.confidence_level,
                parameter_correctness=parameter_correctness,
                confidence_score=confidence_score,
                classification=classification,
                execution_time_ms=execution_time_ms,
            )

            logger.info(f"Test run {test_run.id} completed with classification: {classification}")

            return test_run

        except Exception as e:
            logger.exception(f"Exception executing test run {test_run.id}")
            try:
                # Update test run status to failed (ensure at least 1ms)
                execution_time_ms = max(1, int((time.time() - start_time) * 1000))
                test_run = await self.test_run_repo.update_status(
                    test_run.id,
                    status="failed",
                    error_message=str(e),
                    execution_time_ms=execution_time_ms,
                )
            except Exception:
                logger.exception(f"Exception updating test run {test_run.id} status to 'failed'.")
            return test_run

    async def ingest_tools_for_test_run(
        self,
        test_case_id: str,
        test_run_id: str,
        commit: bool = True,
    ) -> None:
        """Ingest fresh tools from all MCP servers for a test run.

        This function uses asyncio.gather() to concurrently fetch tools from
        multiple MCP servers for optimal performance.

        Args:
            test_case_id: Test case ID
            test_run_id: Test run ID to associate tools with
            commit: Whether to commit the transaction (default: True)

        Raises:
            ToolIngestionError: If any server tool loading fails
        """
        # Get all MCP servers for this test case
        server_urls = await self.test_case_repo.get_test_case_servers(test_case_id)

        if not server_urls:
            logger.warning("No MCP servers found for test case", test_case_id=test_case_id)
            return

        logger.info(
            "Ingesting tools for test run",
            test_run_id=test_run_id,
            test_case_id=test_case_id,
            server_count=len(server_urls),
        )

        # Ingest tools from all servers concurrently
        try:
            results = await asyncio.gather(
                *[
                    self._ingest_from_single_server(server_url, test_run_id)
                    for server_url in server_urls
                ]
            )

            # Aggregate results
            total_ingested = sum(len(ingested) for ingested, _ in results)
            total_skipped = sum(len(skipped) for _, skipped in results)

            logger.info(
                "Tool ingestion completed",
                test_run_id=test_run_id,
                server_count=len(server_urls),
                total_ingested=total_ingested,
                total_skipped=total_skipped,
            )

            # Commit transaction if requested
            if commit:
                await self.tool_repo.db.commit()

        except ToolIngestionError:
            # Re-raise ToolIngestionError as-is
            raise
        except Exception as e:
            # Wrap unexpected errors
            logger.error(
                "Unexpected error during tool ingestion",
                test_run_id=test_run_id,
                error=str(e),
            )
            raise ToolIngestionError(
                message=f"Unexpected error: {str(e)}",
                server_url="<multiple>",
                original_error=e,
            ) from e

    async def _ingest_from_single_server(
        self,
        server_url: str,
        test_run_id: str,
    ) -> tuple[list, list[str]]:
        """Ingest tools from a single MCP server for a test run.

        Args:
            server_url: MCP server to ingest from
            test_run_id: Test run ID to associate tools with

        Returns:
            Tuple of (ingested_tools, skipped_tool_names)

        Raises:
            ToolIngestionError: If tool loading fails
        """
        try:
            # Load tools from MCP server
            tools_data = await self.mcp_loader.load_tools_from_url(server_url)

            # Prepare tool definitions for batch insert
            tools_to_create = [
                ToolDefinitionCreate(
                    name=tool_dict["name"],
                    description=tool_dict["description"],
                    input_schema=tool_dict["input_schema"],
                    output_schema=tool_dict.get("output_schema"),
                    mcp_server_url=server_url,
                    test_run_id=test_run_id,
                )
                for tool_dict in tools_data
            ]

            # Batch create tool definitions in database
            ingested_tools, skipped_tools = await self.tool_repo.batch_create(
                tools_to_create, commit=False
            )

            logger.debug(
                "Ingested tools from MCP server",
                server_url=server_url,
                test_run_id=test_run_id,
                total_loaded=len(tools_data),
                total_ingested=len(ingested_tools),
                total_skipped=len(skipped_tools),
            )

            return ingested_tools, skipped_tools

        except Exception as e:
            logger.error(
                "Failed to ingest tools from MCP server",
                server_url=server_url,
                test_run_id=test_run_id,
                error=str(e),
            )
            raise ToolIngestionError(
                message=str(e),
                server_url=server_url,
                original_error=e,
            ) from e

    def _classify_result(self, expected_tool_id: str | None, selected_tool_id: str | None) -> str:
        """Classify test result as TP/FP/TN/FN.

        Args:
            expected_tool_id: Expected tool selection (None = no tool expected)
            selected_tool_id: Tool selected by LLM (None = no tool selected)

        Returns:
            Classification string (TP/FP/TN/FN)
        """
        if expected_tool_id is not None and selected_tool_id == expected_tool_id:
            return "TP"  # True Positive: expected tool was correctly selected

        if expected_tool_id is None and selected_tool_id is None:
            return "TN"  # True Negative: correctly predicted no tool

        if expected_tool_id is None and selected_tool_id is not None:
            return "FP"  # False Positive: tool selected when shouldn't have been

        # expected_tool_id is not None and selected_tool_id != expected_tool_id
        return "FN"  # False Negative: expected tool was NOT selected

    def _evaluate_parameters(
        self,
        expected_params: dict | None,
        actual_params: dict | None,
    ) -> float:
        """Evaluate parameter correctness and return a score from 0 to 10.

        Scoring criteria:
        - Completeness: Are all required parameters present?
        - Correctness: Do parameter values match expected values?
        - Type conformance: Do values match schema types?
        - Hallucination check: Are there unexpected extra parameters?

        Each category contributes up to 2.5 points for a total of 10 points.

        Args:
            expected_params: Expected parameter values from test case
            actual_params: Parameters extracted by LLM

        Returns:
            Score from 0 to 10
        """
        # If no expected parameters defined, return perfect score
        if expected_params is None or not expected_params:
            return 10.0

        # If no actual parameters provided but expected ones exist, return 0
        if actual_params is None or not actual_params:
            return 0.0

        # Calculate score based on parameter matching
        total_expected = len(expected_params)

        completeness_params = 0
        correctness_params = 0
        conformance_params = 0

        # Check each expected parameter
        for param_name, expected_value in expected_params.items():
            if param_name in actual_params:
                completeness_params += 1
                actual_value = actual_params[param_name]

                # Normalize values for comparison (handle type differences)
                if self._normalize_value(actual_value) == self._normalize_value(expected_value):
                    correctness_params += 1

                # For type conformance, we can do a basic type check
                if type(actual_value) is type(expected_value):
                    conformance_params += 1

        total_score = 0
        total_score += 2.5 * (completeness_params / total_expected)
        total_score += 2.5 * (correctness_params / total_expected)
        total_score += 2.5 * (conformance_params / total_expected)

        # Penalty for hallucinated parameters (unexpected extras)
        extra_params = set(actual_params.keys()) - set(expected_params.keys())
        # If no extra parameters, award bonus points
        if not extra_params:
            total_score += 2.5

        return total_score

    def _normalize_value(self, value) -> str:
        """Normalize a value for comparison.

        Args:
            value: Value to normalize

        Returns:
            Normalized string representation
        """
        if value is None:
            return "null"
        if isinstance(value, bool):
            return str(value).lower()
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, str):
            return value.strip().lower()
        # For complex types, convert to string
        return str(value).strip().lower()
