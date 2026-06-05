# fix_sop_with_crew_activity ユニットテスト追加 結果報告

## A. System Interaction Flow

```
pytest tests/test_fix_sop_activity.py
    ├─ test_build_prompt_*（既存 2件）
    │     └─ _build_prompt() を直接呼び出し
    ├─ test_fix_activity_*（既存 3件）
    │     └─ patch("google.genai.Client") でモック
    └─ test_fix_sop_with_crew_activity_*（新規 3件）
          ├─ patch("crewai.LLM")
          └─ patch("activities.fix_sop_activity._build_sop_crew", return_value=mock_crew)
                └─ mock_crew.kickoff.return_value = mock_crew_output
                      ← asyncio.to_thread(crew.kickoff) がこれを返す
```

## B. Responsibility Matrix

| ファイルパス | テスト名 | 検証内容 | モック対象 |
|:---|:---|:---|:---|
| `tests/test_fix_sop_activity.py` | `test_fix_sop_with_crew_activity_raises_without_api_key` | API キー未設定時の EnvironmentError | `monkeypatch.delenv` |
| `tests/test_fix_sop_activity.py` | `test_fix_sop_with_crew_activity_returns_llm_result` | LLMResult の型・全フィールド値 | `crewai.LLM` + `_build_sop_crew` |
| `tests/test_fix_sop_activity.py` | `test_fix_sop_with_crew_activity_passes_args_to_crew` | `_build_sop_crew` への引数の正確な受け渡し | `crewai.LLM` + `_build_sop_crew` |

## C. 設計の意図・クリティカルポイント

### 設計選択の理由
- **`_build_sop_crew` をパッチする** — Agent/Task/Crew の構築ロジック全体を 1 点でバイパスできる。`crewai.Agent`・`crewai.Task`・`crewai.Crew` を個別にモックするより可読性が高く、テストが実装詳細に過剰依存しない。
- **`asyncio.to_thread` への対応** — `mock_crew.kickoff.return_value` に設定するだけで `asyncio.to_thread(crew.kickoff)` がモック値を返す。`asyncio.to_thread` 自体はモックしない（本物の thread pool を使い、mock の synchronous kickoff を実行する）。
- **`ANY` で LLM インスタンスを検証** — LLM インスタンス自体は `crewai.LLM` モックが返す MagicMock であり、同一性チェックは意味がない。引数の数と他 3 引数の値を検証することで「正しく渡っているか」を確認する。

### クリティカルポイント（2点）
1. **`mock_crew_output.tasks_output = [mock_task_output]`** — リストでなく `MagicMock()` のまま渡すと `if crew_output.tasks_output:` が常に True になり、`.raw` アクセスで意図しない MagicMock が返る。明示的にリストを設定することが重要。
2. **`result.input_tokens == 0` / `result.output_tokens == 0` の assert** — 将来 CrewAI がタスク単位の内訳を返すようになった場合は、この assert を緩和する必要がある（その時が実装変更のサイン）。

---

## 検証結果

| 検証項目 | 結果 |
|---|---|
| 既存 5 テスト | 全 PASSED（変更なし） |
| 新規 3 テスト | 全 PASSED |
| 合計 | **8 passed in 1.15s** |

### 実行コマンド
```bash
docker cp tests/test_fix_sop_activity.py temporal-worker:/app/tests/test_fix_sop_activity.py
docker exec temporal-worker pytest tests/test_fix_sop_activity.py -v
```
