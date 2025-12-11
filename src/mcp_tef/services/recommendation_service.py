"""Recommendation service for generating differentiation recommendations."""

from typing import Any

import structlog

from mcp_tef.api.errors import LLMProviderError
from mcp_tef.models.schemas import (
    DifferentiationIssue,
    DifferentiationRecommendation,
    NormalizedTool,
    RecommendationItem,
)
from mcp_tef.services.llm_service import LLMService
from mcp_tef.services.similarity_service import calculate_jaccard_similarity

logger = structlog.get_logger(__name__)


class RecommendationService:
    """Service for detecting differentiation issues and generating recommendations."""

    def __init__(self, llm_service: LLMService | None = None):
        """Initialize recommendation service.

        Args:
            llm_service: Optional LLM service for generating recommendations
        """
        self.llm_service = llm_service

    @staticmethod
    def _get_tool_attr(tool: NormalizedTool | dict[str, Any], attr: str) -> Any:
        """Get attribute from tool, whether it's a NormalizedTool or dict.

        Args:
            tool: Tool definition (NormalizedTool object or dict)
            attr: Attribute name to retrieve

        Returns:
            Attribute value
        """
        if isinstance(tool, dict):
            return tool.get(attr)
        return getattr(tool, attr, None)

    def detect_issues(
        self,
        tool_a: NormalizedTool | dict[str, Any],
        tool_b: NormalizedTool | dict[str, Any],
        similarity_score: float,
    ) -> list[DifferentiationIssue]:
        """Detect differentiation issues between two tools using rule-based analysis.

        Args:
            tool_a: First tool definition
            tool_b: Second tool definition
            similarity_score: Similarity score between tools

        Returns:
            List of identified issues
        """
        issues = []

        # Issue 1: Terminology overlap
        desc_a = self._get_tool_attr(tool_a, "description") or ""
        desc_b = self._get_tool_attr(tool_b, "description") or ""
        desc_a_words = set(desc_a.lower().split())
        desc_b_words = set(desc_b.lower().split())
        overlap = desc_a_words.intersection(desc_b_words)

        if len(overlap) > 5:  # More than 5 common words
            issues.append(
                DifferentiationIssue(
                    issue_type="terminology_overlap",
                    description=f"Descriptions share {len(overlap)} common terms",
                    tool_a_id=self._get_tool_attr(tool_a, "id"),
                    tool_b_id=self._get_tool_attr(tool_b, "id"),
                    evidence={"overlapping_terms": list(overlap)[:10]},
                )
            )

        # Issue 2: Naming clarity
        name_a = (self._get_tool_attr(tool_a, "name") or "").lower()
        name_b = (self._get_tool_attr(tool_b, "name") or "").lower()

        # Check for very similar names
        name_similarity = calculate_jaccard_similarity(
            set(name_a.replace("_", " ").split()),
            set(name_b.replace("_", " ").split()),
        )

        if name_similarity > 0.5:
            issues.append(
                DifferentiationIssue(
                    issue_type="naming_clarity",
                    description="Tool names are very similar",
                    tool_a_id=self._get_tool_attr(tool_a, "id"),
                    tool_b_id=self._get_tool_attr(tool_b, "id"),
                    evidence={"name_similarity": name_similarity},
                )
            )

        # Issue 3: Parameter uniqueness
        params_a = set((self._get_tool_attr(tool_a, "parameters") or {}).keys())
        params_b = set((self._get_tool_attr(tool_b, "parameters") or {}).keys())
        param_overlap = params_a.intersection(params_b)

        if param_overlap and len(param_overlap) >= min(len(params_a), len(params_b)) * 0.5:
            issues.append(
                DifferentiationIssue(
                    issue_type="parameter_uniqueness",
                    description=f"Tools share {len(param_overlap)} parameter names",
                    tool_a_id=self._get_tool_attr(tool_a, "id"),
                    tool_b_id=self._get_tool_attr(tool_b, "id"),
                    evidence={"shared_parameters": list(param_overlap)},
                )
            )

        # Issue 4: Scope clarity
        if similarity_score > 0.85:
            # Check if descriptions lack specific domain/scope indicators
            scope_keywords = [
                "for",
                "in",
                "from",
                "to",
                "with",
                "using",
                "within",
                "specific",
            ]
            has_scope_a = any(kw in desc_a.lower() for kw in scope_keywords)
            has_scope_b = any(kw in desc_b.lower() for kw in scope_keywords)

            if not has_scope_a or not has_scope_b:
                issues.append(
                    DifferentiationIssue(
                        issue_type="scope_clarity",
                        description="Tool purposes are not clearly differentiated",
                        tool_a_id=self._get_tool_attr(tool_a, "id"),
                        tool_b_id=self._get_tool_attr(tool_b, "id"),
                        evidence={
                            "high_similarity": similarity_score,
                            "lacks_scope_indicators": True,
                        },
                    )
                )

        return issues

    async def generate_recommendations(
        self,
        tool_a: NormalizedTool | dict[str, Any],
        tool_b: NormalizedTool | dict[str, Any],
        issues: list[DifferentiationIssue],
    ) -> list[RecommendationItem]:
        """Generate actionable recommendations for identified issues.

        Args:
            tool_a: First tool definition
            tool_b: Second tool definition
            issues: List of identified issues

        Returns:
            List of recommendations
        """
        recommendations = []

        for issue in issues:
            # Generate rule-based recommendations with LLM-enhanced descriptions
            if issue.issue_type == "terminology_overlap":
                # Generate improved descriptions for both tools
                revised_desc_a = await self._generate_revised_description(
                    tool_a,
                    tool_b,
                    "Remove overlapping terminology and emphasize unique aspects",
                )
                revised_desc_b = await self._generate_revised_description(
                    tool_b,
                    tool_a,
                    "Remove overlapping terminology and emphasize unique aspects",
                )

                recommendations.append(
                    RecommendationItem(
                        issue=issue.description,
                        tool_id=self._get_tool_attr(tool_a, "id"),
                        recommendation=(
                            "Use distinct terminology in description. "
                            "Focus on what makes this tool unique."
                        ),
                        rationale=("Overlapping terminology confuses LLMs during tool selection"),
                        priority="high",
                        revised_description=revised_desc_a,
                        apply_commands=self._generate_apply_commands(tool_a, revised_desc_a),
                    )
                )
                recommendations.append(
                    RecommendationItem(
                        issue=issue.description,
                        tool_id=self._get_tool_attr(tool_b, "id"),
                        recommendation=(
                            "Use distinct terminology in description. "
                            "Focus on what makes this tool unique."
                        ),
                        rationale=("Overlapping terminology confuses LLMs during tool selection"),
                        priority="high",
                        revised_description=revised_desc_b,
                        apply_commands=self._generate_apply_commands(tool_b, revised_desc_b),
                    )
                )

            elif issue.issue_type == "naming_clarity":
                # Suggest renaming one tool with improved description
                tool_b_name = self._get_tool_attr(tool_b, "name")
                tool_a_name = self._get_tool_attr(tool_a, "name")
                revised_desc = await self._generate_revised_description(
                    tool_a,
                    tool_b,
                    f"Make the description more specific to differentiate from '{tool_b_name}'",
                )

                recommendations.append(
                    RecommendationItem(
                        issue=issue.description,
                        tool_id=self._get_tool_attr(tool_a, "id"),
                        recommendation=f"Consider renaming '{tool_a_name}' to be more specific",
                        rationale="Similar names increase confusion during tool selection",
                        priority="medium",
                        revised_description=revised_desc,
                        apply_commands=self._generate_apply_commands(tool_a, revised_desc),
                    )
                )

            elif issue.issue_type == "parameter_uniqueness":
                # Generate improved descriptions emphasizing parameter differences
                revised_desc_a = await self._generate_revised_description(
                    tool_a,
                    tool_b,
                    "Clarify how the parameters are used differently from the other tool",
                )
                revised_desc_b = await self._generate_revised_description(
                    tool_b,
                    tool_a,
                    "Clarify how the parameters are used differently from the other tool",
                )

                recommendations.append(
                    RecommendationItem(
                        issue=issue.description,
                        tool_id=self._get_tool_attr(tool_a, "id"),
                        recommendation=(
                            "Clarify how parameters are used uniquely in this tool's context"
                        ),
                        rationale="Shared parameter names suggest overlapping functionality",
                        priority="medium",
                        revised_description=revised_desc_a,
                        apply_commands=self._generate_apply_commands(tool_a, revised_desc_a),
                    )
                )
                recommendations.append(
                    RecommendationItem(
                        issue=issue.description,
                        tool_id=self._get_tool_attr(tool_b, "id"),
                        recommendation=(
                            "Clarify how parameters are used uniquely in this tool's context"
                        ),
                        rationale="Shared parameter names suggest overlapping functionality",
                        priority="medium",
                        revised_description=revised_desc_b,
                        apply_commands=self._generate_apply_commands(tool_b, revised_desc_b),
                    )
                )

            elif issue.issue_type == "scope_clarity":
                # Generate improved descriptions with clearer scope
                revised_desc_a = await self._generate_revised_description(
                    tool_a,
                    tool_b,
                    "Add specific details about the scope, domain, or use cases",
                )
                revised_desc_b = await self._generate_revised_description(
                    tool_b,
                    tool_a,
                    "Add specific details about the scope, domain, or use cases",
                )

                tool_a_name = self._get_tool_attr(tool_a, "name")
                tool_b_name = self._get_tool_attr(tool_b, "name")
                recommendations.append(
                    RecommendationItem(
                        issue=issue.description,
                        tool_id=self._get_tool_attr(tool_a, "id"),
                        recommendation=(
                            f"Clarify the specific scope/domain of '{tool_a_name}' "
                            "in the description"
                        ),
                        rationale="Unclear scope makes it hard to distinguish from similar tools",
                        priority="high",
                        revised_description=revised_desc_a,
                        apply_commands=self._generate_apply_commands(tool_a, revised_desc_a),
                    )
                )
                recommendations.append(
                    RecommendationItem(
                        issue=issue.description,
                        tool_id=self._get_tool_attr(tool_b, "id"),
                        recommendation=(
                            f"Clarify the specific scope/domain of '{tool_b_name}' "
                            "in the description"
                        ),
                        rationale="Unclear scope makes it hard to distinguish from similar tools",
                        priority="high",
                        revised_description=revised_desc_b,
                        apply_commands=self._generate_apply_commands(tool_b, revised_desc_b),
                    )
                )

        return recommendations

    async def _generate_revised_description(
        self,
        tool: NormalizedTool,
        other_tool: NormalizedTool,
        guidance: str,
    ) -> str:
        """Generate LLM-improved description for a tool.

        Args:
            tool: Tool to generate description for
            other_tool: Other tool to differentiate from
            guidance: Specific guidance for improvement

        Returns:
            Improved tool description
        """
        if not self.llm_service:
            # Fall back to slightly improved rule-based description
            return (
                f"{tool.description} "
                f"(Note: Use this tool specifically for {tool.name.replace('_', ' ')}, "
                f"not for {other_tool.name.replace('_', ' ')})"
            )

        # Build context about the tool's parameters
        params_summary = (
            "No parameters"
            if not tool.parameters
            else (f"Parameters: {', '.join(tool.parameters.keys())}")
        )
        other_params_summary = (
            "No parameters"
            if not other_tool.parameters
            else (f"Parameters: {', '.join(other_tool.parameters.keys())}")
        )

        # Create system prompt for the agent
        system_prompt = """
You are an expert at writing clear, concise tool descriptions for LLM-based tool selection systems.

Your goal is to help differentiate similar tools by improving their descriptions.

Guidelines:
- Keep descriptions concise (1-2 sentences)
- Focus on what makes the tool unique
- Use specific terminology that distinguishes it from similar tools
- Avoid generic phrases
- Highlight key differentiators in use cases, scope, or domain
- Return ONLY the improved description text, nothing else"""

        # Create the user prompt with context
        user_prompt = f"""
Improve the description for this tool to better differentiate it from a similar tool.

TOOL TO IMPROVE:
Name: {tool.name}
Current Description: {tool.description}
{params_summary}

SIMILAR TOOL TO DIFFERENTIATE FROM:
Name: {other_tool.name}
Description: {other_tool.description}
{other_params_summary}

SPECIFIC GUIDANCE:
{guidance}

Provide an improved description that clearly differentiates this tool:"""

        try:
            # Create an agent with the system prompt
            # Use output_type=str to accept plain text responses (important for Ollama models)
            agent = self.llm_service.make_agent(system_prompt=system_prompt, output_type=str)

            # Run the agent to generate the improved description
            result = await agent.run(user_prompt)

            # Extract the text response
            improved_description = str(result.output).strip()

            logger.info(
                "Generated improved description via LLM",
                tool_name=tool.name,
                original_length=len(tool.description),
                improved_length=len(improved_description),
            )

            return improved_description

        except (LLMProviderError, TimeoutError) as e:
            logger.warning(
                "Failed to generate LLM description, using fallback",
                tool_name=tool.name,
                error=str(e),
            )
            return (
                f"{tool.description} "
                f"(Note: Use this tool specifically for {tool.name.replace('_', ' ')}, "
                f"not for {other_tool.name.replace('_', ' ')})"
            )

    def _generate_apply_commands(
        self,
        tool: NormalizedTool,
        revised_description: str,
    ) -> list[str]:
        """Generate executable commands or JSON patches to apply changes.

        Args:
            tool: Tool definition
            revised_description: Revised description text

        Returns:
            List of commands/patches to apply the change
        """
        tool_name = tool.name
        server_url = tool.server_url or "unknown"

        # Generate both command-line style and JSON patch format
        commands = []

        # Command-line style (if MCP server has CLI)
        if server_url and server_url != "unknown":
            commands.append(
                f"thv dummy update config --server {server_url} "
                f"--tool {tool_name} "
                f'--description "{revised_description}"'
            )

        # JSON Patch format (RFC 6902)
        import json

        json_patch = {
            "op": "replace",
            "path": f"/tools/{tool_name}/description",
            "value": revised_description,
        }
        commands.append(json.dumps(json_patch))

        # Direct Python dictionary update format (for programmatic use)
        commands.append(
            f"tool_definition['{tool_name}']['description'] = "
            f'"{revised_description.replace(chr(34), chr(92) + chr(34))}"'
        )

        return commands

    async def analyze_and_recommend(
        self,
        tool_a: NormalizedTool | dict[str, Any],
        tool_b: NormalizedTool | dict[str, Any],
        similarity_score: float,
    ) -> DifferentiationRecommendation:
        """Analyze tool pair and generate differentiation recommendations.

        Args:
            tool_a: First tool definition
            tool_b: Second tool definition
            similarity_score: Similarity score between tools

        Returns:
            Differentiation recommendation with issues and suggestions
        """
        tool_a_id = self._get_tool_attr(tool_a, "id")
        tool_b_id = self._get_tool_attr(tool_b, "id")
        logger.info(
            f"Generating recommendations for {tool_a_id} and {tool_b_id} "
            f"(similarity={similarity_score:.3f})"
        )

        # Detect issues
        issues = self.detect_issues(tool_a, tool_b, similarity_score)

        # Generate recommendations
        recommendations = await self.generate_recommendations(tool_a, tool_b, issues)

        return DifferentiationRecommendation(
            tool_pair=[tool_a_id, tool_b_id],
            similarity_score=similarity_score,
            issues=issues,
            recommendations=recommendations,
        )
