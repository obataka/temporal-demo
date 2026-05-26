## SOPレビュー結果

### 改善点リスト

以下に、提供されたSOP草稿に対する改善点をリストアップします。

1.  **全体的な構成と明確性:**
    *   **[重要] 目的と範囲の具体性:** 「Web UI 結合動作確認テスト用 SOP（Temporal × Hono 統合検証）」というタイトルは具体的ですが、SOP本文の「1. はじめに」セクションにおいて、テスト対象となる具体的なWeb UIアプリケーション名や、連携するTemporal/Honoの具体的な機能（例：ユーザー認証、データ同期、非同期処理など）について、より明確に言及することが望ましいです。現状は一般的な説明に留まっています。
    *   **[重要] コード例のコンテキスト:** コード例は有用ですが、それぞれのコードがどのファイルに配置され、どのように連携するのか、より詳細なコンテキストが必要です。特に、Pythonのダミーモジュールとの連携部分について、TypeScriptからPythonコードをどのように呼び出すのか（例：gRPC、REST API、あるいは何らかのライブラリ経由か）が不明瞭です。
    *   **[中] 用語の定義:** 「ダミーモジュール」の定義が「E2E デモ用に用意された、一部のロジック（バリデーション、戻り値など）が実装されていない、または簡易的な実装にとどまっている Python コードモジュール」となっていますが、これは「テストのために用意されたモジュール」というニュアンスで、より具体的に「テスト目的で、実際のサービスロジックの代わり、または特定のテストシナリオ（例：エラー再現）のために実装されたモジュール」と定義する方が良いでしょう。
    *   **[中] 表記ゆれ・誤字:**
        *   「Temporal」の表記が「Temporal」と「temporal」で混在しています（例: `temporalio/auto-setup`, `@temporalio/workflow`, `@temporal/shared`）。一貫性を保つために、プロジェクト内で使用している表記に統一してください。
        *   「実際の И結果」という箇所は「実際の 結果」の誤字と思われます。
        *   「Temporal UI (または `tctl`)」は、`tctl` は CLI ツールであり、UI ではないため、誤解を招く可能性があります。Temporal Web UI と Temporal CLI (`tctl`) を区別して記述することを推奨します。

2.  **テスト環境の準備:**
    *   **[中] Docker Compose の詳細:** `docker-compose.yml` の例が提示されていますが、Hono や Web UI をコンテナ化して実行する場合の `docker-compose.yml` の設定例も追加すると、環境構築の再現性が高まります。
    *   **[低] 依存関係のバージョン管理:** Node.js の LTS バージョン推奨は良いですが、具体的なバージョン（例: Node.js v18.x）や、Hono、Temporal SDK などのライブラリのバージョンについても、可能であれば指定またはバージョン管理方法（例: `package-lock.json`, `yarn.lock`）を明記することが望ましいです。

3.  **テスト実行手順:**
    *   **[重要] テストシナリオの具体性:** 各シナリオの説明は良いですが、UI 上での具体的な操作（ボタン名、入力フィールド名など）を、より詳細に記述するか、UI のスクリーンショットへの参照を加えると、テストの再現性が向上します。
    *   **[重要] Python ダミーモジュールとの連携:** シナリオ D および付録 5.1.1 で、Python ダミーモジュールが `None` を返すことが前提となっていますが、TypeScript から Python モジュールをどのように呼び出しているかの詳細な説明が不足しています。これが E2E テストの重要な部分であるため、この連携部分（例: gRPC, Docker 経由での通信など）を明確にする必要があります。現状のコード例では `import { DataProcessor } from '@your-project/dummy-module';` となっていますが、これがどのように実現されているのか説明が必要です。
    *   **[中] Hono 側の Task Queue 名:** Hono 側のコード例で `taskQueue: 'my-task-queue'` とありますが、この Task Queue 名がどこで定義され、Temporal Worker とどのように一致させるのか、補足説明があると良いでしょう。
    *   **[中] 「ダミーモジュールでの処理失敗」の定義:** シナリオ D では「ダミーモジュールでの処理失敗」を「`None` を返す」と定義していますが、これが意図された失敗なのか、それともエラーとして扱うべきなのか、テストの意図を明確にする必要があります。付録 5.1.1 ではエラーとして扱っていますが、SOP本文との整合性も確認が必要です。
    *   **[低] テストデータの具体例:** テストデータファイル (`test_data/workflow_inputs.json`) の例は良いですが、各シナリオで具体的にどのようなデータが入力されるのか、より詳細な例があると分かりやすいです。

4.  **結果の記録と評価:**
    *   **[中] テスト管理ツールの利用:** テスト管理ツールを使用している場合、そのツールへの記録方法や、リンクの張り方など、具体的な手順を追記すると、より実践的になります。
    *   **[中] ログ収集のポイント:** ログレベルの設定や、時系列での収集の重要性は良い点ですが、「関連するコンポーネントのログを時系列で収集し、連携を確認します」という部分について、どのようなツール（例: Fluentd, ELK Stackなど）を使用するか、または手動でどのように収集・整理するかを具体的に示唆すると、より実用的になります。
    *   **[低] エラー発生時の対応（切り分け）:** 問題の切り分け方法について、より具体的なチェックリストやフローチャートのようなものがあると、担当者が迅速に対応しやすくなります。

