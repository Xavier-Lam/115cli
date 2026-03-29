class TestAccount:

    def test_info(self, api_client):
        info = api_client.account.info()
        assert info.user_id
        assert info.user_name
