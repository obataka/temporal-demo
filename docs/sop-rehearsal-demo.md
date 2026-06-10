# デモ動画本番撮影リハーサル用 SOP（Temporal × Hono HITL 統合検証）

## 1. はじめに

### 1.1. 本 SOP の目的

本 SOP は、Temporal と Hono を連携させた Human-in-the-Loop (HITL) 統合検証のデモ動画本番撮影に向けた、リハーサル手順を定めるものです。この SOP に従うことで、以下の点を効率的に実施・確認することを目的とします。

*   **コンポーネント連携の確認:** Temporal Worker と Hono Adapter が期待通りに連携しているか。
*   **HITL シナリオのシミュレーション:** ダミーモジュールを用いた意図的なエラー発生による HITL 介入要求フローの検証。
*   **潜在的問題の早期発見:** 本番撮影前に、デモシナリオにおける技術的な問題点やロジックの不備を特定し、修正する。
*   **デモ動画シナリオとの整合性確認:** リハーサルを通じて、デモ動画で示すべきストーリーラインと、実際のシステム動作との整合性を検証する。
*   **デモ動画撮影の準備:** リハーサル結果を基に、デモ動画撮影時の手順、スクリプト、および期待される結果を最終確認し、スムーズな撮影を可能にする。

### 1.2. 対象読者

本 SOP は、以下の関係者を対象としています。

*   Temporal Workflow および Activity の開発者・運用担当者
*   Hono Adapter の開発者・運用担当者
*   HITL シナリオの実装・検証担当者
*   デモ動画撮影のシナリオプランナー・ディレクター
*   品質保証 (QA) 担当者、テスター
*   プロジェクトマネージャーおよび関係者

### 1.3. 用語集

*   **Temporal:** 分散システムにおけるワークフローのオーケストレーションを容易にするオープンソースのプラットフォームです。耐久性、スケーラビリティ、および信頼性の高いワークフロー実行を提供します。
*   **Hono:** 産業用IoT向けのオープンソースのIoTサービスプラットフォームです。デバイス管理、データ処理、およびアプリケーション連携機能を提供します。本 SOP では、Hono Adapter を介して Temporal と連携します。
*   **HITL (Human-in-the-Loop):** システムの意思決定プロセスに人間が関与する仕組みです。本 SOP では、自動処理が失敗したり、確認が必要な場合に、人間が介入するシナリオをシミュレーションします。
*   **SOP (Standard Operating Procedure):** 標準作業手順書。特定のタスクを実行するための、段階的で明確な指示書です。
*   **Workflow:** Temporal における一連の処理の定義および実行単位です。本 SOP では、データ処理パイプライン全体をオーケストレーションし、ダミーモジュールからの失敗を検知してHITL介入をトリガーする役割も管理します。
*   **Activity:** Temporal Workflow 内で実行される、個々のタスクまたは操作です。本 SOP では、データ処理や検証、通知などの具体的な処理を Activity として実装します。
*   **Worker:** Temporal Workflow および Activity を実行するプロセスです。Temporal Server と通信し、タスクをポーリングして実行します。
*   **Client:** Temporal Workflow の実行を開始したり、その状態をクエリしたりするためのアプリケーションです。
*   **Hono Adapter:** Temporal WorkflowからHITL介入要求を受信し、Honoプラットフォームへ連携するためのプログラムです。本SOPでは、HTTP/RESTを介してTemporalとHonoを連携させる役割を担います。
*   **Dummy Module:** 本SOPのリハーサルにおいて、意図的にデータ処理の失敗や検証の失敗をシミュレートするために使用されるモジュールです。これにより、HITL介入シナリオを再現します。

## 2. 環境構築

本リハーサルを実施するための環境を構築します。

### 2.1. 前提条件

*   Python 3.8+
*   Docker (Temporal Server 起動用)
*   Git

### 2.2. 必要なツールのインストール

Temporal CLI をインストールします。

