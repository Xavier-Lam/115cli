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
