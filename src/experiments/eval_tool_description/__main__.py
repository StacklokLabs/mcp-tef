"""
Main entry point for the Eval Tool Description experiment.
Example:
```
uv run python -m src.experiments.eval_tool_description
    --input_file src/experiments/eval_tool_description/input_data/mcp_tools_cleaned_sample.json
```

JSON formatted results are saved to --output_file, defaulting the ./output_data/ folder

Requires:
- An input JSON file containing MCP server and tool descriptions, see models.py.
- Environment variables for model configuration: ANTHROPIC_API_KEY.
"""

import argparse
import asyncio
import json
import logging

from dotenv import load_dotenv

from experiments.eval_tool_description.runner import Runner
from experiments.eval_tool_description.util import DateTimeEncoder

logger = logging.getLogger(__name__)


def main(input_file: str, output_file: str, debug: bool):
    if debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    logger.info(f"Running Tool Description evaluation on input file {input_file}...")

    load_dotenv()

    with open(input_file) as f:
        file_content = f.read()

    input_data = json.loads(file_content)

    asyncio.run(run_async(input_data, output_file))

    logger.info(f"Evaluation results saved to {output_file}")


async def run_async(input_data: list[dict], output_file: str):
    runner = Runner()
    with open(output_file, "w") as f:
        f.write("[\n")
        first = True
        count = 0
        try:
            async for result in runner.run(input_data):
                if not first:
                    f.write(",\n")
                first = False
                count += 1
                f.write(json.dumps(result.model_dump(), indent=2, cls=DateTimeEncoder))
                f.flush()
        except Exception:
            logger.exception(f"Error evaluating tool, terminating after {count} tools...")
        f.write("]\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Eval Tool Description")
    parser.add_argument(
        "--input_file",
        type=str,
        required=True,
        help="Path to the input file containing MCP server and tool descriptions",
    )
    parser.add_argument(
        "--output_file",
        type=str,
        default="./src/experiments/eval_tool_description/output_data/temp_eval_tool_description_results.json",
        help="Path to the output file for evaluation results",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    main(args.input_file, args.output_file, args.debug or False)
