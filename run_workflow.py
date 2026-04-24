"""
Workflow Starter — ワークフローを外部から発火する CLI ツール。

Usage:
    python run_workflow.py                        # 通常（Gemini API）
    python run_workflow.py --mock                 # モックモード（API キー不要）
    python run_workflow.py --mock "任意プロンプト"
"""

import asyncio
import os
import sys
import uuid

from dotenv import load_dotenv

load_dotenv()

from temporalio.client import Client

from workflows.ai_agent_workflow import ai_agent_workflow

TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = "llm-task-queue"

DEFAULT_PROMPT = (
    "Temporal というワークフローエンジンの主な特徴を3点、箇条書きで日本語で説明してください。"
)


async def main() -> None:
    args = sys.argv[1:]
    use_mock = "--mock" in args
    prompt_args = [a for a in args if a != "--mock"]
    prompt = prompt_args[0] if prompt_args else DEFAULT_PROMPT

    client = await Client.connect(TEMPORAL_HOST)

    workflow_id = f"ai-agent-{'mock-' if use_mock else ''}{uuid.uuid4()}"
    mode = "MOCK" if use_mock else "GEMINI"
    print(f"[{mode}] Workflow 発火: {workflow_id}")
    print(f"Prompt: {prompt}\n")

    result = await client.execute_workflow(
        ai_agent_workflow.run,
        args=[prompt, use_mock],
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    print("=== LLM 応答 ===")
    print(result)
    print(f"\nTemporal UI: http://localhost:8080/namespaces/default/workflows/{workflow_id}")


if __name__ == "__main__":
    asyncio.run(main())
