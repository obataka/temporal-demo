# sop_workflow.py — fix_sop_with_crew_activity への差し替え 結果報告

## A. System Interaction Flow

```
sop_generation_workflow._call_fix()
    └─ workflow.execute_activity(fix_sop_with_crew_activity, ...)   ← 変更後
          ├─ [CrewAI] Writer Agent（SOP 修正担当）
          └─ [CrewAI] Reviewer Agent（セキュリティ・規律レビュー担当）
                context=[task_write]
                └─ LiteLLM → gemini/gemini-2.5-flash
```

## B. Responsibility Matrix

| ファイルパス | 変更箇所 | 変更内容 | 影響 |
|:---|:---|:---|:---|
| `workflows/sop_workflow.py` L38 | `imports_passed_through` ブロック | `fix_sop_activity` → `fix_sop_with_crew_activity` に変更 | Phase 4 修正ループが CrewAI 版を呼ぶようになる |
| `workflows/sop_workflow.py` L351 | `_call_fix` docstring | 関数名を更新 | ドキュメントの正確性 |
| `workflows/sop_workflow.py` L359 | `execute_activity` 第1引数 | `fix_sop_activity` → `fix_sop_with_crew_activity` | 実際の Activity 切り替え |
| `worker.py` L26 | インポート行 | `fix_sop_with_crew_activity` を追加インポート | Worker が新 Activity を認識できるようになる |
| `worker.py` L77 | activities リスト | `fix_sop_with_crew_activity` を追加登録 | Temporal Worker が新 Activity を実行できるようになる |

## C. 設計の意図・クリティカルポイント

### 設計選択の理由
- **`fix_sop_activity` を worker.py から除去しない** — `tests/test_fix_sop_activity.py` が Activity 関数を直接インポートしているため、除去すると tests/ の import に影響しないが、将来 Worker の Activity 一覧との整合性維持のため並存とした。
- **引数変更なし** — `fix_sop_with_crew_activity` のシグネチャが `fix_sop_activity` と同一（`sop_text, failures, human_feedback=""` → `LLMResult`）なため、`args=[sop_text, failures, human_feedback]` の変更は不要。
- **`imports_passed_through` ブロック内での差し替え** — Temporal Workflow Sandbox はファイル I/O・OS 呼び出しを制限するため、Activity のインポートは `workflow.unsafe.imports_passed_through()` 内に置く必要がある。この制約を維持したまま差し替えた。

### クリティカルポイント（2点）
1. **`worker.py` への登録が必須** — `sop_workflow.py` で `fix_sop_with_crew_activity` を呼び出しても、Worker に登録されていなければ Temporal が `ActivityNotRegisteredError` を返す。2 ファイルをセットで変更することが重要。
2. **`start_to_close_timeout=timedelta(minutes=7)` の維持** — CrewAI 版は 2 エージェントを直列実行するため、単一 Gemini 呼び出しより時間がかかる。既存の 7 分タイムアウトはそのまま維持（変更不要）。

---

## 検証結果

| 検証項目 | 結果 |
|---|---|
| `pytest tests/` | **43 passed in 1.63s** |
| デグレード（既存 40 件） | なし（全 PASSED） |
| 新規テスト（3 件 fix_sop_with_crew） | PASSED |

### 実行コマンド
```bash
docker cp workflows/sop_workflow.py temporal-worker:/app/workflows/sop_workflow.py
docker cp worker.py temporal-worker:/app/worker.py
docker exec temporal-worker pytest tests/ -v
```
