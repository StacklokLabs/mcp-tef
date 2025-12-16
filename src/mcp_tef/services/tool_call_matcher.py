"""Service for matching expected tool calls against actual LLM tool calls."""

from dataclasses import dataclass
from typing import Any

import structlog
from mcp_tef_models.schemas import ExpectedToolCall

from mcp_tef.models.llm_models import LLMToolCall

logger = structlog.get_logger(__name__)


@dataclass
class ToolCallMatchResult:
    """Result of matching one expected call against one actual call."""

    expected_index: int | None  # None for FP
    actual_index: int | None  # None for FN
    match_type: str  # "TP", "FP", "FN", "TN"
    parameter_correctness: float | None
    expected_call: ExpectedToolCall | None
    actual_call: LLMToolCall | None
    parameter_justification: str | None  # Explanation of score


class ToolCallMatcher:
    """Matches expected tool calls against actual LLM responses."""

    def match_order_independent(
        self,
        expected_calls: list[ExpectedToolCall],
        actual_calls: list[LLMToolCall],
    ) -> list[ToolCallMatchResult]:
        """Match expected vs actual tool calls in order-independent manner.

        Algorithm (Greedy Best-Fit):
        1. For each expected call, find best matching actual call (by tool name + server)
        2. Mark matched pairs as TP, calculate parameter scores
        3. Remaining expected calls = FN
        4. Remaining actual calls = FP
        5. If no expected calls and no actual calls = TN

        Args:
            expected_calls: List of expected tool calls
            actual_calls: List of actual LLM tool calls

        Returns:
            List of match results (one per expected or actual tool call)
        """
        results = []
        used_actual_indices = set()

        # Handle TN case (no tools expected, no tools selected)
        if not expected_calls and not actual_calls:
            return [
                ToolCallMatchResult(
                    expected_index=None,
                    actual_index=None,
                    match_type="TN",
                    parameter_correctness=None,
                    expected_call=None,
                    actual_call=None,
                    parameter_justification=None,
                )
            ]

        # Match expected calls to actual calls
        for exp_idx, expected in enumerate(expected_calls):
            best_match_idx = None

            # Find matching actual call by tool name and server
            for act_idx, actual in enumerate(actual_calls):
                if act_idx in used_actual_indices:
                    continue

                # Check if tool names match and server matches. We don't have the server_name
                # coming from the LLM in all cases, so we only match by name here.
                if actual.name == expected.tool_name:
                    # Found a match
                    best_match_idx = act_idx
                    break

            if best_match_idx is not None:
                # TP: Found matching tool call
                actual = actual_calls[best_match_idx]
                used_actual_indices.add(best_match_idx)

                param_score, param_justification = self._evaluate_parameters(
                    expected.parameters, actual.parameters
                )

                results.append(
                    ToolCallMatchResult(
                        expected_index=exp_idx,
                        actual_index=best_match_idx,
                        match_type="TP",
                        parameter_correctness=param_score,
                        expected_call=expected,
                        actual_call=actual,
                        parameter_justification=param_justification,
                    )
                )
            else:
                # FN: Expected tool call not found in actual
                results.append(
                    ToolCallMatchResult(
                        expected_index=exp_idx,
                        actual_index=None,
                        match_type="FN",
                        parameter_correctness=0.0,
                        expected_call=expected,
                        actual_call=None,
                        parameter_justification="Expected tool not called by LLM",
                    )
                )

        # FP: Actual tool calls that weren't matched
        for act_idx, actual in enumerate(actual_calls):
            if act_idx not in used_actual_indices:
                results.append(
                    ToolCallMatchResult(
                        expected_index=None,
                        actual_index=act_idx,
                        match_type="FP",
                        parameter_correctness=None,
                        expected_call=None,
                        actual_call=actual,
                        parameter_justification=None,
                    )
                )

        return results

    def match_order_dependent(
        self,
        expected_calls: list[ExpectedToolCall],
        actual_calls: list[LLMToolCall],
    ) -> list[ToolCallMatchResult]:
        """Match expected vs actual tool calls in order-dependent manner.

        Algorithm (Positional Matching):
        1. Compare position-by-position (0th expected vs 0th actual, etc.)
        2. If tool names match = TP
        3. If tool names differ = FN for expected + FP for actual
        4. Extra actual calls = FP
        5. Missing actual calls = FN

        Args:
            expected_calls: List of expected tool calls
            actual_calls: List of actual LLM tool calls

        Returns:
            List of match results
        """
        results = []
        max_len = max(len(expected_calls), len(actual_calls))

        # Handle TN case
        if max_len == 0:
            return [
                ToolCallMatchResult(
                    expected_index=None,
                    actual_index=None,
                    match_type="TN",
                    parameter_correctness=None,
                    expected_call=None,
                    actual_call=None,
                    parameter_justification=None,
                )
            ]

        for i in range(max_len):
            expected = expected_calls[i] if i < len(expected_calls) else None
            actual = actual_calls[i] if i < len(actual_calls) else None

            if expected and actual:
                # Both exist at this position
                if expected.tool_name == actual.name:
                    # TP: Correct tool in correct position
                    param_score, param_justification = self._evaluate_parameters(
                        expected.parameters, actual.parameters
                    )
                    results.append(
                        ToolCallMatchResult(
                            expected_index=i,
                            actual_index=i,
                            match_type="TP",
                            parameter_correctness=param_score,
                            expected_call=expected,
                            actual_call=actual,
                            parameter_justification=param_justification,
                        )
                    )
                else:
                    # Mismatch: FN for expected + FP for actual
                    results.append(
                        ToolCallMatchResult(
                            expected_index=i,
                            actual_index=None,
                            match_type="FN",
                            parameter_correctness=0.0,
                            expected_call=expected,
                            actual_call=None,
                            parameter_justification=f"Expected tool not called at position {i}",
                        )
                    )
                    results.append(
                        ToolCallMatchResult(
                            expected_index=None,
                            actual_index=i,
                            match_type="FP",
                            parameter_correctness=None,
                            expected_call=None,
                            actual_call=actual,
                            parameter_justification=None,
                        )
                    )
            elif expected:
                # FN: Expected but no actual at this position
                results.append(
                    ToolCallMatchResult(
                        expected_index=i,
                        actual_index=None,
                        match_type="FN",
                        parameter_correctness=0.0,
                        expected_call=expected,
                        actual_call=None,
                        parameter_justification=f"Expected tool not called at position {i}",
                    )
                )
            else:
                # FP: Actual but no expected at this position
                results.append(
                    ToolCallMatchResult(
                        expected_index=None,
                        actual_index=i,
                        match_type="FP",
                        parameter_correctness=None,
                        expected_call=None,
                        actual_call=actual,
                        parameter_justification=None,
                    )
                )

        return results

    def _evaluate_parameters(
        self,
        expected_params: dict[str, Any] | None,
        actual_params: dict[str, Any] | None,
    ) -> tuple[float, str]:
        """Evaluate parameter correctness (0-10 scale) with justification.

        - Completeness (2.5 pts): All required params present
        - Correctness (2.5 pts): Values match expected
        - Type conformance (2.5 pts): Types match
        - No hallucinations (2.5 pts): No extra params

        Args:
            expected_params: Expected parameter values
            actual_params: Actual parameter values from LLM

        Returns:
            Tuple of (score, justification)
        """
        if expected_params is None or not expected_params:
            return 10.0, "No parameters expected, full score"

        if actual_params is None or not actual_params:
            return 0.0, "No parameters provided by LLM"

        total_expected = len(expected_params)
        completeness_params = 0
        correctness_params = 0
        conformance_params = 0

        for param_name, expected_value in expected_params.items():
            if param_name in actual_params:
                completeness_params += 1
                actual_value = actual_params[param_name]

                if self._normalize_value(actual_value) == self._normalize_value(expected_value):
                    correctness_params += 1

                # Check type conformance with numeric equivalence support
                if self._types_match(actual_value, expected_value):
                    conformance_params += 1

        total_score = 0.0
        total_score += 2.5 * (completeness_params / total_expected)
        total_score += 2.5 * (correctness_params / total_expected)
        total_score += 2.5 * (conformance_params / total_expected)

        extra_params = set(actual_params.keys()) - set(expected_params.keys())
        if not extra_params:
            total_score += 2.5

        # Generate justification
        justification_parts = []
        if completeness_params < total_expected:
            missing = set(expected_params.keys()) - set(actual_params.keys())
            justification_parts.append(f"Missing params: {missing}")
        if correctness_params < total_expected:
            justification_parts.append(
                f"Incorrect values: {total_expected - correctness_params}/{total_expected}"
            )
        if conformance_params < total_expected:
            justification_parts.append(
                f"Type mismatches: {total_expected - conformance_params}/{total_expected}"
            )
        if extra_params:
            justification_parts.append(f"Extra params: {extra_params}")

        if not justification_parts:
            justification = "Perfect parameter match"
        else:
            justification = "; ".join(justification_parts)

        return total_score, justification

    def _types_match(self, actual_value: Any, expected_value: Any) -> bool:
        """Check if two values have matching types, with numeric equivalence support.

        Args:
            actual_value: The actual parameter value
            expected_value: The expected parameter value

        Returns:
            True if types match or both are numeric types
        """
        # Handle exact type match
        if type(actual_value) is type(expected_value):
            return True

        # Handle numeric equivalence (int/float are considered compatible)
        return isinstance(actual_value, (int, float)) and isinstance(expected_value, (int, float))

    def _normalize_value(self, value: Any) -> str:
        """Normalize value for comparison.

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
        return str(value).strip().lower()
