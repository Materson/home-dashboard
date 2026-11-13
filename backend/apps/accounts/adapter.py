"""allauth hooks: accounts are made by an admin (People / Django admin),
never by signing up — the family app isn't open to anyone who reaches it."""

from __future__ import annotations

from typing import TYPE_CHECKING

from allauth.account.adapter import DefaultAccountAdapter

if TYPE_CHECKING:
    from django.http import HttpRequest


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request: HttpRequest) -> bool:
        return False
