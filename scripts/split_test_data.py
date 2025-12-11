#!/usr/bin/env python3
"""Generate test data chunks from mcp_tools_cleaned.json.

This script splits the full test data into smaller chunks for consistent reproducible testing.
It creates 5, 10, and 25 server chunks using the first N servers from the dataset.
"""

import json
from pathlib import Path


def split_test_data() -> None:
    """Split mcp_tools_cleaned.json into smaller test chunks."""
    # Paths
    repo_root = Path(__file__).parent.parent
    input_file = repo_root / "tests" / "data" / "mcp_tools_cleaned.json"
    output_dir = repo_root / "tests" / "data"

    # Read full dataset
    print(f"Reading {input_file}...")
    with open(input_file) as f:
        all_servers = json.load(f)

    print(f"Loaded {len(all_servers)} servers")

    # Create chunks
    chunks = [
        (5, "mcp_tools_5.json"),
        (10, "mcp_tools_10.json"),
        (25, "mcp_tools_25.json"),
    ]

    for num_servers, filename in chunks:
        if num_servers > len(all_servers):
            print(
                f"⚠️  Warning: Requested {num_servers} servers but only {len(all_servers)} available"
            )
            continue

        chunk_data = all_servers[:num_servers]
        output_file = output_dir / filename

        # Write chunk
        with open(output_file, "w") as f:
            json.dump(chunk_data, f, indent=2)

        # Count tools
        total_tools = sum(len(server.get("tools", [])) for server in chunk_data)
        print(f"✓ Created {filename}: {num_servers} servers, {total_tools} tools")

    print("\n✅ Test data chunks created successfully!")


if __name__ == "__main__":
    split_test_data()
