# TemporalとHonoを用いたHITL統合検証リハーサルSOP

## 1. はじめに

### 1.1. 目的

本SOPは、デモ動画本番撮影に先立つリハーサルとして、TemporalとHonoを組み合わせたHuman-in-the-Loop (HITL) 統合検証パイプラインの動作確認手順を定めます。特に、**意図的に不完全な実装（`DataProcessor.process` メソッドが常に `None` を返却し、`DataProcessor.validate` メソッドが常に `False` を返却する）が、HITLパイプライン全体に与える影響を、デモシナリオを通して具体的に確認すること**を目的とします。

### 1.2. 適用範囲

本SOPは、デモ動画撮影に先立つリハーサルを目的とし、特定の不備を含む実装がHITLパイプラインに与える影響を検証します。開発・テスト環境における網羅的な単体テストや結合テスト、または本番運用に関する手順は、本SOPの対象外です。

### 1.3. 重要性

このリハーサルは、以下の点において重要です。

*   **HITL要素の検証:** 人間による判断や承認が必要なステップが、ワークフロー内で適切にトリガーされ、その結果がシステムに反映されるか（例: TemporalのSignalやUpsertWorkflowExecutionを利用した承認プロセス、データ修正、エラーハンドリングなど）を確認します。
*   **不完全な実装の影響確認:** ソースコードは意図的に不完全な部分を含んでおり、その予期せぬ挙動を意図的に確認します。**このリハーサルでは、`DataProcessor.process` メソッドが常に `None` を返却し、`DataProcessor.validate` メソッドが常に `False` を返却する、という意図的な不備がある実装を対象とします。これにより、これらの不備が HITL パイプライン全体に与える影響を、デモシナリオを通して具体的に確認することを目的とします。**
*   **デモの再現性確保:** デモ動画撮影時の予期せぬトラブルを未然に防ぎ、安定したデモンストレーションを可能にします。

## 2. 用語定義

*   **Temporal:** 分散型ワークフローオーケストレーションエンジン。信頼性の高いワークフロー実行を保証します。
*   **Hono:** 軽量で高速なWebフレームワーク。本SOPでは、HITLのためのWeb UIおよびAPIを提供します。
*   **HITL (Human-in-the-Loop):** 人間の判断や介入をシステムプロセスに組み込むこと。承認プロセス、データ入力、エラー対応など、人間が判断を下し、その結果をシステムにフィードバックするプロセスを指します。
*   **アクティビティ:** Temporalワークフロー内で実行されるビジネスロジックの単位。HonoのAPIエンドポイントやPythonの`DataProcessor`クラスの`process`メソッドなどが、具体的なアクティビティとして実装され、Temporalによってオーケストレーションされます。
*   **ワークフロー:** Temporalにおける一連のアクティビティの実行ロジック。本SOPでは、データ処理からHITLステップを含む一連のプロセスを指します。

## 3. リハーサル準備

### 3.1. 必要な機材・ソフトウェアの確認

以下の機材・ソフトウェアが準備され、正しく動作することを確認してください。

*   **PC:** macOS, Linux, または Windows (WSL2推奨)
*   **Docker / Docker Compose:** バージョン20.10以上
    *   `docker --version`
    *   `docker compose version`
*   **Git:** バージョン2.25以上
    *   `git --version`
*   **Python:** バージョン3.9以上
    *   `python3 --version`
    *   `pip3 --version`
*   **Node.js / npm または Bun:**
    *   `node --version` (または `bun --version`)
    *   `npm --version` (または `bun --version`)
*   **Temporal Cloud (またはローカルTemporal Cluster):**
    *   Temporal Cloudを使用する場合: Namespace, Host, API Keyが設定済みであること。環境変数での管理を推奨します（例: `TEMPORAL_NAMESPACE`, `TEMPORAL_HOST_URL`, `TEMPORAL_CLIENT_CERT`, `TEMPORAL_CLIENT_KEY`）。
