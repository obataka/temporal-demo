# ループバック制御実装計画

## Context
Phase 5（GitHub PR 承認待機）で `reject_with_feedback` シグナルを受けたとき、現在は
`rejected: True` で即リターンしていた。これを Phase 4（自律修正ループ）へ逆流させ、
人間のフィードバックを LLM プロンプトに注入した上で再修正→再承認を繰り返す
「対話型ループバック制御」へ拡張する。

---

## 変更ファイル

### 1. `activities/fix_sop_activity.py`

#### `_build_prompt` に `human_feedback: str = ""` を追加
- `human_feedback` が非空の場合、プロンプト内に `## 人間からの修正指示` セクションを挿入する。
- 既存の引数 `(sop_text, failures)` はそのまま保持（後方互換）。

```
## 修正が必要な問題点
<failures>

## 人間からの修正指示          ← human_feedback が非空のときのみ追加
<human_feedback>

## 修正対象の SOP
<sop_text>
```

#### `fix_sop_activity` に `human_feedback: str = ""` を追加
- `_build_prompt` 呼び出し時に `human_feedback` を渡すだけ。
- Activity シグネチャが変わるため、呼び出し側（workflow）も更新が必要。

---

### 2. `workflows/sop_workflow.py`

#### `_call_fix` に `human_feedback: str = ""` を追加
```python
async def _call_fix(self, sop_text, failures, human_feedback="") -> LLMResult:
    return await workflow.execute_activity(
        fix_sop_activity,
        args=[sop_text, failures, human_feedback],
        ...
    )
```

#### `run` メソッド — Phase 4 + Phase 5 を外側 `while True` で包む

```
outer: while True
  ① human_feedback = self._human_feedback
     self._human_feedback = ""    # ← リセット（二重ループ防止）
     self._fix_attempt = 0
     self._current_phase = "autonomous_fix"
     final_sop = current_sop

  ② [人間フィードバックの事前注入]
     if human_feedback:
         fix_result = await _call_fix(final_sop, [], human_feedback)
         final_sop = fix_result.text
         history に記録
         self._fix_attempt += 1

  ③ [通常バリデーションループ]
     while self._fix_attempt < MAX_FIX_ATTEMPTS:
         validate → if passed: break
         fix_result = await _call_fix(final_sop, failures)
         fix_attempt++
     else:
         raise ApplicationError(...)

  ④ current_sop = final_sop   # 次の外側ループ用に保持

  ⑤ [Phase 5]
     if github_params:
         if require_approval:
             self._pr_approved = False   # ← 再入時リセット
             await wait_condition(lambda: self._pr_approved or bool(self._human_feedback))
             if self._human_feedback:
                 continue  # ← outer loop へ逆流 (return を廃止)
         create_pr...
     break  # 通常終了
```

**戻り値の変更点:**
- `rejected: True` で早期リターンしていたブランチを削除。
- 差し戻し・再修正・再承認のすべてが同一ワークフロー実行内で完結する。

---

## テスト戦略

### デグレチェック（既存 40 件）
```bash
python -m pytest tests/ -q
```
- `fix_sop_activity` の新引数はデフォルト値付き → 既存テストは無変更で Green 継続。
- ワークフロー本体のテストは現時点で存在しないため影響なし。

---

## クリティカルポイント

1. **`self._pr_approved = False` の再入リセット（⑤）**
   前回ループで approve_pr が届いていた場合に wait_condition を即通過してしまう。
   `await wait_condition` 直前でリセットすることで冪等性を保つ。

2. **事前 fix パス（②）の fix_attempt カウント**
   `MAX_FIX_ATTEMPTS` の残り枠を 1 消費する。
   事前 fix で通常ループが 1 回減るが、許容範囲（合計 3 回は変わらず）。

3. **`_human_feedback` のリセットタイミング（①）**
   外側ループ先頭でキャプチャ直後にリセットする。
   Activity 実行中に次の `reject_with_feedback` が届いても正しく次の外側ループ
   で処理され、二重処理にならない。
