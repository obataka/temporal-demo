# Plan: 画面承認デモスクリプト（hitl_webui_demo.py）

## Context

Web UI の承認ボタンを使った「人間承認デモ」をライブ実行する。
ワークフローを Phase 5 承認待ちで安全停止させ、ブラウザ操作でシグナルを送信し、
自動完走と PR 作成まで連続して観察する。

## 新規ファイル

- `hitl_webui_demo.py`（プロジェクトルート）

## 再利用（web_ui_e2e_test.py から流用）

- `DUMMY_SOURCE_CODE`（禁止用語なし・チェック済み）
- Phase 1–3 自動承認ループ
- `_poll_phase4_and_pr_gate()` ロジック

## 動作フロー

### フェーズ A（自動）

ワークフロー起動 → Phase 1–3 自動承認 → Phase 4 → `awaiting_pr_approval` 到達

### フェーズ B（待機）

明示的な案内メッセージを出力後、5 秒ポーリング（ドットのみ）で無音待機：

```
[Phase 5 GATE] ══════════════════════════════════
  Workflow ID : sop-hitl-demo-XXXXXXXX
  ■ http://localhost:3000 を開いてください。
  ■ ドロップダウンから ID を選択し「承認する」を押してください。
  待機中...
═════════════════════════════════════════════════
```

`status != "awaiting_pr_approval"` になったら受信確定。タイムアウト 10 分。

### フェーズ C（自動）

シグナル受信 → Phase 5 GitHub PR 作成 → `completed` → PR URL 表示

## ブランチ設定

- `FEATURE_BRANCH = "auto-fix/hitl-webui-demo"`
- `FILE_PATH      = "docs/sop-hitl-webui-demo.md"`
