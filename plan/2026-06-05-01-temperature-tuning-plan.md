# 案B：ラウンド数 × temperature 動的チューニング 実装計画

作成日: 2026-06-05  
対象ファイル: `activities/fix_sop_activity.py`, `workflows/sop_workflow.py`, `tests/test_fix_sop_activity.py`  
設計根拠: `docs/spike_next_features.md` 案 B 節

---

## Context

差し戻し回数（`_fix_attempt`）が増えるほど LLM が大胆な修正を試みるよう、temperature とプロンプトの urgency を動的に引き上げる。現状は毎回同一の temperature・同一プロンプトで Activity を呼ぶため、1 回目と 3 回目で同じアプローチが繰り返される問題がある。

---

## 変更ファイル一覧

| ファイル | 変更内容 |
|---|---|
| `activities/fix_sop_activity.py` | 定数テーブル追加、`_build_sop_crew` に `attempt` 追加、`fix_sop_with_crew_activity` に `attempt` 追加 |
| `workflows/sop_workflow.py` | `_call_fix` の `args` に `self._fix_attempt` を追加 |
| `tests/test_fix_sop_activity.py` | 既存テスト 1 件の期待値修正 + 新規テスト 4 件追加 |

---

## 実装詳細

### 1. `activities/fix_sop_activity.py`

#### (a) モジュールレベル定数を追加（`_CREW_MODEL` 定義の直後）

```python
_TEMPERATURE_BY_ROUND: dict[int, float] = {
    0: 0.3,   # 保守的：最小変更で確実に直す
    1: 0.6,   # 中庸：前回より踏み込んだ再解釈を許容
    2: 0.9,   # 積極的：大胆な再構成も許容
}

_URGENCY_PREFIX_BY_ROUND: dict[int, str] = {
    0: "",
    1: (
        "\n\n【重要】前回の修正では指摘事項を解消しきれませんでした。"
        "今回は全項目を一つずつ確認し、必ず解消してください。"
    ),
    2: (
        "\n\n【最終修正】これが最後の修正機会です。"
        "セキュリティと規律の不備を大胆かつクリエイティブな視点で洗い出し、"
        "残存する問題点を全て解消してください。"
    ),
}
```

#### (b) `_build_sop_crew` のシグネチャに `attempt: int = 0` を追加

urgency を `task_write` の `description` 末尾に注入する。

```python
def _build_sop_crew(
    sop_text: str,
    failures: list[str],
    human_feedback: str,
    llm,
    attempt: int = 0,
) -> Crew:
    ...
    urgency = _URGENCY_PREFIX_BY_ROUND.get(attempt, _URGENCY_PREFIX_BY_ROUND[2])

    task_write = Task(
        description=(
            "以下の問題点リストを全て解消した改善版 SOP を Markdown 形式で出力してください。"
            "内容の本質は変えず、最小限の修正で問題を解消してください。\n\n"
            f"## 修正が必要な問題点\n{failures_str}{human_section}\n\n"
            f"## 修正対象の SOP\n{sop_snippet}"
            f"{urgency}"
        ),
        ...
    )
```

#### (c) `fix_sop_with_crew_activity` のシグネチャに `attempt: int = 0` を追加

temperature を動的計算し、LLM インスタンスと `_build_sop_crew` の両方へ渡す。

```python
@activity.defn
async def fix_sop_with_crew_activity(
    sop_text: str,
    failures: list[str],
    human_feedback: str = "",
    attempt: int = 0,
) -> LLMResult:
    ...
    temperature = _TEMPERATURE_BY_ROUND.get(attempt, 0.9)
    llm = LLM(model=_CREW_MODEL, api_key=api_key, temperature=temperature)
    crew = _build_sop_crew(sop_text, failures, human_feedback, llm, attempt)
```

### 2. `workflows/sop_workflow.py` — `_call_fix` に `self._fix_attempt` を追加

```python
async def _call_fix(self, sop_text, failures, human_feedback=""):
    return await workflow.execute_activity(
        fix_sop_with_crew_activity,
        args=[sop_text, failures, human_feedback, self._fix_attempt],  # attempt 追加
        ...
    )
```

### 3. `tests/test_fix_sop_activity.py`

#### (a) 既存テスト修正 — `_build_sop_crew` の引数数変化に対応

`test_fix_sop_with_crew_activity_passes_args_to_crew` の `assert_called_once_with` に `attempt=0` を追加:

```python
mock_build.assert_called_once_with(
    "対象 SOP",
    ["失敗項目A"],
    "セキュリティ項目を追加してください",
    ANY,
    0,  # attempt デフォルト値
)
```

#### (b) 新規テスト 4 件

1. `test_temperature_by_round_table` — 定数テーブルの値を確認（attempt 0/1/2/999）
2. `test_urgency_prefix_by_round_table` — urgency 定数テーブルの値を確認
3. `test_fix_sop_with_crew_activity_passes_attempt_to_build_crew` — attempt=2 を渡したとき `_build_sop_crew` に attempt=2 がリレーされることを確認
4. `test_fix_sop_with_crew_activity_backward_compatible_without_attempt` — attempt 引数省略時（デフォルト 0）に正常動作することを確認

---

## 後方互換性の保証

- `fix_sop_with_crew_activity` の `attempt` は `= 0` デフォルト。既存呼び出し元は変更不要。
- `_build_sop_crew` の `attempt` も `= 0` デフォルト。呼び出し箇所が1箇所のため後方互換は実質不要だが、念のため付与。
- Temporal のシリアライズは位置引数リスト（`args=[...]`）なので、ワークフロー側の `_call_fix` に `self._fix_attempt` を末尾追加するだけで ok。

---

## 検証

```bash
docker compose exec worker pytest tests/ -v
```

全 45 件（既存） + 新規 4 件 = 計 49 件が PASS になることを確認する。
