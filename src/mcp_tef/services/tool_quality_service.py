import json
from collections.abc import AsyncIterator

import structlog
from pydantic import BaseModel, Field
from pydantic_ai import Agent

from mcp_tef.config.prompts import EVALUATE_TOOL_DESCRIPTION_PROMPT
from mcp_tef.models.schemas import ToolDefinition
from mcp_tef.services.json_schema_utils import extract_parameter_descriptions
from mcp_tef.services.llm_service import LLMService
from mcp_tef.services.mcp_loader import MCPLoaderService


class EvaluationDimensionResult(BaseModel):
    """
    Model for the result of evaluation along a single dimension
    (e.g. clarity, completeness, or conciseness).
    """

    score: int = Field(..., description="A score from 1 to 10 for this dimension.")
    explanation: str = Field(
        ..., description="An explanation of the reasoning for the given score."
    )


class EvaluationResult(BaseModel):
    """Output model for the tool description evaluation."""

    clarity: EvaluationDimensionResult = Field(
        ..., description="Evaluation of the clarity of the tool description."
    )
    completeness: EvaluationDimensionResult = Field(
        ..., description="Evaluation of the completeness of the tool description."
    )
    conciseness: EvaluationDimensionResult = Field(
        ..., description="Evaluation of the conciseness of the tool description."
    )
    suggested_description: str | None = Field(
        default=None,
        description="Suggested tool description (optional).",
    )


class ToolQualityResult(BaseModel):
    tool_name: str = Field(..., description="Tool name.")
    tool_description: str = Field(..., description="Original tool description.")
    evaluation_result: EvaluationResult = Field(..., description="Result of the tool evaluation.")


class ToolQualityResponse(BaseModel):
    results: list[ToolQualityResult] = Field(..., description="Tool quality results.")
    errors: list[str] | None = Field(
        default=None, description="Errors encountered during evaluation."
    )


class ToolQualityService:
    """
    Service to evaluate individual tool description quality and provide
    recommendations for improvement.
    """

    def __init__(
        self,
        mcp_loader_service: MCPLoaderService,
        llm_service: LLMService,
    ):
        self._mcp_loader_service = mcp_loader_service
        self._agent: Agent = llm_service.make_agent(EVALUATE_TOOL_DESCRIPTION_PROMPT)
        self._logger = structlog.get_logger(__name__)

    async def evaluate_server(
        self,
        server_url: str,
    ) -> list[ToolQualityResult]:
        """Evaluates all the tools for the given MCP server."""
        tools = await self._mcp_loader_service.load_tools_from_url(server_url)

        tool_definitions = []
        for tool in tools:
            input_schema = tool.get("input_schema", {})
            # Extract parameter descriptions (handles $ref)
            parameters = extract_parameter_descriptions(input_schema) if input_schema else {}

            tool_definitions.append(
                ToolDefinition(
                    name=tool["name"],
                    description=tool["description"],
                    input_schema=input_schema,
                    parameters=parameters,
                )
            )

        results = []
        async for result in self.evaluate_tools(tool_definitions):
            self._logger.debug(f"Evaluated tool {result.tool_name}:")
            self._logger.debug(json.dumps(result.evaluation_result.model_dump(), indent=2))
            results.append(result)
        return results

    async def evaluate_tools(
        self, tool_definitions: list[ToolDefinition]
    ) -> AsyncIterator[ToolQualityResult]:
        for tool in tool_definitions:
            try:
                yield await self.evaluate_tool(tool)
            except Exception as e:
                self._logger.error(
                    f"Failed to evaluate tool {tool.name}",
                    error=str(e),
                    exc_info=True,
                )
                # Skip tools that fail evaluation - they'll be reported in errors
                continue

    async def evaluate_tool(self, tool_definition: ToolDefinition) -> ToolQualityResult:
        prompt = f"""
        Evaluate the following tool descriptions on the given criteria:
        Tool Name: {tool_definition.name}
        Tool Description:
        {tool_definition.description}
        Tool Input Schema:
        {
            json.dumps(tool_definition.input_schema, indent=2)
            if tool_definition.input_schema
            else "{}"
        }

        IMPORTANT: Return ONLY valid JSON in the exact format specified. Do not include markdown code blocks, extra text, or comments.
        """
        try:
            evaluation_result = await self._agent.run(user_prompt=prompt, output_type=EvaluationResult)
            return ToolQualityResult(
                tool_name=tool_definition.name,
                tool_description=tool_definition.description,
                evaluation_result=evaluation_result.output,
            )
        except Exception as e:
            self._logger.error(
                f"LLM failed to evaluate tool {tool_definition.name}",
                error=str(e),
                exc_info=True,
            )
            raise
