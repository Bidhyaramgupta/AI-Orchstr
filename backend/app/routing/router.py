from __future__ import annotations
from dataclasses import dataclass
from typing import AsyncIterator, List, Optional, Dict, Any, Tuple

from fastapi import HTTPException

from app.schemas.chat import Message
from app.providers.registry import get_provider
from app.routing.catalog import CATALOG
from app.routing.circuit_breaker import breaker
from app.core.redis_client import get_redis
from app.ratelimit.limiter import reserve, raise_429

# MVP limits (tune later)
# rpm: requests per minute bucket => capacity=RPM, refill_per_sec=RPM/60, cost=1 per request
DEFAULT_RPM = 30

# tpm-like: "units" per minute (we’ll estimate tokens crudely later)
DEFAULT_UNITS_PER_MIN = 20000


@dataclass
class Attempt:
    provider: str
    model: str


def build_plan(
    preference: str,
    provider_allowlist: Optional[List[str]] = None,
) -> List[Attempt]:
    if preference not in CATALOG:
        preference = "best"

    attempts = [Attempt(p, m) for (p, m) in CATALOG[preference]]

    if provider_allowlist:
        allow = set(provider_allowlist)
        attempts = [a for a in attempts if a.provider in allow]

    return attempts


def pick_key(api_keys: Dict[str, str], provider: str) -> str:
    key = api_keys.get(provider)
    if not key:
        raise HTTPException(status_code=400, detail=f"Missing api_keys['{provider}']")
    return key


async def run_with_fallback(
    *,
    api_keys: Dict[str, str],
    messages: List[Message],
    preference: str,
    provider_allowlist: Optional[List[str]] = None,
    timeout_s: float = 30.0,
    extra: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str, str]:
    """
    Returns (provider, model, output_text)
    """
    plan = build_plan(preference, provider_allowlist)
    if not plan:
        raise HTTPException(status_code=400, detail="No providers available after allowlist filtering")

    last_err = None

    for attempt in plan:
        if not breaker.allow(attempt.provider, attempt.model):
            continue

        prov = get_provider(attempt.provider)
        key = pick_key(api_keys, attempt.provider)

        r = await get_redis()

        # Identify user. For MVP use a deterministic string.
        # Later: real user_id from auth.
        user_key = "anon"  # replace later

        # 1) requests/minute limit
        rpm_res = await reserve(
            r,
            user_key=user_key,
            provider=attempt.provider,
            model=attempt.model,
            kind="rpm",
            capacity=DEFAULT_RPM,
            refill_per_sec=DEFAULT_RPM / 60.0,
            cost=1,
        )
        if not rpm_res.allowed:
            raise_429(rpm_res, "rpm")

        # 2) units/minute limit (token-like). MVP: use a rough estimate.
        # For now charge a fixed cost per request (you can improve next).
        unit_cost = 1000

        tpm_res = await reserve(
            r,
            user_key=user_key,
            provider=attempt.provider,
            model=attempt.model,
            kind="units",
            capacity=DEFAULT_UNITS_PER_MIN,
            refill_per_sec=DEFAULT_UNITS_PER_MIN / 60.0,
            cost=unit_cost,
        )
        if not tpm_res.allowed:
            raise_429(tpm_res, "units")

        try:
            res = await prov.chat(
                api_key=key,
                model=attempt.model,
                messages=messages,
                timeout_s=timeout_s,
                extra=extra,
            )
            breaker.record_success(attempt.provider, attempt.model)
            return res["provider"], res["model"], res["output_text"]
        except Exception as e:
            breaker.record_failure(attempt.provider, attempt.model)
            last_err = e
            continue

    raise HTTPException(status_code=502, detail=f"All providers failed. Last error: {type(last_err).__name__}")


async def stream_with_fallback(
    *,
    api_keys: Dict[str, str],
    messages: List[Message],
    preference: str,
    provider_allowlist: Optional[List[str]] = None,
    timeout_s: float = 30.0,
    extra: Optional[Dict[str, Any]] = None,
) -> AsyncIterator[dict]:
    """
    Streams normalized events:
    meta, token, switch, error, done
    """
    plan = build_plan(preference, provider_allowlist)
    if not plan:
        yield {"event": "error", "data": "No providers available after allowlist filtering"}
        yield {"event": "done", "data": ""}
        return

    for idx, attempt in enumerate(plan):
        if not breaker.allow(attempt.provider, attempt.model):
            continue

        prov = get_provider(attempt.provider)
        try:
            key = pick_key(api_keys, attempt.provider)
            r = await get_redis()

            # Identify user. For MVP use a deterministic string.
            # Later: real user_id from auth.
            user_key = "anon"  # replace later

            # 1) requests/minute limit
            rpm_res = await reserve(
                r,
                user_key=user_key,
                provider=attempt.provider,
                model=attempt.model,
                kind="rpm",
                capacity=DEFAULT_RPM,
                refill_per_sec=DEFAULT_RPM / 60.0,
                cost=1,
            )
            if not rpm_res.allowed:
                raise_429(rpm_res, "rpm")

            # 2) units/minute limit (token-like). MVP: use a rough estimate.
            # For now charge a fixed cost per request (you can improve next).
            unit_cost = 1000

            tpm_res = await reserve(
                r,
                user_key=user_key,
                provider=attempt.provider,
                model=attempt.model,
                kind="units",
                capacity=DEFAULT_UNITS_PER_MIN,
                refill_per_sec=DEFAULT_UNITS_PER_MIN / 60.0,
                cost=unit_cost,
            )
            if not tpm_res.allowed:
                raise_429(tpm_res, "units")
        except HTTPException as he:
            # Missing key: treat as “skip provider” not “system failure”
            continue

        # Tell client when we begin or switch providers
        yield {"event": "switch" if idx > 0 else "meta",
               "data": f'{{"provider":"{attempt.provider}","model":"{attempt.model}"}}'}

        try:
            async for tok in prov.stream_chat(
                api_key=key,
                model=attempt.model,
                messages=messages,
                timeout_s=timeout_s,
                extra=extra,
            ):
                yield {"event": "token", "data": tok}

            breaker.record_success(attempt.provider, attempt.model)
            yield {"event": "done", "data": ""}
            return
        except Exception as e:
            breaker.record_failure(attempt.provider, attempt.model)
            yield {"event": "error", "data": f"{attempt.provider}:{attempt.model}:{type(e).__name__}"}
            # continue to next fallback

    yield {"event": "error", "data": "All providers failed"}
    yield {"event": "done", "data": ""}