"""
テスト共通設定 — オプション依存パッケージのモック注入。

ローカル環境に未インストールのパッケージを sys.modules へモックとして登録する。
パッケージが実際にインストール済みの場合は try/except により実物を使う。
"""

import sys
from unittest.mock import MagicMock


try:
    import prometheus_client  # noqa: F401
except ImportError:
    sys.modules["prometheus_client"] = MagicMock()


try:
    import google.genai  # noqa: F401
except ImportError:
    _mock_genai = MagicMock()
    sys.modules["google.genai"] = _mock_genai
    sys.modules["google.genai.types"] = MagicMock()
    import google
    google.genai = _mock_genai  # from google import genai が解決できるよう注入