5.  **付録:**
    *   **[重要] Python ダミーモジュールとの連携方法:** 付録 5.1.1 での Python ダミーモジュールと TypeScript からの連携について、具体的な実装方法（例: gRPC サーバーを立てて通信する、Docker コンテナ間で通信するなど）を追記することが最も重要です。
    *   **[中] パフォーマンス測定:** パフォーマンス測定の SOP が別途存在する場合、その SOP への参照を明記すると良いでしょう。

---

### 最終版 SOP

上記改善点を踏まえ、以下に最終版 SOP を提示します。一部、説明を補足・明確化し、コード例のコンテキストを改善しました。

---

# Web UI 結合動作確認テスト用 SOP（Temporal × Hono 統合検証）

## 1. はじめに

### 1.1. 本 SOP の目的

本標準作業手順書（SOP）は、[具体的なWeb UIアプリケーション名] において、Temporal と Hono を連携させた結合動作確認テストを、一貫性のある正確な手順で実施することを目的とします。これにより、テストの再現性、効率性を確保し、開発チーム全体が共通の理解のもとでテストを進めることを支援します。特に、ユーザー操作から Web UI、Hono API ゲートウェイ、Temporal Workflow、そして結果の Web UI への反映までの一連のエンドツーエンド（E2E）の動作を検証します。

### 1.2. 適用範囲

本 SOP は、以下のコンポーネントが連携して動作する、[具体的なWeb UIアプリケーション名] の結合動作確認テスト全般に適用されます。

*   **Web UI:** ユーザーがブラウザから操作するフロントエンドアプリケーション。
*   **Hono:** Web UI からのリクエストを受け付け、Temporal Workflow をトリガーする API ゲートウェイ。
*   **Temporal:** Hono からトリガーされた Workflow を実行・管理するワークフローエンジン。

対象となるテストは、ユーザーの UI 操作が Hono API に送信され、Hono が Temporal Workflow をトリガーし、Workflow の実行結果が Hono API を経由して Web UI にフィードバックされるまでの一連のフローです。

### 1.3. 用語の定義

| 用語                   | 定義                                                                                                                                                                                            |
| :--------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Temporal**           | 分散システムにおけるステートフルなアプリケーションを構築するためのワークフローエンジン。信頼性、スケーラビリティ、耐障害性に優れたアプリケーション開発を支援します。                                                                                                 |
| **Hono**               | 軽量で高速な Node.js フレームワーク。HTTP サーバー、ルーティング、ミドルウェア機能を提供し、API サービスや Web アプリケーションのバックエンド構築に利用されます。                                                                                                |
| **Web UI**             | Web ブラウザを通じてユーザーが操作するインターフェース。本 SOP では、[具体的なWeb UIアプリケーション名] を指します。                                                                                                                                      |
| **結合動作確認テスト**   | システムの複数のコンポーネント（Web UI, Hono, Temporal）が連携して正しく動作することを確認するテスト。エンドツーエンド（E2E）テストの一環として実施されます。                                                                                                                |
| **Workflow (Temporal)**| Temporal における一連の処理（アクティビティの実行など）を定義・管理するコード。複雑なビジネスロジックや長期間実行される処理の実装に使用されます。                                                                                                                             |
| **Activity (Temporal)**| Temporal Workflow 内で実行される個々のタスク。外部サービス連携や具体的な処理ロジックを実装します。                                                                                                                                                           |
| **API Gateway (Hono)** | Hono が提供する、クライアントからのリクエストを受け付け、適切なバックエンドサービス（Temporal Workflow のトリガーなど）へルーティングする機能。                                                                                                                             |
| **E2E テスト**         | End-to-End テストの略。ユーザーが実際にシステムを利用する流れを模倣し、システム全体の機能が要件通りに動作するかを確認するテスト。                                                                                                                                                           |
| **テスト用モジュール**   | テスト目的で、実際のサービスロジックの代わり、または特定のテストシナリオ（例：エラー再現）のために用意されたコードモジュール。本 SOP では、Python で実装され、Temporal Worker から呼び出される `dummy_module` を指します。                                                                                                      |

## 2. テスト環境の準備

### 2.1. 必要なソフトウェア・ツール

テストを実行するために、以下のソフトウェアおよびツールが必要です。

*   **Temporal:**
    *   Temporal Server (Docker Compose によるデプロイを推奨)
    *   Temporal CLI (`tctl` または `temporal` コマンドラインインターフェース)
*   **Hono:**
    *   Node.js (v18.x LTS バージョン推奨)
    *   npm (v9.x 以降) または yarn (v1.x 以降)
    *   Hono アプリケーションコード
*   **Web UI:**
    *   Node.js (v18.x LTS バージョン推奨)
    *   npm (v9.x 以降) または yarn (v1.x 以降)
    *   Web UI アプリケーションコード
*   **開発・実行環境:**
    *   Docker および Docker Compose (Temporal Server、および必要に応じて Hono/Web UI のコンテナ化に利用)
    *   Git (ソースコード管理)
    *   テキストエディタまたは IDE (VS Code など)
    *   Web ブラウザ (Google Chrome, Firefox など、テスト対象)
    *   [Python バージョン (例: Python 3.10)] (テスト用モジュール用)

