# デモ動画撮影用検証プロセスSOP

## 1. はじめに

### 1.1. SOP の目的
本SOPは、デモ動画撮影に必要な検証プロセス、特にワークフローのロジック、HITL介入のトリガー条件、およびエラーハンドリングの検証を効率的かつ再現性高く実行するための手順を提供します。

### 1.2. 対象読者
デモ動画撮影関係者（デモンストレーションの確認者、オブザーバーとしてリハーサルに参加し、シナリオ理解およびリハーサル結果の確認を行う者）

## 2. システム概要

### 2.1. システム構成
本システムは、Hono環境と連携することを想定していますが、リハーサルではPythonスクリプトとして直接実行されます。Hono環境からはHTTPリクエストを介して本システムが呼び出される構成も想定しています。`DataProcessor`はPythonコードとして直接実行することも可能です。

システム連携イメージ図において、`DataProcessor`はHono環境内での実行を想定していますが、Honoアプリケーションから独立したPythonスクリプトとして呼び出されることも可能です。

### 2.2. ワークフロー
ワークフロー図における「HITL シナリオ（想定）」のパスは、現状のダミー実装では実行されずスキップされますが、将来的な拡張パスとして考慮されることを示しています。

Temporalは、ワークフローの状態遷移を管理し、`validate`メソッドの結果に応じて処理を分岐させます。本SOPで扱うリハーサルでは、`validate`メソッドがFalseを返した場合にHITL介入の**代替/前段階**として処理がスキップされる挙動を検証します。

## 3. リハーサル準備

### 3.1. 環境構築
1.  **Python環境の準備:** Python 3.x がインストールされていることを確認します。
2.  **必要なライブラリのインストール:** 必要なライブラリ（`temporalio`など）をインストールします。
3.  **Hono環境の準備:** Hono環境の準備は、本SOPのリハーサル実施範囲外とします。ただし、デモ動画撮影全体の構成要素としてHonoアプリケーションが必要な場合は、別途その準備手順（例: `docker-compose up`によるコンテナ起動など）に従って準備してください。
4.  **Temporal 環境の準備:** Temporal 環境への接続情報を設定します。Temporal Cloudを利用する場合はAPIキーやNamespaceを環境変数（例: `TEMPORAL_CLOUD_API_KEY`, `TEMPORAL_CLOUD_NAMESPACE`）で、Self-hostedの場合はサービスエンドポイント（例: `TEMPORAL_GRPC_ENDPOINT=localhost:7233`）を環境変数またはコード内で設定します。

### 3.2. コードの準備

#### 3.2.1. ダミーモジュール (`DataProcessor`) の理解
*   **`process` メソッド:**
    *   **現状:** このメソッドは、実際にはどのような処理も行わず、常に `None` を返します。
    *   **リハーサルでの役割:** これにより、`run_pipeline` 関数内の `if result is None:` の条件分岐が常に真となり、警告ログが出力される挙動を確認します。これは、**Temporal がワークフローの状態遷移やエラーハンドリング（この場合はスキップ処理）をどのように管理するかを検証する**ことを目的としています。
*   **`validate` メソッド:**
    *   **現状:** このメソッドは、実際にはどのような処理も行わず、常に `True` を返します。
    *   **リハーサルでの役割:** 本リハーサルでは直接的な動作確認は行いませんが、その存在意義を理解することが重要です。このメソッドは、4.3節で説明する「HITL シナリオのシミュレーション」において、将来的にHITL介入をトリガーする条件を評価する役割を担います。

#### 3.2.2. コードの配置とビルド
*   **コードの配置:** リハーサルに使用するPythonコード（例: `workflow.py`, `dummy_processor.py`）を適切なディレクトリに配置します。
*   **ビルド:** Pythonコード自体はビルド不要です。必要なPythonライブラリ（例: `temporalio`）は、`pip install -r requirements.txt` などでインストールします。Honoアプリケーションのビルドが必要な場合は、別途その手順に従ってください。

## 4. リハーサル実施手順

### 4.1. リハーサル開始
1.  **ロガー設定:** リハーサルスクリプトの冒頭、またはメイン関数の開始時に、以下のロガー設定を追加します。
    ```python
    import logging
    logging.basicConfig(level=logging.DEBUG)
    ```
2.  **Temporal Workerの起動:** Temporal Workerを起動します。
    ```bash
    temporal worker start --task-queue my-task-queue --workflow-type MyWorkflowClass
    ```

### 4.2. パイプライン実行 (`run_pipeline`)

#### 4.2.1. `run_pipeline` 関数の実行
*   `run_pipeline` 関数を実行します。Temporal ワークフローとして実行する場合、以下のようなコマンドを使用します。
    ```bash
    temporal workflow start --task-queue my-task-queue --workflow-id my-workflow --workflow-type MyWorkflowClass
    ```
    （`my-task-queue`, `my-workflow`, `MyWorkflowClass` は実際の環境に合わせて適宜変更してください。）

#### 4.2.2. `DataProcessor.process` の動作
*   **確認事項:** デバッグログが出力されることを確認します。このログは、ローカル実行時の標準出力、またはTemporal Workerのログとして記録されます。

#### 4.2.3. ログの確認
*   以下のようなログが出力されていることを確認します。
    ```
    DEBUG:__main__:Starting pipeline...
    DEBUG:dummy_processor:DataProcessor.process called.
    WARNING:__main__:DataProcessor returned None, skipping further processing.
    DEBUG:__main__:Pipeline finished.
    ```
    上記のログ出力例は、`run_pipeline` 関数が直接実行され、`dummy_processor` モジュール内でログが出力された場合のものです。
*   Temporal ワークフローの実行ログは、Temporal Web UI (通常 `http://localhost:8080` またはTemporal Cloudのダッシュボード) で確認できます。ワークフローIDを検索して、詳細なイベント履歴とログを確認してください。

### 4.3. HITL シナリオのシミュレーション
現状、ダミーモジュール `DataProcessor` の `validate` メソッドは常に `True` を返すように実装されているため、HITL介入は発生しません。将来的にHITL介入シナリオをシミュレーションする場合は、`validate` メソッドを `False` を返すように修正するか、または`run_pipeline`ワークフロー内で`validate`の結果を強制的に`False`にするロジックを追加して、HITL介入のトリガーとそれに続く処理の検証を行います。

## 5. 結果評価

### 5.1. 評価項目
*   **ログ出力の確認:** `DataProcessor` の `process` メソッドが `None` を返した際に、期待される警告ログ（例: `WARNING:__main__:DataProcessor returned None, skipping further processing.`）が出力されていることを確認します。
*   **ワークフローの状態遷移:** Temporal Web UIで、`run_pipeline` ワークフローが期待通りに実行され、`DataProcessor.process` の結果が `None` であったために後続の処理がスキップされ、最終的にワークフローが正常終了していることを確認します。

### 5.2. 評価基準
以下の点が期待される動作と一致していることを確認します:
*   `DataProcessor.process` の実行後、警告ログが正しく出力されていること。
*   Temporal Web UI上で、ワークフローがスキップパスを辿り、エラーなく正常に完了していること。
*   デモ動画撮影のシナリオにおける、この検証ポイントの目的が達成されていること。