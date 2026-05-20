# 概要ドキュメント: GitHub PR 実戦疎通テスト — Docker 対応修正

**作成日:** 2026-05-18  
**タスク:** Docker Worker で GitHubActivity が動作するよう Dockerfile / docker-compose.yaml を修正

---

## A. System Interaction Flow

```
.env (GITHUB_TOKEN)
    ↓ docker-compose.yaml が読み込み
Worker コンテナ (GITHUB_TOKEN 環境変数として注入)
    ↓ GitHubActivity.create_pull_request()
    ↓   git clone/fetch  ← git CLI (Dockerfile でインストール済み)
    ↓   gh pr create     ← gh CLI (Dockerfile でインストール済み、GITHUB_TOKEN で認証)
GitHub API → PR 作成
```

---

## B. Responsibility Matrix

| ファイルパス | 変更箇所 | 処理の目的・役割 | 相互作用する相手 |
| :--- | :--- | :--- | :--- |
| `Dockerfile` | `apt-get install git gh` 追加 | Worker コンテナに git と gh CLI を同梱 | `GitHubActivity._clone_or_update_repo`, `_submit_pr` |
| `docker-compose.yaml` | `GITHUB_TOKEN=${GITHUB_TOKEN}` 追加 | `.env` のトークンを Worker コンテナへ渡す | `GitHubActivity.create_pull_request` |
| `.env` | `GITHUB_TOKEN` にコメント追記 | トークンの用途と期限切れ時の対処を明記 | `docker-compose.yaml` |
| `sop_github_test.py` | docstring の実行手順を書き直し | Docker ベースの正しい手順を示す | 開発者 |

---

## C. 設計の意図とクリティカルポイント

### なぜこの設計か
- Docker コンテナ内でもホストと同じ `gh` CLI ＋ `GITHUB_TOKEN` で PR 作成できるようにする最小変更
- `gh` CLI は `GITHUB_TOKEN` 環境変数を自動的に認証情報として使用するため、`gh auth login` 不要

### クリティカルポイント（最大3点）

1. **`--build` が必須** — Dockerfile を変更したため、既存の `temporal-worker` イメージは古い。`docker compose up --build worker -d` で必ずリビルドすること。`docker compose up worker -d`（`--build` なし）では git / gh が入らない。

2. **GITHUB_TOKEN の期限** — `gh auth token` が返すトークンはOAuth App トークン（`gho_` プレフィックス）で期限がある。テスト失敗時は `.env` の値を `gh auth token` で再取得して更新すること。

3. **コンテナ内の `_REPO_BASE`** — `GitHubActivity._REPO_BASE` は `/tmp/temporal_github/` を指す。コンテナ再起動でこのディレクトリは消えるが、`_clone_or_update_repo` が冪等なので再クローンされる（問題なし）。

---

## 実行手順（修正後）

```bash
# Docker Worker を rebuild して起動
docker compose up --build worker -d

# テスト実行（ホストマシンから）
python sop_github_test.py
```