### 2.2. 環境構築手順

#### 2.2.1. Temporal のセットアップ

1.  **Docker のインストール:** Docker 公式サイトの指示に従ってインストールします。
2.  **Temporal Server の起動:**
    *   プロジェクトのルートディレクトリ、または専用のインフラディレクトリに `docker-compose.yml` ファイルを作成します。
    ```yaml
    version: '3.8'
    services:
      temporal:
        image: temporalio/auto-setup:latest
        ports:
          - "7233:7233" # Frontend service port
          - "7234:7234" # Matching service port
          - "7239:7239" # Admin service port
        environment:
          TEMPORAL_CLI_SHOW_STACK_TRACE: "true"
    ```
    *   ターミナルで `docker-compose up -d` コマンドを実行し、Temporal Server をバックグラウンドで起動します。
    *   `docker ps` コマンドで `temporalio/auto-setup` コンテナが起動していることを確認します。
3.  **Temporal CLI の確認:** `tctl version` または `temporal version` コマンドを実行し、CLI が Temporal Server と通信できることを確認します。

#### 2.2.2. Hono アプリケーションのセットアップ

1.  **Node.js およびパッケージマネージャーのインストール:** Node.js (v18.x LTS 推奨) と npm (v9.x 以降) または yarn をインストールします。
2.  **Hono プロジェクトのセットアップ:**
    *   Hono アプリケーションのソースコードディレクトリに移動します。
    *   `npm install` または `yarn install` を実行して、依存パッケージをインストールします。
3.  **Temporal との連携設定:**
    *   Hono アプリケーションが Temporal Workflow をトリガーするための API エンドポイント（例: `/api/register`）が実装されていることを確認します。
    *   Temporal Server への接続情報（デフォルト: `localhost:7233`）が環境変数 (`TEMPORAL_GRPC_ENDPOINT`) や設定ファイルで正しく設定されていることを確認します。

#### 2.2.3. Web UI アプリケーションのセットアップ

1.  **Node.js およびパッケージマネージャーのインストール:** Node.js (v18.x LTS 推奨) と npm (v9.x 以降) または yarn をインストールします。
2.  **Web UI プロジェクトのセットアップ:**
    *   Web UI アプリケーションのソースコードディレクトリに移動します。
    *   `npm install` または `yarn install` を実行して、依存パッケージをインストールします。
3.  **Hono API への接続設定:**
    *   Web UI が Hono API サーバー（例: `http://localhost:3000`）にリクエストを送信できるよう、CORS 設定などが Hono 側で適切に行われていることを確認します。
    *   Web UI のコード内で、Hono API のエンドポイント URL が環境変数（例: `VITE_API_BASE_URL`）などで正しく設定されていることを確認します。

#### 2.2.4. Python テスト用モジュールのセットアップ

1.  **Python のインストール:** Python 3.10 以降をインストールします。
2.  **テスト用モジュールディレクトリへ移動:** `dummy_module.py` が含まれるディレクトリに移動します。
3.  **依存関係のインストール (必要な場合):** もし `dummy_module.py` が外部ライブラリに依存している場合は、`pip install -r requirements.txt` などを実行します。

#### 2.2.5. 連携設定の確認 (事前テスト)

E2E テスト実行前に、以下の基本的な連携が機能することを確認します。

*   Web UI から Hono API へのリクエストが成功すること（CORS、ネットワーク接続）。
*   Hono API が Temporal Workflow を正しくトリガーできること（Temporal Server への接続、Workflow 開始）。
*   Temporal Worker が Workflow を実行できること。

### 2.3. テストデータの準備

テストシナリオで使用するデータは、以下の方法で準備します。

*   **テストデータファイル:**
    *   JSON や CSV 形式でテストデータをファイルに保存します。
    *   例: `tests/fixtures/workflow_inputs.json`
    ```json
    [
      {
        "workflow_type": "DataProcessingWorkflow",
        "input_data": { "id": "test-001", "payload": "sample payload" }
      },
      {
        "workflow_type": "AnotherWorkflow",
        "input_data": { "user_id": "user-abc", "settings": {"timeout": 60} }
      }
    ]
    ```
*   **配置場所:**
    *   テストコードからアクセスしやすいように、プロジェクト内の `tests/fixtures` ディレクトリなどに配置します。
*   **データ生成スクリプト:**
    *   必要に応じて、Python スクリプトなどで動的にテストデータを生成し、ファイルに保存します。

## 3. テスト実行手順

### 3.1. テストシナリオの概要

本テストでは、Web UI からのユーザー操作が Hono API を介して Temporal Workflow をトリガーし、その実行結果が Web UI に正しく表示されるまでの一連の結合動作を検証します。

*   **シナリオ A:** 新規データ登録ワークフローの実行
*   **シナリオ B:** 既存データ更新ワークフローの実行
*   **シナリオ C:** ワークフロー実行中のステータス確認
*   **シナリオ D:** 異常系ワークフロー（テスト用モジュールでの処理失敗）の実行

### 3.2. 各コンポーネントの起動

