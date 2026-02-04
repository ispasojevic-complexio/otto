"""Pytest configuration: add component and repo root to path; load shared fixtures."""

import sys
from pathlib import Path

_component_dir = Path(__file__).resolve().parent.parent
_repo_root = _component_dir.parent.parent
for d in (_component_dir, _repo_root):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

pytest_plugins = ["shared.core.pytest_fixtures"]
