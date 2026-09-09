"""Shared browser preference logic runs in CI without Playwright or a backend."""

import subprocess
from pathlib import Path


def test_hidden_preference_store():
    subprocess.run(
        ["node", "--test", "tests/browser/hidden-store.cjs"],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
    )
