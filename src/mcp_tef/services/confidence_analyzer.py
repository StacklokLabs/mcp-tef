"""Confidence score analysis and categorization service."""

import structlog

from mcp_tef.models.evaluation_models import ConfidenceAnalysis

logger = structlog.get_logger(__name__)


class ConfidenceAnalyzer:
    """Service for analyzing LLM confidence scores and generating recommendations."""

    # Confidence thresholds for categorization
    HIGH_CONFIDENCE_THRESHOLD = 0.7
    LOW_CONFIDENCE_THRESHOLD = 0.4

    def analyze_confidence(
        self,
        confidence_score: float | None,
        tool_selection_correct: bool,
    ) -> ConfidenceAnalysis:
        """Analyze confidence score and categorize result.

        Categories:
        - robust: High confidence + correct selection (tool description is clear)
        - needs_clarity: Low confidence + correct selection (works but could be clearer)
        - misleading: High confidence + incorrect selection (CRITICAL - description is misleading)

        Args:
            confidence_score: LLM confidence score (0-1) or None if unavailable
            tool_selection_correct: Whether the correct tool was selected

        Returns:
            Confidence analysis with category and recommendations
        """
        # Handle missing confidence scores gracefully
        if confidence_score is None:
            logger.debug("Confidence score unavailable from LLM provider")
            return ConfidenceAnalysis(
                confidence_score=None,
                tool_selection_correct=tool_selection_correct,
                confidence_category=None,
                recommendations=self._generate_recommendations_no_confidence(
                    tool_selection_correct
                ),
            )

        # Categorize based on confidence and correctness
        category = self._categorize_confidence(confidence_score, tool_selection_correct)

        # Generate recommendations based on pattern
        recommendations = self._generate_recommendations(
            confidence_score, tool_selection_correct, category
        )

        logger.info(
            f"Confidence analysis: score={confidence_score:.2f}, "
            f"correct={tool_selection_correct}, category={category}"
        )

        return ConfidenceAnalysis(
            confidence_score=confidence_score,
            tool_selection_correct=tool_selection_correct,
            confidence_category=category,
            recommendations=recommendations,
        )

    def _categorize_confidence(self, confidence_score: float, tool_selection_correct: bool) -> str:
        """Categorize confidence into robust/needs_clarity/misleading.

        Args:
            confidence_score: Confidence score (0-1)
            tool_selection_correct: Whether correct tool was selected

        Returns:
            Category string
        """
        high_confidence = confidence_score >= self.HIGH_CONFIDENCE_THRESHOLD
        low_confidence = confidence_score < self.LOW_CONFIDENCE_THRESHOLD

        if high_confidence and tool_selection_correct:
            return "robust"

        if low_confidence and tool_selection_correct:
            return "needs_clarity"

        if high_confidence and not tool_selection_correct:
            return "misleading"

        # Medium confidence with incorrect selection - also needs clarity
        return "needs_clarity"

    def _generate_recommendations(
        self, confidence_score: float, tool_selection_correct: bool, category: str
    ) -> list[str]:
        """Generate recommendations based on confidence pattern.

        Args:
            confidence_score: Confidence score
            tool_selection_correct: Whether correct tool selected
            category: Confidence category

        Returns:
            List of recommendation strings
        """
        recommendations = []

        if category == "robust":
            recommendations.append(
                f"Tool description is clear and effective (confidence: {confidence_score:.2f})"
            )

        elif category == "needs_clarity":
            if tool_selection_correct:
                recommendations.append(
                    f"Tool works but confidence is low ({confidence_score:.2f}). "
                    "Consider adding more examples or clarifying the description."
                )
            else:
                recommendations.append(
                    f"Wrong tool selected with medium confidence ({confidence_score:.2f}). "
                    "Review tool description for ambiguity."
                )

        elif category == "misleading":
            recommendations.append(
                f"CRITICAL: Wrong tool selected with high confidence ({confidence_score:.2f}). "
                "Tool description is likely misleading - review and rewrite immediately."
            )

        return recommendations

    def _generate_recommendations_no_confidence(self, tool_selection_correct: bool) -> list[str]:
        """Generate recommendations when confidence score is unavailable.

        Args:
            tool_selection_correct: Whether correct tool was selected

        Returns:
            List of recommendation strings
        """
        if tool_selection_correct:
            return ["Correct tool selected (confidence score not available from LLM provider)"]
        return [
            "Wrong tool selected. Consider reviewing tool description clarity "
            "(confidence score not available from LLM provider)."
        ]
