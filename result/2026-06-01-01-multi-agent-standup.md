# マルチエージェント化 Phase 0 — 環境スタンドアップ 結果報告

## A. System Interaction Flow

```
python3 workflows/agent_test.py
    └─ main()
        ├─ LLM(model="gemini/gemini-2.5-flash", api_key=GEMINI_API_KEY)
        ├─ build_agents(llm)  →  Writer, Reviewer（Agent インスタンス）
        ├─ build_tasks(writer, reviewer)
        │     ├─ task_write（Writer が SOP を修正）
        │     └─ task_review（Reviewer が Writer 出力を参照して指摘）
        │           context=[task_write] ← タスク連鎖
        └─ Crew([writer, reviewer], [task_write, task_review]).kickoff()
              ├─ [LiteLLM → Gemini API] Writer タスク実行
              └─ [LiteLLM → Gemini API] Reviewer タスク実行
```

## B. Responsibility Matrix

| ファイルパス | クラス/メソッド名 | 処理の目的・役割 | 相互作用する相手 |
|:---|:---|:---|:---|
| `workflows/agent_test.py` | `main()` | エントリポイント。LLM/Agent/Task/Crew を組み立てて kickoff を呼ぶ | CrewAI Crew |
| `workflows/agent_test.py` | `build_agents(llm)` | Writer・Reviewer の Agent インスタンスを生成して返す | crewai.Agent |
| `workflows/agent_test.py` | `build_tasks(writer, reviewer)` | task_write・task_review を生成。context=[task_write] でタスク連鎖 | crewai.Task |
| `workflows/agent_test.py` | `_separator(label)` | コンソール区切り出力（表示ユーティリティ） | なし |
| `workflows/agent_test.py` | `_print_output(text)` | エージェント出力を折り返し整形して印字 | なし |

## C. 設計の意図・クリティカルポイント

### 設計選択の理由
- **`context=[task_write]`**: Reviewer が Writer の出力を参照できるようにする CrewAI のタスク連鎖機能を採用。これにより Reviewer はサンプル SOP の原文ではなく Writer の改善案を対象にレビューする。
- **既存パターン踏襲**: `activities/crew_activity.py` の `LLM(model="gemini/gemini-2.5-flash", api_key=...)` を流用。将来 Temporal Activity 化する際にそのまま移植可能な形にしている。
- **同期実行**: 本スクリプトは Temporal を介さないスタンドアロン確認用。`crew.kickoff()` を asyncio ラップせず同期で呼ぶことでシンプルに保つ。

### クリティカルポイント（3点）
1. **`context=[task_write]`の有無**: これを外すと Reviewer はサンプル SOP 原文のみを見てしまい、タスク連鎖が機能しない。
2. **`allow_delegation=False`**: True にすると CrewAI が動的にサブエージェントを生成しようとし、確認テストの範囲を超えた LLM 呼び出しが発生する。
3. **`GEMINI_API_KEY` 未設定時の明示的終了**: `sys.stderr` にエラーを出力して ExitCode 1 で終了する。サイレント失敗を防ぐ。

---

## 実行結果ファクト確認

| 検証項目 | 結果 |
|---|---|
| ExitCode | **0**（正常終了）|
| ImportError | なし |
| API 認証エラー | なし |
| Writer 出力 | SOP を修正（平文パスワード削除、VPN 接続手順追加 等） |
| Reviewer 出力 | 高重大度 3 件（承認フロー不備・監査ログ不備・ロールバック手順欠落）を指摘 |
| 総トークン数 | 15,518 |
| 所要時間 | 42.2 秒 |

### 実行コマンド
```bash
docker cp workflows/agent_test.py temporal-worker:/app/workflows/agent_test.py
docker exec temporal-worker python3 workflows/agent_test.py
```
