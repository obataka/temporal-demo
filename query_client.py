"""
Query Client — 実行中の immortal_agent_workflow の状態をリアルタイムで取得する CLI。

Usage:
    python query_client.py <workflow_id> get_status
    python query_client.py <workflow_id> get_live_stats
    python query_client.py <workflow_id>              # 両方取得（デフォルト）
"""

import asyncio
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from temporalio.client import Client

TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "localhost:7233")

QUERY_NAMES = ["get_status", "get_live_stats"]


async def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("Usage: python query_client.py <workflow_id> [query_name]")
        print(f"Available queries: {', '.join(QUERY_NAMES)}")
        sys.exit(1)

    workflow_id = args[0]
    queries_to_run = [args[1]] if len(args) > 1 else QUERY_NAMES

    for q in queries_to_run:
        if q not in QUERY_NAMES:
            print(f"Unknown query: {q}. Available: {', '.join(QUERY_NAMES)}")
            sys.exit(1)

    client = await Client.connect(TEMPORAL_HOST)
    handle = client.get_workflow_handle(workflow_id)

    print(f"\nWorkflow: {workflow_id}")
    print("=" * 60)

    for query_name in queries_to_run:
        try:
            result = await handle.query(query_name)
            print(f"\n[{query_name}]")
            print(json.dumps(result, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"\n[{query_name}] ERROR: {e}")

    print()


if __name__ == "__main__":
    asyncio.run(main())
