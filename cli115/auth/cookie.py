"""Cookie-based authentication for 115 netdisk."""

from cli115.auth.base import Auth


class CookieAuth(Auth):
    """Authenticate using four cookie values: UID, CID, SEID, KID."""

    def __init__(self, uid: str, cid: str, seid: str, kid: str):
        self._uid = uid
        self._cid = cid
        self._seid = seid
        self._kid = kid

    def get_cookies(self) -> dict[str, str]:
        """Return the four authentication cookies."""
        return {
            "UID": self._uid,
            "CID": self._cid,
            "SEID": self._seid,
            "KID": self._kid,
        }
