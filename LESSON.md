# LESSON.md — 実戦疎通テスト実施時に発見した不具合と対応

作成日: 2026-05-19  
対象タスク: `sop_generation_workflow` Phase 5（GitHub PR 作成）の非モック統合テスト

---

## Lesson 1: Docker Worker に `git` / `gh` CLI が未インストール

### 現象
`GitHubActivity.create_pull_request` 実行時に `git clone` / `gh pr create` の subprocess 呼び出しが失敗する。

### 原因
ベースイメージ `python:3.12-slim` には `git` も `gh` CLI も含まれていない。  
ユニットテストはすべて `subprocess.run` をモックしていたため、この問題がテスト段階で顕在化しなかった。

### 対応
`Dockerfile` に以下を追加してリビルドした:

```dockerfile
RUN apt-get update && apt-get install -y git curl \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
       | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) \
       signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] \
       https://cli.github.com/packages stable main" \
       | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update && apt-get install -y gh \
    && rm -rf /var/lib/apt/lists/*
```

### 教訓
subprocess を使う Activity は、Docker イメージに必要な CLI ツールが含まれているかを必ず確認する。  
モックでカバーしたテストは「コードの正しさ」は検証するが「実行環境の完全性」は検証しない。

---

## Lesson 2: Docker Worker に `GITHUB_TOKEN` が渡されていない

### 現象
`GitHubActivity.create_pull_request` が `EnvironmentError: GITHUB_TOKEN が設定されていません。` を送出する。

### 原因
`docker-compose.yaml` の worker サービスの `environment` に `GITHUB_TOKEN` が含まれていなかった。  
`gh` CLI はコンテナ内で認証済みでないため、`GITHUB_TOKEN` 環境変数を通じて認証情報を渡す必要がある。

### 対応
`docker-compose.yaml` の worker サービスに追記:

```yaml
environment:
  - GITHUB_TOKEN=${GITHUB_TOKEN}
```

`.env` に `GITHUB_TOKEN` を設定（`.gitignore` 対象なので安全）:

```
# GitHub PR 作成用トークン（gh auth token で取得。期限切れ時は再取得すること）
GITHUB_TOKEN=<gh auth token の出力値>
```

### 教訓
外部 API を呼び出す Activity に必要な認証情報は、`docker-compose.yaml` の `environment` セクションに明示的に列挙する。  
`gh` CLI は `GITHUB_TOKEN` 環境変数を認証トークンとして自動的に利用するため、コンテナ内で `gh auth login` は不要。

---

## Lesson 3: Docker コンテナ内で `git commit` が exit 128 で失敗

### 現象
```
subprocess.CalledProcessError: Command 'git commit -m ...' returned non-zero exit status 128.
```

### 原因
`python:3.12-slim` ベースの Docker コンテナには `git config user.email` / `user.name` がグローバルに設定されていない。  
`git commit` は identity が未設定の場合に exit 128 を返す。  
ローカル環境では `~/.gitconfig` が存在するため発生しないが、クリーンなコンテナでは必ず発生する。

### 対応
`activities/github_activity.py` の `_commit_and_push` で、差分がある場合のコミット直前に identity を設定するよう修正:

```python
if diff.returncode != 0:
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

`--global` ではなくリポジトリ単位の設定（デフォルトが `--local`）にしているため、ホスト環境に影響しない。

### 教訓
Docker コンテナ内で `git commit` を実行する場合は、必ず事前に `user.email` / `user.name` を設定すること。  
ローカルでは通る処理がコンテナ内で失敗するパターンの典型例。統合テストは実際の実行環境（Docker）で行うことで初めて検出できる。

---

## 共通パターンのまとめ

| # | 問題カテゴリ | 根本原因 | 対策 |
|---|---|---|---|
| 1 | 実行環境の不完全性 | Docker イメージに CLI ツールが未同梱 | Dockerfile に必要ツールを明示的に追加 |
| 2 | 認証情報の未設定 | docker-compose.yaml への環境変数追記漏れ | 外部 API 系の認証情報は compose の environment に列挙する |
| 3 | コンテナ固有の設定不足 | git identity がクリーンコンテナに存在しない | subprocess で git commit する前に user.email/name を設定する |
