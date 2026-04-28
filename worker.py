"""
Temporal Worker — Docker コンテナとして起動し、docker-compose logs で JSON ログを確認できる。

Usage（ローカル）:
    python worker.py

Usage（Docker）:
    docker compose up --build
"""

import asyncio
import os

import structlog
from dotenv import load_dotenv
from prometheus_client import start_http_server

load_dotenv()

from temporalio.client import Client
from temporalio.worker import Worker

from activities.llm_activity import call_llm_activity, call_llm_with_context_activity
from activities.mock_activity import call_mock_llm_activity
from workflows.ai_agent_workflow import ai_agent_workflow
from workflows.comparison_workflow import comparison_workflow
from workflows.hitl_agent_workflow import hitl_agent_workflow
from workflows.immortal_agent_workflow import immortal_agent_workflow

TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = "llm-task-queue"

logger = structlog.get_logger()


async def connect_with_retry(host: str, max_attempts: int = 15) -> Client:
    """Temporal Server の起動を待ちながら接続を試みる（Docker起動順序の吸収）。"""
    for attempt in range(1, max_attempts + 1):
        try:
            client = await Client.connect(host)
            logger.info("temporal_connected", host=host)
            return client
        except Exception as e:
            logger.warning("temporal_connect_retry",
                           attempt=attempt, max=max_attempts, error=str(e)[:60])
            if attempt < max_attempts:
                await asyncio.sleep(3)
    raise RuntimeError(f"Temporal への接続に失敗しました: {host}")


async def main() -> None:
    start_http_server(8000)
    logger.info("metrics_server_started", port=8000)

    client = await connect_with_retry(TEMPORAL_HOST)

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[ai_agent_workflow, comparison_workflow, immortal_agent_workflow, hitl_agent_workflow],
        activities=[call_llm_activity, call_llm_with_context_activity, call_mock_llm_activity],
    )

    logger.info("worker_started", task_queue=TASK_QUEUE,
                debug_fail=os.environ.get("DEBUG_FAIL", "0"))
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
