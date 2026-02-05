"""Unit tests for seed loading (no Redis)."""

import tempfile
from pathlib import Path

import pytest
from crawler_scheduler.seeds import load_seeds


def test_load_seeds_missing_file() -> None:
    path = Path("/nonexistent/seeds.yaml")
    assert load_seeds(path) == []


def test_load_seeds_empty_file() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("")
    try:
        assert load_seeds(Path(f.name)) == []
    finally:
        Path(f.name).unlink()


def test_load_seeds_empty_seeds_key() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("seeds: []")
    try:
        assert load_seeds(Path(f.name)) == []
    finally:
        Path(f.name).unlink()


def test_load_seeds_invalid_yaml_returns_empty() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("seeds:\n  - not a list at next line\nbroken")
    try:
        # Invalid YAML (e.g. scanner error) -> load_seeds returns []
        result = load_seeds(Path(f.name))
        assert result == []
    finally:
        Path(f.name).unlink()


def test_load_seeds_valid_list() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("seeds:\n  - https://a.com/1\n  - https://b.com/2")
    try:
        assert load_seeds(Path(f.name)) == ["https://a.com/1", "https://b.com/2"]
    finally:
        Path(f.name).unlink()


def test_load_seeds_skips_non_strings() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("seeds:\n  - https://a.com\n  - 123\n  - null")
    try:
        result = load_seeds(Path(f.name))
        assert result == ["https://a.com"]
    finally:
        Path(f.name).unlink()
