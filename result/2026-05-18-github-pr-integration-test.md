# 概要ドキュメント: GitHub PR 実戦疎通テストスクリプト

**作成日:** 2026-05-18  
**タスク:** sop_generation_workflow Phase 5（GitHub PR作成）の非モック統合テスト

---

## A. System Interaction Flow

```
sop_github_test.py (クライアント)
    ↓ Client.start_workflow(args=[topic, source_code, GitHubParams])
Temporal Server (localhost:7233)
    ↓ Task Queue: llm-task-queue
Worker (python worker.py with GITHUB_TOKEN)
    ↓ Phase 1: generate_sop_phase_activity (outline)
    ↓ Signal: approve_step("") ← スクリプトが自動送信
    ↓ Phase 2: generate_sop_phase_activity (draft)
    ↓ Signal: approve_step("") ← スクリプトが自動送信
    ↓ Phase 3: generate_sop_phase_activity (review)
    ↓ Signal: approve_step("") ← スクリプトが自動送信
    ↓ Phase 4: validate_sop_activity → fix_sop_activity (自律修正)
    ↓ Phase 5: GitHubActivity.create_pull_request
        ↓ git clone/fetch → checkout -B → write file → commit → force-push
        ↓ gh pr create --repo obataka/temporal-demo
GitHub: Pull Request 作成
    ↓ pr_url を返却
sop_github_test.py: PR URL を標準出力へ表示
```

---

## B. Responsibility Matrix

| ファイルパス | クラス/メソッド名 | 処理の目的・役割 | 相互作用する相手 |
| :--- | :--- | :--- | :--- |
| `sop_github_test.py` | `main()` | ワークフロー起動・ポーリング・自動承認・PR URL表示 | Temporal Client, `sop_generation_workflow` |
| `sop_github_test.py` | `_ensure_github_token()` | GITHUB_TOKEN を環境変数に設定（未設定時は gh CLI から取得） | `subprocess.run(["gh", "auth", "token"])` |
| `sop_github_test.py` | `_load_source_code()` | `activities/github_activity.py` をソースとして読み込む | ファイルシステム |
| `sop_github_test.py` | `_poll_until_ready()` | 指定ステータスになるまで `get_status` Query をポーリング | `WorkflowHandle.query()` |
| `activities/github_activity.py` | `GitHubActivity.create_pull_request()` | git clone/push + `gh pr create` で PR 作成 | GitHub API (gh CLI) |

---

## C. 設計の意図とクリティカルポイント

### なぜこの設計か
- **既存実装を無変更で検証**: `worker.py` / `sop_workflow.py` / `github_activity.py` に一切手を加えず、クライアントスクリプトのみで疎通テストを実現
- **GITHUB_TOKEN の自動取得**: Worker を `GITHUB_TOKEN=$(gh auth token) python worker.py` で起動する前提だが、スクリプト自身も `gh auth token` フォールバックを持つことで柔軟性を確保

### クリティカルポイント（最大3点）

1. **Worker に GITHUB_TOKEN を渡すこと（必須）**  
   Docker Compose の `worker` サービスには `GITHUB_TOKEN` が未設定。**Worker はローカルで** `GITHUB_TOKEN=$(gh auth token) python worker.py` として起動する必要がある。Docker Worker のままでは Phase 5 で `EnvironmentError` が発生する。

2. **自動承認のタイミング（asyncio.sleep(2.0)）**  
   Signal 送信後、Worker がシグナルを消化して `generating` ステータスに遷移するまで 2 秒待機している。これを省くと次フェーズのポーリングで `awaiting_approval` を誤検知するリスクがある。

3. **冪等性: 同ブランチへの再実行**  
   `_submit_pr` は `gh pr list --head <branch>` で既存 PR を確認し、存在すれば URL をそのまま返す。同じブランチ (`auto-fix/sop-first-test`) で再実行しても PR が重複作成されない。

---

## 実行手順

```bash
# Terminal 1: Worker 起動（GITHUB_TOKEN を渡す）
GITHUB_TOKEN=$(gh auth token) python worker.py

# Terminal 2: 疎通テスト実行
python sop_github_test.py
```

## 期待される出力
```
[SUCCESS] PR URL: https://github.com/obataka/temporal-demo/pull/N
```
