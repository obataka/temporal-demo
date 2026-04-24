"""
Mock LLM Activity — API キー不要。ランダムな遅延とトークン数をシミュレート。
observability と Search Attributes の動作確認用。
"""

import asyncio
import random
import time

from temporalio import activity

from core.models import LLMResult
from core.observability import log_llm_interaction

MOCK_RESPONSES = [
    "Temporal はワークフローの状態を永続化し、障害から自動復旧します。",
    "Activity は独立した処理単位で、RetryPolicy により自動リトライされます。",
    "Search Attributes を使うと Temporal UI でワークフローをフィルタリングできます。",
    "structlog の JSON ログは ELK や Datadog に直接流し込めます。",
]


@activity.defn
async def call_mock_llm_activity(prompt: str) -> LLMResult:
    """本物の LLM を呼ばずにランダムな応答を返すモックActivity。"""
    model = "mock-llm-v1"

    with log_llm_interaction(model, prompt) as result_box:
        # ランダムな推論遅延をシミュレート (0.3 〜 1.5 秒)
        latency_sec = random.uniform(0.3, 1.5)
        start = time.monotonic()
        await asyncio.sleep(latency_sec)
        latency_ms = (time.monotonic() - start) * 1000

        # ランダムなトークン数をシミュレート
        input_tokens = random.randint(50, 300)
        output_tokens = random.randint(80, 500)

        result = LLMResult(
            text=random.choice(MOCK_RESPONSES),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            latency_ms=round(latency_ms, 2),
        )
        result_box.append(result)

    return result
