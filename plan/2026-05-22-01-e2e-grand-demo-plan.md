# E2E グランドデモ スクリプト設計 — sop_e2e_demo.py

## Context
temporal-demo プロジェクトの全 Phase（1〜5）を一本で繋ぐ実証スクリプトを作成する。
既存の `sop_github_test.py` は require_approval=False かつ Phase 4 の詳細ログがなく、
「意図的バグ注入 → AI 自己修正 → 人間承認ゲート → PR 発行」のストーリーが可視化できない。

---

## 新規ファイル: `sop_e2e_demo.py`

### 主な設定値

| 項目 | 値 |
|---|---|
| TOPIC | "E2E グランドデモ — AI自律修正ループ 統合検証SOP" |
| SOURCE_FILE | `sop_e2e_demo.py` 自身（動的に読み込む）|
| FEATURE_BRANCH | `auto-fix/sop-e2e-final` |
| FILE_PATH | `docs/sop-e2e-final.md` |
| require_approval | `True` |

### バリデーションエラー注入戦略

Phase 3（review）の **1回目の awaiting_approval** に対して、以下のフィードバック Signal を送信する：

```
「現状の問題点」セクションを追加し、以下の文章を必ず一字一句そのまま含めてください：
「本手順書は現在確認中のため、一部の仕様は未定であり、実装は作成中の段階です。」
```

これにより Phase 3 の 2 回目の出力に禁止用語（確認中・未定・作成中）が埋め込まれる。
Phase 4 の `validate_sop_activity` がこれを検出 → `fix_sop_activity` が修正 → 再検証 PASS。

### 実行フロー

```
STEP 1  ワークフロー起動（GitHubParams.require_approval=True）
        ↓
STEP 2  Phase 1 (outline): awaiting_approval を待って → approve_step("") 送信
        ↓
STEP 3  Phase 2 (draft):   awaiting_approval を待って → approve_step("") 送信
        ↓
STEP 4  Phase 3 (review):
        ├─ 1回目 awaiting_approval → 禁止用語注入フィードバック Signal 送信
        ├─ 2回目 awaiting_approval（禁止用語入り）→ approve_step("") で承認
        └─ [LOG] "Phase 3 完了: 禁止用語を含む SOP を承認しました（意図的）"
        ↓
STEP 5  Phase 4 (autonomous_fix): ポーリングで詳細ログ
        ├─ status=validating → "[検証中] 試行#1"
        ├─ status=fixing    → "[AI修正中] 失敗: {failures}"
        ├─ status=validating → "[検証中] 試行#2"
        └─ status が awaiting_pr_approval に変化したら STEP 6 へ
        ↓
STEP 6  status=awaiting_pr_approval → "承認ゲート到達" ログ出力
        → approve_pr() Signal 送信
        ↓
STEP 7  status=completed を待つ
        → pr_url を表示して終了
```

### ポーリング関数設計

```python
async def _poll_phase4_and_pr(handle, timeout=600.0) -> dict:
    """Phase 4 の validating/fixing 遷移をリアルタイムで表示しつつ
    awaiting_pr_approval に達したら即座に返す。"""
    last_status = None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = await handle.query("get_status")
        st = status["status"]
        fix_attempt = status.get("fix_attempt", 0)
        if st != last_status:
            if st == "validating":
                print(f"  [Phase 4] 検証中 ... (fix試行#{fix_attempt})")
            elif st == "fixing":
                v = status.get("validation_result") or {}
                for f in v.get("failures", []):
                    print(f"    ✗ {f}")
                print(f"  [Phase 4] AI修正開始 ...")
            elif st == "awaiting_pr_approval":
                print(f"  [Phase 4] PASS — PR承認ゲートに到達")
                return status
            elif st == "completed":
                return status
            last_status = st
        await asyncio.sleep(2.0)
```

### 変更ファイル一覧

| ファイル | 種別 | 内容 |
|---|---|---|
| `sop_e2e_demo.py` | **新規作成** | E2E デモスクリプト本体 |

既存ファイルへの変更は一切なし。

### 検証

1. `docker compose up --build worker -d` でワークフロー確認
2. `python sop_e2e_demo.py` を実行（約 15〜20分）
3. 以下が出力されることを確認:
   - Phase 4 で `✗ 禁止用語が含まれる: 確認中, 未定, 作成中` ログ
   - `approve_pr Signal 送信` ログ
   - 最終的な `PR URL: https://github.com/obataka/temporal-demo/pull/N`
4. Temporal UI `http://localhost:8080` でワークフロー履歴を確認