```bash
go install github.com/temporalio/temporal/cmd/temporal@latest
```

Python の依存関係をインストールします。

```bash
pip install temporalio requests
```

### 2.3. コードの準備

リハーサル用のコードリポジトリをクローンし、必要なファイルを配置します。

```bash
git clone <your-repository-url>
cd <your-repository-name>
# 以下のファイルがカレントディレクトリまたは指定されたパスに存在することを確認
# - workflow.py
# - worker.py
# - client.py
# - adapter.py
# - dummy_module.py
```

### 2.4. Temporal Server の起動

Docker を使用して Temporal Server を開発モードで起動します。

```bash
temporal server start-dev
```
Temporal UI は `http://localhost:8080` でアクセス可能です。

## 3. リハーサル手順

本リハーサルでは、ダミーモジュールによる意図的な失敗をトリガーとして、Temporal Workflow が HITL 介入を要求し、Hono Adapter がそれを受信する一連のフローを検証します。

### 3.1. ダミーモジュールの役割とHITLシナリオ

本リハーサルでは、`dummy_module.py` が以下の挙動をします。

*   `DataProcessor.process` メソッドは、常に `None` を返します。これは、データ処理が何らかの理由で失敗し、手動での確認が必要な状況をシミュレートします。
*   `DataValidator.validate` メソッドは、常に `False` を返します。これは、処理されたデータの検証が失敗し、人間の承認や修正が必要な状況をシミュレートします。

この挙動により、Temporal Workflow はデータ処理の失敗または検証の失敗を検知し、HITL 介入を要求するシナリオをトリガーします。

### 3.2. 各コンポーネントの起動

以下の順序で各コンポーネントを起動します。各コンポーネントは異なるターミナルで起動してください。

1.  **Temporal Worker の起動**
    ```bash
    python worker.py
    ```
    *期待される出力例:*
    ```
    Running worker on task queue 'my-task-queue'...
    ```

2.  **Hono Adapter の起動**
    Hono Adapter は、Temporal Worker からの HITL 介入要求を HTTP/REST で受信するためのサーバーとして機能します。
    ```bash
    python adapter.py
    ```
    *期待される出力例:*
    ```
    * Running on http://127.0.0.1:8000 (Press CTRL+C to quit)
    ```

3.  **Temporal Workflow の実行 (Client)**
    Workflow を開始し、HITL シナリオをトリガーします。
    ```bash
    python client.py
    ```
    *期待される出力例:*
    ```
    Started workflow. Workflow ID: my-workflow-id-xxxx, Run ID: xxxx
    ```

### 3.3. HITL シミュレーションの詳細と確認

各コンポーネントのログ出力と Temporal Dashboard を確認しながら、HITL シナリオのフローを追跡します。

