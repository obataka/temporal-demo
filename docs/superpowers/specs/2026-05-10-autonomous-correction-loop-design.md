# 設計仕様: 自律修正ループ (Autonomous Correction Loop)

**作成日:** 2026-05-10  
**対象ワークフロー:** `sop_generation_workflow`  
**方針:** Option A — 既存 Workflow に第4フェーズとして追加

---

## 1. 概要

SOP 生成ワークフロー（3フェーズ: outline → draft → review）完了後、
生成物をルールベースで自動検証し、品質基準を満たさない場合は AI が自律的に修正を試みる。
最大3回の修正試行内で基準を満たせない場合は `ApplicationError(non_retryable=True)` で終了する。

---

## 2. アーキテクチャ全体像

```
sop_generation_workflow.run()
│
├─ [既存] Phase 1: outline
├─ [既存] Phase 2: draft
├─ [既存] Phase 3: review
│   └─ approved["review"] に最終 SOP が格納される
│
└─ [新規] Phase 4: autonomous_fix ループ
    │
    ├─ fix_attempt = 0
    ├─ while fix_attempt < MAX_FIX_ATTEMPTS (=3):
    │   │
    │   ├─ workflow.execute_activity(validate_sop_activity, sop_text)
    │   │   → ValidationResult(passed: bool, failures: list[str], score: dict)
    │   │
    │   ├─ if passed: break  ← 正常完了
    │   │
    │   ├─ workflow.execute_activity(fix_sop_activity, sop_text, failures)
    │   │   → LLMResult(text, tokens, latency_ms)
    │   │
    │   ├─ sop_text を更新、_history に記録
    │   └─ fix_attempt += 1
    │
    └─ fix_attempt == 3 かつ未通過
        → raise ApplicationError("自律修正失敗: 最大試行回数超過", non_retryable=True)
```

---

## 3. 新規コンポーネント

### 3-1. `ValidationResult` データクラス（`core/models.py` に追記）

```python
@dataclass
class ValidationResult:
    passed: bool
    failures: list[str]   # 失敗したルール名と理由の文字列
    score: dict           # {"word_count": 500, "section_count": 5, ...}
```

### 3-2. `validate_sop_activity`（新規: `activities/validate_sop_activity.py`）

ステートレスなルールベース検証。同一入力に対して常に同一結果を返す（冪等）。

**検証ルール（初期セット）:**

| ルール名 | 条件 | 失敗メッセージ例 |
| :--- | :--- | :--- |
| `min_word_count` | 文字数 ≥ 500 | `"文字数不足: 320文字 (最低500文字必要)"` |
| `required_sections` | `## ` 見出し ≥ 3個 | `"セクション数不足: 2個 (最低3個必要)"` |
| `has_code_block` | バッククォート3つのブロックが1個以上 | `"コードブロックが存在しない"` |
| `no_placeholder` | `TODO` / `TBD` / `[TODO]` を含まない | `"未完成プレースホルダーが含まれる"` |

**シグネチャ:**
```python
@activity.defn
async def validate_sop_activity(sop_text: str) -> ValidationResult:
    ...
```

### 3-3. `fix_sop_activity`（新規: `activities/fix_sop_activity.py`）

`failures` リストをプロンプトに注入し、Gemini 2.5 Flash に修正を依頼する。

```python
@activity.defn
async def fix_sop_activity(sop_text: str, failures: list[str]) -> LLMResult:
    ...
```

**system_instruction:** 品質改善担当ロール。`failures` を箇条書きで提示し、
最小限の変更で全指摘を解消した改善版 SOP を出力させる。

**タイムアウト:** `start_to_close_timeout=timedelta(seconds=180)`（既存 LLM Activity と統一）  
**リトライポリシー:** `LLM_RETRY_POLICY`（`core/retry_policy.py`）

---

## 4. `sop_generation_workflow.py` の変更詳細

### 追加インポート（`workflow.unsafe.imports_passed_through` ブロック内）

```python
from activities.validate_sop_activity import validate_sop_activity
from activities.fix_sop_activity import fix_sop_activity
```

### `ApplicationError` インポート

```python
from temporalio.exceptions import ApplicationError
```