1.  **Temporal Server の起動:**
    *   `docker-compose up -d` を実行し、Temporal Server が起動していることを確認します (`docker ps`)。
2.  **Temporal Worker の起動:**
    *   Temporal Worker プロジェクトのディレクトリに移動し、Worker を起動します。
    ```bash
    # 例: npm start または ts-node src/worker.ts
    npm run start:worker
    ```
    *   Worker が指定された Task Queue (`my-task-queue` など) でリッスンを開始したことを確認します。
3.  **Hono アプリケーションの起動:**
    *   Hono アプリケーションのディレクトリで、開発サーバーを起動します。
    ```bash
    # 例:
    npm run dev:hono
    # または yarn dev:hono
    ```
    *   サーバーが `http://localhost:3000` (または指定ポート) で起動したことを確認します。
4.  **Web UI アプリケーションの起動:**
    *   Web UI アプリケーションのディレクトリで、開発サーバーを起動します。
    ```bash
    # 例:
    npm run dev:web
    # または yarn dev:web
    ```
    *   開発サーバーが `http://localhost:5173` (または指定ポート) で起動したことを確認します。

### 3.3. 各テストシナリオの実行

#### 3.3.1. シナリオ A: 新規データ登録ワークフローの実行

**目的:** Web UI から新規データを登録し、Hono を介して Temporal Workflow がトリガーされ、正常に完了することを確認する。

**手順:**

1.  **Web UI アクセス:** ブラウザで Web UI (`http://localhost:5173`) にアクセスします。
2.  **新規登録画面遷移:** UI 上の「新規登録」ボタンをクリックし、データ入力画面へ遷移します。
3.  **データ入力:** 必須項目（例: `ID`, `Payload`）にテストデータを入力します。
    *   例:
        *   ID: `new-item-001`
        *   Payload: `{"message": "This is a new item"}`
4.  **登録ボタンクリック:** 「登録」ボタンをクリックします。
5.  **Hono API リクエスト:** Web UI は入力データを Hono API (`POST /api/register`) へ送信します。
6.  **Temporal Workflow トリガー (Hono):** Hono は受け取ったデータで Temporal の `DataProcessingWorkflow` をトリガーします。
    ```javascript
    // Hono application (e.g., src/api.ts)
    import { Hono } from 'hono';
    import { client } from '@temporalio/client'; // Assuming client is initialized elsewhere
    import { WorkflowNames } from '@temporal/shared'; // Define WorkflowNames appropriately

    const app = new Hono();

    app.post('/api/register', async (c) => {
      const body = await c.req.json();
      const { id, payload } = body;

      try {
        // Ensure client is initialized with Temporal GRPC endpoint
        const temporalClient = await client.connect({
           address: Deno.env.get("TEMPORAL_GRPC_ENDPOINT") || "localhost:7233",
           // namespace: Deno.env.get("TEMPORAL_NAMESPACE") || "default", // Optional
        });

        const handle = await temporalClient.workflow.start(WorkflowNames.DataProcessingWorkflow, {
          args: [{ id, payload }],
          taskQueue: 'my-task-queue', // Task Queue name must match Worker configuration
          workflowId: `data-processing-${id}-${Date.now()}`,
        });
        return c.json({ message: 'Workflow started', workflowId: handle.workflowId });
      } catch (error) {
        console.error('Failed to start Temporal workflow:', error);
        return c.json({ error: 'Failed to start workflow' }, 500);
      }
    });
    export default app;
    ```
7.  **Temporal Workflow 実行:** Temporal Server が `DataProcessingWorkflow` を実行し、`processData` Activity を呼び出します。
    ```typescript
    // Temporal Worker (e.g., src/workflows/dataProcessingWorkflow.ts)
    import { proxyActivities } from '@temporalio/workflow';
    import type * as activities from '../activities'; // Define activities path

    const { processData } = proxyActivities<typeof activities>(
      { startToCloseTimeout: '1 minute' },
      { scheduleToCloseTimeout: '10 minutes' },
    );

    export async function DataProcessingWorkflow(input: { id: string; payload: any }): Promise<string> {
      await processData(input.payload); // Call the activity
      return `Data processed for ID: ${input.id}`;
    }
    ```
    ```typescript
    // Temporal Worker Activity (e.g., src/activities/index.ts)
    // This assumes the Python dummy module is exposed via a service or compiled module.
    // For demonstration, we'll simulate calling a Python module result.
    import { callPythonDummyProcessor } from '../utils/pythonBridge'; // Hypothetical function

    export async function processData(data: any): Promise<any> {
        console.log('Activity: processData called with', data);
        // Assume callPythonDummyProcessor handles the communication with the Python module
        const result = await callPythonDummyProcessor('process', data);
        console.log('Activity: processData received result:', result);
        // In this success scenario, assume the Python module returns a valid result (not None)
        return result;
    }
    ```
8.  **結果確認 (Web UI):** Hono API は Workflow の実行結果を Web UI に返します。UI は成功メッセージを表示します（例: 「データが正常に登録されました。」）。
    *   **期待される結果:** UI に成功メッセージが表示されること。

#### 3.3.2. シナリオ B: 既存データ更新ワークフローの実行

**目的:** Web UI から既存データを更新し、Hono を介して Temporal Workflow がトリガーされ、正常に完了することを確認する。

