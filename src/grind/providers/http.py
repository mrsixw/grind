"""The base class for providers that talk to an HTTP API."""

import os

import requests

from ..constants import HTTP_TIMEOUT_SECONDS, USER_AGENT
from ..logger import logger
from .base import Provider, ProviderError

__all__ = [
    "HttpProvider",
]


class HttpProvider(Provider):
    """Base class for anything with an HTTP API — which is nearly everything.

    Handles the parts every HTTP ticket system shares: the base URL, reading
    the token from the environment (never from the config file), timeouts,
    request counting, and turning transport and status failures into
    :class:`ProviderError` with a message a person can act on.

    Subclasses usually set :attr:`default_url` and :attr:`default_token_env`,
    and override :meth:`auth` when a bearer token is not what the API wants.
    """

    #: Used when the source config has no ``url``. Empty means url is required.
    default_url = ""
    #: Environment variables to try for the token when ``token-env`` is unset.
    default_token_env: tuple[str, ...] = ()

    def __init__(self, source: str, config: dict):
        super().__init__(source, config)
        self.base_url = str(config.get("url") or self.default_url).rstrip("/")
        if not self.base_url:
            raise ProviderError(
                f"Source '{source}' is missing 'url' in its config "
                f"([sources.{source}])."
            )
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT

    def token(self) -> str:
        """Return the API token from the environment.

        ``token-env`` in the source config names the variable; otherwise the
        provider's defaults are tried in order. Tokens are never read from the
        config file, so a config is always safe to commit or paste.
        """
        configured = self.config.get("token-env")
        names = (str(configured),) if configured else self.default_token_env
        for name in names:
            value = os.environ.get(name)
            if value:
                return value
        wanted = " or ".join(names) if names else "a 'token-env' variable"
        raise ProviderError(
            f"No token for source '{self.source}'. Set {wanted} in your environment."
        )

    def auth(self):
        """Return the ``requests`` auth for a call. Default: a bearer token."""
        token = self.token()

        def bearer(request):
            request.headers["Authorization"] = f"Bearer {token}"
            return request

        return bearer

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Make one authenticated call and return the successful response.

        *path* is joined onto the base URL unless it is already absolute,
        which lets pagination follow the links an API hands back.
        """
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        self.request_count += 1
        logger.debug("request source=%s %s %s", self.source, method, url)
        try:
            response = self.session.request(
                method,
                url,
                auth=self.auth(),
                timeout=HTTP_TIMEOUT_SECONDS,
                **kwargs,
            )
        except requests.exceptions.RequestException as exc:
            raise ProviderError(
                f"Could not reach source '{self.source}' at {self.base_url}: {exc}"
            ) from exc
        if response.status_code >= 400:
            raise ProviderError(self.describe_failure(response))
        return response

    def describe_failure(self, response: requests.Response) -> str:
        """Turn an error response into a one-line explanation."""
        code = response.status_code
        prefix = f"Source '{self.source}' answered {code}"
        if code == 401:
            return f"{prefix}: the token was rejected. Check it has not expired."
        if code == 403:
            return f"{prefix}: the token is not allowed to do that."
        if code == 404:
            return f"{prefix}: not found (or not visible to this token)."
        detail = self.error_detail(response)
        return f"{prefix}: {detail}" if detail else f"{prefix}."

    def error_detail(self, response: requests.Response) -> str:
        """Extract the API's own error text. Override for richer messages."""
        return response.text.strip()[:200]
