"""
共通 RetryPolicy 定義。どの Workflow からも import して使う。
"""

from datetime import timedelta

from temporalio.common import RetryPolicy

# LLM 呼び出し向け: 最大3回、指数バックオフ
LLM_RETRY_POLICY = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
)
