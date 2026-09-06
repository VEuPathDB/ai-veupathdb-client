"""The registered VEuPathDB account the live WDK tests act as.

VEuPathDB serves the WDK service to registered users only, so a live test
carries this account's token or it skips. The environment may name the token
directly, or the email and password the suite logs in with.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict, Field

from veupathdb.wdk.auth_login import password_login

LOGIN_SITE_ID = "plasmodb"

NO_CREDENTIALS_REASON = (
    "live WDK requires a registered user; set WDK_TEST_TOKEN, or "
    "WDK_TEST_EMAIL/WDK_TEST_PASSWORD"
)


class WdkTestAccount(BaseModel):
    """The credential the environment names, read once. Its values never print."""

    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    token: str = Field(default="", alias="WDK_TEST_TOKEN")
    email: str = Field(default="", alias="WDK_TEST_EMAIL")
    password: str = Field(default="", alias="WDK_TEST_PASSWORD")

    @property
    def is_named(self) -> bool:
        """True when the environment names a token or both halves of a login."""
        return bool(self.token or (self.email and self.password))


def wdk_test_account() -> WdkTestAccount:
    """The account the environment names. Its values never reach the output."""
    return WdkTestAccount.model_validate(dict(os.environ))


async def registered_wdk_token() -> str | None:
    """Return the account's WDK token, or None when the environment names none.

    A named token is used as it stands. Otherwise the suite logs in, and a
    rejected login raises, because a live suite that silently ran
    unauthenticated would prove nothing.
    """
    account = wdk_test_account()
    if account.token:
        return account.token
    if not account.is_named:
        return None
    token = await password_login(LOGIN_SITE_ID, account.email, account.password)
    if token is None:
        msg = (
            f"{LOGIN_SITE_ID} rejected the account WDK_TEST_EMAIL names, so the "
            "live tests cannot act as a registered user"
        )
        raise RuntimeError(msg)
    return token
