# Gemini モデル切り替えホットフィックス — gemini-2.5-flash → gemini-2.5-flash-lite

## Context
E2E グランドデモの3回実行（Run 1〜3）で Gemini free tier の **20 req/day 上限**（gemini-2.5-flash）を使い切った。
ワークフロー `sop-e2e-grand-demo-fd0edabc` が Phase 3 2回目生成中に 429 RESOURCE_EXHAUSTED で失敗し終了。

調査の結果、同じ API キーで以下のモデルは残量あり（テスト確認済み）:
- `gemini-2.5-flash-lite` ← 同系列・最小リスク → **採用**
- `gemini-3.5-flash`, `gemini-3.1-flash-lite` も使用可能

## 変更ファイル（2箇所のみ）

| ファイル | 変更箇所 |
|---|---|
| `activities/sop_activity.py` | `_MODEL = "gemini-2.5-flash"` → `"gemini-2.5-flash-lite"` |
| `activities/fix_sop_activity.py` | `_MODEL = "gemini-2.5-flash"` → `"gemini-2.5-flash-lite"` （+ docstring 内の Gemini 2.5 Flash 記述を Lite に更新） |

## 実行手順

1. 上記2ファイルの `_MODEL` 定数を Edit ツールで変更
2. Docker worker を再ビルド（モデル変更はコード変更のため必須）:
   ```
   docker compose -f compose.yml up --build worker -d
   ```
3. E2E デモを再実行（Run 4）:
   ```
   .venv/bin/python sop_e2e_demo.py 2>&1 | tee /tmp/run4.log
   ```

## 検証

- Phase 3 2回目生成が正常完了（awaiting_approval に到達）
- Phase 4 自律修正ループが `禁止用語が含まれる` を検出・修正・再検証 PASS
- `approve_pr Signal` 送信後 GitHub PR URL が出力される
- 完了後 `result/` に概要ドキュメントを作成

## 影響範囲

- 既存テストは影響なし（モデル名は conftest でモック済み）
- SOP 品質は若干低下する可能性があるが、デモの主目的（自律修正ループの実証）には支障なし
