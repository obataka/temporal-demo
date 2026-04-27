"""
Resilience Test 専用 Worker。
resilience-demo-queue のみを listen し、immortal_agent_workflow だけ処理する。
resilience_test.py のサブプロセスとして起動される。
"""

import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

from temporalio.client import Client
from temporalio.worker import Worker

from activities.llm_activity import call_llm_activity
from activities.mock_activity import call_mock_llm_activity
from workflows.immortal_agent_workflow import immortal_agent_workflow

TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = os.environ.get("RESILIENCE_TASK_QUEUE", "resilience-demo-queue")


async def main() -> None:
    client = await Client.connect(TEMPORAL_HOST)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[immortal_agent_workflow],
        activities=[call_llm_activity, call_mock_llm_activity],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
