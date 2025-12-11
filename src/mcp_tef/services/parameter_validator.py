"""Parameter validation service for evaluating LLM parameter extraction."""

from typing import Any

import structlog

from mcp_tef.models.evaluation_models import ParameterComparison, ParameterValidationResult
from mcp_tef.services.json_schema_utils import resolve_refs

logger = structlog.get_logger(__name__)


class ParameterValidator:
    """Service for validating parameters extracted by LLM."""

    def validate_parameters(
        self,
        tool_schema: dict[str, Any],
        expected_parameters: dict[str, Any] | None,
        extracted_parameters: dict[str, Any] | None,
    ) -> ParameterValidationResult:
        """Validate parameters extracted by LLM.

        Args:
            tool_schema: Tool input schema (JSON Schema, may contain $ref)
            expected_parameters: Expected parameter values from test case
            extracted_parameters: Parameters extracted by LLM

        Returns:
            Parameter validation result with completeness, correctness, and conformance
        """
        extracted_parameters = extracted_parameters or {}
        expected_parameters = expected_parameters or {}

        # Resolve any $ref references in the schema
        resolved_schema = resolve_refs(tool_schema)

        # Get schema properties and required fields
        schema_properties = resolved_schema.get("properties", {})
        required_fields = resolved_schema.get("required", [])

        # Build comparisons for expected parameters
        comparisons = self._build_comparisons(
            expected_parameters, extracted_parameters, schema_properties
        )

        # Calculate completeness (required params present)
        completeness = self._calculate_completeness(
            required_fields, extracted_parameters, expected_parameters
        )

        # Calculate correctness (expected values match)
        correctness = self._calculate_correctness(comparisons)

        # Check type conformance (all params match schema types)
        type_conformance = self._check_type_conformance(extracted_parameters, schema_properties)

        # Find hallucinated parameters (params not in schema)
        hallucinated = self._find_hallucinated_parameters(extracted_parameters, schema_properties)

        # Find missing required parameters
        missing_required = self._find_missing_required(
            required_fields, extracted_parameters, expected_parameters
        )

        return ParameterValidationResult(
            comparisons=comparisons,
            completeness=completeness,
            correctness=correctness,
            type_conformance=type_conformance,
            hallucinated_parameters=hallucinated,
            missing_required=missing_required,
        )

    def _build_comparisons(
        self,
        expected: dict[str, Any],
        extracted: dict[str, Any],
        schema_properties: dict[str, Any],
    ) -> list[ParameterComparison]:
        """Build individual parameter comparisons.

        Args:
            expected: Expected parameter values
            extracted: Extracted parameter values
            schema_properties: Schema properties for type checking

        Returns:
            List of parameter comparisons
        """
        comparisons = []

        for param_name, expected_value in expected.items():
            actual_value = extracted.get(param_name)
            is_present = param_name in extracted

            # Normalize and compare values
            is_correct = self._values_match(expected_value, actual_value)

            # Get expected type from schema
            param_schema = schema_properties.get(param_name, {})
            expected_type = param_schema.get("type", "unknown")

            # Get actual type
            actual_type = type(actual_value).__name__ if actual_value is not None else None

            # Check type match
            type_matches = self._type_matches_schema(actual_value, param_schema)

            comparisons.append(
                ParameterComparison(
                    parameter_name=param_name,
                    expected_value=expected_value,
                    actual_value=actual_value,
                    is_present=is_present,
                    is_correct=is_correct,
                    type_matches=type_matches,
                    expected_type=expected_type,
                    actual_type=actual_type,
                )
            )

        return comparisons

    def _calculate_completeness(
        self,
        required_fields: list[str],
        extracted: dict[str, Any],
        expected: dict[str, Any],
    ) -> float:
        """Calculate parameter completeness.

        Completeness = (Present Required Params) / (Total Required Params)

        Args:
            required_fields: Required fields from schema
            extracted: Extracted parameters
            expected: Expected parameters

        Returns:
            Completeness ratio (0.0 to 1.0)
        """
        if not required_fields:
            return 1.0

        # Only consider required fields that are in expected parameters
        relevant_required = [f for f in required_fields if f in expected]

        if not relevant_required:
            return 1.0

        present_count = sum(1 for field in relevant_required if field in extracted)
        return present_count / len(relevant_required)

    def _calculate_correctness(self, comparisons: list[ParameterComparison]) -> float:
        """Calculate parameter correctness.

        Correctness = (Correct Params) / (Total Expected Params)

        Args:
            comparisons: Parameter comparisons

        Returns:
            Correctness ratio (0.0 to 1.0)
        """
        if not comparisons:
            return 1.0

        correct_count = sum(1 for comp in comparisons if comp.is_correct)
        return correct_count / len(comparisons)

    def _check_type_conformance(
        self, extracted: dict[str, Any], schema_properties: dict[str, Any]
    ) -> bool:
        """Check if all extracted parameters match schema types.

        Args:
            extracted: Extracted parameters
            schema_properties: Schema properties

        Returns:
            True if all params match types, False otherwise
        """
        for param_name, param_value in extracted.items():
            param_schema = schema_properties.get(param_name, {})
            if not self._type_matches_schema(param_value, param_schema):
                return False
        return True

    def _find_hallucinated_parameters(
        self, extracted: dict[str, Any], schema_properties: dict[str, Any]
    ) -> list[str]:
        """Find parameters not in schema (hallucinations).

        Args:
            extracted: Extracted parameters
            schema_properties: Schema properties

        Returns:
            List of hallucinated parameter names
        """
        return [param_name for param_name in extracted if param_name not in schema_properties]

    def _find_missing_required(
        self,
        required_fields: list[str],
        extracted: dict[str, Any],
        expected: dict[str, Any],
    ) -> list[str]:
        """Find missing required parameters.

        Args:
            required_fields: Required fields from schema
            extracted: Extracted parameters
            expected: Expected parameters

        Returns:
            List of missing required parameter names
        """
        relevant_required = [f for f in required_fields if f in expected]
        return [field for field in relevant_required if field not in extracted]

    def _values_match(self, expected: Any, actual: Any) -> bool:
        """Check if two values match with normalization.

        Handles case-insensitive string comparison and type coercion.

        Args:
            expected: Expected value
            actual: Actual value

        Returns:
            True if values match (after normalization)
        """
        if actual is None:
            return False

        # Direct equality check
        if expected == actual:
            return True

        # String comparison (case-insensitive)
        if isinstance(expected, str) and isinstance(actual, str):
            return expected.lower().strip() == actual.lower().strip()

        # Number comparison (allow int/float equivalence)
        if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
            return float(expected) == float(actual)

        # Boolean comparison (case-insensitive string to bool)
        if isinstance(expected, bool) and isinstance(actual, str):
            return expected == (actual.lower() in ["true", "yes", "1"])

        return False

    def _type_matches_schema(self, value: Any, param_schema: dict[str, Any]) -> bool:
        """Check if value type matches schema type.

        Args:
            value: Parameter value
            param_schema: Parameter schema

        Returns:
            True if type matches, False otherwise
        """
        if not param_schema or value is None:
            return True

        schema_type = param_schema.get("type")
        if not schema_type:
            return True

        # Map Python types to JSON Schema types
        type_mapping = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
        }

        expected_python_type = type_mapping.get(schema_type)
        if not expected_python_type:
            return True

        return isinstance(value, expected_python_type)
