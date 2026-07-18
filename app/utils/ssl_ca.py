"""Ensure HTTPS clients can locate a CA bundle (VPS-safe)."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIGURED = False

# Debian/Ubuntu, RHEL, macOS/Homebrew, Alpine
SYSTEM_CA_BUNDLES = (
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/etc/ssl/cert.pem",
    "/etc/ssl/ca-bundle.pem",
)


def _certifi_bundle_path() -> str | None:
    try:
        import certifi
    except ImportError:
        return None
    path = certifi.where()
    return path if Path(path).is_file() else None


def resolve_ca_bundle() -> str:
    """Return the first usable CA bundle (certifi, then system paths)."""
    certifi_path = _certifi_bundle_path()
    if certifi_path:
        return certifi_path

    certifi_expected = None
    try:
        import certifi

        certifi_expected = certifi.where()
    except ImportError:
        pass

    for path in SYSTEM_CA_BUNDLES:
        if Path(path).is_file():
            if certifi_expected and not Path(certifi_expected).is_file():
                logger.warning(
                    "certifi bundle missing at %s — using system CA bundle %s",
                    certifi_expected,
                    path,
                )
            return path

    if certifi_expected:
        raise RuntimeError(
            f"certifi CA bundle missing at {certifi_expected} and no system CA bundle found"
        )
    raise RuntimeError("No CA certificate bundle found (certifi missing and no system bundle)")


def ensure_ca_bundle() -> str:
    """Point SSL env vars at a verified CA bundle; never set a missing path."""
    global _CONFIGURED

    bundle = resolve_ca_bundle()

    for name in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        current = os.environ.get(name)
        if current and not Path(current).is_file():
            logger.warning("Clearing invalid %s=%s", name, current)
            os.environ.pop(name, None)
        if not os.environ.get(name) or not Path(os.environ[name]).is_file():
            os.environ[name] = bundle

    if not _CONFIGURED:
        logger.info("Using CA bundle: %s", bundle)
        _CONFIGURED = True

    return bundle
