import logging
import socket

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPSConnection
from urllib3.connectionpool import HTTPSConnectionPool
from urllib3.exceptions import ConnectTimeoutError, NameResolutionError, NewConnectionError
from urllib3.util import connection as urllib3_connection

from clinics.ai_provider_validation import is_ai_provider_resolved_address_safe, validate_ai_provider_base_url


logger = logging.getLogger(__name__)


class AIProviderError(Exception):
    pass


def _create_safe_provider_connection(
    address,
    timeout=urllib3_connection._DEFAULT_TIMEOUT,
    source_address=None,
    socket_options=None,
):
    host, port = address
    if host.startswith("["):
        host = host.strip("[]")
    provider_request_failed = False
    try:
        host.encode("idna")
    except UnicodeError:
        raise OSError("AI provider host is invalid") from None

    results = socket.getaddrinfo(host, port, urllib3_connection.allowed_gai_family(), socket.SOCK_STREAM)
    if not results:
        raise OSError("getaddrinfo returns an empty list")
    for result in results:
        if not is_ai_provider_resolved_address_safe(result[4][0]):
            raise OSError("AI provider resolved to an unsafe address")

    err = None
    for result in results:
        address_family, socktype, proto, _canonname, socket_address = result
        sock = None
        try:
            sock = socket.socket(address_family, socktype, proto)
            urllib3_connection._set_socket_options(sock, socket_options)
            if timeout is not urllib3_connection._DEFAULT_TIMEOUT:
                sock.settimeout(timeout)
            if source_address:
                sock.bind(source_address)
            sock.connect(socket_address)
            err = None
            return sock
        except OSError as exc:
            err = exc
            if sock is not None:
                sock.close()

    if err is not None:
        raise err
    raise OSError("getaddrinfo returns an empty list")


class _SafeAIProviderHTTPSConnection(HTTPSConnection):
    def _new_conn(self):
        try:
            sock = _create_safe_provider_connection(
                (self._dns_host, self.port),
                self.timeout,
                source_address=self.source_address,
                socket_options=self.socket_options,
            )
        except socket.gaierror as exc:
            raise NameResolutionError(self.host, self, exc) from exc
        except socket.timeout as exc:
            raise ConnectTimeoutError(self, f"Connection to {self.host} timed out. (connect timeout={self.timeout})") from exc
        except OSError as exc:
            raise NewConnectionError(self, f"Failed to establish a new connection: {exc}") from exc
        return sock


class _SafeAIProviderHTTPSConnectionPool(HTTPSConnectionPool):
    ConnectionCls = _SafeAIProviderHTTPSConnection


class _SafeAIProviderHTTPAdapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)
        self.poolmanager.pool_classes_by_scheme = self.poolmanager.pool_classes_by_scheme.copy()
        self.poolmanager.pool_classes_by_scheme["https"] = _SafeAIProviderHTTPSConnectionPool


def _create_ai_provider_session():
    session = requests.Session()
    session.trust_env = False
    session.mount("https://", _SafeAIProviderHTTPAdapter())
    return session


def _chat_completions_url(provider_settings):
    base_url = validate_ai_provider_base_url(provider_settings.base_url)
    return f"{base_url}/chat/completions"


def call_chat_completion(provider_settings, messages, tools=None, model=None, model_role="primary"):
    selected_model = (model or provider_settings.model or "").strip()
    payload = {
        "model": selected_model,
        "messages": messages,
        "temperature": 0.2,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    try:
        with _create_ai_provider_session() as session:
            response = session.post(
                _chat_completions_url(provider_settings),
                headers={
                    "Authorization": f"Bearer {provider_settings.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=getattr(settings, "AI_PROVIDER_TIMEOUT_SECONDS", 20),
                allow_redirects=False,
            )
        if 300 <= response.status_code < 400:
            raise requests.RequestException("AI provider redirect response.")
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") if isinstance(data, dict) else None
        message = choices[0].get("message") if choices and isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            raise AIProviderError("AI provider returned an invalid response.")
        return message
    except AIProviderError:
        raise
    except (requests.RequestException, ValidationError, ValueError, KeyError, IndexError, TypeError):
        logger.warning(
            "AI provider request failed",
            extra={
                "clinic_id": provider_settings.clinic_id,
                "model_role": model_role,
            },
        )
        provider_request_failed = True
    if provider_request_failed:
        raise AIProviderError("AI provider request failed.")
