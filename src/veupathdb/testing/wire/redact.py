from __future__ import annotations

import re
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict

from veupathdb.testing.wire.key import FAKE_USER_ID

ACCOUNT_EMAIL = "e2e-account@strategist.test"
ACCOUNT_FIRST_NAME = "E2E"
ACCOUNT_LAST_NAME = "Account"
ACCOUNT_ORGANIZATION = "Strategist e2e"
REDACTED = "wire-redacted"

_JWT = re.compile(rb"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")


class Identity(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: int
    email: str
    first_name: str = ""
    last_name: str = ""
    organization: str = ""


class Redactor:
    def __init__(self, identity: Identity) -> None:
        self._user_id = re.compile(rf"(?<!\d){identity.user_id}(?!\d)".encode())
        emails = {identity.email, quote(identity.email, safe="")}
        self._emails = [email.encode() for email in emails if email]
        names = (
            (identity.first_name, ACCOUNT_FIRST_NAME),
            (identity.last_name, ACCOUNT_LAST_NAME),
            (identity.organization, ACCOUNT_ORGANIZATION),
        )
        self._names = [
            (f'"{value}"'.encode(), f'"{placeholder}"'.encode())
            for value, placeholder in names
            if value
        ]

    def body(self, body: bytes) -> bytes:
        body = _JWT.sub(REDACTED.encode(), body)
        for email in self._emails:
            body = body.replace(email, ACCOUNT_EMAIL.encode())
        for value, placeholder in self._names:
            body = body.replace(value, placeholder)
        return self._user_id.sub(str(FAKE_USER_ID).encode(), body)

    def path(self, path: str) -> str:
        return self.body(path.encode()).decode()
