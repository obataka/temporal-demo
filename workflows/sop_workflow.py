"""
SOP Generation Workflow — Step-by-Step Approval with Dynamic Refinement

3フェーズを順番に実行し、各フェーズ完了後に人間の承認を待つ。
フィードバックがあれば同フェーズを再生成（Dynamic Refinement）する。

Phases:
    1. outline        : 章立て提案
    2. draft          : 詳細執筆
    3. review         : 最終レビュー
    4. autonomous_fix : ルールベース検証 → AI修正（最大3回）

Signals:
    approve_step(feedback: str)
        "" (空文字)  → 現フェーズを承認して次フェーズへ進む
        非空文字    → フィードバックとして同フェーズを再生成
    approve_pr()
        require_approval=True 時、Phase 5 直前に呼び出して PR 作成を解放する
    reject_with_feedback(input_data: dict)
        {"comment": "修正指示"} を受け取り、PR 承認待機を差し戻しとして解除する

Queries:
    get_status() -> dict    current_phase / status / attempt / current_output
    get_history() -> list   全フェーズ・全試行の比較ログ（人間介入の Evidence）
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.exceptions import ApplicationError

from core.models import SOPRequest, LLMResult, ValidationResult, GitHubParams
from core.retry_policy import LLM_RETRY_POLICY

with workflow.unsafe.imports_passed_through():
    from activities.sop_activity import generate_sop_phase_activity
    from activities.validate_sop_activity import validate_sop_activity
    from activities.fix_sop_activity import fix_sop_activity
    from activities.github_activity import GitHubActivity

PHASES = ["outline", "draft", "review"]

PHASE_LABELS = {
    "outline":        "フェーズ1: 章立て提案",
    "draft":          "フェーズ2: 詳細執筆",
    "review":         "フェーズ3: 最終レビュー",
    "autonomous_fix": "フェーズ4: 自律修正",
    "github_pr":      "フェーズ5: GitHub PR作成",
    "rejected":       "差し戻し済み",
}

MAX_FIX_ATTEMPTS = 3


@workflow.defn
class sop_generation_workflow:

    def __init__(self) -> None:
        # Signal state — Activity 実行中に届いても取りこぼさない
        self._signal_received: bool = False
        self._step_feedback: str = ""

        # Workflow state
        self._topic: str = ""
        self._current_phase: str = "initializing"
        self._current_output: str | None = None
        self._attempt_in_phase: int = 0
        self._status: str = "initializing"

        # フェーズごとの承認済み出力
        self._approved: dict[str, str] = {}

        # Evidence log: 全試行の比較ログ
        self._history: list[dict] = []

        # 自律修正ループ状態
        self._fix_attempt: int = 0
        self._validation_result: dict | None = None
        self._pr_url: str | None = None

        # PR 承認ゲート（require_approval=True 時に approve_pr Signal を待つ）
        self._pr_approved: bool = False

        # 差し戻しシグナルで受け取った人間のフィードバックコメント
        self._human_feedback: str = ""

    # ─── Signal Handlers ─────────────────────────────────────────────────────

    @workflow.signal
    def approve_step(self, feedback: str) -> None:
        """
        "" (空文字): 現フェーズを承認して次フェーズへ進む。
        非空文字:   フィードバックとして同フェーズを再生成する。
        """
        self._step_feedback = feedback
        self._signal_received = True

    @workflow.signal
    def approve_pr(self) -> None:
        """
        Phase 5（GitHub PR 作成）の実行を承認する。

        GitHubParams.require_approval=True のワークフローでのみ使用する。
        呼び出し後、wait_condition が解除されて PR 作成が開始される。
        """
        self._pr_approved = True

    @workflow.signal
    def reject_with_feedback(self, input_data: dict) -> None:
        """
        人間からの修正指示を受け取り、PR 承認待機を差し戻しとして解除する。

        :param input_data: {"comment": "修正指示テキスト"} 形式の辞書。
                           辞書以外が渡された場合は文字列に変換して保持する。
        """
        self._human_feedback = (
            input_data.get("comment", "") if isinstance(input_data, dict) else str(input_data)
        )

    # ─── Query Handlers ──────────────────────────────────────────────────────

    @workflow.query
    def get_status(self) -> dict:
        return {
            "status": self._status,
            "current_phase": self._current_phase,
            "phase_label": PHASE_LABELS.get(self._current_phase, self._current_phase),
            "attempt_in_phase": self._attempt_in_phase,
            "current_output": self._current_output,
            "approved_phases": list(self._approved.keys()),
            "fix_attempt": self._fix_attempt,
            "validation_result": self._validation_result,
            "pr_url": self._pr_url,
            "pr_approved": self._pr_approved,
            "human_feedback": self._human_feedback,
        }

    @workflow.query
    def get_history(self) -> list:
        """全フェーズ・全試行の比較ログ。人間介入の Evidence として使用する。"""
        return list(self._history)

    # ─── Main ────────────────────────────────────────────────────────────────

    @workflow.run
    async def run(
        self,
        topic: str,
        source_code: str,
        github_params: GitHubParams | None = None,
    ) -> dict:
        self._topic = topic

        for phase in PHASES:
            self._current_phase = phase
            self._attempt_in_phase = 0
            last_feedback: str | None = None

            while True:
                self._status = "generating"

                # Activity 実行前にシグナル受信フラグをリセット
                # （Activity 実行中に届いたシグナルは wait_condition で即座に検出される）
                self._signal_received = False

                request = SOPRequest(
                    topic=topic,
                    source_code=source_code,
                    phase=phase,
                    attempt=self._attempt_in_phase,
                    previous_output=self._current_output if self._attempt_in_phase > 0 else None,
                    outline=self._approved.get("outline"),
                    draft=self._approved.get("draft"),
                    feedback=last_feedback,
                )
                result = await self._call_llm(request)
                self._current_output = result.text

                self._history.append({
                    "phase": phase,
                    "phase_label": PHASE_LABELS[phase],
                    "attempt": self._attempt_in_phase,
                    "feedback": last_feedback,
                    "output": result.text,
                    "tokens": result.total_tokens,
                    "latency_ms": result.latency_ms,
                    "approved": False,
                })

                self._status = "awaiting_approval"

                # シグナルを待つ（Activity 実行中に届いた場合は即座に返る）
                await workflow.wait_condition(lambda: self._signal_received)

                feedback = self._step_feedback
                self._step_feedback = ""
                self._signal_received = False

                if not feedback:
                    # 承認 → 次フェーズへ
                    self._history[-1]["approved"] = True
                    self._approved[phase] = self._current_output
                    break
                else:
                    # フィードバック → 同フェーズを再生成
                    last_feedback = feedback
                    self._attempt_in_phase += 1

        # ── Phase 4 + Phase 5: 対話型ループバック制御 ─────────────────────────
        # reject_with_feedback シグナルで差し戻された場合、Phase 4 から再実行する。
        current_sop = self._approved["review"]
        while True:
            # ① human_feedback をキャプチャしてリセット（二重ループ防止）
            human_feedback = self._human_feedback
            self._human_feedback = ""
            self._fix_attempt = 0
            self._current_phase = "autonomous_fix"
            final_sop = current_sop

            # ② 人間フィードバックがある場合は事前 fix パスで LLM へ注入する
            if human_feedback:
                workflow.logger.info(
                    "人間フィードバックを受けて Phase 4 再実行 — フィードバック: %s",
                    human_feedback,
                )
                self._status = "fixing"
                fix_result = await self._call_fix(final_sop, [], human_feedback)
                final_sop = fix_result.text
                self._history.append({
                    "phase": "autonomous_fix",
                    "phase_label": PHASE_LABELS["autonomous_fix"],
                    "attempt": self._fix_attempt,
                    "failures": [f"[人間フィードバック] {human_feedback}"],
                    "output": fix_result.text,
                    "tokens": fix_result.total_tokens,
                    "latency_ms": fix_result.latency_ms,
                    "approved": False,
                })
                self._fix_attempt += 1

            # ③ 通常バリデーション＋修正ループ
            while self._fix_attempt < MAX_FIX_ATTEMPTS:
                self._status = "validating"
                v_result = await self._call_validate(final_sop)
                self._validation_result = {
                    "passed": v_result.passed,
                    "failures": v_result.failures,
                    "score": v_result.score,
                }

                if v_result.passed:
                    self._approved["review"] = final_sop
                    self._history.append({
                        "phase": "autonomous_fix",
                        "phase_label": PHASE_LABELS["autonomous_fix"],
                        "attempt": self._fix_attempt,
                        "failures": [],
                        "output": final_sop,
                        "tokens": 0,
                        "latency_ms": 0,
                        "approved": True,
                    })
                    break

                self._status = "fixing"
                fix_result = await self._call_fix(final_sop, v_result.failures)
                final_sop = fix_result.text
                self._history.append({
                    "phase": "autonomous_fix",
                    "phase_label": PHASE_LABELS["autonomous_fix"],
                    "attempt": self._fix_attempt,
                    "failures": v_result.failures,
                    "output": fix_result.text,
                    "tokens": fix_result.total_tokens,
                    "latency_ms": fix_result.latency_ms,
                    "approved": False,
                })
                self._fix_attempt += 1
            else:
                raise ApplicationError(
                    "自律修正失敗: 最大試行回数超過",
                    non_retryable=True,
                )

            # ④ 次の外側ループ用に最新 SOP を保持
            current_sop = final_sop

            # ⑤ Phase 5: GitHub PR 作成
            if github_params is not None:
                self._current_phase = "github_pr"
                if github_params.require_approval:
                    self._status = "awaiting_pr_approval"
                    self._pr_approved = False  # 再入時リセット
                    await workflow.wait_condition(
                        lambda: self._pr_approved or bool(self._human_feedback)
                    )
                    if self._human_feedback:
                        # 差し戻し → Phase 4 へループバック
                        continue
                self._status = "creating_pr"
                pr_result = await self._call_github_pr(
                    sop_text=final_sop,
                    topic=topic,
                    github_params=github_params,
                )
                self._pr_url = pr_result["pr_url"]

            break  # 通常完了でループを抜ける

        self._status = "completed"
        self._current_phase = "completed"

        return {
            "topic": topic,
            "outline": self._approved.get("outline", ""),
            "draft": self._approved.get("draft", ""),
            "review": self._approved.get("review", ""),
            "history": self._history,
            "pr_url": self._pr_url,
        }

    async def _call_llm(self, request: SOPRequest) -> LLMResult:
        return await workflow.execute_activity(
            generate_sop_phase_activity,
            request,
            start_to_close_timeout=timedelta(minutes=7),
            retry_policy=LLM_RETRY_POLICY,
        )

    async def _call_validate(self, sop_text: str) -> ValidationResult:
        """
        validate_sop_activity を実行して ValidationResult を返す。

        :param sop_text: 検証対象の SOP 全文
        :returns: 検証結果
        """
        return await workflow.execute_activity(
            validate_sop_activity,
            sop_text,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=LLM_RETRY_POLICY,
        )

    async def _call_fix(
        self,
        sop_text: str,
        failures: list[str],
        human_feedback: str = "",
    ) -> LLMResult:
        """
        fix_sop_activity を実行して修正済み SOP を返す。

        :param sop_text: 修正対象の SOP 全文
        :param failures: validate_sop_activity が返した失敗メッセージのリスト
        :param human_feedback: 人間からの追加修正指示（省略時は空文字）
        :returns: 修正済み SOP を含む LLMResult
        """
        return await workflow.execute_activity(
            fix_sop_activity,
            args=[sop_text, failures, human_feedback],
            start_to_close_timeout=timedelta(minutes=7),
            retry_policy=LLM_RETRY_POLICY,
        )

    async def _call_github_pr(
        self,
        sop_text: str,
        topic: str,
        github_params: GitHubParams,
    ) -> dict:
        """
        GitHubActivity.create_pull_request を実行して PR URL を返す。

        :param sop_text: 最終承認済み SOP 全文
        :param topic: SOP のトピック名（PR タイトル/コミットメッセージに使用）
        :param github_params: GitHub 操作に必要なメタデータ
        :returns: {"pr_url": "https://github.com/.../pull/N"}
        """
        params = {
            "repository":     github_params.repository,
            "base_branch":    github_params.base_branch,
            "feature_branch": github_params.feature_branch,
            "file_path":      github_params.file_path,
            "file_content":   sop_text,
            "commit_message": f"docs: auto-generated SOP for {topic}",
            "pr_title":       f"[Auto SOP] {topic}",
            "pr_body": (
                f"このPRは `sop_generation_workflow` により自動生成されました。\n\n"
                f"**トピック:** {topic}\n\n"
                f"バリデーション（{MAX_FIX_ATTEMPTS}回以内）を通過した最終版SOPです。"
            ),
        }
        return await workflow.execute_activity(
            GitHubActivity.create_pull_request,
            params,
            start_to_close_timeout=timedelta(minutes=7),
            retry_policy=LLM_RETRY_POLICY,
        )
