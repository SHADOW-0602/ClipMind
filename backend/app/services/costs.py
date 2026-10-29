from __future__ import annotations

import contextvars
import logging
from dataclasses import dataclass

from sqlalchemy import func
from sqlmodel import Session, select

from ..config import get_settings
from ..db import get_engine
from ..models import AsrCall, ModelCall

logger = logging.getLogger(__name__)

current_job_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "clipmind_current_job", default=None
)


class BudgetExceeded(RuntimeError):
    pass


@dataclass(slots=True)
class TokenCost:
    input_tokens: int
    cached_tokens: int
    output_tokens: int
    cost_usd: float


def token_cost(input_tokens: int, cached_tokens: int, output_tokens: int, *, model: str = "") -> TokenCost:
    settings = get_settings()
    cached_tokens = max(0, min(cached_tokens, input_tokens))
    uncached = max(0, input_tokens - cached_tokens)
    cost = (
        uncached * settings.active_input_price_per_m
        + cached_tokens * settings.active_cached_input_price_per_m
        + output_tokens * settings.active_output_price_per_m
    ) / 1_000_000
    return TokenCost(input_tokens, cached_tokens, output_tokens, round(cost, 8))


def spent_usd() -> float:
    with Session(get_engine()) as session:
        model_cost = session.exec(select(func.coalesce(func.sum(ModelCall.cost_usd), 0.0))).one()
        asr_cost = session.exec(select(func.coalesce(func.sum(AsrCall.cost_usd), 0.0))).one()
    return float(model_cost or 0.0) + float(asr_cost or 0.0)


def ensure_budget(estimated_next_usd: float = 0.0) -> None:
    settings = get_settings()
    total = spent_usd()
    if total + estimated_next_usd > settings.max_budget_usd:
        raise BudgetExceeded(
            f"Budget guard tripped: ${total:.2f} spent, ${estimated_next_usd:.2f} estimated, "
            f"limit ${settings.max_budget_usd:.2f}. Raise MAX_BUDGET_USD or switch to a free "
            "provider preset such as groq, gemini, openrouter, or ollama."
        )


def log_model_call(
    *,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int,
    cost_usd: float,
    latency_ms: int,
    purpose: str,
    cache_hit: bool = False,
    job_id: str | None = None,
) -> None:
    job = job_id or current_job_id.get()
    with Session(get_engine()) as session:
        call = ModelCall(
            job_id=job,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            purpose=purpose,
            cache_hit=cache_hit,
        )
        session.add(call)
        session.commit()
    logger.info(
        "model_call provider=%s model=%s purpose=%s in=%d out=%d cost=$%.6f latency=%dms cache=%s",
        provider,
        model,
        purpose,
        input_tokens,
        output_tokens,
        cost_usd,
        latency_ms,
        cache_hit,
    )


def log_asr_call(
    *,
    model: str,
    audio_seconds: float,
    latency_ms: int,
    usd_per_hour: float | None = None,
    job_id: str | None = None,
) -> float:
    settings = get_settings()
    rate = settings.active_asr_usd_per_hour if usd_per_hour is None else usd_per_hour
    cost = round(audio_seconds / 3600 * rate, 8)
    job = job_id or current_job_id.get()
    with Session(get_engine()) as session:
        session.add(
            AsrCall(
                job_id=job,
                model=model,
                audio_seconds=audio_seconds,
                cost_usd=cost,
                latency_ms=latency_ms,
            )
        )
        session.commit()
    return cost


def usage_totals() -> dict[str, float | int]:
    settings = get_settings()
    with Session(get_engine()) as session:
        calls = session.exec(select(ModelCall)).all()
        asr_calls = session.exec(select(AsrCall)).all()
        input_tokens = sum(call.input_tokens for call in calls)
        output_tokens = sum(call.output_tokens for call in calls)
        cached_tokens = sum(call.cached_tokens for call in calls)
        model_cost = sum(call.cost_usd for call in calls)
        asr_cost = sum(call.cost_usd for call in asr_calls)
    total = model_cost + asr_cost
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_tokens": cached_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cost_usd": round(model_cost, 6),
        "asr_cost_usd": round(asr_cost, 6),
        "total_cost_usd": round(total, 6),
        "budget_usd": settings.max_budget_usd,
        "remaining_usd": round(max(0.0, settings.max_budget_usd - total), 6),
        "credits_remaining_usd": round(max(0.0, settings.hackathon_credits_usd - total), 6),
        "calls": len(calls) + len(asr_calls),
    }