*   **Honoアプリケーション:**
    *   プロジェクトディレクトリで `npm install` または `bun install` を実行し、依存関係がインストールされていることを確認します。
    *   Honoサーバーが起動できるかどうかの確認手順（例: `bun run dev` または `npm start` を実行し、ブラウザで `http://localhost:3000` にアクセスして正常に応答することを確認します）。

### 3.2. 環境構築

1.  **リポジトリのクローン:**
    ```bash
    git clone https://github.com/your-org/temporal-hono-hitl-demo.git # 例: リポジトリURLを指定
    cd temporal-hono-hitl-demo
    ls -F # 確認例: クローンされたファイルやディレクトリが表示されることを確認
    ```
2.  **Temporal Cloudの設定 (Cloudを使用する場合):**
    環境変数にTemporal Cloudの接続情報を設定します。
    ```bash
    export TEMPORAL_NAMESPACE="your-namespace" # 例: your-namespace
    export TEMPORAL_HOST_URL="your-host-url.tmprl.cloud:7233" # 例: your-host-url.tmprl.cloud:7233
    export TEMPORAL_CLIENT_CERT="/path/to/your/client.pem" # 例: /Users/user/certs/client.pem
    export TEMPORAL_CLIENT_KEY="/path/to/your/client.key" # 例: /Users/user/certs/client.key
    echo "Temporal Namespace: $TEMPORAL_NAMESPACE" # 確認例: 設定した値が表示されることを確認
    temporal operator cluster health # 確認例: Temporal CLIが正しく設定され、クラスタに接続できることを確認
    ```
    または、Temporal CLIを設定します。
    ```bash
    temporal config set-context my-cloud-context --namespace your-namespace --address your-host-url.tmprl.cloud:7233 --tls-cert-path /path/to/your/client.pem --tls-key-path /path/to/your/client.key
    temporal config use-context my-cloud-context
    temporal config get-context # 確認例: 設定したコンテキストが表示されることを確認
    ```
3.  **ローカル Temporal Cluster の構築 (ローカル環境を使用する場合):**
    リポジトリに含まれる `docker-compose.yml` を使用してTemporal Clusterを起動します。
    ```bash
    docker compose up -d
    docker ps # 確認例: temporal-frontend, temporal-worker, temporal-history, temporal-matching, postgres, adminerなどのコンテナが起動していることを確認
    temporal system health # 確認例: Temporal Clusterが正常であることを確認
    ```
4.  **Hono 環境構築:**
    Honoアプリケーションのディレクトリに移動し、依存関係をインストールします。
    ```bash
    cd hono-app # 例: hono-appディレクトリに移動
    bun install # または npm install
    # 確認例: node_modulesディレクトリが作成され、依存関係がインストールされたことを確認
    bun run dev # または npm start
    # 確認例: コンソールに "Hono server listening on http://localhost:3000" のようなメッセージが表示されることを確認。
    # ブラウザで http://localhost:3000 にアクセスし、Hono UIが正常に表示されるか確認。
    ```
5.  **Python 環境構築:**
    Pythonアプリケーションのディレクトリに移動し、依存関係をインストールします。
    ```bash
    cd python-worker # 例: python-workerディレクトリに移動
    python3 -m venv .venv # 仮想環境の作成 (推奨)
    source .venv/bin/activate # 仮想環境の有効化
    pip install -r requirements.txt
    # 確認例: pip list コマンドで必要なライブラリ (temporalio, pydanticなど) がインストールされていることを確認
    # 仮想環境を終了するには `deactivate` コマンドを使用します。
    ```

## 4. リハーサル手順

本セクションでは、HITL統合検証パイプラインのリハーサル手順を説明します。

1.  **Temporal Workerの起動:**
    Pythonアプリケーションディレクトリで、Temporal Workerを起動します。
    ```bash
    cd python-worker # 例: python-workerディレクトリに移動
    source .venv/bin/activate # 仮想環境を有効化 (もし作成した場合)
    python3 worker.py # 例: worker.pyがエントリーポイントの場合
    # 確認例: コンソールに "Worker started" のようなメッセージが表示され、エラーなく動作していることを確認
    ```