1.  **Temporal Dashboard での Workflow 状況確認**
    Temporal Dashboard (http://localhost:8080) を開き、Workflow の実行状況をリアルタイムで監視します。
    *   `my-workflow-id-xxxx` の Workflow が開始され、実行中であることを確認します。
    *   Workflow のイベント履歴を確認し、`DataProcessingActivity` や `DataValidationActivity` が実行され、その結果が Workflow に返されていることを確認します。
    *   ダミーモジュールの設定により、これらの Activity は失敗を示す結果を返すため、Workflow が `RequestHitlInterventionActivity` をスケジュールすることを確認します。

2.  **Workflow での検証失敗の検知と HITL 介入要求**
    Workflow は `dummy_module` の結果を受け取り、失敗を検知します。その後、HITL 介入を要求する Activity を呼び出します。

    *(ファイル: workflow.py の一部)*
    ```python
    # ... (前略) ...
    from temporalio.workflow import workflow_method, ActivityMethod
    from my_activities import process_data, validate_data, request_hitl_intervention
    from datetime import timedelta

    @workflow_method
    async def MyWorkflow(self, input_data: str) -> str:
        # 1. データ処理 Activity の実行
        processed_result = await self.execute_activity(
            process_data, input_data, start_to_close_timeout=timedelta(seconds=10)
        )

        if processed_result is None:
            # データ処理が失敗した場合、HITL 介入を要求
            await self.execute_activity(
                request_hitl_intervention,
                {"workflow_id": self.info.workflow_id, "reason": "Data processing failed"},
                start_to_close_timeout=timedelta(seconds=10)
            )
            return "HITL Intervention Requested: Data Processing Failed"

        # 2. データ検証 Activity の実行
        validation_result = await self.execute_activity(
            validate_data, processed_result, start_to_close_timeout=timedelta(seconds=10)
        )

        if not validation_result:
            # データ検証が失敗した場合、HITL 介入を要求
            await self.execute_activity(
                request_hitl_intervention,
                {"workflow_id": self.info.workflow_id, "reason": "Data validation failed"},
                start_to_close_timeout=timedelta(seconds=10)
            )
            return "HITL Intervention Requested: Data Validation Failed"

        return "Workflow Completed Successfully"
    ```
    *Worker のターミナルで、`RequestHitlInterventionActivity` が実行されたことを示すログを確認します。*

3.  **Adapter での HITL 介入要求の受信と Hono 連携シミュレーション**
    `RequestHitlInterventionActivity` は、HTTP/REST (POST メソッド) を使用して Hono Adapter の特定のエンドポイントに HITL 介入要求を送信します。

    *(ファイル: my_activities.py の一部)*
    ```python
    # ... (前略) ...
    import requests
    from temporalio.worker import activity

    @activity.defn
    async def request_hitl_intervention(self, payload: dict) -> str:
        adapter_url = "http://localhost:8000/hitl-request" # Hono Adapter のエンドポイント
        try:
            response = requests.post(adapter_url, json=payload, timeout=5)
            response.raise_for_status() # HTTP エラーが発生した場合に例外を発生させる
            return f"HITL request sent to Adapter: {response.status_code}"
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Failed to send HITL request to Adapter: {e}") from e
    ```

    *Hono Adapter のターミナルで、受信した HITL 介入要求のログを確認します。*
    ```
    INFO:     127.0.0.1:xxxxx - "POST /hitl-request HTTP/1.1" 200 OK
    Received HITL request: {'workflow_id': 'my-workflow-id-xxxx', 'reason': 'Data processing failed'}
    Simulating notification to Hono platform...
    ```
    Hono Adapter は、受信したデータを Hono プラットフォームへの通知をシミュレートするため、ログに出力します。これにより、Adapter 側で HITL 介入が必要なシナリオが適切に処理されていることを確認できます。

### 3.4. 期待されるログ出力と結果

*   **Temporal Worker のログ:**
    *   `DataProcessingActivity` および `DataValidationActivity` の実行ログ。
    *   `RequestHitlInterventionActivity` が実行され、Hono Adapter へリクエストを送信したログ。
*   **Hono Adapter のログ:**
    *   `/hitl-request` エンドポイントへの POST リクエスト受信ログ。
    *   受信したペイロード (`workflow_id`, `reason` など) の出力ログ。
    *   「Simulating notification to Hono platform...」のような Hono 連携シミュレーションログ。
*   **Temporal Dashboard (UI):**
    *   Workflow が `Completed` 状態になり、最終結果が「HITL Intervention Requested: Data Processing Failed」または「HITL Intervention Requested: Data Validation Failed」となっていることを確認します。
    *   Workflow のイベント履歴に、各 Activity の実行と `RequestHitlInterventionActivity` の呼び出しが記録されていることを確認します。

## 4. トラブルシューティング

リハーサル中に発生しうる一般的な問題とその解決策を以下に示します。

### 4.1. Temporal Server 接続エラー

**エラーメッセージ例:**
`temporalio.exceptions.ServiceError: Connection refused: localhost:7233`

**原因:**
Temporal Server が起動していないか、指定されたアドレスでリッスンしていません。

**解決手順:**
1.  別のターミナルで `temporal server start-dev` コマンドが実行されていることを確認します。
2.  Docker Desktop が起動していることを確認します。
3.  ファイアウォール設定が Temporal Server のポート (デフォルト 7233) をブロックしていないか確認します。

### 4.2. Activity タイムアウト

**エラーメッセージ例:**
`temporalio.exceptions.ActivityTimeoutError: Activity 'process_data' timed out after 10s`

**原因:**
Activity が指定された `start_to_close_timeout` 時間内に完了しなかった場合に発生します。Worker が起動していない、または Activity の処理に時間がかかりすぎている可能性があります。

**解決手順:**
1.  Worker プロセスが起動していることを確認します (`python worker.py`)。
2.  Activity のロジックに無限ループや長時間かかる処理がないか確認します。
3.  必要に応じて Workflow 定義内の `start_to_close_timeout` の値を増やします。

### 4.3. Hono Adapter 通信エラー

**エラーメッセージ例:**
`requests.exceptions.ConnectionError: ('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer'))`
`requests.exceptions.HTTPError: 500 Server Error: Internal Server Error for url: http://localhost:8000/hitl-request`

**原因:**
Hono Adapter が起動していない、または Adapter 側でエラーが発生しています。

**解決手順:**
1.  Hono Adapter プロセスが起動していることを確認します (`python adapter.py`)。
2.  Hono Adapter のターミナルでエラーログを確認し、Adapter 側の問題（ポート競合、コードエラーなど）を特定します。
3.  Workflow の Activity で指定している Adapter の URL (`http://localhost:8000/hitl-request`) が正しいことを確認します。

### 4.4. Workflow が期待通りに進行しない

**原因:**
コードのロジックエラー、Worker がタスクキューを正しくポーリングしていない、または Activity の実装に問題がある可能性があります。

**解決手順:**
1.  Temporal Dashboard (http://localhost:8080) で Workflow のイベント履歴を確認し、どの Activity で問題が発生しているかを特定します。
2.  Worker のログを確認し、エラーや警告が出力されていないか確認します。
3.  Workflow および Activity のコードをレビューし、ロジックに誤りがないか確認します。特に、ダミーモジュールの戻り値を正しく処理しているか確認します。

## 5. リハーサル結果の確認とデモ動画撮影への活用

### 5.1. リハーサル結果の評価

リハーサルが完了したら、以下の項目について評価を行います。

*   **HITL シナリオの再現性:** ダミーモジュールによる失敗が期待通りに検知され、HITL 介入要求が Hono Adapter に到達したか。
*   **コンポーネント連携の安定性:** 各コンポーネントがエラーなくスムーズに連携したか。
*   **ログ出力の明確性:** 各コンポーネントのログが、デバッグや状況把握に十分な情報を提供しているか。
*   **Temporal Dashboard の活用度:** Dashboard が Workflow の状態把握に有効であったか。
*   **デモ動画シナリオとの整合性:** リハーサルで確認された動作が、デモ動画で示すべきストーリーラインと一致しているか。

### 5.2. デモ動画撮影に向けた最終確認

リハーサル結果に基づき、デモ動画撮影に向けて以下の最終確認を行います。

*   **スクリプトの調整:** 実際のシステム動作に合わせて、デモ動画のスクリプトやナレーションを微調整します。
*   **環境の安定化:** リハーサル中に発見された問題は全て解決し、本番撮影環境が安定していることを確認します。
*   **デモデータの準備:** デモ動画で使う具体的な入力データや、期待される出力結果を準備します。
*   **手順の簡素化:** デモ動画の視聴者にとって分かりやすいよう、手順を簡素化または強調するポイントを決定します。
*   **役割分担の確認:** 撮影時の各担当者の役割（操作、ナレーション、カメラなど）を再確認します。

このSOPに従うことで、Temporal × Hono HITL 統合検証のデモ動画本番撮影を成功に導くための強固な基盤を築くことができます。