"""
LLM Observability — structlog を使った構造化JSONログ。

使い方:
    with log_llm_interaction(model, prompt) as result_box:
        result = call_llm(...)
        result_box.append(result)   # LLMResult を渡すとログが記録される
"""

import time
from contextlib import contextmanager
from typing import Generator, List

import structlog
from prometheus_client import Counter, Gauge, Histogram

from core.models import LLMResult

# --------------------------------------------------------------------------- #
# structlog 設定（JSON出力 / docker-compose logs で視認可能）                  #
# --------------------------------------------------------------------------- #

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(10),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger()

# --------------------------------------------------------------------------- #
# Prometheus メトリクス定義（モジュールロード時に一度だけ生成）                  #
# --------------------------------------------------------------------------- #

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total number of LLM tokens consumed",
    ["model", "type"],  # type: input | output
)

llm_inference_latency_seconds = Histogram(
    "llm_inference_latency_seconds",
    "LLM inference latency in seconds",
    ["model"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

# モデル別単価テーブル（USD / 1M tokens）
# 価格改定時はここだけ変更すれば PromQL 側は変更不要
_MODEL_PRICES_USD_PER_MILLION: dict[str, dict[str, float]] = {
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-2.0-flash": {"input": 0.10,  "output": 0.40},
    "mock-llm-v1":      {"input": 0.10,  "output": 0.10},  # デモ用仮単価
}

llm_price_per_million_tokens = Gauge(
    "llm_price_per_million_tokens",
    "Price per million tokens in USD (model/type別単価テーブル)",
    ["model", "type"],
)

# モジュールロード時に単価を Gauge に書き込む（以降は参照のみ）
for _model, _prices in _MODEL_PRICES_USD_PER_MILLION.items():
    for _token_type, _price in _prices.items():
        llm_price_per_million_tokens.labels(model=_model, type=_token_type).set(_price)


# --------------------------------------------------------------------------- #
# コンテキストマネージャ                                                        #
# --------------------------------------------------------------------------- #

@contextmanager
def log_llm_interaction(
    model: str, prompt: str
) -> Generator[List[LLMResult], None, None]:
    """LLM 呼び出しをラップし、実行後に構造化 JSON ログを出力する。

    成功時: result_box に LLMResult を append する。
    失敗時: 例外を再送出しつつ error ログを出力する。

    Example:
        with log_llm_interaction(model, prompt) as result_box:
            result = call_llm(prompt)
            result_box.append(result)
    """
    start = time.monotonic()
    result_box: List[LLMResult] = []
    try:
        yield result_box
        latency_ms = (time.monotonic() - start) * 1000
        if result_box:
            r = result_box[0]
            # Prometheus メトリクス更新
            llm_tokens_total.labels(model=r.model, type="input").inc(r.input_tokens)
            llm_tokens_total.labels(model=r.model, type="output").inc(r.output_tokens)
            llm_inference_latency_seconds.labels(model=r.model).observe(latency_ms / 1000)

            logger.info(
                "llm_interaction",
                status="success",
                model=r.model,
                prompt_summary=prompt[:120] + ("…" if len(prompt) > 120 else ""),
                output_summary=r.text[:120] + ("…" if len(r.text) > 120 else ""),
                input_tokens=r.input_tokens,
                output_tokens=r.output_tokens,
                total_tokens=r.total_tokens,
                latency_ms=round(latency_ms, 2),
            )
    except Exception as exc:
        latency_ms = (time.monotonic() - start) * 1000
        logger.error(
            "llm_interaction",
            status="error",
            model=model,
            prompt_summary=prompt[:120] + ("…" if len(prompt) > 120 else ""),
            error=str(exc),
            latency_ms=round(latency_ms, 2),
        )
        raise