**手順:**

1.  **Web UI アクセス:** ブラウザで Web UI (`http://localhost:5173`) にアクセスします。
2.  **既存データ選択:** 更新対象のデータ（例: シナリオ A で登録した `new-item-001`）を選択します。
3.  **編集画面遷移:** 「編集」ボタンをクリックし、データ編集画面へ遷移します。
4.  **データ更新:** `Payload` を更新します。
    *   例: `Payload: {"message": "This item has been updated"}`
5.  **更新ボタンクリック:** 「更新」ボタンをクリックします。
6.  **Hono API リクエスト:** Web UI は更新データを Hono API (`PUT /api/update/:id`) へ送信します。
7.  **Temporal Workflow トリガー (Hono):** Hono は `UpdateDataWorkflow` をトリガーします。
8.  **Temporal Workflow 実行:** Workflow が `UpdateDataActivity` を呼び出します。
9.  **結果確認 (Web UI):** Hono API は Workflow の実行結果を Web UI に返します。UI は更新成功メッセージを表示します。
    *   **期待される結果:** UI に更新成功メッセージが表示されること。

#### 3.3.3. シナリオ C: ワークフロー実行中のステータス確認

**目的:** Temporal Workflow の実行中に、Web UI でそのステータス（進行中など）が正しく表示されることを確認する。

**手順:**

1.  **長時間実行ワークフローのトリガー:** 意図的に処理に時間がかかるような入力データを使用するか、Activity 内で `sleep` を挿入するなどして、長時間実行されるワークフローを開始します（シナリオ A または B を応用）。
2.  **ステータス確認画面遷移:** Web UI の「ワークフロー一覧」や「実行状況」画面に遷移します。
3.  **ステータス確認:** 実行中のワークフローのステータスが「進行中 (Running)」と表示されていることを確認します。
4.  **完了後のステータス確認:** Workflow が完了した後、ステータスが「成功 (Completed)」に更新されることを確認します。
    *   **期待される結果:** UI 上のステータス表示が、Workflow の実行状態に合わせて更新されること。

#### 3.3.4. シナリオ D: 異常系ワークフロー（テスト用モジュールでの処理失敗）の実行

**目的:** テスト用モジュール (`dummy_module.py`) の `process` メソッドが `None` を返す場合に、Temporal Workflow が失敗として検知され、Web UI にエラー通知が表示されることを確認する。

**前提:**
Python の `dummy_module.py` の `DataProcessor.process` メソッドは、常に `None` を返すように実装されています。

**手順:**

1.  **Web UI アクセス:** ブラウザで Web UI (`http://localhost:5173`) にアクセスし、新規登録画面を開きます。
2.  **データ入力:** テストデータを入力します（例: `ID: "fail-test-001"`, `Payload: {"data": "trigger failure"}`）。
3.  **登録ボタンクリック:** 「登録」ボタンをクリックします。
4.  **Hono API リクエスト:** Web UI はデータを Hono API へ送信します。
5.  **Temporal Workflow トリガー (Hono):** Hono は `DataProcessingWorkflow` をトリガーします。
6.  **Temporal Workflow 実行:** Worker の Activity (`processData`) が実行され、Python の `DataProcessor.process` を呼び出します。
    ```python
    # dummy_module.py (example)
    import logging
    logger = logging.getLogger(__name__)

    class DataProcessor:
        def process(self, data: dict) -> dict | None:
            logger.debug(f"Processing data: {data}")
            # Simulate returning None, indicating a failure or unexpected state
            return None
    ```
7.  **Activity の失敗:** Temporal Worker の Activity 実装で、`None` が返された場合、エラーをスローするように実装します。
    ```typescript
    // Temporal Worker Activity (e.g., src/activities/index.ts)
    import { callPythonDummyProcessor } from '../utils/pythonBridge';

    export async function processData(data: any): Promise<any> {
        console.log('Activity: processData called with', data);
        const result = await callPythonDummyProcessor('process', data); // This will return null

        if (result === null) {
            console.warn('Activity: processData received None result. Simulating workflow failure.');
            // Explicitly throw an error to mark the Activity and Workflow as failed
            throw new Error('Simulated processing failure: DataProcessor returned None.');
        }
        console.log('Activity: processData successful with result:', result);
        return result;
    }
    ```
8.  **Workflow 失敗:** Temporal Server は、Activity の失敗を受けて Workflow を「失敗 (Failed)」状態にします。
9.  **結果確認 (Web UI):** Hono API は Workflow の失敗情報（エラーメッセージ）を Web UI に返します。UI はエラーメッセージ（例: 「データの処理に失敗しました。(Processor returned None)」）を表示します。
    *   **期待される結果:** UI に、処理の失敗を示すエラーメッセージが表示されること。

### 3.4. [必要に応じてシナリオを追加]

*   **シナリオ E:** ワークフローのキャンセル
*   **シナリオ F:** タイムアウト処理
*   **シナリオ G:** リトライ処理

## 4. 結果の記録と評価

### 4.1. テスト結果の記録方法

各テストシナリオの実行結果は、以下のフォーマットに従って記録します。テスト管理ツール（TestRail, Allure Report など）を使用している場合は、そちらに記録します。

