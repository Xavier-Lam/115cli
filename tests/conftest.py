import pytest


@pytest.fixture(autouse=True)
def _no_real_config(tmp_path, monkeypatch):
    # Point DEFAULT_CONFIG_FILE to a path that doesn't exist so load_config()
    # always returns defaults instead of reading the real machine config.
    monkeypatch.setattr("cli115.cli.DEFAULT_CONFIG_FILE", tmp_path / "config.ini")


def pytest_collection_modifyitems(items):
    """Run non-client tests first, then client readonly, then client mutating."""
    readonly_modules = {"test_account", "test_file_readonly"}

    def sort_key(item):
        parts = item.nodeid.split("/")
        is_client = any(p == "client" for p in parts)
        if not is_client:
            return (0, item.nodeid)
        module = parts[-1].split("::")[0].replace(".py", "")
        if module in readonly_modules:
            return (1, item.nodeid)
        return (2, item.nodeid)

    items.sort(key=sort_key)
