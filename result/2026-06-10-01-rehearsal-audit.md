# デモ動画本番撮影 リハーサル監査報告

**実施日**: 2026-06-10  
**監査スクリプト**: `rehearsal_audit.py`  
**最終ワークフロー ID**: `sop-rehearsal-9fcd94ea`  
**Feature Branch**: `auto-fix/rehearsal-20260610-101524`

---

## System Interaction Flow

```
rehearsal_audit.py
  ↓  start_workflow
sop_generation_workflow
  ↓  generate_sop_phase_activity × 3（Phase 1-3: outline/draft/review）
  ↓  auto approve_step("") × 3
  ↓  validate_sop_activity（PASS: SOP品質基準クリア）
  ↓  → awaiting_pr_approval
  ↓  POST /api/reject（Web UI 差し戻しボタン相当）
  ↓  reject_with_feedback Signal
  ↓  writer_task_activity        [active_agent="Writer"  ← 緑パルス]
  ↓  reviewer_task_activity      [active_agent="Reviewer" ← アンバーパルス]
  ↓  validate_sop_activity（PASS）
  ↓  → awaiting_pr_approval
  ↓  POST /api/approve（Web UI 承認ボタン相当）
  ↓  approve_pr Signal
  ↓  GitHubActivity.create_pull_request
  ↓  → completed
GitHub PR https://github.com/obataka/temporal-demo/pull/8
```

---

## Responsibility Matrix

| ファイルパス | クラス/メソッド名 | 処理の目的・役割 | 相互作用する相手 |
| :--- | :--- | :--- | :--- |
| `rehearsal_audit.py` | `main()` | E2E 監査の全体制御 | Temporal Client, Web UI API |
| `rehearsal_audit.py` | `_capture_writer_reviewer_visual()` | Writer/Reviewer バッジ遷移を監視 | Temporal Query `get_status` |
| `workflows/sop_workflow.py` | `_call_fix_decomposed()` | Writer → Reviewer の 2 ステップ修正 | writer_task_activity, reviewer_task_activity |
| `web-ui/src/index.ts` | `POST /api/reject` | 差し戻しシグナルを Temporal へ中継 | `reject_with_feedback` Signal |
| `web-ui/src/index.ts` | `POST /api/approve` | 承認シグナルを Temporal へ中継 | `approve_pr` Signal |
| `web-ui/public/index.html` | `updateAgentBadges()` | active_agent 値に応じてバッジ色を切替 | ポーリング API |
| `web-ui/public/index.html` | `showTypingCursor()` | active_agent 非 null 時にカーソル表示 | ポーリング API |

---

## 撮影ビジュアル要件 監査結果（全 14 項目）

### 要件① Writer（緑パルス明滅）

| # | 検証項目 | 結果 | 実測値 |
| :- | :--- | :---: | :--- |
| 1 | Writer バッジ `active_agent=Writer` | ✅ PASS | `active_agent='Writer'` `status='fixing'` |
| 2 | Writer ステータスログ存在 | ✅ PASS | `[Writer] 修正案を生成中...` |
| 3 | agentLogs 空 → タイピングカーソルのみ表示（仕様通り） | ✅ PASS | active_agent 非 null → カーソル出現 |

**起動タイムライン**: 差し戻し送信（10:17:01）→ Writer 検出（10:17:03）= 2 秒以内

### 要件② Reviewer（アンバーパルス）→ バッジ色・ログ連動

| # | 検証項目 | 結果 | 実測値 |
| :- | :--- | :---: | :--- |
| 4 | Reviewer バッジ `active_agent=Reviewer` | ✅ PASS | `active_agent='Reviewer'` `status='fixing'` |
| 5 | Reviewer ステータスログ存在 | ✅ PASS | `[Reviewer] セキュリティ・品質チェック中...` |
| 6 | Reviewer 遷移後の agentLogs（仕様通り） | ✅ PASS | サイクル完了後 2,249 chars 蓄積 |
| 7 | エージェント完了後 agentLogs 累積確認 | ✅ PASS | len=2,249 chars |

**Writer → Reviewer 遷移**: 10:17:03 → 10:17:54 = 51 秒（Writer LLM 生成時間）

### 要件③ ループ完走 → 承認ボタン → PR 自動生成（ノータイム）

| # | 検証項目 | 結果 | 実測値 |
| :- | :--- | :---: | :--- |
| 8 | `POST /api/reject` 成功（200 OK） | ✅ PASS | `{"success": true}` |
| 9 | `POST /api/approve` 成功（200 OK） | ✅ PASS | `{"success": true}` |
| 10 | GitHub PR 自動生成 | ✅ PASS | [#8: https://github.com/obataka/temporal-demo/pull/8](https://github.com/obataka/temporal-demo/pull/8) |
| 11 | 承認 → PR 生成のリードタイム | ✅ PASS | 8 秒（10:18:18 → 10:18:26） |

### Web UI API / コンテナ整合性

| # | 検証項目 | 結果 | 実測値 |
| :- | :--- | :---: | :--- |
| 12 | Web UI 最終確認: `phase=completed` `status=completed` | ✅ PASS | 正常 |
| 13 | 最終 agentLogs に Reviewer ログ累積 | ✅ PASS | len=2,249 chars |
| 14 | Worker ログにコードバグ起因の例外なし | ✅ PASS | 非一時的エラー 0 件 |

> ⚠️ **Gemini API 503 (一時的レート制限)**: 計 13 件のレート制限エラーが `reviewer_task_activity` で発生。  
> Temporal の `retry_policy` が自動リトライして全件回復済み。ワークフローは正常完了し、Web UI には影響なし。  
> デモ動画撮影中に再発した場合も、Reviewer バッジのアニメが若干長くなるだけ（UI 上は透過）。

---

## 設計の意図・クリティカルポイント

**なぜ「差し戻し → Writer/Reviewer → 再承認」の 2 ラウンド構成か**  
Phase 3（最終レビュー）の SOP は品質基準を通常クリアするため、Phase 4 バリデーションが一発 PASS する。Writer/Reviewer アニメを確実に見せるには、プレゼンターが意図的に「差し戻し」を行い、人間フィードバック inject ルート（`_call_fix_decomposed`）を通す必要がある。

**クリティカルポイント 3 点**

1. **差し戻しコメントの内容は非重要** — `reject_with_feedback` のコメントテキストはそのまま Writer への指示として注入されるが、バリデーション基準（文字数・セクション数・コードブロック・禁止語）をクリアできる改善方向なら何でもよい。
2. **Bun HTTP 10 秒タイムアウト** — Temporal Query が LLM 生成中に重なると Web UI の `/api/status` が空応答を返すケースがある（Bun のデフォルト idle timeout）。ポーリング間隔 5 秒で次のポーリングが成功するため実害なし。デモ時は `refreshBtn` を連打しない。
3. **Gemini API 503 対策** — 本番撮影は午前中（JST）など API 負荷が低い時間帯を選ぶと 503 リトライ遅延を最小化できる。

---

## 総合判定

**✅ リハーサル完了。本番撮影いつでも GO 可能です。**

- GitHub PR URL: https://github.com/obataka/temporal-demo/pull/8
- 全 3 ビジュアル要件 100% 動作確認
- Worker ログにコードバグ起因の例外ゼロ
- Temporal Resilience: Phase 1-3 → Phase 4（Writer/Reviewer） → Phase 5（PR）完全完走
