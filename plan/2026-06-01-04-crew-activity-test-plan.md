# Plan: fix_sop_with_crew_activity のユニットテスト追加

## Context

昨日実装した `fix_sop_with_crew_activity`（CrewAI 2 エージェント版）に
ユニットテストを追加する。既存の `test_fix_sop_activity.py` の 4 テストを
壊さずに、独立した 3 テストケースを末尾に追加する。

---

## 前提確認（既調査）

| 項目 | 状態 |
|---|---|
| 既存テスト | `test_build_prompt_*` × 2、`test_fix_activity_*` × 2（計 4 件） |
| モック戦略 | `patch("google.genai.Client")` + `patch.dict("os.environ", {...})` |
| crewai インストール | コンテナ内 v1.14.5 ✅（conftest へのモック追加不要） |
| asyncio テスト | `@pytest.mark.asyncio` を使用（既存パターン踏襲） |

---

## 追加するテスト（3件）

### Test 1: `test_fix_sop_with_crew_activity_raises_without_api_key`
既存 `test_fix_activity_raises_without_api_key` と同パターン。
`monkeypatch.delenv("GEMINI_API_KEY")` → `EnvironmentError` を期待。

### Test 2: `test_fix_sop_with_crew_activity_returns_llm_result`
CrewAI スタックを 2 層でモック:
- `patch("crewai.LLM")` — LLM インスタンス化を無害化
- `patch("activities.fix_sop_activity._build_sop_crew", return_value=mock_crew)` — Crew 構築をバイパス

**assert 内容:**
- `isinstance(result, LLMResult)`
- `result.text == "CrewAI による修正済み SOP"`
- `result.model == "gemini/gemini-2.5-flash"`
- `result.total_tokens == 500`
- `result.input_tokens == 0`
- `result.output_tokens == 0`
- `result.latency_ms >= 0.0`

### Test 3: `test_fix_sop_with_crew_activity_passes_args_to_crew`
`_build_sop_crew` が正しい引数で呼ばれることを `assert_called_once_with` で検証。
第3引数に `"セキュリティ項目を追加してください"` が渡ることを確認。

---

## 変更ファイル一覧

| ファイル | 操作 | 内容 |
|---|---|---|
| `tests/test_fix_sop_activity.py` | 追記（既存行は不変） | 3 テストケースを末尾に追加 |

※ `conftest.py`・実装ファイルへの変更なし。

---

## 実装後の確認手順

```bash
docker cp tests/test_fix_sop_activity.py temporal-worker:/app/tests/test_fix_sop_activity.py
docker exec temporal-worker pytest tests/test_fix_sop_activity.py -v
```

期待: 全 7 テスト（既存 4 + 新規 3）が PASSED
