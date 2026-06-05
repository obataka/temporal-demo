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
| 6 | docker compose サービス名の誤り | サービス名を確認せず推測で入力した | `docker compose up` 実行前に `docker-compose.yaml` でサービス名を確認する |
| 7 | Python↔TypeScript 命名変換の見落とし | snake_case と camelCase が自動変換されない | Hono 受信側で `typeof` チェックと両表記へのフォールバックを必ず入れる |
| 8 | ポーリング起因の UI ノイズ | 手動／システムトリガーを区別せずトーストを表示 | `silent` フラグで呼び出し元の性質を明示し、定周期ポーリングには `silent: true` を渡す |
| 9 | 自動スクロールによる視線の強奪 | コンテンツ更新時に無条件で末尾スクロールしていた | 更新前に末尾 50px 以内判定し、ユーザーが上方スクロール中は自動スクロールしない |

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

---

## Lesson 8: Python（snake_case）↔ TypeScript（camelCase）命名変換の表記揺れ（2026-06-01〜02）

### 現象
Hono API が Python Worker から受け取った JSON に含まれる `agent_logs` キーを、TypeScript の慣習に従い `agentLogs` として参照したところ値が `undefined` になり、ログが空のまま描画された。

### 原因
Python は `snake_case`、TypeScript は `camelCase` が慣習だが、両者間の JSON データは**自動的にキー名変換されない**。Python 側が `{"agent_logs": [...]}` を出力しても、TypeScript 側でそのまま `body.agentLogs` と参照すると `undefined` になる。マルチエージェント化の過程で Python の Activity が返す辞書キーと、Hono 側が期待するキー名が静かにずれ続けた。

### 対応
Hono の受信ハンドラ側で `typeof` チェックと両表記へのフォールバックを入れるディフェンシブ・プログラミングを徹底した:

```typescript
// NG: キー名を決め打ちで参照する
const logs = (body as any).agentLogs;

// OK: typeof チェックと両表記へのフォールバック
const rawBody = body as Record<string, unknown>;
const logs = (rawBody.agent_logs ?? rawBody.agentLogs) as AgentLog[] | undefined;
```

### 教訓
Python と TypeScript の境界をまたぐ JSON データは、どちらの表記で来るかを**受信側で必ず型チェック（`typeof`）と正規化**してから使うこと。送信側の命名規則を強制できない場合は特に重要。フォールバック式 `(obj.snake_key ?? obj.camelKey)` を Hono のリクエストハンドラの先頭に置くことをデフォルトとせよ。

---

## Lesson 9: 定周期ポーリング時のトースト通知ノイズ（`silent` フラグ）（2026-06-02）

### 現象
`fetchStatus()` を 5 秒ごとに定周期実行したところ、「ステータスを取得しました」などのトースト通知が絶え間なく表示され、ユーザーが実際の操作フィードバックを見逃す UI になった。

### 原因
トースト表示の呼び出しが手動ボタン操作とシステムポーリングで共通化されており、トリガーの性質（ユーザー起点 vs システム起点）を区別していなかった。定周期ポーリングは「ユーザーが意図して要求した行為」ではないため、その都度フィードバックを返すのは UI ノイズでしかない。

### 対応
`fetchStatus` に `silent` 引数を追加し、呼び出し元の性質を明示的に渡す:

```typescript
// NG: トリガーの区別なくトーストを表示する
async function fetchStatus() {
    const data = await api.getStatus();
    showToast("ステータスを取得しました");
}

// OK: silent フラグで制御する
async function fetchStatus(silent = false) {
    const data = await api.getStatus();
    if (!silent) showToast("ステータスを取得しました");
}

// 定周期ポーリング（システムトリガー）
setInterval(() => fetchStatus(true), 5000);

// 手動更新ボタン（ユーザーtrigger）
refreshButton.onclick = () => fetchStatus(false);
```

### 教訓
「ユーザーが明示的に操作した結果」だけがトーストフィードバックに値する。定周期ポーリングや自動リフレッシュなどのシステムトリガーからはトーストを出さない。`silent` フラグを関数シグネチャに設けることで、呼び出し元がトリガーの性質を宣言する責任を持つ設計とせよ。

---

## Lesson 10: ログコンソール自動スクロールによるユーザーの視線の強奪（2026-06-02）

### 現象
エージェントログコンソールで古いログを読もうとユーザーが上方スクロールしている最中に、新しいログが追加されるたびに画面が末尾へ強制スクロールされ、ユーザーが読んでいた箇所を見失い続けた。

### 原因
ログ追加時に無条件で `el.scrollTop = el.scrollHeight` を実行していた。コンテンツの更新とスクロール位置の制御が分離されておらず、ユーザーのスクロール状態を考慮していなかった。