2.  **Honoサーバーの起動:**
    Honoアプリケーションディレクトリで、Honoサーバーが起動していることを確認します。
    ```bash
    cd hono-app # 例: hono-appディレクトリに移動
    bun run dev # または npm start
    # 確認例: ブラウザで http://localhost:3000 にアクセスし、UIが表示されることを確認
    ```

3.  **ワークフローの開始:**
    別のターミナルで、Temporalクライアントを使用してワークフローを開始します。
    ```bash
    cd python-client # 例: ワークフローをトリガーするクライアントスクリプトがあるディレクトリ
    source .venv/bin/activate # 仮想環境を有効化 (もし作成した場合)
    python3 client.py start_workflow --data "sample_data_input" # 例: クライアントスクリプトと引数
    # 確認例: ワークフローID (Workflow ID) が出力されることを確認
    ```

4.  **Temporal UI/CLIでのワークフロー監視:**
    Temporal UI (通常 `http://localhost:8080` または Temporal Cloud UI) にアクセスし、開始したワークフローのステータスを監視します。
    *   ワークフローが `DataProcessor.process` アクティビティで失敗し、`None` を返却する、または `DataProcessor.validate` アクティビティで失敗し、`False` を返却する挙動を確認します。
    *   ワークフローがHITLステップ（例: `WaitForHumanApproval` アクティビティ）で一時停止していることを確認します。

5.  **Hono UIからのHITL操作:**
    Hono UI (`http://localhost:3000`) にアクセスし、ワークフローIDに対応するHITLタスクを探します。
    *   意図的に不完全なデータが表示されていることを確認します。
    *   データ修正や承認の操作を行います。例えば、「承認」ボタンをクリックするか、データを修正して「送信」ボタンをクリックします。
    *   **注意:** 本SOPの目的上、`DataProcessor` の不備により、Hono UIから承認/修正を行っても、ワークフローは最終的に失敗する可能性があります。この挙動を観察することが重要です。

6.  **ワークフロー結果の確認:**
    Temporal UI/CLIに戻り、ワークフローの最終的なステータスを確認します。
    *   `DataProcessor` の意図的な不備により、ワークフローが最終的に失敗する（例: `WorkflowFailed` ステータス）ことを確認します。
    *   イベント履歴を確認し、Hono UIからのSignalがTemporalによって受信され、その後のワークフローロジックがどのように進行したか（そして失敗したか）を分析します。

## 5. トラブルシューティング

リハーサル中に発生しうる一般的な問題と、その解決手順を以下に示します。

### 5.1. Temporal Cluster/Cloud 接続エラー

*   **エラーコード/メッセージ例:**
    *   `gRPC connection failed`
    *   `Unable to connect to Temporal service`
    *   `TEMPORAL_HOST_URL` or `TEMPORAL_NAMESPACE` not found
    *   `x509: certificate signed by unknown authority` (TLS/証明書関連)
*   **解決手順:**
    1.  **環境変数の確認:** `TEMPORAL_HOST_URL`, `TEMPORAL_NAMESPACE`, `TEMPORAL_CLIENT_CERT`, `TEMPORAL_CLIENT_KEY` の各環境変数が正しく設定されているか、スペルミスがないかを確認してください。`echo $TEMPORAL_HOST_URL` などで確認できます。
    2.  **Temporal Cloudの場合:**
        *   APIキーの有効期限が切れていないか確認してください。
        *   ネットワーク接続が安定しているか確認してください。
        *   指定されたホストURLが正しいか確認してください。
    3.  **ローカルTemporal Clusterの場合:**
        *   `docker compose ps` コマンドで、Temporal関連の全てのコンテナ（`temporal-frontend`, `temporal-worker`, `temporal-history`, `temporal-matching`など）が `Up` ステータスで起動していることを確認してください。
        *   `docker compose logs` コマンドで、各コンテナのログを確認し、起動時のエラーがないか確認してください。
        *   `temporal system health` コマンドを実行し、クラスタの状態が正常であることを確認してください。
    4.  **TLS/証明書エラーの場合:**
        *   `TEMPORAL_CLIENT_CERT` と `TEMPORAL_CLIENT_KEY` で指定された証明書と秘密鍵のパスが正しいか、ファイルが存在するか確認してください。
        *   証明書が有効であるか、またTemporal Cloud側で正しく登録されているか確認してください。

