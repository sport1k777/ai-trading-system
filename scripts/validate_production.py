#!/usr/bin/env python3
"""Production readiness validation — run before deploy."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(label: str, ok: bool, detail: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {label}" + (f" — {detail}" if detail else ""))
    return ok


def main() -> int:
    print("=" * 50)
    print(" AI Trading System — Production Validation")
    print("=" * 50)

    results: list[bool] = []

    # 1. Config template
    results.append(check(".env.example exists", (ROOT / ".env.example").is_file()))

    # 2. systemd unit
    results.append(check(
        "systemd unit template",
        (ROOT / "deploy/systemd/ai-trading-signals.service").is_file(),
    ))

    # 3. Deploy scripts
    deploy_scripts = [
        "scripts/deploy/deploy.sh",
        "scripts/deploy/update.sh",
        "scripts/deploy/rollback.sh",
        "scripts/deploy/inspect.sh",
    ]
    for rel in deploy_scripts:
        results.append(check(f"deploy script {Path(rel).name}", (ROOT / rel).is_file()))

    # 4. Bash syntax
    for script in (ROOT / "scripts" / "deploy").glob("*.sh"):
        r = subprocess.run(["bash", "-n", str(script)], capture_output=True)
        results.append(check(f"bash -n {script.name}", r.returncode == 0))

    # 5. Import all app modules
    r = subprocess.run(
        [sys.executable, "-c", """
import importlib, pkgutil, app, sys
for m in pkgutil.walk_packages(app.__path__, prefix='app.'):
    importlib.import_module(m.name)
print('ok')
"""],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    results.append(check("import all app modules", r.returncode == 0, r.stderr.strip()[:120]))

    # 6. Pytest
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    passed = "passed" in r.stdout and r.returncode == 0
    summary = r.stdout.strip().split("\n")[-1] if r.stdout else r.stderr[:120]
    results.append(check("pytest suite", passed, summary))

    # 7. No TODO/FIXME in source
    bad = []
    skip = {"scripts/validate_production.py"}
    for path in ROOT.rglob("*"):
        if path.suffix not in (".py", ".sh"):
            continue
        if any(p in path.parts for p in (".cache", "venv", ".venv", ".git")):
            continue
        rel = str(path.relative_to(ROOT))
        if rel in skip:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for marker in ("TODO", "FIXME", "HACK", "XXX"):
                if marker in line:
                    bad.append(f"{rel}:{i}:{marker}")
                    break
    results.append(check("no TODO/FIXME in source", not bad, ", ".join(bad[:3])))

    print("=" * 50)
    failed = sum(1 for r in results if not r)
    if failed:
        print(f"VALIDATION FAILED — {failed} check(s)")
        return 1
    print("VALIDATION PASSED — production-ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
