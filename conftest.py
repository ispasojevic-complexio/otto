"""Root conftest: load shared core fixtures so all component tests can use them."""

pytest_plugins = ["shared.core.pytest_fixtures"]
