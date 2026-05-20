# 概要ドキュメント: GitHub PR 実戦疎通テスト 実行結果

**作成日:** 2026-05-19  
**タスク:** sop_generation_workflow Phase 5（GitHub PR作成）の非モック統合テスト実行

---

## 結果

**GREEN** — PR 作成成功

```
PR URL: https://github.com/obataka/temporal-demo/pull/1
Workflow ID: sop-github-test-271d70b8
```

---

## A. System Interaction Flow（実際の実行フロー）

```
sop_github_test.py
    ↓ start_workflow(topic, source_code, GitHubParams)
sop_generation_workflow（Temporal Worker コンテナ内）
    ↓ Phase 1: generate_sop_phase_activity(outline)  → awaiting_approval
    ↓ Signal: approve_step("")  ← スクリプトが自動送信
    ↓ Phase 2: generate_sop_phase_activity(draft)    → awaiting_approval
    ↓ Signal: approve_step("")
    ↓ Phase 3: generate_sop_phase_activity(review)   → awaiting_approval
    ↓ Signal: approve_step("")
    ↓ Phase 4: validate_sop_activity → バリデーション通過（修正不要）
    ↓ Phase 5: GitHubActivity.create_pull_request
        ↓ git clone obataka/temporal-demo → /tmp/temporal_github/obataka_temporal-demo
        ↓ git checkout -B auto-fix/sop-first-test
        ↓ write docs/sop-integration-test.md
        ↓ git config user.email/name（コンテナ内の identity 設定）
        ↓ git commit → git push --force
        ↓ gh pr create --repo obataka/temporal-demo
GitHub: PR #1 作成
```

---

## B. Responsibility Matrix

| ファイルパス | 変更箇所 | 処理の目的・役割 | 相互作用する相手 |
| :--- | :--- | :--- | :--- |
| `activities/github_activity.py` | `_commit_and_push` にgit config 2行追加 | Docker コンテナ内の git identity 未設定を解消 | `subprocess.run(git commit)` |

---

## C. 発見したバグと修正

### バグ: `git commit` exit 128（git identity 未設定）

**発生箇所:** `activities/github_activity.py:130` `_commit_and_push()`

**原因:** `python:3.12-slim` ベースの Docker コンテナには `git config user.email/name` がグローバル設定されておらず、`git commit` が identity エラー（exit 128）で失敗。

**修正:** `diff.returncode != 0` ブロック内、`git commit` の直前に以下を追加:
```python
subprocess.run(["git", "-C", str(repo_dir), "config", "user.email", "temporal-worker@local"], ...)
subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "Temporal Worker"], ...)
```

**クリティカルポイント:** リポジトリ単位の設定（`--local`）で行うため、ホスト環境の git 設定に影響しない。
