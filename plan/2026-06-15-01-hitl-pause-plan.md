# rehearsal_audit.py — HITL 一時停止制御 追加プラン

## Context

現在 `rehearsal_audit.py` は Phase 1-3 自動承認 → Phase 4 差し戻し（Writer/Reviewer）→ **即座に** GitHub PR 承認まで全自動で完走する。
これにより以下が不可能：

- UI 側から追加指示を手動で投入すること
- Writer/Reviewer パルス明滅の撮影タイミングを人間が制御すること
- 承認（Complete）ボタンを手動でクリックすること

**目標**: Writer/Reviewer の自律議論が完了した直後（`awaiting_pr_approval` 復帰後）かつ GitHub PR 生成の直前に、ターミナルが `input()` で待機し、人間が Enter を押すまで先へ進まないよう制御を追加する。

---

## 修正対象ファイル

`rehearsal_audit.py` 1 ファイルのみ

---

## 挿入位置（1 か所）

```
[現在の流れ]
Line 459-461: _capture_writer_reviewer_visual(...)  ← Writer/Reviewer 完了
Line 463:     # ラウンド 2: 承認 → GitHub PR 作成   ← ここが問題（即座に承認）

[変更後]
Line 459-461: _capture_writer_reviewer_visual(...)  ← Writer/Reviewer 完了
              ★ HITL 待機ブロック（input() ループ） ← 追加
Line 463:     # ラウンド 2: 承認 → GitHub PR 作成
```

---

## 追加する HITL 待機ブロックの仕様

### 基本フロー

1. `_rule()` + 説明メッセージ表示（UI 確認・追加指示投入を促す）
2. `input("  >> Enter を押して GitHub PR 承認に進む: ")` で待機
3. Enter 押下後に `handle.query("get_status")` でワークフロー状態を確認
   - `awaiting_pr_approval` → break（承認フェーズへ進む）
   - `fixing` / `validating` → "UI から差し戻し実行中" を表示し `_capture_writer_reviewer_visual` を再呼び出し → ループ先頭へ戻り再度 Enter 待機
   - `completed` → ログ表示して break（PR 承認ステップはスキップ）
   - その他 → 警告表示して break

### EOFError / KeyboardInterrupt 処理

非対話環境（CI / パイプ入力）や Ctrl+C が来た場合は `except (EOFError, KeyboardInterrupt)` で捕捉してそのまま break し、スクリプトを継続させる。

### `_capture_writer_reviewer_visual` の再利用

UI 側から差し戻しが来た場合の追加 Writer/Reviewer サイクルの監視に、既存の `_capture_writer_reviewer_visual` を `round_label="UI差し戻し"` で再呼び出しする（新規関数不要）。

---

## 変更後のコードイメージ

```python
    # ── [HITL 待機] Writer/Reviewer 完了 → 人間がUI操作・Enter で承認 ──────────
    _rule()
    print("  ⏸  [HITL] Writer/Reviewer の自律議論が完了しました。")
    print()
    print("  ブラウザ UI を確認し、追加指示を入力する場合は「差し戻し」ボタンから")
    print("  操作してください（Writer/Reviewer が再起動します）。")
    print()
    print("  ターミナルで Enter を押すと GitHub PR の承認・生成に進みます。")
    _rule()

    while True:
        try:
            input("  >> Enter を押して GitHub PR 承認に進む: ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        st = await handle.query("get_status")
        st_val = st.get("status", "")
        if st_val == "awaiting_pr_approval":
            break
        elif st_val in ("fixing", "validating"):
            _log("HITL", f"UI から差し戻しが実行中 (status={st_val!r})。Writer/Reviewer 完了を待機...")
            await _capture_writer_reviewer_visual(
                handle, audit, timeout=TIMEOUT_PHASE4, round_label="UI差し戻し"
            )
        elif st_val == "completed":
            _log("HITL", "ワークフロー完了済み — PR 承認をスキップ")
            break
        else:
            _log("WARN", f"予期しないステータス: {st_val!r} — 承認へ進みます")
            break
```

---

## audit 判定への影響

- 既存の 14 監査項目への影響なし（`audit.ok/fail` の呼び出し順序・内容は変わらない）
- `【要件③】GitHub PR が自動生成された（ノータイム）` のラベル文言を `（手動承認後）` に変更する（軽微）

---

## 検証手順

1. `python rehearsal_audit.py` を実行
2. Phase 1-3 が自動承認されることを確認
3. Writer/Reviewer が起動・完了後に **ターミナルが入力待ちで停止** することを確認
4. ブラウザで UI 追加指示（差し戻し）を送信 → Writer/Reviewer が再起動することを確認（任意）
5. ターミナルで Enter を押す → `【要件③】POST /api/approve 成功` が出力されることを確認
6. GitHub PR URL が表示され、監査サマリーが `14/14 PASS` になることを確認
