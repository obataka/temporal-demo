# Plan: agentLogs リアルタイム可視化デモ検証セットアップ

## Context
ブラウザの黒いコンソール（`#agentLogsContainer`）に Reviewer の思考プロセスが
流れる様子をリアルタイムで目視確認するための一時的なデモ設定変更。

`tasks_output[1].raw`（Reviewer の出力テキスト）がブラウザに表示される仕組みは
すでに完成している。現状 Reviewer の `expected_output` が箇条書き一行形式のため
「思考プロセスが流れる」感が薄い。以下2点を調整して観察しやすくする。

## 変更ファイル（1ファイル）

`activities/fix_sop_activity.py` — `_build_sop_crew()` 内のみ。

### ① verbose=True（Writer・Reviewer・Crew の3箇所）
Worker stdout ログに CrewAI のステップログが出力される。

### ② task_review の expected_output を拡張
Reviewer が思考プロセスをテキストに書き出すよう明示指示。
`tasks_output[1].raw` の中身が詳細になり、ブラウザコンソールに可視化される。

変更後フォーマット:
- ## レビュー観点チェック（各観点の評価）
- ## 発見した問題点（重大度付き）
- ## 総評（エンタープライズ品質観点の2〜3文）

## テスト件数
`task_review.expected_output` は既存テストで検査されていないため 45 件維持。

## 実行手順
1. `docker compose up --build -d worker web-ui`
2. `python hitl_webui_demo.py > /tmp/hitl_demo2.log 2>&1 &`
3. Phase 5 到達を確認 → ブラウザで差し戻し操作を案内
4. Worker ログ + ブラウザコンソールでログ伝播を確認・報告
