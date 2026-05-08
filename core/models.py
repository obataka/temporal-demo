"""
Sandbox-safe データクラス。
Temporal ワークフロー Sandbox からもインポート可能（os/structlog に依存しない）。
"""

from dataclasses import dataclass, field
from typing import Optional, List


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
class LLMRequest:
    """HITL ワークフローが Activity に渡す構造化リクエスト。Temporal がシリアライズできる。"""
    user_message: str
    attempt: int = 0
    previous_answer: Optional[str] = None  # リトライ時: 前回の回答
    feedback: Optional[str] = None         # リトライ時: 人間からのフィードバック


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


@dataclass
class AgentReviewRequest:
    """agentic_review_workflow が Agent Activity に渡すリクエスト。Temporal がシリアライズできる。"""
    draft: str                                  # レビュー対象の SOP 草稿
    agent_role: str                             # "proofreader" | "tech_reviewer"
    hints: List[str] = field(default_factory=list)   # Signal で注入されたヒント
    proofreader_output: Optional[str] = None    # tech_reviewer 専用: 校正担当の出力


@dataclass
class AgentResult:
    """Agent Activity の実行結果。Temporal がシリアライズできる。"""
    agent_role: str
    output: str
    thoughts: List[str]    # task_callback で収集した中間ステップ出力
    tokens: int
    latency_ms: float


@dataclass
class SOPRequest:
    """SOP 生成ワークフローが Activity に渡す構造化リクエスト。Temporal がシリアライズできる。"""
    topic: str                              # ドキュメント化対象の説明
    source_code: str                        # 対象ソースコード
    phase: str                              # "outline" | "draft" | "review"
    attempt: int = 0                        # フェーズ内リトライ回数
    previous_output: Optional[str] = None  # 同フェーズ前回出力（リトライ時）
    outline: Optional[str] = None          # 承認済みアウトライン（draft/review フェーズ）
    draft: Optional[str] = None            # 承認済み草稿（review フェーズ）
    feedback: Optional[str] = None         # 人間からのフィードバック（リトライ時）
