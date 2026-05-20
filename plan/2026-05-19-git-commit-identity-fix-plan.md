# 計画: git commit 失敗修正 — Docker コンテナ内の user.email/name 未設定

## Context
実戦疎通テスト中、Phase 5（GitHub PR 作成）の `git commit` が exit code 128 で失敗。
Docker コンテナ内に `git config user.email` / `user.name` が未設定なのが原因。
現在のワークフロー（`sop-github-test-262af4df`）は LLM_RETRY_POLICY の最大試行を超えて失敗済み。
修正後にテストを再実行する必要がある。

## 変更ファイル

| ファイル | 操作 | 概要 |
|---|---|---|
| `activities/github_activity.py` | **修正** | `_commit_and_push` 内、コミット直前に `git config user.email/name` を設定 |

## 変更内容

`_commit_and_push`（`github_activity.py:111`）の差分がある場合のコミットブロックに、直前で git identity を設定する 2 行を追加する。

```python
# 追加位置: diff.returncode != 0 ブロック内、git commit の直前
subprocess.run(
    ["git", "-C", str(repo_dir), "config", "user.email", "temporal-worker@local"],
    check=True, capture_output=True,
)
subprocess.run(
    ["git", "-C", str(repo_dir), "config", "user.name", "Temporal Worker"],
    check=True, capture_output=True,
)
subprocess.run(
    ["git", "-C", str(repo_dir), "commit", "-m", message],
    check=True, capture_output=True,
)
```

## 再実行手順（修正後）

```bash
docker compose up --build worker -d
python sop_github_test.py
```

## 検証
Worker ログに `git commit` の CalledProcessError が出なくなり、PR URL が標準出力に表示されること。