*   **テストケース ID:** (例: `TC-JOIN-001`)
*   **シナリオ名:** (例: `新規データ登録ワークフローの実行`)
*   **実行日時:**
*   **実行者:**
*   **テスト環境:** (Temporal, Hono, Web UI, Worker, Python モジュールのバージョン、OS など)
*   **テスト手順:** (SOP の該当セクションへの参照、または詳細な手順)
*   **期待される結果:**
*   **実際の И結果:** (「実際の 結果」の誤字修正)
*   **ステータス:** (`Passed` / `Failed` / `Blocked`)
*   **備考:** (特記事項、エラーメッセージの詳細など)
*   **スクリーンショット/ログへのリンク:** (該当する場合)

**例:**

| テストケース ID | シナリオ名                     | 実行日時             | 実行者 | ステータス | 備考                                       |
| :-------------- | :----------------------------- | :------------------- | :----- | :--------- | :----------------------------------------- |
| TC-JOIN-001     | 新規データ登録ワークフロー実行 | 2023-10-27 10:00:00  | 山田   | Passed     | UI に成功メッセージが表示された。           |
| TC-JOIN-004     | 異常系ワークフロー実行         | 2023-10-27 10:15:00  | 山田   | Failed     | UI にエラー「処理失敗 (Processor returned None)」が表示。ログ確認要。 |

### 4.2. ログの取得方法

問題発生時のデバッグに不可欠なため、以下のコンポーネントからログを取得します。

*   **Temporal Server:**
    *   Docker を使用している場合:
        ```bash
        docker logs <temporal-server-container-name>
        ```
*   **Temporal Worker:**
    *   Worker プロセスを起動しているターミナルまたはログファイルを確認します。
    *   Worker コード内の `console.log`, `console.warn`, `console.error` で出力されるログ。
*   **Hono Application:**
    *   Hono サーバーを起動しているターミナルまたはログファイルを確認します。
    *   Hono アプリケーション内の `console.log`, `c.log` で出力されるログ。
*   **Web UI:**
    *   ブラウザの開発者コンソール（F12 キー）の「コンソール」タブを確認します。
    *   Web UI の開発サーバー起動時のログも確認します。
*   **Python テスト用モジュール:**
    *   Python モジュールを呼び出す際のプロセス（例: Worker 内の `pythonBridge`）のログ、または Python モジュール自体のログファイルを確認します。

**ログ収集のポイント:**

*   テスト実行前に、各コンポーネントのログレベルを `DEBUG` など詳細なレベルに設定することを推奨します。
*   問題発生時は、関連するコンポーネントのログを **時系列** で収集し、問題箇所を特定します。
*   エラーメッセージは必ずコピーまたはスクリーンショットで記録します。

### 4.3. 判定基準

*   **Passed:**
    *   テストシナリオで定義されたすべての手順が実行され、期待される結果と一致した場合。
    *   Web UI には、操作に対する正常な応答（成功メッセージ、更新されたデータ表示など）が表示されること。
    *   関連するログに、予期しないエラーや致命的な警告が含まれていないこと。
*   **Failed:**
    *   テスト手順の実行中にエラーが発生し、期待される結果が得られなかった場合。
    *   Web UI がクラッシュしたり、応答しなくなったりした場合。
    *   Web UI にエラーメッセージが表示され、その原因が Temporal、Hono、Web UI、またはそれらの連携にあると特定された場合。
    *   期待されるデータが正しく表示・更新されない場合。
*   **Blocked:**
    *   テスト対象のコンポーネント（Temporal, Hono, Web UI など）に問題があり、テストを実行できない場合（例: サーバーが起動しない、ネットワーク接続がない）。

### 4.4. エラー発生時の対応

1.  **エラーの特定と再現:**
    *   発生したエラーメッセージを正確に記録します。
    *   可能であれば、エラーを再現できる手順を特定します。
2.  **ログの確認:**
    *   前述の「4.2. ログの取得方法」に従い、関連するコンポーネントのログを確認します。
    *   エラーメッセージとログを照合し、問題の原因箇所を特定します。
3.  **テストの再実行:**
    *   一時的な問題（ネットワーク遅延など）の可能性もあるため、可能であればテストを再実行します。
4.  **問題の切り分け:**
    *   **Web UI → Hono:** ブラウザ開発者コンソール（ネットワークタブ、コンソールタブ）で、リクエスト/レスポンス、CORS、JavaScript エラーを確認。
    *   **Hono → Temporal:** Hono アプリケーションのログで、Temporal Server への接続、Workflow 開始の成否を確認。
    *   **Temporal Worker:** Worker のログで、Workflow/Activity の実行状況、エラーを確認。
    *   **Temporal Server/UI:** `tctl` や Temporal Web UI で Workflow の実行履歴、イベントログを確認。
    *   **Worker (TypeScript) → Python モジュール:** Python モジュール呼び出し部分 (`utils/pythonBridge`) のログや、Python モジュール自体のログを確認。
5.  **バグレポートの作成:**
    *   上記対応でも解決しない問題については、詳細なバグレポートを作成します。
    *   レポートには、テストケース ID、発生日時、再現手順、期待される結果、実際の И結果、エラーメッセージ、関連ログ（抜粋または全文）、スクリーンショット、テスト環境の情報を含めます。
