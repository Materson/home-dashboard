"""`/api/me/...` — current user + merged permissions for the SPA shell."""
from __future__ import annotations

from django.http import HttpRequest
from ninja import Router, Schema

from apps.access.context import get_ctx

router = Router()


class UserOut(Schema):
    id: int
    email: str
    locale: str
    first_name: str
    last_name: str


class PermissionsOut(Schema):
    modules: dict[str, dict[str, bool]]  # {"finance": {"view": True, "edit": True, "manage": False}, ...}
    person_ids: list[str]  # Person UUIDs the caller can at least view (any module)
    is_admin: bool


@router.get("/", response=UserOut)
def me(request: HttpRequest) -> UserOut:
    u = request.user
    return UserOut(
        id=u.id,
        email=u.email,
        locale=u.locale,
        first_name=u.first_name,
        last_name=u.last_name,
    )


@router.get("/permissions", response=PermissionsOut)
def permissions(request: HttpRequest) -> PermissionsOut:
    ctx = get_ctx(request)
    return PermissionsOut(
        modules=ctx.module_summary(),
        person_ids=[str(pid) for pid in ctx.visible_person_ids()],
        is_admin=ctx.is_admin,
    )
