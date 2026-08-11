"""Tests for SSL CA bundle bootstrap."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.utils import ssl_ca
from app.utils.ssl_ca import ensure_ca_bundle, resolve_ca_bundle


def test_ensure_ca_bundle_sets_valid_paths(monkeypatch):
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.delenv("CURL_CA_BUNDLE", raising=False)
    ssl_ca._CONFIGURED = False

    bundle = ensure_ca_bundle()

    assert os.path.isfile(bundle)
    assert os.environ["SSL_CERT_FILE"] == bundle
    assert os.environ["REQUESTS_CA_BUNDLE"] == bundle
    assert os.environ["CURL_CA_BUNDLE"] == bundle


def test_ensure_ca_bundle_clears_invalid_path(monkeypatch):
    ssl_ca._CONFIGURED = False
    monkeypatch.setenv("SSL_CERT_FILE", "/tmp/definitely-not-a-ca-bundle.pem")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", "/tmp/definitely-not-a-ca-bundle.pem")

    bundle = ensure_ca_bundle()

    assert os.path.isfile(bundle)
    assert os.environ["SSL_CERT_FILE"] == bundle


def test_resolve_ca_bundle_falls_back_to_system(tmp_path, monkeypatch):
    fake_certifi = tmp_path / "certifi"
    fake_certifi.mkdir()
    missing = fake_certifi / "cacert.pem"
    system_ca = tmp_path / "system-ca.crt"
    system_ca.write_text("dummy-ca-bundle\n", encoding="utf-8")

    monkeypatch.setattr(ssl_ca, "SYSTEM_CA_BUNDLES", (str(system_ca),))
    monkeypatch.setattr(
        ssl_ca,
        "_certifi_bundle_path",
        lambda: None,
    )

    def fake_where():
        return str(missing)

    import certifi

    monkeypatch.setattr(certifi, "where", fake_where)

    assert resolve_ca_bundle() == str(system_ca)


def test_resolve_ca_bundle_raises_when_nothing_available(monkeypatch):
    monkeypatch.setattr(ssl_ca, "_certifi_bundle_path", lambda: None)
    monkeypatch.setattr(ssl_ca, "SYSTEM_CA_BUNDLES", ("/no/such/file.pem",))

    import certifi

    monkeypatch.setattr(certifi, "where", lambda: "/no/such/certifi.pem")

    with pytest.raises(RuntimeError, match="certifi CA bundle missing"):
        resolve_ca_bundle()
