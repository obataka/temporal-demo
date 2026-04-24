"""
Sandbox-safe データクラス。
Temporal ワークフロー Sandbox からもインポート可能（os/structlog に依存しない）。
"""

from dataclasses import dataclass


@dataclass
class LLMResult:
    """Activity が返す LLM 呼び出し結果。Temporal がそのままシリアライズできる。"""
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: float
