"""Validate deployment shell scripts parse correctly."""

from __future__ import annotations

import subprocess
from pathlib import Path

DEPLOY_DIR = Path(__file__).resolve().parents[1] / "scripts" / "deploy"


def test_deploy_scripts_bash_syntax():
    scripts = list(DEPLOY_DIR.glob("*.sh")) + list((DEPLOY_DIR / "lib").glob("*.sh"))
    assert scripts, "No deploy scripts found"
    for script in scripts:
        result = subprocess.run(
            ["bash", "-n", str(script)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"{script.name}: {result.stderr}"
