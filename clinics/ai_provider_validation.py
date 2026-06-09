import ipaddress
import socket
from urllib.parse import urlparse

from django.core.exceptions import ValidationError


def _host_resolves_to_unsafe_address(host):
    try:
        results = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError):
        return True
    for result in results:
        address_text = result[4][0]
        try:
            address = ipaddress.ip_address(address_text)
        except ValueError:
            return True
        if not is_ai_provider_resolved_address_safe(address_text):
            return True
    return False


def is_ai_provider_resolved_address_safe(address_text):
    try:
        address = ipaddress.ip_address(address_text)
    except ValueError:
        return False
    return not address.is_multicast and address.is_global


def _unsafe_provider_host(hostname):
    host = (hostname or "").strip().lower().rstrip(".")
    if not host:
        return True
    if host in {"localhost", "internal", "0", "0.0.0.0"}:
        return True
    if host.endswith((".localhost", ".local", ".internal")):
        return True
    wildcard_dns_suffixes = ("nip.io", "sslip.io", "lvh.me", "localtest.me")
    if host in wildcard_dns_suffixes or host.endswith(tuple(f".{suffix}" for suffix in wildcard_dns_suffixes)):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if all(char.isdigit() or char == "." for char in host):
            return True
        if any(not (char.isalnum() or char in {"-", "."}) for char in host):
            return True
        labels = host.split(".")
        if len(labels) < 2:
            return True
        if any(not label or label.startswith("-") or label.endswith("-") for label in labels):
            return True
        if len(host) > 253:
            return True
        if any(len(label) > 63 for label in labels):
            return True
        return _host_resolves_to_unsafe_address(host)
    return not is_ai_provider_resolved_address_safe(host)


def validate_ai_provider_base_url(value):
    submitted_value = value or ""
    if submitted_value != submitted_value.strip():
        raise ValidationError("Enter a valid provider base URL.")
    raw_value = submitted_value.strip()
    if any(ord(char) < 32 or ord(char) == 127 for char in submitted_value):
        raise ValidationError("Enter a valid provider base URL.")
    if any(char.isspace() for char in raw_value) or "\\" in raw_value:
        raise ValidationError("Enter a valid provider base URL.")
    try:
        parsed = urlparse(raw_value)
        hostname = parsed.hostname
        parsed.port
    except ValueError:
        raise ValidationError("Enter a valid provider base URL.")
    if parsed.scheme != "https":
        raise ValidationError("Base URL must use HTTPS.")
    if parsed.netloc.endswith(":"):
        raise ValidationError("Enter a valid provider base URL.")
    if "@" in parsed.netloc or parsed.username or parsed.password:
        raise ValidationError("Base URL cannot include usernames or passwords.")
    if not parsed.netloc or _unsafe_provider_host(hostname):
        raise ValidationError("Base URL host is not allowed.")
    if parsed.query or parsed.fragment:
        raise ValidationError("Base URL cannot include query strings or fragments.")
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
