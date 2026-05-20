# 概要ドキュメント: conftest.py によるライブラリモック + グローバルルール化

**作成日:** 2026-05-20  
**タスク:** 未インストールライブラリ起因のテスト除外を廃止し、conftest.py モックで全 40 件 Green を達成

---

## A. System Interaction Flow

```
pytest tests/ 実行
    ↓ conftest.py が最初に読み込まれる（pytest の自動検出）
    ↓ try/except で prometheus_client が未インストールと判定
    ↓   sys.modules["prometheus_client"] = MagicMock()
    ↓ try/except で google.genai が未インストールと判定
    ↓   sys.modules["google.genai"] = MagicMock()
    ↓   google.genai = MagicMock()  （属性注入）
    ↓
test_observability.py
    ↓ from core.observability import log_llm_interaction
    ↓   core/observability.py: from prometheus_client import Counter ...
    ↓   → sys.modules から MagicMock を取得 → インポート成功
    ↓ 4 件すべて PASSED

test_fix_sop_activity.py
    ↓ fix_sop_activity() 呼び出し時に from google import genai
    ↓   → google.genai 属性が MagicMock → インポート成功
    ↓   patch("google.genai.Client") が MagicMock 上で動作
    ↓ 5 件すべて PASSED
```

---

## B. Responsibility Matrix

| ファイルパス | 変更箇所 | 処理の目的・役割 | 相互作用する相手 |
| :--- | :--- | :--- | :--- |
| `tests/conftest.py` | 新規作成 | 未インストールパッケージを sys.modules にモック注入。インストール済みなら実物を使う | `test_observability.py`, `test_fix_sop_activity.py` |
| `~/.claude/CLAUDE.md` | `Test Dependency Mocking` セクション追記 | 未インストールライブラリに対するテスト対処ルールをグローバル化 | 全プロジェクトのテスト作成時 |

---

## C. 設計の意図とクリティカルポイント

### なぜ conftest.py か
pytest は `conftest.py` をテスト収集前に自動実行する。`sys.modules` への注入がここで行われることで、どのテストファイルがインポートされる前にもモックが確実に適用される。

### クリティカルポイント（最大3点）

1. **`google.genai` は sys.modules だけでは不足** — `from google import genai` は `sys.modules["google.genai"]` だけでなく `google` モジュールオブジェクトの `.genai` 属性も参照する。`google.genai = _mock_genai` の属性注入が必須。

2. **try/except で実物優先** — `prometheus_client` や `google-genai` が Docker 環境や CI でインストール済みの場合は実物を使う。conftest.py はローカル環境の差を吸収するためのものであり、常にモックで上書きすることは避ける。

3. **テストファイルの除外（--ignore）は禁止** — 除外は「動かない理由を隠す」だけで、テストカバレッジの実態を歪める。グローバルルールとして CLAUDE.md に明記した。

---

## テスト結果

```
40 passed（除外なし）
内訳:
  test_fix_sop_activity.py  : 5 passed（旧: 3 failed / 収集エラー）
  test_observability.py     : 4 passed（旧: 収集エラー）
  test_github_activity.py   : 12 passed
  test_models.py            : 7 passed
  test_validate_sop_activity.py : 12 passed
```
