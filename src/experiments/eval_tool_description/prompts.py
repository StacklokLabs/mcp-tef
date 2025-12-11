"""
Contains prompt templates for evaluating tool descriptions.
"""

EVALAUTE_TOOL_DESCRIPTION_PROMPT = """
You are given the descriptions of an MCP server and the tools it exposes.
For each server description and tool description pair, evaluate it on the following criteria:
1. Clarity: Is the tool description clear and easy to understand?
    - Does the description convey what the tool does?
    - Does the description convey when the tool should be used?
    - Does the description convey how to interpret the output?
2. Completeness: Does the tool description cover all necessary aspects of the tool?
    - Are tool parameters fully described?
    - Does the description include good usage examples?
3. Conciseness: Is the tool description concise without unnecessary information?

Provide a score from 1 to 10 for each criterion, along with a brief explanation for each score.
Then, provide suggested values for the tool name and description that would improve the its
measurement against the given criteria. Provide a natural language explanation of the reasoning
behind the suggested values.

Return the results in the following JSON format:
{
  "clarity": {
    "score": <int>,
    "explanation": <string>
  },
  "completeness": {
    "score": <int>,
    "explanation": <string>
  },
  "conciseness": {
    "score": <int>,
    "explanation": <string>
  }
  "suggested_values": {
    "name": <string>,
    "description": <string>,
    "explanation": <string>
  }
}
"""
