"""
Runner class for the Eval Tool Description experiment.
This class is responsible for executing the evaluation logic using an AI agent.
"""

import json
import logging
import os
from collections.abc import AsyncIterator
from dataclasses import asdict

from pydantic_ai import AgentRunResult
from pydantic_ai.agent import Agent

from experiments.eval_tool_description.models import (
    EvaluationResult,
    InputServerInfo,
    InputToolInfo,
    RunResult,
)
from experiments.eval_tool_description.prompts import EVALAUTE_TOOL_DESCRIPTION_PROMPT
from experiments.eval_tool_description.util import DateTimeEncoder

MODEL = "anthropic:claude-sonnet-4-5"


class Runner:
    def __init__(self):
        api_key = os.environ.get("ANTHROPIC_API_KEY", None)
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")

        self._logger = logging.getLogger(__name__)
        self._agent = Agent(
            model=MODEL,
            system_prompt=EVALAUTE_TOOL_DESCRIPTION_PROMPT,
            model_settings={"temperature": 0.1},
        )

    async def run(self, input_data: list[dict]) -> AsyncIterator[RunResult]:
        for row in input_data:
            server_info = InputServerInfo(**row)
            self._logger.info(f"Evaluating tools for server: {server_info.name}")
            for tool in server_info.tools:
                agent_result = await self._evaluate_tool_description(tool, server_info)
                # output_json = None
                # with contextlib.suppress(json.JSONDecodeError):
                #     output_json = json.loads(eval_result.output)

                # if output_json is None:
                #     stripped_output = (
                #         eval_result.output.removeprefix("```json")
                #         .removesuffix("```")
                #         .strip()
                #     )
                #     try:
                #         output_json = json.loads(stripped_output)
                #     except json.JSONDecodeError:
                #         self._logger.warning(
                #             f"Agent output for server '{server_info.name}' is not JSON: \n"
                #             + f"{eval_result.output}"
                #         )

                # Log results
                self._logger.info(f"Evaluated tool '{tool.name}' for server '{server_info.name}':")
                self._logger.debug(
                    f"    Usage:\n{json.dumps(asdict(agent_result.usage()), indent=2)}"
                )
                self._logger.debug("    Messages:\n")
                for message in agent_result.all_messages():
                    self._logger.debug(
                        f"{json.dumps(asdict(message), indent=2, cls=DateTimeEncoder)}"
                    )

                yield RunResult(
                    tool_info=tool,
                    server_name=server_info.name,
                    server_description=server_info.description,
                    server_summary=server_info.summary,
                    evaluation=agent_result.output,
                )

    async def _evaluate_tool_description(
        self, tool: InputToolInfo, server: InputServerInfo
    ) -> AgentRunResult:
        prompt = f"""
        Evaluate the following tool descriptions on the given criteria:
        Server Name: {server.name}
        Server Description:
        {server.description}

        Tool Name: {tool.name}
        Tool Description:
        {tool.description}
        Tool Parameters:
        {json.dumps(tool.parameter, indent=2) if tool.parameter else "{}"}
        """

        # Run the prompt without message_history
        return await self._agent.run(user_prompt=prompt, output_type=EvaluationResult)
