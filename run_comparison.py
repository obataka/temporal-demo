"""
Comparison Workflow Starter — Mock と Gemini を同時実行してコスト差を比較する CLI。

Usage:
    python run_comparison.py
    python run_comparison.py "任意のプロンプト"
"""

import asyncio
import json
import os
import sys
import uuid

from dotenv import load_dotenv

load_dotenv()

from temporalio.client import Client

from workflows.comparison_workflow import comparison_workflow

TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = "llm-task-queue"

DEFAULT_PROMPT = "AIエージェントの信頼性を高める設計パターンを3つ挙げてください。"

# モデル別単価 (USD / 1M tokens) — docs/costs.md と同期
PRICES = {
    "gemini-2.5-flash": {"input": 0.075, "output": 0.300},
    "mock-llm-v1":      {"input": 0.100, "output": 0.100},
}


def calc_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    p = PRICES.get(model, {"input": 0.0, "output": 0.0})
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000


async def main() -> None:
    args = sys.argv[1:]
    prompt = args[0] if args else DEFAULT_PROMPT

    client = await Client.connect(TEMPORAL_HOST)
    workflow_id = f"comparison-{uuid.uuid4()}"

    print("=" * 60)
    print("  Comparison Workflow: Mock vs Gemini")
    print("=" * 60)
    print(f"Prompt : {prompt}")
    print(f"ID     : {workflow_id}\n")

    result: dict = await client.execute_workflow(
        comparison_workflow.run,
        args=[prompt],
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    mock = result["mock"]
    gem  = result["gemini"]
    mock_cost   = calc_cost(mock["model"],  mock["input_tokens"],  mock["output_tokens"])
    gemini_cost = calc_cost(gem["model"],   gem["input_tokens"],   gem["output_tokens"])

    print("┌─────────────────────────────────────────────────────┐")
    print("│                   RESULTS SUMMARY                  │")
    print("├──────────────────────┬──────────────┬──────────────┤")
    print(f"│ {'Metric':<20} │ {'Mock':^12} │ {'Gemini Flash':^12} │")
    print("├──────────────────────┼──────────────┼──────────────┤")
    print(f"│ {'Model':<20} │ {mock['model']:^12} │ {gem['model']:^12} │")
    print(f"│ {'Input tokens':<20} │ {mock['input_tokens']:^12,} │ {gem['input_tokens']:^12,} │")
    print(f"│ {'Output tokens':<20} │ {mock['output_tokens']:^12,} │ {gem['output_tokens']:^12,} │")
    print(f"│ {'Total tokens':<20} │ {mock['total_tokens']:^12,} │ {gem['total_tokens']:^12,} │")
    print(f"│ {'Latency (ms)':<20} │ {mock['latency_ms']:^12.1f} │ {gem['latency_ms']:^12.1f} │")
    print(f"│ {'Cost (USD)':<20} │ ${mock_cost:^11.8f} │ ${gemini_cost:^11.8f} │")
    print("└──────────────────────┴──────────────┴──────────────┘")
    print()
    print(f"[Mock]   {mock['text']}")
    print(f"[Gemini] {gem['text']}")
    print(f"\nTemporal UI: http://localhost:8080/namespaces/default/workflows/{workflow_id}")


if __name__ == "__main__":
    asyncio.run(main())
