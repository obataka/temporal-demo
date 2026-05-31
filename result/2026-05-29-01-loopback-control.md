# ループバック制御 実装完了レポート

## A. System Interaction Flow

```
reject_with_feedback({"comment": "..."})
    ↓ self._human_feedback に格納
    ↓
[外側 while True ループ]
    ↓
① human_feedback キャプチャ & self._human_feedback リセット
    ↓
② [human_feedback 非空の場合]
    _call_fix(current_sop, [], human_feedback)
        → fix_sop_activity(sop_text, failures=[], human_feedback)
            → _build_prompt: "## 人間からの修正指示" セクション追加
    ↓
③ [通常バリデーションループ]
    _call_validate → ValidationResult
        passed=True  → break（Phase 5 へ）
        passed=False → _call_fix(sop, failures) → fix_attempt++
    ↓
⑤ Phase 5: require_approval=True
    self._pr_approved = False  ← 再入時リセット
    wait_condition(pr_approved or human_feedback)
        human_feedback あり → continue（Phase 4 へ逆流）
        pr_approved      → create_pr → break（完了）
```

---

## B. Responsibility Matrix

| ファイルパス | クラス/メソッド名 | 処理の目的・役割 | 相互作用する相手 |
| :--- | :--- | :--- | :--- |
| `activities/fix_sop_activity.py` | `_build_prompt` | `human_feedback` を `## 人間からの修正指示` セクションとしてプロンプトに注入 | `fix_sop_activity` |
| `activities/fix_sop_activity.py` | `fix_sop_activity` | `human_feedback: str = ""` 引数を追加（後方互換）してプロンプト構築に渡す | Gemini API |
| `workflows/sop_workflow.py` | `_call_fix` | `human_feedback` 引数を追加し `fix_sop_activity` の `args` に渡す | `fix_sop_activity` |
| `workflows/sop_workflow.py` | `run` (Phase 4+5) | Phase 4 + Phase 5 を外側 `while True` で包み、差し戻し時に Phase 4 へループバックする | `_call_fix`, `_call_validate`, `_call_github_pr` |

---

## C. 設計の意図とクリティカルポイント

### 設計の意図
`reject_with_feedback` シグナルで早期リターンしていた設計を、同一ワークフロー実行内で
何度でもループできるように変更した。
ループバックとフィードバック注入を分離（事前 fix パス②）することで、SOP がバリデーション
をすでに通過済みの場合でも人間の指摘を LLM に確実に届けられる。

### クリティカルポイント

1. **`self._human_feedback = ""` のリセットタイミング（外側ループ先頭）**
   Activity 実行中に次の `reject_with_feedback` が届いた場合でも、現在のループが
   終了した後の次イテレーションで正しく処理される（二重処理なし）。

2. **`self._pr_approved = False` の再入リセット（⑤直前）**
   前回イテレーションで `approve_pr` が届いていた状態で再入すると
   `wait_condition` を即通過してしまうため、ループバック後に必ずリセットする。

3. **事前 fix パスの `fix_attempt` カウント（②）**
   事前 fix も `MAX_FIX_ATTEMPTS` の残り枠を 1 消費する。
   human_feedback あり時は通常バリデーションループの試行が最大 2 回になるが、
   合計 3 回の上限自体は変わらず安全範囲内。

---

## D. テスト結果

```
40 passed in 1.08s
```

既存 40 件全件 Green（デグレなし）。
新引数 `human_feedback: str = ""` はデフォルト値付きのため既存テストへの影響なし。
