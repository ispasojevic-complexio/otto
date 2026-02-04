"""Pytest configuration: add repo root and core to path; load shared fixtures."""

import sys
from pathlib import Path

_tests_dir = Path(__file__).resolve().parent
_core_root = _tests_dir.parent  # shared/core
_repo_root = _core_root.parent.parent  # otto
for d in (_repo_root, _core_root):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

pytest_plugins = ["shared.core.pytest_fixtures"]
