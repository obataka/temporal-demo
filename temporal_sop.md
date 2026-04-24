# Project: Unbreakable AI Agent with Temporal
## Context & Goal
本プロジェクトの目的は、Temporalを使用して「回復性（Resiliency）」と「可観測性（Observability）」を兼ね備えたAIエージェントのプロトタイプを構築することである。
AIの推論という不安定なプロセスをTemporalのWorkflowで包み込み、「絶対に失敗しない（または失敗を追跡できる）」業務フローを実現する。

## 必須スタック
- **Runtime**: Python (3.10+)
- **SDK**: `temporalio` (Official Python SDK)
- **Infrastructure**: Docker Compose (Temporal Server用)
- **LLM**: Gemini API or Claude API

## 実装ステップ (Phase 1)
### 1. インフラ構築
- `docker-compose.yaml` を作成し、Temporal Cluster (server, ui, database) を立ち上げよ。

### 2. 環境セットアップ
- `requirements.txt` に `temporalio`, `google-generativeai` (または `anthropic`) を追加しインストールせよ。

### 3. Workflow & Activity の定義
- **Activity (`call_llm_activity`)**:
    - LLMに特定のタスク（例：リバースエンジニアリングの要約）を依頼する処理。
    - **重要**: 意図的に失敗（Exception）を発生させるデバッグモードを搭載せよ。
- **Workflow (`ai_agent_workflow`)**:
    - 上記Activityを呼び出す。
    - Temporalの `RetryPolicy` を設定し、Activityが失敗しても自動で再試行する設定（最大3回）を行え。

### 4. Worker & Starter
- ワークフローを待ち受ける `worker.py` と、外部から発火させる `run_workflow.py` を実装せよ。

## 評価基準
- Temporal UI (localhost:8080) で、Workflowの実行履歴が「不滅」であることを確認できるか？
- AIがエラーを吐いた際、コードがクラッシュせず、Temporalによって自動リトライが行われるか？