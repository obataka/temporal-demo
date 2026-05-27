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
| 4 | E2E テストシナリオの不備 | 実行前の机上デバッグを省略した | バリデーションルールとテストデータを静的に突き合わせてから実行する |
| 5 | SDK 返り値の型の思い込み | TypeScript SDK の status が文字列でなくオブジェクト | コンテナ内の `bun -e` でランタイムの実型を確認してから実装する |

---

## Lesson 4: E2E テスト実行前の机上デバッグ不足

### 現象
E2E グランドデモ（`sop_e2e_demo.py`）を3回実行したが、すべて失敗した。

| 実行 | 失敗原因 | 机上デバッグで防げたか |
|---|---|---|
| Run 1 | `DUMMY_SOURCE_CODE` に禁止用語（未定・確認中・作成中）が含まれていた | ✓ grep で即検知可能 |
| Run 2 | `"仮"` 1文字の substring 検索が `仮定`・`仮説` 等に誤マッチした | ✓ ロジック読解で即検知可能 |
| Run 3 | Gemini free tier 上限（20 req/day）を超えてクォータ枯渇 | ✓ 事前にクォータ残量を確認すれば防止可能 |

### 原因
実行前にバリデーションルールとテストデータを静的に突き合わせる工程を省略した。

- Run 1: `validate_sop_activity.py` の `_PROHIBITED_TERMS` を確認した後、`DUMMY_SOURCE_CODE` に対して
  `grep` や `python -c` でチェックすれば一発で検知できた。
- Run 2: `_PROHIBITED_TERMS` に `"仮"` を含めたとき「日本語 SOP に `仮定`・`仮説`・`仮に` が自然に現れないか」
  を考えれば即座に気づけた。1文字の substring 検索はマルチバイト文字で過剰マッチしやすい。
- Run 3: 1回のデモあたり 5〜8 req、free tier 上限 20 req/day を考えると、3回目で枯渇すると計算できた。

### 対応（それぞれの修正）

- Run 1 → `DUMMY_SOURCE_CODE` から禁止用語・TODO を除去
- Run 2 → `_PROHIBITED_TERMS` から `"仮"` を削除し、docstring に理由（複合語との区別不能）を記載
- Run 3 → `gemini-2.5-flash-lite`（別クォータ枠、残量あり）に切り替え

### 教訓
E2E テストは「コードが正しいか」だけでなく「テストシナリオ自体が正しいか」を実行前に机上で確認する。

1. **テストデータの静的検証**: バリデーション関数を `python -c` でローカル実行し、テストデータを通して
   意図した結果（PASS / FAIL）になるか確認する。
2. **substring 検索の副作用確認**: 1文字・短い文字列の部分一致検索は、特にマルチバイト文字（日本語・中国語等）で
   compound word に誤マッチしやすい。正規表現の単語境界 `\b` や前後文脈確認を検討する。
3. **外部 API クォータの事前確認**: 1回の実行あたりの API 呼び出し回数を概算し、クォータ残量と照合してから
   実行を開始する。残量が少ない場合は代替モデル・サービスを事前に調査しておく。

---

## Lesson 5: 既存 Python スタックへ Bun + Hono コンテナを追加する手順（2026-05-25〜26）

### 背景
Python Worker + Temporal Server で動く既存スタックに、ブラウザから操作できる Web UI 拠点を追加した。

### 対応
- `web-ui/` ディレクトリに Bun + Hono アプリを作成し、TypeScript SDK（`@temporalio/client`）で Temporal Server に接続。
- `docker-compose.yaml` に `webui` サービスを追加し、既存の `temporal-network` に参加させた。
  これにより Python Worker と同じネットワーク内で `temporal:7233` への gRPC 通信が可能になる。
- `TEMPORAL_ADDRESS=temporal:7233` を環境変数で渡すだけで接続が成立した。

### 教訓
- 異なる言語スタックを同一 Docker ネットワークへ追加するコストは低い。`networks` セクションで共通ネットワークを定義し、各サービスに追記するだけ。
- ポートの役割を混同しないこと。`ports` はホストへの公開用、コンテナ間通信はサービス名（DNS）で直接解決する。
- Bun は `bun install` だけで `node_modules` が揃うため、Dockerfile のビルドが軽量になる。

---

## Lesson 6: TypeScript SDK の `workflow.list` が返すステータスは `{code, name}` のオブジェクト（2026-05-26）

### 現象
`client.workflow.list` で取得したワークフローに対して `wf.status === "RUNNING"` の比較が常に false になった。

### 原因
`wf.status` は文字列ではなく `{ code: number, name: string }` のオブジェクト構造を持つ。SDK のドキュメントや型定義だけでは把握しにくく、型推論も期待した動作をしなかった。

### 対応
コンテナ内で `bun -e` を使ってランタイムの実型を確認した:

```bash
docker exec <container> bun -e "
const { Client } = await import('@temporalio/client');
const client = new Client({ connection: { address: 'temporal:7233' } });
for await (const wf of client.workflow.list({ pageSize: 1 })) {
  console.log(JSON.stringify(wf.status));
  break;
}
"
```

`{ "code": 1, "name": "RUNNING" }` と出力されたことを確認し、`wf.status.name` を参照するよう実装を修正した。

### 教訓
SDK の返り値の型がドキュメントと異なる可能性がある場合、推測で実装せず、コンテナ内の `bun -e` や `python -c` で実際の値を確認してから実装する。これは外部 SDK 全般に適用できる原則。

---

## Lesson 7: Temporal Signal による Human-in-the-Loop の言語横断実証（2026-05-26）

### 背景
ブラウザから承認ボタンを押すことで、Python 側のワークフローが待機状態を解除して完走することを確認したかった。

### 構成
```
ブラウザ → POST /approve/:workflowId (Hono)
         → client.workflow.getHandle(id).signal("approve_pr") (TypeScript SDK)
         → Temporal Server → Python Worker の approve_pr Signal ハンドラ
         → self._approved = True → wait_condition 解除 → 後続 Activity へ進行
```

### 結果
ブラウザのボタン操作から Python ワークフローの完走まで、一連のフローが正常に動作することを実証した。

### 教訓
- Temporal の Signal はプロセス境界・言語境界を越えて動作する。TypeScript クライアントから Python ワークフローへ Signal を送ることができる。
- ワークフローの待機は `wait_condition(lambda: self._approved)` で記述し、Signal ハンドラがフラグを立てる設計にすることで、リプレイ安全性が保たれる。
- Signal を「外部トリガーとしての API」と捉えると、任意の言語・フレームワークからワークフローを操作する入口として活用できる。
