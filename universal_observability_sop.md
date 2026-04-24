# Project: Universal AI Observability & Reliability Wrapper
## Context & Goal
本プロジェクトの目的は、AIエージェントの推論プロセスに「透明性（Observability）」と「回復性（Resiliency）」を付与する、移植性の高いモジュール一式を構築することである。
特定のアプリケーション（VS Code拡張等）に依存せず、後からどんなプロジェクトにも「差し込む」だけで、トークン数、コスト、実行履歴を完全に管理可能にすることをゴールとする。

## 必須スタック
- **Runtime**: Python (3.10+)
- **Reliability**: `temporalio` (Official Python SDK)
- **Monitoring**: `structlog` (構造化JSONログ)
- **LLM SDK**: `google-genai` (実装のサンプルとして使用)

## 実装ステップ (Phase 2: Universal Integration)
### 1. 汎用 Observability デコレータの実装
- LLM呼び出しをラップする `log_llm_interaction` デコレータ、またはコンテキストマネージャを作成せよ。
- **記録対象**:
    - モデル名、入力プロンプト（要約）、出力（要約）、トークン数（Input/Output/Total）、実行時間（Latency）。
- **出力形式**:
    - `structlog` を用い、後で分析ツール（ELKやDatadog等）に流し込みやすいJSON形式で出力せよ。

### 2. Temporal Search Attributes の自動連携
- Workflowのメタデータ（Search Attributes）を動的に更新するユーティリティを実装せよ。
- `LLM_Model`, `Total_Tokens`, `Status` (Success/Retry/Fail) を、Temporal UI上から一覧・フィルタリングできるようにせよ。

### 3. モック推論モードの搭載 (隔離環境用)
- APIキーがなくても動作確認できるよう、`MockLLMActivity` を作成せよ。
- これはランダムな推論時間とトークン数をシミュレートし、上記1と2の監視機能が正しく動作することを証明するためのものである。

### 4. フォルダ構成の整理
- 今後の統合を見据え、以下のようなクリーンな構成にリファクタリングせよ。
    - `/core`: Observability, RetryPolicy 定義
    - `/activities`: LLM呼び出し、モックActivity
    - `/workflows`: Temporalワークフロー定義
    - `/tests`: モックを使用した監視機能のテストコード

## 評価基準
- `docker-compose logs` で、AI推論の内実が構造化されたJSONとして視認できるか。
- Temporal UI上で、モック実行した際の「消費トークン数」がカスタム属性として表示されているか。
- 本モジュールが、昨日のソースコードがなくても「単体で完璧に動作」するか。