6.  **エスカレーション:**
    *   担当チーム（Web UI, バックエンド, QA, インフラ）にバグレポートを共有し、対応を依頼します。
    *   必要に応じて、関係者会議を設定し、問題解決に向けた議論を行います。

## 5. 付録

### 5.1. Python テスト用モジュールとの連携詳細

#### 5.1.1. `dummy_module.py` の呼び出し方法

Temporal Worker (TypeScript) から Python の `dummy_module.py` を呼び出すには、いくつかの方法が考えられます。ここでは、`utils/pythonBridge.ts` を介して gRPC 通信を行う例を示します。

**前提:**

*   Python の `dummy_module.py` を実行する gRPC サーバーが別途起動されている。
*   gRPC クライアントライブラリ (`@grpc/grpc-js`, `@grpc/proto-loader` など) が Worker プロジェクトにインストールされている。
*   Protobuf 定義ファイル (`.proto`) が用意され、gRPC サービスとメッセージが定義されている。

**例:**

1.  **Protobuf 定義 (`proto/dummy_service.proto`)**
    ```protobuf
    syntax = "proto3";

    package dummy;

    service DummyService {
      rpc Process (ProcessRequest) returns (ProcessResponse);
    }

    message ProcessRequest {
      string method_name = 1; // e.g., "process"
      google.protobuf.Struct data = 2; // JSON-like structure for arbitrary data
    }

    message ProcessResponse {
      // Represents either a dictionary/object or null
      oneof result {
        google.protobuf.Struct data = 1;
        NullValue null_value = 2;
      }
    }

    // Import standard well-known types
    import "google/protobuf/struct.proto";
    import "google/protobuf/empty.proto"; // for NullValue if needed, or use a specific enum/field
    ```
    (注: `NullValue` の扱いは gRPC ライブラリや Protobuf のバージョンによって異なる場合があります。ここでは概念的な表現です。)

2.  **Python gRPC サーバー (`python_grpc_server.py`)**
    ```python
    # python_grpc_server.py
    import grpc
    from concurrent import futures
    import logging
    from google.protobuf import struct_pb2, json_format

    import proto.dummy_service_pb2 as pb2 # Generated gRPC code
    import proto.dummy_service_pb2_grpc as pb2_grpc # Generated gRPC code
    from dummy_module import DataProcessor # Your Python module

    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)

    class DummyServiceServicer(pb2_grpc.DummyServiceServicer):
        def __init__(self):
            self.data_processor = DataProcessor()

        def Process(self, request, context):
            logger.info(f"gRPC received: Method={request.method_name}, Data={request.data}")
            try:
                input_data = json_format.MessageToDict(request.data)

                if request.method_name == "process":
                    result = self.data_processor.process(input_data)
                    logger.debug(f"Python module returned: {result}")

                    response = pb2.ProcessResponse()
                    if result is None:
                        # Indicate None explicitly if the proto supports it
                        # response.null_value = pb2.NULL_VALUE # Example if NullValue enum exists
                        # Or use a dedicated field, or rely on absence of `data` field
                        # For simplicity, let's assume absence of `data` implies None for the caller
                        logger.debug("Returning None indication.")
                        pass # No data field will be set
                    else:
                        response.data.update(result)
                    return response
                else:
                    context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Unknown method name")
            except Exception as e:
                logger.error(f"Error processing request: {e}", exc_info=True)
                context.abort(grpc.StatusCode.INTERNAL, str(e))

    def serve():
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        pb2_grpc.add_DummyServiceServicer_to_server(DummyServiceServicer(), server)
        port = '50051'
        server.add_insecure_port(f'[::]:{port}')
        server.start()
        logger.info(f"gRPC server started on port {port}")
        server.wait_for_termination()

    if __name__ == '__main__':
        serve()
    ```

3.  **Temporal Worker (`src/utils/pythonBridge.ts`)**
    ```typescript
    // src/utils/pythonBridge.ts
    import * as grpc from '@grpc/grpc-js';
    import * as protoLoader from '@grpc/proto-loader';
    import { loadPackageDefinition, GrpcObject, ServiceClientConstructor } from '@grpc/grpc-js';
    import type { Struct } from 'google-protobuf/google/protobuf/struct_pb'; // Type for Struct
    import { ProcessRequest } from '../generated/proto/dummy_service_pb'; // Generated client code

    // Load the proto definition
    const PROTO_PATH = './proto/dummy_service.proto'; // Adjust path as needed
    const packageDefinition = protoLoader.loadSync(PROTO_PATH, {
      keepCase: true,
      longsAsStrings: true,
      enumsAsInts: true,
      defaults: true,
      oneofs: true,
    });
    const proto = loadPackageDefinition(packageDefinition) as GrpcObject;
    const dummyPackage = proto.dummy as GrpcObject;
    const DummyService = dummyPackage.DummyService as ServiceClientConstructor;

    // Initialize gRPC client
    const client = new DummyService(
      'localhost:50051', // gRPC server address
      grpc.credentials.createInsecure()
    );

    // Helper to convert JS object to Protobuf Struct
    function convertToStruct(obj: any): Struct {
      // Use google.protobuf.struct_pb's own utilities or a helper library
      // Example using google-protobuf library directly (requires installation)
      const { Struct } = require('google-protobuf/google/protobuf/struct_pb');
      return Struct.fromObject(obj);
    }

    // Helper to convert Protobuf response Struct/Null back to JS object
    function convertFromResponse(response: any): any {
       if (response.data) {
           return response.data.toObject(); // Assuming toObject() converts Struct
       } else if (response.nullValue !== undefined) { // Check for null indicator
           return null;
       }
       // Handle cases where no specific field is set or default behavior
       return null; // Default to null if no data or explicit null value
    }


    export async function callPythonDummyProcessor(methodName: string, data: any): Promise<any> {
        return new Promise((resolve, reject) => {
            const request = new ProcessRequest();
            request.setMethodName(methodName);
            request.setData(convertToStruct(data));

            client.Process(request, (err, response) => {
                if (err) {
                    console.error(`gRPC call failed: ${err.message}`);
                    reject(err);
                } else if (response) {
                    const result = convertFromResponse(response);
                    resolve(result);
                } else {
                    // Should not happen if response object is guaranteed
                    reject(new Error("gRPC call returned empty response"));
                }
            });
        });
    }
    ```