### 定数追加

```python
MAX_FIX_ATTEMPTS = 3
```

### `__init__` に追加する状態変数

```python
self._fix_attempt: int = 0
self._validation_result: dict | None = None
```

### `get_status()` への追記

```python
"fix_attempt": self._fix_attempt,
"validation_result": self._validation_result,
```

### `run()` 末尾への追加（review フェーズ承認後）

```python
final_sop = self._approved["review"]

while self._fix_attempt < MAX_FIX_ATTEMPTS:
    self._status = "validating"
    v_result = await self._call_validate(final_sop)
    self._validation_result = {
        "passed": v_result.passed,
        "failures": v_result.failures,
        "score": v_result.score,
    }

    if v_result.passed:
        self._approved["review"] = final_sop  # 最終承認版を更新（return dict に自動反映）
        break

    self._status = "fixing"
    fix_result = await self._call_fix(final_sop, v_result.failures)
    final_sop = fix_result.text
    self._history.append({
        "phase": "autonomous_fix",
        "attempt": self._fix_attempt,
        "failures": v_result.failures,
        "output": fix_result.text,
        "tokens": fix_result.total_tokens,
        "latency_ms": fix_result.latency_ms,
        "approved": False,
    })
    self._fix_attempt += 1
else:
    raise ApplicationError(
        "自律修正失敗: 最大試行回数超過",
        non_retryable=True,
    )
```

### 新規プライベートメソッド

```python
async def _call_validate(self, sop_text: str) -> ValidationResult:
    return await workflow.execute_activity(
        validate_sop_activity,
        sop_text,
        start_to_close_timeout=timedelta(seconds=30),
    )

async def _call_fix(self, sop_text: str, failures: list[str]) -> LLMResult:
    return await workflow.execute_activity(
        fix_sop_activity,
        args=[sop_text, failures],
        start_to_close_timeout=timedelta(seconds=180),
        retry_policy=LLM_RETRY_POLICY,
    )
```

---

## 5. 変更ファイル一覧

| ファイル | 変更種別 | 内容 |
| :--- | :--- | :--- |
| `workflows/sop_workflow.py` | 修正 | Phase 4 ループ・状態変数・Query 更新・新規メソッド追加 |
| `activities/validate_sop_activity.py` | **新規** | ルールベース検証 Activity |
| `activities/fix_sop_activity.py` | **新規** | Gemini による自律修正 Activity |
| `core/models.py` | 修正 | `ValidationResult` データクラス追加 |
| `worker.py` | 修正 | `validate_sop_activity`・`fix_sop_activity` を登録 |

---

## 6. 監査チェックリスト（Pre-Implementation Audit）

### Temporal Resilience（決定論的保証）

| チェック項目 | 結果 |
| :--- | :--- |
| バリデーションロジックを Activity に閉じ込め、Workflow 内で直接評価しない | ✅ `validate_sop_activity` として隔離 |
| ループカウンタ `_fix_attempt` を Workflow インスタンス変数で管理 | ✅ Event History に記録→クラッシュ後も自動復元 |
| `datetime.now()` / `random` を Activity 外で使用しない | ✅ Workflow 内ではカウンタと条件分岐のみ |

### Idempotency（冪等性）

| チェック項目 | 結果 |
| :--- | :--- |
| `validate_sop_activity` は同一入力で常に同一出力（ステートレス純粋関数） | ✅ 外部状態を参照しない |
| `fix_sop_activity` のリトライで出力が変わる可能性を許容 | ✅ 外部 DB 書き込み等の副作用なし。結果差異は許容設計 |

### Error Handling（エラー区分）

| エラー種別 | 対処 |
| :--- | :--- |
| API キー欠落・不正引数 | `ApplicationError(non_retryable=True)` で即終了 |
| Gemini 一時障害 | `LLM_RETRY_POLICY` で自動リトライ |
| 最大試行回数超過 | `ApplicationError("自律修正失敗...", non_retryable=True)` |
| バリデーション Activity タイムアウト | `start_to_close_timeout=30s`（ルールベースなので軽量） |
| Fix Activity タイムアウト | `start_to_close_timeout=180s`（LLM 呼び出し標準値） |
