"""Small OpenAI-compatible Chat Completions client used by the map agent."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

try:
    from .config import Config
    from .errors import ServiceError
except ImportError:  # Supports `python server.py` from the backend directory.
    from config import Config
    from errors import ServiceError


class OpenAIChatClient:
    """Calls an OpenAI-compatible /chat/completions endpoint without exposing secrets."""

    def __init__(self, config: Config, policy_gate=None, credentials=None) -> None:
        self.config = config
        self.policy_gate = policy_gate
        self.credentials = credentials

    @property
    def available(self) -> bool:
        if self.policy_gate:
            try:
                self.policy_gate()
            except ServiceError:
                return False
            key = self.config.openai_api_key or (self.credentials() if self.credentials else {}).get('api_key', '')
            return bool(self.config.openai_base_url and key and self.config.model_name)
        return self.config.agent_available

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.available:
            raise ServiceError("AI map configuration is incomplete.", 503)
        if self.policy_gate:
            self.policy_gate()
        api_key = self.config.openai_api_key or (self.credentials() if self.credentials else {}).get('api_key', '')
        base_url = self.config.openai_base_url
        endpoint = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
        payload = {
            "model": self.config.model_name,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
        }
        if self.config.agent_temperature is not None:
            payload["temperature"] = self.config.agent_temperature
        if self.config.agent_max_tokens:
            # Azure reasoning deployments commonly reject `max_tokens`; only
            # send their modern completion limit when an operator opts in.
            payload["max_completion_tokens"] = self.config.agent_max_tokens
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if len(body) > 512_000:
            raise ServiceError("The map-agent request is too large.", 413)
        request = urllib.request.Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        token = None
        quota = None
        try:
            if self.policy_gate:
                from backend.providers.transport import HTTPSPinnedTransport, Request
                from backend.providers.quota import QuotaRule
                from backend.server import service_foundation
                state = self.policy_gate()
                limit = min(20, int(state.get('limits', {}).get('requests_day', 20)))
                if limit < 1:
                    raise ServiceError('Local inference quota exhausted.', 429)
                quota = service_foundation()[1].quota
                token = quota.reserve('openai.api', 'local', (QuotaRule(limit=limit, calendar='day'),))
                raw = HTTPSPinnedTransport().fetch(Request(endpoint, 'https://api.openai.com',
                    headers=(('Authorization', f'Bearer {api_key}'), ('Content-Type', 'application/json')),
                    method='POST', body=body, max_decompressed=2_000_000, timeout=45))
                quota.finish(token)
                token = None
            else:
                with urllib.request.urlopen(request, timeout=45) as response:
                    raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ServiceError('The AI map response exceeded its size limit.', 502)
        except urllib.error.HTTPError as error:
            detail = self._error_detail(error)
            if error.code == 429:
                raise ServiceError(f"The AI map provider is busy{detail}. Try again shortly.", 503, 15) from error
            if error.code in {401, 403}:
                raise ServiceError(f"The AI map provider rejected the configured credentials{detail}.", 503) from error
            raise ServiceError(f"The AI map provider rejected the request (HTTP {error.code}){detail}.", 503) from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise ServiceError("The AI map provider is unavailable.", 503) from error
        finally:
            if token is not None and quota is not None:
                quota.finish(token, ambiguous=True)
        try:
            response = json.loads(raw.decode("utf-8"))
            message = response["choices"][0]["message"]
        except (KeyError, TypeError, IndexError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ServiceError("The AI map provider returned an invalid response.", 503) from error
        if not isinstance(message, dict):
            raise ServiceError("The AI map provider returned an invalid response.", 503)
        return message

    def _error_detail(self, error: urllib.error.HTTPError) -> str:
        """Extract a small, credential-redacted provider explanation for the local UI."""
        try:
            raw = error.read(16_384).decode("utf-8", errors="replace")
            payload = json.loads(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return ""
        value: Any = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(value, dict):
            value = value.get("message") or value.get("detail") or value.get("error")
        if value is None and isinstance(payload, dict):
            value = payload.get("message") or payload.get("detail")
        if not isinstance(value, str):
            return ""
        message = " ".join(value.split())
        if self.config.openai_api_key:
            message = message.replace(self.config.openai_api_key, "[redacted]")
        return f": {message[:280]}" if message else ""
