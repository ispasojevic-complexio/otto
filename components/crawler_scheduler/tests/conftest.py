"""Pytest configuration: add component directory to path for imports."""

import sys
from pathlib import Path

_component_dir = Path(__file__).resolve().parent.parent
if str(_component_dir) not in sys.path:
    sys.path.insert(0, str(_component_dir))
