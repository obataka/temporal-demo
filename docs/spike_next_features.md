# 先行技術スパイク：次なる一手の設計メモ

作成日: 2026-06-03  
対象フェーズ: Phase 2（6 月第 2 週）先行検証  
前提: 現行の `sop_generation_workflow` + Hono + CrewAI 構成を壊さない後方互換設計

---

## 現行アーキテクチャの要点（前提確認）

```
sop_generation_workflow（Python）
  │
  ├─ _status: str          ← "fixing" / "validating" など粗粒度の状態
  ├─ _agent_logs: list     ← Reviewer の出力テキストを蓄積
  ├─ _fix_attempt: int     ← 現在の修正ラウンド（0〜2）
  │
  └─ get_status() Query
         │
Hono /api/status/:workflowId
         │
フロントエンド（5 秒ポーリング）
```

`fix_sop_with_crew_activity` は Writer + Reviewer を `crew.kickoff()` の **単一 Activity 呼び出し** として実行する。Temporal の設計上、Activity 実行中にワークフローは自身の状態を変更できない。これが案 A の技術的な核心的制約となる。

---

## 案 A：エージェントステータスのパルス表示

### 目標

「Writer が執筆中...」「Reviewer が監査中...」を別フィールドで管理し、フロントエンドにパルスインジケーターとして表示する。

### 制約の整理

| アプローチ | 概要 | 採否 |
|---|---|---|
| Activity 内部からワークフロー状態を更新 | Temporal では不可。Activity はワークフローのメモリを直接変更できない | 採用不可 |
| Activity Heartbeat | Activity 内部から `activity.heartbeat({"active_agent": "Writer"})` を送出できるが、Heartbeat Details はワークフローの Query からアクセスできない。死活監視用途には向くが、UI への状態公開には不向き | 採用不可 |
| Temporal Update API（1.24+） | Activity からワークフローへの状態 push が可能になるが、Python SDK での対応は現時点で Limited。採用は時期尚早 | 見送り |
| **Activity の分割** | Writer と Reviewer を別々の Activity に分解し、両者の呼び出しの間でワークフロー状態を更新する | **採用** |

### 採用設計：2 Activity 分割

#### 新規 Activity（`activities/fix_sop_activity.py` に追記）

```python
@activity.defn
async def writer_activity(
    sop_text: str, failures: list[str], human_feedback: str = "", attempt: int = 0
) -> LLMResult:
    """Writer エージェント単体を実行し、修正済み SOP を返す。"""
    ...

@activity.defn
async def reviewer_activity(corrected_sop: str) -> LLMResult:
    """Reviewer エージェント単体を実行し、レビューログを返す。"""
    ...
```

#### ワークフロー側の変更（`sop_workflow.py`）

```python
# 追加するフィールド（__init__ に追記）
self._active_agent: str | None = None

# _call_fix() を 2 ステップに分解
async def _call_fix_decomposed(self, sop_text, failures, human_feedback="", attempt=0):
    self._active_agent = "Writer"
    writer_result = await workflow.execute_activity(writer_activity, ...)
    self._active_agent = "Reviewer"
    reviewer_result = await workflow.execute_activity(reviewer_activity, ...)
    self._active_agent = None
    return writer_result, reviewer_result

# get_status() に追加
"active_agent": self._active_agent,   # None | "Writer" | "Reviewer"
```

#### Hono 側の変更（`web-ui/src/index.ts`）

変更は不要。`/api/status/:workflowId` は既存のまま `get_status()` の応答を中継する。`active_agent` フィールドが追加されれば自動的にフロントに届く。Python/TypeScript の命名変換（`active_agent` → `activeAgent`）のフォールバック処理は既存パターンに倣い実装する。

#### フロントエンド側

```typescript
// activeAgent が non-null の間はパルスアニメーションを表示
const agentLabel = status.active_agent ?? status.activeAgent ?? null;
if (agentLabel) {
    indicator.textContent = `${agentLabel} が処理中...`;
    indicator.classList.add("pulsing");
} else {
    indicator.classList.remove("pulsing");
}
```

### 後方互換性

- 既存の `fix_sop_with_crew_activity` はそのまま残す（ワーカー登録済みのため、実行中ワークフローに影響しない）
- ワークフロー内の `_call_fix()` を段階的に `_call_fix_decomposed()` に切り替える
- `get_status()` は追加フィールドのみなので、既存クライアントは影響を受けない

### 注意点

`sop_generation_workflow` は Temporal の `RUNNING` 状態のままイベント履歴でリプレイされる。分割 Activity のシグネチャを変更した場合、実行中のワークフロー（古いコードで開始されたもの）がリプレイ不可能になる可能性がある。本番環境では Workflow Versioning（`workflow.patched()`）を使うか、デプロイ前に実行中のワークフローをすべて完了させること。開発環境では Worker を停止してから再ビルドすれば問題ない。

