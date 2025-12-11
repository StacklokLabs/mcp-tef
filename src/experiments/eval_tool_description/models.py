"""
Pydantic models for the eval_tool_description experiment.
"""

from pydantic import BaseModel, Field


class InputToolInfo(BaseModel):
    name: str = Field(..., min_length=1, description="The name of the tool.")
    description: str = Field(..., min_length=1, description="The description of the tool.")
    parameter: dict[str, str] | None = Field(
        ..., description="The parameters and their descriptions."
    )


class InputServerInfo(BaseModel):
    name: str = Field(..., min_length=1, description="The name of the MCP server.")
    description: str = Field(..., min_length=1, description="The description of the MCP server.")
    url: str | None = Field(..., description="The URL of the MCP server.")
    readme_file: str | None = Field(..., description="The README file content of the MCP server.")
    summary: str | None = Field(..., description="A brief summary of the MCP server.")
    tools: list[InputToolInfo] = Field(
        ..., description="A list of tools exposed by the MCP server."
    )


class EvaluationDimensionResult(BaseModel):
    """
    Model for the result of evaluation along a single dimension
    (e.g. clarity, completeness, or conciseness).
    """

    score: int = Field(..., description="A score from 1 to 10 for this dimension.")
    explanation: str = Field(
        ..., description="An explanation of the reasoning for the given score."
    )


class SuggestedValues(BaseModel):
    """
    Model for the suggested tool name and description, along with the explanation
    for the suggestion.
    """

    name: str = Field(..., description="Suggested tool name.")
    description: str = Field(..., description="Suggested tool description.")
    explanation: str = Field(
        ...,
        description="Explanation of the reasoning behind the suggested tool name and description.",
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
    sugggested_values: SuggestedValues = Field(
        ..., description="Suggested tool name and description based on the evaluation."
    )


class RunResult(BaseModel):
    tool_info: InputToolInfo = Field(..., description="The tool information that was evaluated.")
    server_name: str = Field(..., description="The name of the MCP server.")
    server_description: str = Field(..., description="The description of the MCP server.")
    server_summary: str | None = Field(..., description="A brief summary of the MCP server.")
    evaluation: EvaluationResult = Field(
        ..., description="The evaluation results for the tool description."
    )
