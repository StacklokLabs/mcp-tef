"""Evaluation service for tool selection tests."""

from __future__ import annotations

import asyncio
import time

import structlog
from mcp_tef_models.schemas import (
    ModelSettingsCreate,
    TestRunResponse,
    ToolDefinitionCreate,
    ToolDefinitionResponse,
)

from mcp_tef.api.errors import ResourceNotFoundError, ToolIngestionError
from mcp_tef.config.settings import Settings
from mcp_tef.models.llm_models import ConfidenceLevel
from mcp_tef.services.confidence_analyzer import ConfidenceAnalyzer
from mcp_tef.services.llm_service import LLMService
from mcp_tef.services.mcp_loader import MCPLoaderService
from mcp_tef.services.parameter_validator import ParameterValidator
from mcp_tef.services.tool_call_matcher import ToolCallMatcher, ToolCallMatchResult
from mcp_tef.storage.model_settings_repository import ModelSettingsRepository
from mcp_tef.storage.test_case_repository import TestCaseRepository
from mcp_tef.storage.test_run_repository import TestRunRepository
from mcp_tef.storage.tool_call_match_repository import ToolCallMatchRepository
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
        tool_call_match_repo: ToolCallMatchRepository,
        mcp_loader: MCPLoaderService,
        settings: Settings,
    ):
        """Initialize evaluation service.

        Args:
            test_case_repo: Test case repository
            test_run_repo: Test run repository
            model_settings_repo: Model settings repository
            tool_repo: Tool repository
            tool_call_match_repo: Tool call match repository
            mcp_loader: MCP loader service for live tool discovery
            settings: Application settings
        """
        self.test_case_repo = test_case_repo
        self.test_run_repo = test_run_repo
        self.model_settings_repo = model_settings_repo
        self.tool_repo = tool_repo
        self.tool_call_match_repo = tool_call_match_repo
        self.mcp_loader = mcp_loader
        self.settings = settings
        self.parameter_validator = ParameterValidator()
        self.confidence_analyzer = ConfidenceAnalyzer()
        self.tool_call_matcher = ToolCallMatcher()

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
            await llm_service.connect_to_mcp_servers(test_case.available_mcp_servers, system_prompt)

            # Query LLM with tool mapping
            llm_response = await llm_service.select_tool(test_case.query)

            # Match expected tool calls against actual LLM tool calls
            expected_calls = test_case.expected_tool_calls or []
            actual_calls = llm_response.tool_calls

            # Choose matching algorithm based on order_dependent_matching flag
            if test_case.order_dependent_matching:
                match_results = self.tool_call_matcher.match_order_dependent(
                    expected_calls, actual_calls
                )
            else:
                match_results = self.tool_call_matcher.match_order_independent(
                    expected_calls, actual_calls
                )

            # Store tool_call_matches in database
            for match_result in match_results:
                # Resolve expected_tool_call_id
                expected_call_id = None
                if match_result.expected_call and match_result.expected_index is not None:
                    expected_call_id = await self._get_expected_call_id(
                        test_case.id, match_result.expected_index
                    )

                # Resolve actual_tool_id
                actual_tool_id = None
                if match_result.actual_call:
                    try:
                        tool_def = await self.tool_repo.get_by_name_and_test_run(
                            match_result.actual_call.name, test_run.id
                        )
                        actual_tool_id = tool_def.id
                    except ResourceNotFoundError:
                        logger.warning(
                            "Could not resolve actual tool ID",
                            tool_name=match_result.actual_call.name,
                            test_run_id=test_run.id,
                        )

                # Insert tool_call_match record
                await self.tool_call_match_repo.create(
                    test_run_id=test_run.id,
                    expected_tool_call_id=expected_call_id,
                    actual_tool_id=actual_tool_id,
                    match_type=match_result.match_type,
                    parameter_correctness=match_result.parameter_correctness,
                    actual_parameters=match_result.actual_call.parameters
                    if match_result.actual_call
                    else None,
                    parameter_justification=match_result.parameter_justification,
                )

            # Calculate aggregate metrics from match results
            avg_param_correctness = self._calculate_avg_parameter_correctness(match_results)
            overall_classification = self._aggregate_classification(match_results)

            # Calculate confidence_score description
            confidence_score = None
            if llm_response.confidence_level and avg_param_correctness is not None:
                if (
                    llm_response.confidence_level == ConfidenceLevel.HIGH
                    and avg_param_correctness == 10
                ):
                    confidence_score = "robust description"
                elif (
                    llm_response.confidence_level == ConfidenceLevel.HIGH
                    and avg_param_correctness == 0
                ):
                    confidence_score = "misleading description"
                else:
                    confidence_score = "needs clarity"

            # Calculate execution time
            execution_time_ms = max(1, int((time.time() - start_time) * 1000))

            # Update test run with results
            test_run = await self.test_run_repo.update_status(
                test_run.id,
                status="completed",
                llm_response_raw=llm_response.raw_response,
                llm_confidence=llm_response.confidence_level,
                avg_parameter_correctness=avg_param_correctness,
                confidence_score=confidence_score,
                classification=overall_classification,
                execution_time_ms=execution_time_ms,
            )

            logger.info(
                f"Test run {test_run.id} completed with classification: {overall_classification}"
            )

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
        server_configs = await self.test_case_repo.get_test_case_servers(test_case_id)

        if not server_configs:
            logger.warning("No MCP servers found for test case", test_case_id=test_case_id)
            return

        logger.info(
            "Ingesting tools for test run",
            test_run_id=test_run_id,
            test_case_id=test_case_id,
            server_count=len(server_configs),
        )

        # Ingest tools from all servers concurrently
        try:
            results = await asyncio.gather(
                *[
                    self._ingest_from_single_server(server.url, server.transport, test_run_id)
                    for server in server_configs
                ]
            )

            # Aggregate results
            total_ingested = sum(len(ingested) for ingested, _ in results)
            total_skipped = sum(len(skipped) for _, skipped in results)

            logger.info(
                "Tool ingestion completed",
                test_run_id=test_run_id,
                server_count=len(server_configs),
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
        transport: str,
        test_run_id: str,
    ) -> tuple[list[ToolDefinitionResponse], list[str]]:
        """Ingest tools from a single MCP server for a test run.

        Args:
            server_url: MCP server URL to ingest from
            transport: Transport protocol ('sse' or 'streamable-http')
            test_run_id: Test run ID to associate tools with

        Returns:
            Tuple of (list[ToolDefinitionResponse], list[str]) containing
            (ingested_tools, skipped_tool_names)

        Raises:
            ToolIngestionError: If tool loading fails
        """
        try:
            # Load tools from MCP server
            tools_data = await self.mcp_loader.load_tools_from_server(server_url, transport)

            # Prepare tool definitions for batch insert
            tools_to_create = [
                ToolDefinitionCreate(
                    name=tool_def.name,
                    description=tool_def.description,
                    input_schema=tool_def.input_schema,
                    output_schema=None,
                    mcp_server_url=server_url,
                    test_run_id=test_run_id,
                )
                for tool_def in tools_data
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

    async def _get_expected_call_id(self, test_case_id: str, expected_index: int) -> str | None:
        """Get the ID of an expected tool call by its sequence order.

        Args:
            test_case_id: Test case ID
            expected_index: Sequence order of the expected tool call

        Returns:
            Expected tool call ID or None if not found
        """
        try:
            return await self.tool_call_match_repo.get_expected_call_id(
                test_case_id=test_case_id,
                sequence_order=expected_index,
            )
        except Exception as e:
            logger.warning(
                "Failed to get expected call ID",
                test_case_id=test_case_id,
                expected_index=expected_index,
                error=str(e),
            )
            return None

    def _calculate_avg_parameter_correctness(
        self, match_results: list[ToolCallMatchResult]
    ) -> float | None:
        """Calculate average parameter correctness across TP matches.

        Args:
            match_results: List of ToolCallMatchResult objects

        Returns:
            Average parameter correctness score (0-10) or None if no TP matches
        """
        tp_scores = [
            result.parameter_correctness
            for result in match_results
            if result.match_type == "TP" and result.parameter_correctness is not None
        ]

        if not tp_scores:
            return None

        return sum(tp_scores) / len(tp_scores)

    def _aggregate_classification(self, match_results: list[ToolCallMatchResult]) -> str:
        """Aggregate per-tool-call classifications into overall test result.

        Rules:
        - If all matches are TP or TN → TP (or TN if no tools)
        - If any FN exists → FN
        - If any FP exists (and no FN) → FP
        - Mixed cases TN and TP in results → TP

        Args:
            match_results: List of ToolCallMatchResult objects

        Returns:
            Overall classification (TP/FP/TN/FN)
        """
        if not match_results:
            return "TN"

        match_types = {result.match_type for result in match_results}

        if match_types == {"TN"}:
            return "TN"
        if match_types == {"TP"}:
            return "TP"
        if "FN" in match_types:
            return "FN"
        if "FP" in match_types:
            return "FP"

        return "TP"  # Default to TP for mixed cases
