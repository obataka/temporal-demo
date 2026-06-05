# Plan: マルチエージェント化 Phase 0 — 環境スタンドアップ

## Context

「マルチエージェント化」新フェーズの出発点として、CrewAI × Gemini の最小構成が
コンテナ環境で動作することを実証する。将来の Temporal Activity 組み込みに備えた
基盤確認を目的とする。

---

## 前提確認（既調査）

| 項目 | 状態 |
|---|---|
| `crewai` in requirements.txt | ✅ `>=1.14.4`（コンテナ実体は 1.14.5）|
| コンテナ内インストール | ✅ `pip show crewai` で確認済み |
| Gemini LLM パターン | `crew_activity.py` の `LLM(model="gemini/gemini-2.5-flash", api_key=...)` を流用 |
| `GEMINI_API_KEY` | docker-compose.yaml の `worker` サービスに環境変数注入済み |

---

## 実装方針

### 新設ファイル: `workflows/agent_test.py`

**目的:** Temporal を介さずコンテナ内で直接 `python3 workflows/agent_test.py` を実行し、
2 エージェントのインスタンス化・LLM 接続・最小タスク実行を確認する。

**エージェント設計:**

| 名前 | role | 役割 |
|---|---|---|
| Writer | SOP 改善担当 | サンプル SOP の誤りを修正・改善案を提案する |
| Reviewer | セキュリティ・規律レビュー担当 | Writer の出力を受け取り、セキュリティ上の問題・規律違反を指摘する |

**Crew 実行パターン（既存 `crew_activity.py` に倣う）:**

```python
from crewai import Agent, Task, Crew, LLM

api_key = os.environ["GEMINI_API_KEY"]
llm = LLM(model="gemini/gemini-2.5-flash", api_key=api_key)

writer   = Agent(role="SOP 改善担当", ..., llm=llm)
reviewer = Agent(role="セキュリティ・規律レビュー担当", ..., llm=llm)

t1 = Task(description=..., expected_output=..., agent=writer)
t2 = Task(description=..., expected_output=..., agent=reviewer, context=[t1])

crew = Crew(agents=[writer, reviewer], tasks=[t1, t2], verbose=False)
result = crew.kickoff()
```

- `crew.kickoff()` は同期。非同期ラップ不要（スタンドアロン実行のため）。
- `context=[t1]` により Reviewer が Writer の出力を参照する（CrewAI のタスク連鎖）。
- サンプル SOP はスクリプト内のインラインテキスト（外部ファイル依存なし）。

**検証内容（コンテナ内実行）:**

```bash
docker exec temporal-worker python3 workflows/agent_test.py
```

成功条件:
- ExitCode 0
- Writer・Reviewer それぞれの出力がコンソールに表示される
- エラー（ImportError / API 認証エラー / LLM 接続エラー）が出ない

---

## 変更ファイル一覧

| ファイル | 操作 | 内容 |
|---|---|---|
| `workflows/agent_test.py` | 新規作成 | Writer + Reviewer 最小構成スクリプト |

※ `requirements.txt`・`Dockerfile`・既存ファイルへの変更なし。

---

## 実装後の確認手順

1. `docker exec temporal-worker python3 workflows/agent_test.py`
2. 終了コードが 0 であることを確認（`echo $?`）
3. 出力に Writer / Reviewer の応答テキストが含まれることを目視確認
