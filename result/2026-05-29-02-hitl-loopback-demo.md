# 対話型ループバック制御 — 実戦結合デモ検証レポート

## 検証概要

| 項目 | 値 |
| :--- | :--- |
| Workflow ID | `sop-hitl-demo-cd4d486e` |
| 総所要時間 | 8.1 分（486 秒） |
| 差し戻しラウンド | 1 回 |
| GitHub PR | https://github.com/obataka/temporal-demo/pull/5 |

---

## A. 状態遷移フロー（実測）

```
Phase 1（章立て提案）  → 自動承認  → tokens=1,613
Phase 2（詳細執筆）    → 自動承認  → tokens=7,117
Phase 3（最終レビュー）→ 自動承認  → tokens=12,918
Phase 4（自律修正）    attempt=0  → バリデーション PASS（tokens=0）
            ↓
Phase 5（承認待ち）    ←── ブラウザから「差し戻し」シグナル送信
            │           feedback: "セキュリティに関する項目をSOPに追加してください。"
            ↓
Phase 4（ループバック再実行）
   ├─ [事前 fix パス]  failures=["[人間フィードバック] セキュリティに関する…"]
   │                   tokens=12,647（LLM が人間指示を反映した修正版を生成）
   └─ [バリデーション]  attempt=1  → PASS
            ↓
Phase 5（承認待ち ラウンド 2）  ←── ブラウザから「承認」シグナル送信
            ↓
GitHub PR 作成 → https://github.com/obataka/temporal-demo/pull/5
            ↓
completed ✓
```

---

## B. ワークフロー履歴ログ（`get_history` Query 結果）

| フェーズラベル | attempt | approved | tokens | failures |
| :--- | :---: | :---: | ---: | :--- |
| フェーズ1: 章立て提案 | 0 | ✓ | 1,613 | — |
| フェーズ2: 詳細執筆 | 0 | ✓ | 7,117 | — |
| フェーズ3: 最終レビュー | 0 | ✓ | 12,918 | — |
| フェーズ4: 自律修正（初回） | 0 | ✓ | 0 | — |
| **フェーズ4: 自律修正（ループバック事前 fix）** | **0** | — | **12,647** | `[人間フィードバック] セキュリティに関する項目をSOPに追加してください。` |
| フェーズ4: 自律修正（ループバック後バリデーション） | 1 | ✓ | 0 | — |

---

## C. 検証結果サマリー

### 確認済み動作

1. **差し戻しシグナル検知**: `reject_with_feedback` を受信後、ワークフローが
   即座に `await wait_condition` を抜けて外側ループの `continue` へ遷移した。

2. **人間フィードバックの LLM 注入**: ループバック後の Phase 4 で
   `fix_sop_activity` が `failures=["[人間フィードバック] セキュリティ…"]`
   を受け取り、12,647 トークンの修正版 SOP を生成。

3. **`self._human_feedback` リセット**: ループバック後に再び
   `awaiting_pr_approval` へ遷移（二重ループなし）。

4. **再承認ゲート**: ラウンド 2 の承認待ちで `approve_pr` を受信し、
   GitHub PR 作成まで完走。

5. **デグレなし**: 既存ユニットテスト 40 件すべて Green。

### デモスクリプト変更点

- `_wait_for_human_signal` を `_wait_for_human_action(handle, workflow_id, round_num) → "approved" | "rejected"` に置き換え。
- `main()` の Phase B〜C を `while True` ループ化し、差し戻し時に Phase 4 再実行待ちを挟む構造へ変更。
