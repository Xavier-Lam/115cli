import unittest

from tests.base import BaseTestCase


class TestDefaultAccountClient(BaseTestCase):

    def test_info(self):
        info = self.client.account.info()
        self.assertTrue(info.user_id)
        self.assertTrue(info.user_name)


if __name__ == "__main__":
    unittest.main()
