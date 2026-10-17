from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


def normalize_server_url(value: str) -> str:
    server = value.strip()
    if not server:
        raise ValueError("Jellyfin server URL must not be empty")
    if "://" not in server:
        server = f"http://{server}"

    parsed = urlsplit(server)
    scheme = parsed.scheme.lower()
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Jellyfin server URL must not include credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("Jellyfin server URL must not include a query or fragment")
    if url_origin(server) is None:
        raise ValueError("Jellyfin server URL must include a valid HTTP(S) host and port")
    path = parsed.path.rstrip("/")
    if not path.endswith("/web"):
        path = f"{path}/web"

    return urlunsplit((scheme, parsed.netloc, f"{path}/", "", ""))


def url_origin(value: str) -> tuple[str, str, int] | None:
    try:
        parsed = urlsplit(value)
        scheme = parsed.scheme.lower()
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return None

    if (
        scheme not in {"http", "https"}
        or not host
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None

    default_port = 443 if scheme == "https" else 80
    return scheme, host.lower(), port if port is not None else default_port