### 5.2. Hono サーバー起動失敗

*   **エラーコード/メッセージ例:**
    *   `Address already in use` (ポート3000が使用中)
    *   `Error: Cannot find module '...'` (依存関係の不足)
    *   `SyntaxError: Unexpected token '...'` (コードの構文エラー)
*   **解決手順:**
    1.  **依存関係の確認:** Honoアプリケーションディレクトリで `bun install` または `npm install` が正常に完了しているか確認してください。`node_modules` ディレクトリが存在し、必要なパッケージがインストールされていることを確認してください。
    2.  **ポートの競合:** ポート3000が他のプロセスによって使用されていないか確認してください。
        *   macOS/Linux: `lsof -i :3000`
        *   Windows: `netstat -ano | findstr :3000`
        他のプロセスが使用している場合は、そのプロセスを終了するか、Honoアプリケーションのポート設定を変更してください。
    3.  **ログの確認:** `bun run dev` または `npm start` を実行したターミナルの出力ログを確認し、具体的なエラーメッセージを特定してください。

### 5.3. Python Worker 起動失敗 / ワークフローが開始されない

*   **エラーコード/メッセージ例:**
    *   `ModuleNotFoundError: No module named 'temporalio'` (Temporal SDKがインストールされていない)
    *   `temporalio.exceptions.WorkflowFailureError` (ワークフロー実行中のエラー)
    *   `Activity execution failed` (アクティビティ実行中のエラー)
*   **解決手順:**
    1.  **依存関係の確認:** Pythonアプリケーションディレクトリで `pip install -r requirements.txt` が正常に完了しているか確認してください。`pip list` コマンドで `temporalio` やその他の必要なライブラリがインストールされていることを確認してください。
    2.  **仮想環境の有効化:** 仮想環境を使用している場合、`source .venv/bin/activate` で正しく有効化されているか確認してください。
    3.  **Workerログの確認:** Python Workerを起動しているターミナルでエラーログを確認し、具体的なエラーメッセージを特定してください。
    4.  **Temporal UI/CLIでの確認:** Temporal UIまたは `temporal workflow list` コマンドで、ワークフローがそもそも開始されているか、またはどのアクティビティで失敗しているかを確認してください。
    5.  **環境変数の確認:** Python WorkerプロセスにTemporal Cloudの接続情報（`TEMPORAL_NAMESPACE`, `TEMPORAL_HOST_URL`など）が正しく渡されているか確認してください。

### 5.4. HITLステップでのワークフロー停止 / `DataProcessor` 関連のエラー

*   **エラーコード/メッセージ例:**
    *   ワークフローが特定のActivity（例: `WaitForHumanApproval`, `ProcessDataActivity`, `ValidateDataActivity`）で長時間停止している。
    *   Temporal UIのイベント履歴に `DataProcessor.process` が `None` を返却した、または `DataProcessor.validate` が `False` を返却した旨のメッセージが表示される。
    *   `Workflow failed: Data validation failed` のようなメッセージが表示される。
*   **解決手順:**
    1.  **これは本SOPの目的である「意図的な不備」による挙動です。** ワークフローが `DataProcessor.process` または `DataProcessor.validate` アクティビティで失敗した場合、またはHITLステップで一時停止した後に期待通りに進まない場合、それはこのリハーサルの目的である「不完全な実装の影響確認」の範疇です。
    2.  **Hono UIからのSignal送信確認:** Hono UIでデータ修正や承認のSignalが正しく送信されているか確認してください。送信後、Temporal UIでワークフローのイベント履歴を確認し、Signalが受信されているか、その後の処理がどのように進んでいるかを確認してください。
    3.  **想定外の挙動の場合:** もし、この挙動が想定外であり、本来はワークフローが成功すべきである場合は、`DataProcessor` の実装を確認し、`process` メソッドが適切な値を返し、`validate` メソッドが正しい条件で `True` を返すように修正してください。