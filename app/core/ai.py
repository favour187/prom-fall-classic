"""AI integration layer.

A single `AIGateway` gives every competition feature one consistent way to
call an LLM:

- **Remote:** any OpenAI-compatible chat-completions API (config via
  `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL`). Built on `httpx`, retries with
  backoff.
- **Local fallback:** deterministic, dependency-free response generators that
  let the whole product run and be demoed with **zero API key**.
- **Auto mode:** remote when configured, otherwise local — and if a remote
  call fails mid-demo, it degrades gracefully to the local generator instead
  of breaking the user's flow.
- Results are cached briefly (per prompt) to keep demo costs and latency low.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence

import httpx

from .config import Settings
from .errors import ServiceUnavailableError
from .logging import get_logger

logger = get_logger("app.ai")


# --------------------------------------------------------------------------
# Types
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class AIMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True, slots=True)
class AIResult:
    text: str
    provider: str
    used_fallback: bool
    latency_ms: float
    cached: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "provider": self.provider,
            "used_fallback": self.used_fallback,
            "latency_ms": round(self.latency_ms, 1),
            "cached": self.cached,
        }


class AIProvider(Protocol):
    name: str

    def complete(
        self,
        messages: Sequence[AIMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str: ...


# --------------------------------------------------------------------------
# Remote provider (OpenAI-compatible)
# --------------------------------------------------------------------------
class OpenAICompatibleProvider:
    name = "openai-compatible"

    def __init__(self, base_url: str, api_key: str, model: str, *, timeout: float, max_retries: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    def complete(
        self,
        messages: Sequence[AIMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        url = f"{self.base_url}/chat/completions"

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(url, json=payload, headers=headers)
                if response.status_code == 429 or response.status_code >= 500:
                    last_error = ServiceUnavailableError(
                        "AI service is busy.",
                        code="ai_unavailable",
                        status_code=503,
                        details={"status_code": response.status_code},
                    )
                    time.sleep(0.5 * (2**attempt))  # simple backoff
                    continue
                if response.status_code >= 400:
                    raise ServiceUnavailableError(
                        "AI service rejected the request.",
                        code="ai_error",
                        details={"status_code": response.status_code},
                    )
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise ServiceUnavailableError(
                        "AI service returned an empty response.", code="ai_empty_response"
                    )
                return content.strip()
            except httpx.HTTPError as exc:
                last_error = ServiceUnavailableError(
                    "Could not reach the AI service.",
                    code="ai_unreachable",
                    details={"error": type(exc).__name__},
                )
                time.sleep(0.5 * (2**attempt))
        assert last_error is not None
        raise last_error


# --------------------------------------------------------------------------
# Local demo provider (deterministic, no key required)
# --------------------------------------------------------------------------
class LocalSkill(Protocol):
    id: str

    def can_handle(self, user_text: str, system: str) -> bool: ...

    def respond(self, user_text: str, system: str, context: dict[str, Any] | None) -> str: ...


class _DefaultSkill:
    """Generic, honest fallback when no competition-specific skill matches."""

    id = "default"

    def can_handle(self, user_text: str, system: str) -> bool:
        return True

    def respond(self, user_text: str, system: str, context: dict[str, Any] | None) -> str:
        return (
            f"[Local demo mode — no AI_API_KEY configured, so this response is "
            f"generated by the built-in deterministic fallback. Configure "
            f"AI_BASE_URL / AI_API_KEY / AI_MODEL to enable the real LLM.]\n\n"
            f"Understood. Here is a concrete next step for: \"{user_text[:220]}\""
        )


class LocalDemoProvider:
    """Routes prompts to registered deterministic skills (per competition)."""

    name = "local-demo"

    def __init__(self, skills: Sequence[LocalSkill] | None = None) -> None:
        self.skills: list[LocalSkill] = list(skills or [])
        self.skills.append(_DefaultSkill())

    def register(self, skill: LocalSkill) -> None:
        self.skills.insert(0, skill)

    def complete(
        self,
        messages: Sequence[AIMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        system = next((m.content for m in messages if m.role == "system"), "")
        user = next((m.content for m in messages if m.role == "user"), "")
        context: dict[str, Any] = {"temperature": temperature, "max_tokens": max_tokens}
        for skill in self.skills:
            if skill.can_handle(user, system):
                try:
                    return skill.respond(user, system, context)
                except Exception:  # a broken skill must not take the app down
                    logger.exception("Local AI skill %s failed; falling back to default", skill.id)
                    continue
        return _DefaultSkill().respond(user, system, context)


# --------------------------------------------------------------------------
# Gateway
# --------------------------------------------------------------------------
@dataclass(slots=True)
class _CacheEntry:
    expires_at: float
    result: AIResult


class AIGateway:
    def __init__(
        self,
        settings: Settings,
        *,
        provider: AIProvider | None = None,
        local_skills: Sequence[LocalSkill] | None = None,
    ) -> None:
        self.settings = settings
        self._provider = provider
        self._local = LocalDemoProvider(local_skills or [])
        self._cache: dict[str, _CacheEntry] = {}
        # If a provider is injected (tests), respect it.
        if provider is not None and settings.ai_mode == "auto":
            self.settings = settings.with_overrides(ai_mode="remote")

    def register_local_skills(self, skills: Sequence[LocalSkill]) -> None:
        """Register domain-specific deterministic skills (per competition)."""
        for skill in skills:
            self._local.register(skill)

    # -- provider resolution -------------------------------------------
    def _remote_provider(self) -> OpenAICompatibleProvider:
        if not self.settings.ai_api_key:
            raise ServiceUnavailableError(
                "Remote AI is not configured (AI_API_KEY is empty).",
                code="ai_not_configured",
            )
        return OpenAICompatibleProvider(
            self.settings.ai_base_url,
            self.settings.ai_api_key,
            self.settings.ai_model,
            timeout=self.settings.ai_timeout_seconds,
            max_retries=self.settings.ai_max_retries,
        )

    @property
    def provider_name(self) -> str:
        return self._resolve_provider().name

    def _resolve_provider(self) -> AIProvider:
        if self._provider is not None:
            return self._provider
        mode = self.settings.ai_mode
        if mode == "local":
            return self._local
        if mode == "remote":
            return self._remote_provider()
        # auto
        if self.settings.ai_remote_configured:
            return self._remote_provider()
        return self._local

    # -- main entry point ----------------------------------------------
    def chat(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        cache_key: str | None = None,
    ) -> AIResult:
        messages = [AIMessage(role="system", content=system), AIMessage(role="user", content=user)]
        key = cache_key or self._cache_key(system, user, temperature, max_tokens)

        cached = self._cache_get(key)
        if cached is not None:
            from dataclasses import replace

            return replace(cached, cached=True)

        started = time.monotonic()
        try:
            provider = self._resolve_provider()
            text = provider.complete(messages, temperature=temperature, max_tokens=max_tokens)
            result = AIResult(
                text=text,
                provider=provider.name,
                used_fallback=provider.name == "local-demo",
                latency_ms=(time.monotonic() - started) * 1000,
            )
        except ServiceUnavailableError as exc:
            if self.settings.ai_mode == "auto" and self._provider is None:
                logger.warning("Remote AI unavailable (%s); using local fallback.", exc.code)
                text = self._local.complete(messages, temperature=temperature, max_tokens=max_tokens)
                result = AIResult(
                    text=text,
                    provider="local-demo",
                    used_fallback=True,
                    latency_ms=(time.monotonic() - started) * 1000,
                )
            else:
                raise

        self._cache_set(key, result)
        return result

    def _cache_key(self, system: str, user: str, temperature: float, max_tokens: int) -> str:
        digest = hashlib.sha256(
            f"{self.provider_name}|{system}|{user}|{temperature}|{max_tokens}".encode("utf-8")
        ).hexdigest()
        return digest

    def _cache_get(self, key: str) -> AIResult | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        if entry.expires_at < time.monotonic():
            self._cache.pop(key, None)
            return None
        return entry.result

    def _cache_set(self, key: str, result: AIResult) -> None:
        ttl = max(0.0, self.settings.ai_cache_ttl_seconds)
        self._cache[key] = _CacheEntry(time.monotonic() + ttl, result)
        if len(self._cache) > self.settings.ai_cache_max_entries:
            oldest = sorted(self._cache.items(), key=lambda kv: kv[1].expires_at)[0]
            self._cache.pop(oldest[0], None)

    def status(self) -> dict[str, Any]:
        backend = "local" if not self.settings.ai_remote_configured else self.settings.ai_mode
        return {"mode": self.settings.ai_mode, "backend": backend, "model": self.settings.ai_model}


# --------------------------------------------------------------------------
# Module-level singleton bound to the app (set by app factory)
# --------------------------------------------------------------------------
_shared_gateway: AIGateway | None = None


def install_gateway(settings: Settings, *, local_skills: Sequence[LocalSkill] | None = None) -> None:
    global _shared_gateway
    _shared_gateway = AIGateway(settings, local_skills=local_skills)


def get_gateway() -> AIGateway:
    if _shared_gateway is None:  # pragma: no cover - defensive
        install_gateway(Settings())
    return _shared_gateway
