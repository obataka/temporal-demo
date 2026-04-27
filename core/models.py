"""
Sandbox-safe データクラス。
Temporal ワークフロー Sandbox からもインポート可能（os/structlog に依存しない）。
"""

from dataclasses import dataclass, field


@dataclass
class LLMResult:
    """Activity が返す LLM 呼び出し結果。Temporal がそのままシリアライズできる。"""
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: float


@dataclass
class AgentStats:
    """immortal_agent_workflow が保持する累積統計。クラッシュ後もイベント履歴から復元される。"""
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_latency_ms: float = 0.0
    results: list = field(default_factory=list)  # 直近の応答テキスト（最大10件）

    def record_success(self, result: "LLMResult") -> None:
        self.tasks_completed += 1
        self.total_input_tokens += result.input_tokens
        self.total_output_tokens += result.output_tokens
        self.total_latency_ms += result.latency_ms
        self.results.append(result.text)
        if len(self.results) > 10:
            self.results.pop(0)

    def record_failure(self) -> None:
        self.tasks_failed += 1

    @property
    def average_latency_ms(self) -> float:
        if self.tasks_completed == 0:
            return 0.0
        return round(self.total_latency_ms / self.tasks_completed, 1)