#### 5.1.2. シナリオ D の実行フロー再確認

1.  Web UI → Hono API (`POST /api/register`)
2.  Hono → Temporal Workflow (`DataProcessingWorkflow`) 開始
3.  Workflow → Activity (`processData`) 実行
4.  Activity → `callPythonDummyProcessor('process', data)` 呼び出し
5.  `callPythonDummyProcessor` → Python gRPC サーバーへリクエスト送信
6.  Python gRPC サーバー → `dummy_module.DataProcessor.process(data)` 実行
7.  `DataProcessor.process` は `None` を返す
8.  Python gRPC サーバー → gRPC レスポンスで `None` を通知 (例: `data` フィールドなし)
9.  `callPythonDummyProcessor` → `None` を受け取る
10. Activity (`processData`) → `None` を検知し、`new Error(...)` をスロー
11. Temporal Worker → Activity の失敗を検知
12. Temporal Server → Workflow を `Failed` 状態にする
13. Hono → Workflow の失敗ステータスを Web UI へ返却
14. Web UI → エラーメッセージを表示

### 5.2. パフォーマンス測定

本 SOP は主に機能的な結合動作の確認を目的としていますが、必要に応じてパフォーマンス測定も実施します。

*   **測定項目:**
    *   **応答時間:** Web UI 操作から結果表示までの時間。
    *   **スループット:** 単位時間あたりの処理能力。
*   **測定方法:**
    *   Web ブラウザ開発者ツール（ネットワークタブ）。
    *   APM (Application Performance Monitoring) ツール。
    *   負荷テストツール（k6, JMeter など）。
*   **記録:** パフォーマンス測定結果は、別途定義されたパフォーマンス測定 SOP に従い記録・評価します。

### 5.3. よくある質問と回答 (FAQ)

*   **Q1: Temporal Server が起動しません。**
    *   **A1:** Docker が正しくインストールされ、実行されているか確認してください (`docker ps`)。`docker-compose up -d` のログを確認し、エラー原因を調査してください。
*   **Q2: Hono アプリケーションが起動しません。**
    *   **A2:** `npm install` / `yarn install` の完了、Node.js バージョン、起動コマンドのターミナルログを確認してください。
*   **Q3: Web UI が Hono API に接続できません (CORS エラーなど)。**
    *   **A3:** Hono 側の CORS 設定、Hono サーバーの起動状態を確認してください。
*   **Q4: Temporal Workflow が開始されません。**
    *   **A4:** Hono のログで Temporal Server への接続を確認してください。Worker が正しい Task Queue 名で登録されているか確認してください。
*   **Q5: Activity が実行されません。**
    *   **A5:** Worker の起動、Task Queue 名の一致、Workflow での Activity 呼び出しコードを確認してください。Temporal UI/`tctl` で Workflow の実行履歴を確認してください。
*   **Q6: TypeScript Worker から Python モジュールを呼び出せません。**
    *   **A6:** Python gRPC サーバーが起動しているか、Protobuf 定義とコードが一致しているか、ネットワーク接続（ポート `50051`）を確認してください。Worker の `pythonBridge.ts` の設定（アドレス、パス）を見直してください。

### 5.4. 関係者リスト

| 役割                   | 氏名     | 所属部署     | メールアドレス         |
| :--------------------- | :------- | :----------- | :--------------------- |
| QA リード              | 佐藤 一郎 | QA 部        | ichiro.sato@example.com |
| Web UI 開発担当        | 鈴木 花子 | フロントエンド部 | hanako.suzuki@example.com |
| Hono 開発担当          | 高橋 次郎 | バックエンド部   | jiro.takahashi@example.com |
| Temporal 開発担当      | 田中 三郎 | バックエンド部   | saburo.tanaka@example.com |
| Python モジュール担当  | 中村 四郎 | バックエンド部   | shiro.nakamura@example.com |
| プロジェクトマネージャー | 伊藤 五郎 | プロジェクト管理室 | go.ito@example.com   |

---