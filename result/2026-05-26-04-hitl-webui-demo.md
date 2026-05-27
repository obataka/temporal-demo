# Web UI 画面承認デモ（HITL）実行結果

実行日時: 2026-05-26 10:42–10:45
スクリプト: `hitl_webui_demo.py`

## A. フロー全体

```
hitl_webui_demo.py
  ── フェーズ A（自動）──────────────────────────────────────
  10:42:11  ワークフロー起動: sop-hitl-demo-e93c8d96
  10:42:21  Phase 1（章立て）生成完了 → 自動承認
  10:42:59  Phase 2（詳細執筆）生成完了 → 自動承認
  10:44:02  Phase 3（最終レビュー）生成完了 → 自動承認
  10:44:07  Phase 4 バリデーション PASS ✓

  ── フェーズ B（人間待機）──────────────────────────────────
  10:44:07  [Phase 5 GATE] 案内メッセージ表示・無音ポーリング開始
              Workflow ID : sop-hitl-demo-e93c8d96
              URL         : http://localhost:3000

  10:45:44  ブラウザから approve_pr シグナル受信

  ── フェーズ C（自動）──────────────────────────────────────
  10:45:44  GitHub PR 作成開始
  10:45:xx  completed → PR URL 取得
```

## B. 実行結果

| 項目 | 値 |
|---|---|
| Workflow ID | `sop-hitl-demo-e93c8d96` |
| GitHub PR URL | https://github.com/obataka/temporal-demo/pull/5 |
| 総所要時間 | 3.5 分（213 秒） |
| 人間待機時間 | 約 97 秒（10:44:07 → 10:45:44） |
| Phase 4 | バリデーション一発 PASS（AI 修正なし） |
| Temporal UI | http://localhost:8080/namespaces/default/workflows/sop-hitl-demo-e93c8d96 |

## C. 設計のポイント

- フェーズ B の無音ポーリング: `status != "awaiting_pr_approval"` を 5 秒間隔で検出。
  ブラウザからの `POST /api/approve` → Hono → Temporal Signal の経路が正しく機能したことを確認。
- `FEATURE_BRANCH = "auto-fix/hitl-webui-demo"` を使用し、前回の `web_ui_e2e_test.py`
  （`auto-fix/webui-e2e-test`）と衝突しないよう分離した。
