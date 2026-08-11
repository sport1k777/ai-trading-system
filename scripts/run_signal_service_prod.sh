#!/usr/bin/env bash
# Production entrypoint: resolve a verified CA bundle before starting the service.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${ROOT}/venv"
PYTHON="${VENV}/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "Missing venv python: $PYTHON" >&2
  exit 1
fi

export PYTHONPATH="$ROOT"
CERT="$("$PYTHON" -c 'from app.utils.ssl_ca import ensure_ca_bundle; print(ensure_ca_bundle())')"
if [[ ! -f "$CERT" ]]; then
  echo "CA bundle path is not a file: $CERT" >&2
  exit 1
fi

export SSL_CERT_FILE="$CERT"
export REQUESTS_CA_BUNDLE="$CERT"
export CURL_CA_BUNDLE="$CERT"

exec "$PYTHON" -m app.services.signal_service