### 対応
コンテンツ更新前にユーザーが末尾から 50px 以内にいるかを判定し、末尾付近の場合のみ自動スクロールする近接バッファロジックを導入した:

```typescript
function appendLog(text: string): void {
    const el = document.getElementById("log-console")!;

    // 更新前にユーザーが末尾付近（50px 以内）にいるかを先に判定する
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50;

    el.textContent += text + "\n";

    // 末尾付近にいた場合のみ追従スクロールする
    if (isNearBottom) {
        el.scrollTop = el.scrollHeight;
    }
}
```

50px は「ユーザーが末尾を見ている」とみなせる十分なバッファ幅。これより大きくすると誤って自動スクロールが走る場面が増える。

### 教訓
自動スクロールは「ユーザーが既に末尾を見ている場合の利便性向上」であり、「強制的な視線誘導」ではない。コンテンツ更新前に `scrollHeight - scrollTop - clientHeight < 50` を評価し、上方スクロール中のユーザーには一切干渉しないことをデフォルトとせよ。このロジックをログコンソール・チャット画面・ターミナルエミュレータ等、あらゆるライブストリーミング UI に適用すること。

---

## 2026年6月第1週スプリント総括

記録日: 2026-06-05  
対象期間: 2026-06-01 〜 2026-06-05（第1週スプリント）

### 成果：CrewAI × Temporal ワークフロー E2E 結合の完全開通

本スプリントの最大の成果は、**CrewAI（Writer エージェント & Reviewer エージェント）と Temporal ワークフローの E2E 統合に完全成功**したことである。

- Writer と Reviewer の 2 エージェントがそれぞれ役割を持ち、SOP（標準操作手順書）の自動生成・レビュー・修正を自律的に繰り返すマルチエージェント議論ループを Temporal Activity として実装した。
- ブラウザ UI からオペレーターが「差し戻し（人間フィードバック）」ボタンを押すと Temporal Signal が発火し、AI 同士の自律相互レビュー・修正ループが再開する **Human-in-the-Loop** アーキテクチャを完全に開通させた。
- Hono（TypeScript）× Python Worker × Temporal Server の三層構成で、言語をまたぐ Signal 送受信・ログストリーミング・UI 同期がすべて正常に機能することを本番同等の E2E デモで実証した。

### メトリクス：E2E 実行の計測結果

| 指標 | 値 |
|---|---|
| E2E 総所要時間 | 約 6.2 分 |
| 自動生成フェーズ数 | 5 フェーズ（SOP 草案 → マルチエージェント議論 → 修正 → バリデーション → PR 作成） |
| 生成された GitHub PR | PR #5 |
| 完走ステータス | 正常完走（エラーなし） |

5 フェーズの自動生成、CrewAI による Writer/Reviewer の多回往復議論、`validate_sop_activity` によるバリデーション、GitHub PR 作成（PR #5）を含むフル E2E フローが、人手介入なしで約 6.2 分以内に正常完走することを確認した。

### ガバナンス：開発規律の恒久化

本スプリントで生じた設計上の知見（下記3点）を、プロジェクトローカルおよびグローバルの `CLAUDE.md` へ**永続ルールとして完全恒久化**した。これにより将来の全セッションに対して自動的に適用される。

1. **Hono ディフェンシブ型チェック**（Python↔TypeScript 命名変換問題への対処）  
   snake_case / camelCase 両表記へのフォールバック `(rawBody.snake_key ?? rawBody.camelKey)` を、言語境界をまたぐ全エンドポイントに義務化。

2. **`silent` フラグによるトースト通知制御**  
   定周期ポーリング（システムトリガー）と手動ボタン操作（ユーザートリガー）を `silent` フラグで明示的に分離し、システムトリガーからのトーストノイズを根絶。

3. **50px 近接バッファによる自動スクロール制御**  
   ログコンソール等のライブストリーミング UI において、コンテンツ追記前に末尾 50px 以内判定を行い、上方スクロール中のユーザーへの干渉を禁止。

### 振り返り

| 観点 | 評価 |
|---|---|
| 技術的達成度 | CrewAI × Temporal の E2E 統合という、実証例の少ない構成を完全に動作させた |
| 品質 | バリデーション、型安全、UI UX（トースト・スクロール）まで細部を詰めた |
| ガバナンス | 開発規律をコードではなくルールとして `CLAUDE.md` に恒久化し、再発防止を制度化した |
| 課題 | E2E テスト実行前の机上デバッグ（Lesson 4）は手順として確立できたが、個人の習慣定着には継続的な意識が必要 |
