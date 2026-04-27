"""
Signal Client — 実行中の immortal_agent_workflow に Signal を送る CLI ツール。

Usage:
    python signal_client.py <workflow_id> add_task "タスク内容"
    python signal_client.py <workflow_id> inject_human_feedback "簡潔に3行以内で回答せよ"
    python signal_client.py <workflow_id> update_task_priority 9
    python signal_client.py <workflow_id> stop_agent
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from temporalio.client import Client

TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "localhost:7233")

SIGNAL_REGISTRY = {
    "add_task": str,
    "inject_human_feedback": str,
    "update_task_priority": int,
    "stop_agent": None,
}


async def main() -> None:
    args = sys.argv[1:]
    if len(args) < 2:
        print("Usage: python signal_client.py <workflow_id> <signal_name> [arg]")
        print(f"Available signals: {', '.join(SIGNAL_REGISTRY)}")
        sys.exit(1)

    workflow_id, signal_name = args[0], args[1]
    raw_arg = args[2] if len(args) > 2 else None

    if signal_name not in SIGNAL_REGISTRY:
        print(f"Unknown signal: {signal_name}")
        print(f"Available: {', '.join(SIGNAL_REGISTRY)}")
        sys.exit(1)

    client = await Client.connect(TEMPORAL_HOST)
    handle = client.get_workflow_handle(workflow_id)

    arg_type = SIGNAL_REGISTRY[signal_name]
    if arg_type is None:
        await handle.signal(signal_name)
        print(f"Signal sent: {signal_name} → {workflow_id}")
    elif raw_arg is None:
        print(f"Signal '{signal_name}' requires an argument.")
        sys.exit(1)
    else:
        typed_arg = arg_type(raw_arg)
        await handle.signal(signal_name, typed_arg)
        print(f"Signal sent: {signal_name}({typed_arg!r}) → {workflow_id}")


if __name__ == "__main__":
    asyncio.run(main())
