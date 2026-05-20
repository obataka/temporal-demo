# 計画: GitHub PR 実戦疎通テスト — Docker 対応修正

## Context
`sop_github_test.py` の実行手順がローカル Worker 前提になっていた。
実際は Docker Compose で Worker を起動しているため、以下の問題がある。

1. `python:3.12-slim` イメージに `git` / `gh` CLI が未インストール → subprocess 呼び出しが失敗する
2. `docker-compose.yaml` の worker サービスに `GITHUB_TOKEN` が未設定 → `GitHubActivity` が `EnvironmentError` を送出する
3. `sop_github_test.py` の実行手順コメントがローカル起動前提になっており、Docker 環境では誤解を招く

---

## 変更ファイル一覧

| ファイル | 操作 | 概要 |
|---|---|---|
| `Dockerfile` | **修正** | `git` + `gh` CLI をインストール |
| `docker-compose.yaml` | **修正** | worker 環境変数に `GITHUB_TOKEN` を追加 |
| `.env` | **修正** | `GITHUB_TOKEN` のプレースホルダーを追記（`.gitignore` 対象なので安全） |
| `sop_github_test.py` | **修正** | 実行手順コメントを Docker ベースに書き直す |

---

## 各ファイルの変更内容

### Dockerfile
`python:3.12-slim`（Debian ベース）に `apt-get` で `git` と `gh` CLI をインストールする。

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

### docker-compose.yaml — worker サービス
```yaml
environment:
  - TEMPORAL_HOST=temporal:7233
  - GEMINI_API_KEY=${GEMINI_API_KEY}
  - DEBUG_FAIL=${DEBUG_FAIL:-0}
  - GITHUB_TOKEN=${GITHUB_TOKEN}   # 追加
```

`gh` CLI は `GITHUB_TOKEN` 環境変数を自動的に認証トークンとして利用する。

### .env
```
# GitHub PR 作成に必要なトークン（gh auth token で取得）
GITHUB_TOKEN=<gh auth token の出力値をここに貼る>
```

### sop_github_test.py — docstring の実行手順
```
実行手順:
    1. .env に GITHUB_TOKEN を設定:
           GITHUB_TOKEN=$(gh auth token)  # この値を .env に記入する

    2. Docker Worker を rebuild して起動:
           docker compose up --build worker -d

    3. このスクリプトを実行:
           python sop_github_test.py
```

---

## 検証方法
1. `docker compose up --build worker -d` → ログに `worker_started` が出ること
2. `python sop_github_test.py` → コンソールに PR URL が表示されること
3. GitHub 上でブランチ `auto-fix/sop-first-test` と PR が実際に作成されていること