---

## 案 B：ラウンド数に応じた temperature とプロンプトの動的チューニング

### 目標

差し戻し回数（`_fix_attempt`）が増えるほど LLM が大胆な修正を試みるよう、temperature とプロンプトの urgency を自動的に引き上げる。

### 現状の問題

`_call_fix()` は毎回同一の temperature（CrewAI の LLM デフォルト値）と同一のプロンプトで Activity を呼ぶ。1 回目と 3 回目で同じアプローチを繰り返しても突破口が開かない。

### 採用設計

#### Activity のシグネチャ変更（`fix_sop_with_crew_activity`）

```python
@activity.defn
async def fix_sop_with_crew_activity(
    sop_text: str,
    failures: list[str],
    human_feedback: str = "",
    attempt: int = 0,           # ← 追加（デフォルト 0 で後方互換を維持）
) -> LLMResult:
```

#### Activity 内部のチューニングテーブル

```python
_TEMPERATURE_BY_ROUND: dict[int, float] = {
    0: 0.3,   # 保守的：最小変更で確実に直す
    1: 0.6,   # 中庸：前回より踏み込んだ再解釈を許容する
    2: 0.9,   # 積極的：大胆な再構成も許容する
}

_URGENCY_PREFIX_BY_ROUND: dict[int, str] = {
    0: "",
    1: "\n\n【重要】前回の修正では指摘事項を解消しきれませんでした。"
       "今回は全項目を一つずつ確認し、必ず解消してください。",
    2: "\n\n【最終修正】これが最後の修正機会です。"
       "残存する問題点を全て解消してください。",
}
```

```python
temperature = _TEMPERATURE_BY_ROUND.get(attempt, 0.9)
urgency = _URGENCY_PREFIX_BY_ROUND.get(attempt, _URGENCY_PREFIX_BY_ROUND[2])
llm = LLM(model=_CREW_MODEL, api_key=api_key, temperature=temperature)
```

#### ワークフロー側の変更（`sop_workflow.py`）

`_call_fix()` に `attempt` を渡すだけ：

```python
async def _call_fix(self, sop_text, failures, human_feedback=""):
    return await workflow.execute_activity(
        fix_sop_with_crew_activity,
        args=[sop_text, failures, human_feedback, self._fix_attempt],  # ← attempt 追加
        ...
    )
```

#### フロントエンド側（任意強化）

`get_status()` に `fix_attempt` は既に含まれているため、フロントエンドはラウンドバッジを即座に表示できる：

```typescript
if (status.fix_attempt > 0) {
    roundBadge.textContent = `Round ${status.fix_attempt + 1}`;
    roundBadge.style.display = "inline";
}
```

温度値を UI に表示したい場合、`get_status()` に `current_temperature: float` を追加するオプションがあるが、優先度は低い。

### Temporal 制約の遵守確認

温度チューニングのロジックは Activity 内部に完全に閉じており、ワークフロー内には置かない。ワークフローは `attempt` という純粋な整数を渡すだけなので、決定論制約に違反しない。

### 後方互換性

`attempt=0` のデフォルト値により、既存の呼び出しコードは修正不要。temperature が 0.3 になるだけで挙動に実質的な差異はない。

---

## 実装優先度の提案

案 B の方が変更量が小さく、効果が即座に検証できる。以下の順序を推奨する：

1. **先行：案 B**（変更箇所: Activity シグネチャ + テーブル追加 + `_call_fix()` 1 行変更）  
   → 修正ラウンドの「深度」がログから読み取れるようになる。デモ効果が高い。

2. **後続：案 A**（変更箇所: Activity 2 分割 + ワークフロー状態追加 + フロントのパルス CSS）  
   → 案 B の検証が終わってから取り掛かる。Temporal Versioning の考慮が必要なため、1 スプリント分の時間を確保する。

---

## 残課題・未確定事項

| 項目 | 内容 |
|---|---|
| Gemini Flash の temperature 上限 | Flash 系モデルでは temperature 1.0 超で出力品質が劣化する報告あり。0.9 を上限とし、実験で確認する |
| CrewAI の temperature 伝播 | `LLM(temperature=...)` が Task レベルまで正しく伝播するかをコンテナ内で `bun -e` ないし `python -c` で確認する（SDK 返り値確認ルールに準拠） |
| 案 A の CSS パルスアニメーション | 既存の黒背景デザインに合わせた点滅・グロー効果の実装は UI フェーズで別途詳細化する |
| Activity 分割後のテスト戦略 | `writer_activity` と `reviewer_activity` の単体テストを `tests/` に追加する。既存の `test_fix_sop_activity.py` はラッパーテストとして残す |
