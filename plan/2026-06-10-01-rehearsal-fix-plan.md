# リハーサル監査修正計画

## 問題

第 1 回実行で Phase 4 のバリデーションが一発 PASS し、Writer/Reviewer が起動しなかった。
`agent_logs` が空のまま awaiting_pr_approval に達したため、ビジュアル要件 ① ② が検証できなかった。

## 根本原因

SOP がフェーズ 3（最終レビュー）で十分な品質になるため、Phase 4 バリデーションを即座にパスする。
Writer/Reviewer は `_call_fix_decomposed` が呼ばれたときのみ起動する。

## 修正方針

1. **reject_with_feedback → Writer/Reviewer → approve** の 2 ラウンド構成にリハーサルを更新する。
   - ラウンド 1: 最初の `awaiting_pr_approval` で `POST /api/reject` を送信（ダミーフィードバック）
   - 監視: Writer バッジ（active_agent="Writer"）→ Reviewer バッジ（active_agent="Reviewer"）を捕捉
   - ラウンド 2: 2 回目の `awaiting_pr_approval` で `POST /api/approve` を送信
   - 検証: PR URL、agentLogs、Worker 例外ゼロ

2. **ファイル変更範囲**:
   - `rehearsal_audit.py` のみ（生産コード変更なし）

## テスト戦略

- Python `rehearsal_audit.py` を再実行して全 7 項目（Writer/Reviewer 各 3 項目 + PR + Web UI + ログ） PASS を確認する
