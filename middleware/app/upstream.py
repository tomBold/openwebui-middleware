from typing import Any

import httpx


class UpstreamError(Exception):
    def __init__(self, status_code: int, message: str, error_type: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.error_type = error_type

    @classmethod
    def from_transport(cls, exc: httpx.HTTPError) -> "UpstreamError":
        if isinstance(exc, httpx.TimeoutException):
            return cls(504, "Upstream request timed out", "upstream_timeout")
        return cls(502, f"Upstream request failed: {exc!r}", "upstream_unavailable")

    @classmethod
    def from_response(cls, response: httpx.Response) -> "UpstreamError":
        try:
            detail = response.json()["error"]
            message, error_type = detail["message"], detail.get("type", "upstream_error")
        except (ValueError, KeyError, TypeError):
            message, error_type = response.text, "upstream_error"
        return cls(response.status_code, message, error_type)


class OpenAIUpstream:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def list_models(self, timeout_s: float | None = None) -> list[dict[str, Any]]:
        options: dict[str, Any] = {"timeout": timeout_s} if timeout_s else {}
        response = await self._request("GET", "/models", **options)
        data: list[dict[str, Any]] = response.json()["data"]
        return data

    async def chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._request("POST", "/chat/completions", json=payload)
        completion: dict[str, Any] = response.json()
        return completion

    async def open_chat_stream(self, payload: dict[str, Any]) -> httpx.Response:
        request = self._client.build_request("POST", "/chat/completions", json=payload)
        try:
            response = await self._client.send(request, stream=True)
        except httpx.HTTPError as exc:
            raise UpstreamError.from_transport(exc) from exc
        if response.is_error:
            await response.aread()
            await response.aclose()
            raise UpstreamError.from_response(response)
        return response

    async def _request(self, method: str, path: str, **options: Any) -> httpx.Response:  # noqa: ANN401
        try:
            response = await self._client.request(method, path, **options)
        except httpx.HTTPError as exc:
            raise UpstreamError.from_transport(exc) from exc
        if response.is_error:
            raise UpstreamError.from_response(response)
        return response
