# 計画: conftest.py によるライブラリモック + グローバルルール化

## Context
ローカル環境に `prometheus_client` / `google-genai` が未インストールのため
`test_observability.py`（4件）と `test_fix_sop_activity.py`（5件）の計 9 件が実行不可だった。
テストファイルを除外するのではなく、`tests/conftest.py` で `sys.modules` にモックを注入し、
全 40 件をローカルで Green にする。
あわせてこの対処をグローバルルール（`~/.claude/CLAUDE.md`）に追記する。

---

## 問題の構造

| ファイル | 失敗原因 | インポート箇所 |
|---|---|---|
| `test_observability.py` | `prometheus_client` 未インストール | `core/observability.py` の**モジュールレベル** |
| `test_fix_sop_activity.py` | `google.genai` 未インストール | `fix_sop_activity` の**関数内** |

---

## 変更ファイル一覧

| ファイル | 操作 | 概要 |
|---|---|---|
| `tests/conftest.py` | **新規作成** | 未インストールパッケージを try/except で sys.modules にモック注入 |
| `~/.claude/CLAUDE.md` | **修正** | 未インストールライブラリのテスト対処ルールを追記 |

---

## `tests/conftest.py` の実装

```python
import sys
from unittest.mock import MagicMock

try:
    import prometheus_client
except ImportError:
    sys.modules["prometheus_client"] = MagicMock()

try:
    import google.genai
except ImportError:
    _mock_genai = MagicMock()
    sys.modules["google.genai"] = _mock_genai
    sys.modules["google.genai.types"] = MagicMock()
    import google
    google.genai = _mock_genai
```

`from google import genai` が解決できるよう `google` モジュールの属性にも注入する。

---

## 検証
```bash
pytest tests/ -v
```
40 passed（除外なし）になることを確認する。
