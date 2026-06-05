# fix_sop_activity.py — CrewAI 協調ロジック土台実装 結果報告

## A. System Interaction Flow

```
sop_generation_workflow._call_fix()
    └─ workflow.execute_activity(fix_sop_activity, args=[sop_text, failures, human_feedback])
          └─ fix_sop_activity()              ← 既存（変更なし）
                └─ google-genai → Gemini

    ※ 将来の差し替え先:
    └─ workflow.execute_activity(fix_sop_with_crew_activity, args=[...])
          └─ fix_sop_with_crew_activity()    ← 今回追加
                ├─ _build_sop_crew()
                │     ├─ Writer Agent（SOP 修正担当）
                │     └─ Reviewer Agent（セキュリティ・規律レビュー担当）
                │           context=[task_write]
                └─ asyncio.to_thread(crew.kickoff)
                      └─ LiteLLM → gemini/gemini-2.5-flash
```

## B. Responsibility Matrix

| ファイルパス | 関数/クラス名 | 処理の目的・役割 | 相互作用する相手 |
|:---|:---|:---|:---|
| `activities/fix_sop_activity.py` | `_build_sop_crew()` | Writer + Reviewer の Agent/Task/Crew を組み立て Crew インスタンスを返す | crewai.Agent / crewai.Task / crewai.Crew |
| `activities/fix_sop_activity.py` | `fix_sop_with_crew_activity()` | CrewAI 2 エージェントで SOP を修正し LLMResult を返す Temporal Activity | `_build_sop_crew()` / asyncio.to_thread |
| `activities/fix_sop_activity.py` | `fix_sop_activity()` | 既存単一 Gemini 呼び出し（変更なし） | google-genai |
| `workflows/sop_workflow.py` | `_call_fix()` | fix_sop_activity を呼び出す（今回変更なし） | fix_sop_activity |

## C. 設計の意図・クリティカルポイント

### 設計選択の理由
- **既存 Activity を変更せず追加のみ** — `sop_workflow.py` の呼び出し元を変えることなく、将来 `fix_sop_activity` → `fix_sop_with_crew_activity` に差し替えるだけで移行できる。Temporal はワークフロー履歴互換性が重要なため、デプロイ移行コストを最小化する設計にした。
- **`asyncio.to_thread(crew.kickoff)`** — `crew_activity.py` と同一パターン。`crew.kickoff()` は同期ブロッキングであり、asyncio イベントループを止めないために必須。
- **`_build_sop_crew` を分離** — Activity 関数から Crew 構築ロジックを分離することで、将来のユニットテストや設定変更が容易になる。

### クリティカルポイント（3点）
1. **`context=[task_write]`** — これがなければ Reviewer は Writer の修正済み SOP を参照できず、独立したレビューになる。タスク連鎖の核心。
2. **`LLMResult.text = tasks_output[0].raw`** — Writer の修正済み SOP を取得する箇所。`tasks_output[0]` が Writer、`tasks_output[1]` が Reviewer に対応している（タスク定義の順序依存）。
3. **`input_tokens=0, output_tokens=0`** — CrewAI の `token_usage` はタスク単位の内訳を返さず `total_tokens` しか信頼できないため、内訳フィールドは 0 固定。既存 `fix_sop_activity` とは異なる点として明記しておく。

---

## 検証結果

| 検証項目 | 結果 |
|---|---|
| `python3 -m py_compile activities/fix_sop_activity.py` | **ExitCode 0 / "OK"** |
| ImportError | なし |
| SyntaxError | なし |
| 既存 `fix_sop_activity` 関数 | 変更なし（行レベルで不変） |
| 既存 `sop_workflow.py` | 変更なし |

### 実行コマンド
```bash
docker cp activities/fix_sop_activity.py temporal-worker:/app/activities/fix_sop_activity.py
docker exec temporal-worker python3 -m py_compile activities/fix_sop_activity.py && echo OK
```
