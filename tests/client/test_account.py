from cli115.client.models import Usage


class TestAccount:

    def test_info(self, api_client):
        info = api_client.account.info()
        assert info.user_id
        assert info.user_name


class TestAccountUnit:

    def test_disk_usage(self, api_client):
        result = api_client.account.usage()
        assert result.total > 0
        assert result.used > 0
        assert result.remaining > 0
