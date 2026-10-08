"""Fail-closed source-role policy for ZITAR public research."""

from urllib.parse import urlsplit


PRIMARY = "PRIMARY"
INDEPENDENT = "INDEPENDENT"
REJECTED = "REJECTED"


# Provider families prevent two domains controlled by the same provider
# from being treated as independent corroboration.
PROVIDER_FAMILIES = {
    "www.binance.tr": "BINANCE",
    "www.binance.com": "BINANCE",
    "academy.binance.com": "BINANCE",
}


def classify_source(url, primary_family="BINANCE", independent_hosts=None):
    independent_hosts = independent_hosts or {}

    parsed = urlsplit(url)

    if parsed.scheme != "https" or not parsed.hostname:
        return {
            "role": REJECTED,
            "provider_family": None,
            "reason": "INVALID_HTTPS_SOURCE",
        }

    host = parsed.hostname.lower()

    blocked_parts = {
        "my", "account", "login", "register",
        "trade", "trading", "wallet", "markets",
    }

    parts = {p.lower() for p in parsed.path.split("/") if p}

    if parts & blocked_parts:
        return {
            "role": REJECTED,
            "provider_family": PROVIDER_FAMILIES.get(host),
            "reason": "NON_RESEARCH_PATH",
        }

    family = PROVIDER_FAMILIES.get(host)

    if family == primary_family:
        return {
            "role": PRIMARY,
            "provider_family": family,
            "reason": "APPROVED_PRIMARY_PROVIDER",
        }

    if host in independent_hosts:
        return {
            "role": INDEPENDENT,
            "provider_family": independent_hosts[host],
            "reason": "APPROVED_INDEPENDENT_PROVIDER",
        }

    return {
        "role": REJECTED,
        "provider_family": family,
        "reason": "SOURCE_NOT_IN_POLICY",
    }


def corroboration_allowed(primary, independent):
    if primary.get("role") != PRIMARY:
        return False

    if independent.get("role") != INDEPENDENT:
        return False

    a = primary.get("provider_family")
    b = independent.get("provider_family")

    return bool(a and b and a != b)
