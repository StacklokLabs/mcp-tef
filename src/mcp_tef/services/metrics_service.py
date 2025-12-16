"""Metrics calculation and aggregation service."""

import json

import structlog

from mcp_tef.models.evaluation_models import MetricsSummary
from mcp_tef.storage.test_run_repository import TestRunRepository

logger = structlog.get_logger(__name__)


class MetricsService:
    """Service for calculating and aggregating evaluation metrics."""

    def __init__(self, test_run_repo: TestRunRepository):
        """Initialize metrics service.

        Args:
            db: Active aiosqlite connection
        """
        self._test_run_repo = test_run_repo

    async def calculate_summary(
        self,
        test_run_id: str | None = None,
        test_case_id: str | None = None,
        mcp_server_url: str | None = None,
        tool_name: str | None = None,
        limit: int = 100,  # default to the 100 most recent runs
    ) -> MetricsSummary:
        """Calculate aggregated metrics summary with optional filters.

        Args:
            mcp_server_id: Filter by MCP server ID (takes precedence over mcp_server_name)
            mcp_server_name: Filter by MCP server name
            tool_name: Filter by tool name

        Returns:
            Aggregated metrics summary
        """

        test_runs = await self._test_run_repo.query(
            test_run_id=test_run_id,
            test_case_id=test_case_id,
            mcp_server_url=mcp_server_url,
            tool_name=tool_name,
            status="completed",
            limit=limit,
        )

        # Initialize counters
        total_tests = len(test_runs)
        tp_count = 0
        fp_count = 0
        tn_count = 0
        fn_count = 0
        total_execution_time = 0
        robust_count = 0
        needs_clarity_count = 0
        misleading_count = 0
        test_run_ids: list[str] = []
        parameter_correctness_values: list[float] = []

        # Process results
        for test_run in test_runs:
            test_run_id = test_run.id
            classification = test_run.classification
            execution_time_ms = test_run.execution_time_ms
            confidence_score = test_run.confidence_score
            avg_parameter_correctness = test_run.avg_parameter_correctness

            # Collect test run ID
            test_run_ids.append(test_run_id)

            # Count classifications
            if classification == "TP":
                tp_count += 1
            elif classification == "FP":
                fp_count += 1
            elif classification == "TN":
                tn_count += 1
            elif classification == "FN":
                fn_count += 1

            # Sum execution time
            if execution_time_ms is not None:
                total_execution_time += execution_time_ms

            # Track confidence score descriptions
            if confidence_score is not None:
                if confidence_score == "robust description":
                    robust_count += 1
                elif confidence_score == "needs clarity":
                    needs_clarity_count += 1
                elif confidence_score == "misleading description":
                    misleading_count += 1

            # Collect parameter correctness values (0-10 scale)
            if avg_parameter_correctness is not None:
                parameter_correctness_values.append(avg_parameter_correctness)

        # Calculate metrics with division-by-zero handling
        precision = self._calculate_precision(tp_count, fp_count)
        recall = self._calculate_recall(tp_count, fn_count)
        f1_score = self._calculate_f1_score(precision, recall)
        parameter_accuracy = self._calculate_parameter_accuracy(parameter_correctness_values)
        average_execution_time = total_execution_time / total_tests if total_tests > 0 else 0.0

        summary = MetricsSummary(
            total_tests=total_tests,
            true_positives=tp_count,
            false_positives=fp_count,
            true_negatives=tn_count,
            false_negatives=fn_count,
            precision=precision,
            recall=recall,
            f1_score=f1_score,
            parameter_accuracy=parameter_accuracy,
            average_execution_time_ms=average_execution_time,
            robust_description_count=robust_count,
            needs_clarity_count=needs_clarity_count,
            misleading_description_count=misleading_count,
            test_run_ids=test_run_ids,
        )
        logger.debug(
            f"Calculated metrics summary: {total_tests} tests: {json.dumps(summary.model_dump())}"
        )
        return summary

    def _calculate_precision(self, tp: int, fp: int) -> float:
        """Calculate precision with division-by-zero handling.

        Precision = TP / (TP + FP)

        Args:
            tp: True positives count
            fp: False positives count

        Returns:
            Precision value (0.0 if denominator is 0)
        """
        denominator = tp + fp
        if denominator == 0:
            return 0.0
        return tp / denominator

    def _calculate_recall(self, tp: int, fn: int) -> float:
        """Calculate recall with division-by-zero handling.

        Recall = TP / (TP + FN)

        Args:
            tp: True positives count
            fn: False negatives count

        Returns:
            Recall value (0.0 if denominator is 0)
        """
        denominator = tp + fn
        if denominator == 0:
            return 0.0
        return tp / denominator

    def _calculate_f1_score(self, precision: float, recall: float) -> float:
        """Calculate F1 score with division-by-zero handling.

        F1 = 2 * (Precision * Recall) / (Precision + Recall)

        Args:
            precision: Precision value
            recall: Recall value

        Returns:
            F1 score (0.0 if denominator is 0)
        """
        denominator = precision + recall
        if denominator == 0.0:
            return 0.0
        return 2 * (precision * recall) / denominator

    def _calculate_parameter_accuracy(self, parameter_correctness_values: list[float]) -> float:
        """Calculate parameter accuracy with division-by-zero handling.

        Parameter Accuracy = Average of parameter correctness scores (0-10 scale)

        Args:
            parameter_correctness_values: List of parameter correctness scores

        Returns:
            Average parameter accuracy (0.0 if no values)
        """
        if not parameter_correctness_values:
            return 0.0
        return sum(parameter_correctness_values) / len(parameter_correctness_values)

    async def calculate_tool_call_level_summary(
        self,
        test_run_id: str | None = None,
        test_case_id: str | None = None,
        mcp_server_url: str | None = None,
        tool_name: str | None = None,
        limit: int = 1000,
    ) -> MetricsSummary:
        """Calculate metrics at the per-tool-call level (granular).

        This method queries the tool_call_matches table directly to calculate
        metrics at the individual tool call level, rather than aggregating
        at the test case level.

        Args:
            test_run_id: Filter by test run ID
            test_case_id: Filter by test case ID
            mcp_server_url: Filter by MCP server URL
            tool_name: Filter by tool name
            limit: Maximum number of matches to include (default: 1000)

        Returns:
            Aggregated metrics summary at tool-call level
        """
        # Build query with filters
        conditions = []
        params = []

        if test_run_id:
            conditions.append("tcm.test_run_id = ?")
            params.append(test_run_id)

        if test_case_id:
            conditions.append("tr.test_case_id = ?")
            params.append(test_case_id)

        if mcp_server_url:
            conditions.append("(etc.mcp_server_url = ? OR td.mcp_server_url = ?)")
            params.extend([mcp_server_url, mcp_server_url])

        if tool_name:
            conditions.append("(etc.tool_name = ? OR td.name = ?)")
            params.extend([tool_name, tool_name])

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        query = f"""
            SELECT
                tcm.match_type,
                tcm.parameter_correctness,
                tcm.test_run_id
            FROM tool_call_matches tcm
            INNER JOIN test_runs tr ON tcm.test_run_id = tr.id
            LEFT JOIN expected_tool_calls etc ON tcm.expected_tool_call_id = etc.id
            LEFT JOIN tool_definitions td ON tcm.actual_tool_id = td.id
            WHERE {where_clause}
            LIMIT ?
        """  # nosec: "B608" Safe: where_clause built from controlled conditions, values parameterized

        params.append(limit)

        cursor = await self._test_run_repo.db.execute(query, tuple(params))
        rows = await cursor.fetchall()

        # Initialize counters
        total_matches = len(rows)
        tp_count = 0
        fp_count = 0
        tn_count = 0
        fn_count = 0
        parameter_correctness_values: list[float] = []
        test_run_ids_set: set[str] = set()

        # Process matches
        for row in rows:
            match_type = row[0]
            parameter_correctness = row[1]
            test_run_id_val = row[2]

            # Count classifications
            if match_type == "TP":
                tp_count += 1
            elif match_type == "FP":
                fp_count += 1
            elif match_type == "TN":
                tn_count += 1
            elif match_type == "FN":
                fn_count += 1

            # Collect parameter correctness for TP matches
            if parameter_correctness is not None and match_type == "TP":
                parameter_correctness_values.append(parameter_correctness)

            # Track unique test run IDs
            if test_run_id_val:
                test_run_ids_set.add(test_run_id_val)

        # Calculate metrics
        precision = self._calculate_precision(tp_count, fp_count)
        recall = self._calculate_recall(tp_count, fn_count)
        f1_score = self._calculate_f1_score(precision, recall)
        parameter_accuracy = self._calculate_parameter_accuracy(parameter_correctness_values)

        summary = MetricsSummary(
            total_tests=total_matches,
            true_positives=tp_count,
            false_positives=fp_count,
            true_negatives=tn_count,
            false_negatives=fn_count,
            precision=precision,
            recall=recall,
            f1_score=f1_score,
            parameter_accuracy=parameter_accuracy,
            average_execution_time_ms=0.0,
            robust_description_count=0,
            needs_clarity_count=0,
            misleading_description_count=0,
            test_run_ids=list(test_run_ids_set),
        )
        logger.debug(
            f"Calculated tool-call level metrics: {total_matches} matches: "
            f"{json.dumps(summary.model_dump())}"
        )
        return summary
