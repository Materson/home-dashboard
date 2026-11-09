"""AccessContext: the user's merged, fast-lookup permission view.

Built per request by the middleware and cached on ``request.access_ctx``.
AI tool calls and Slack handlers build one with ``for_user(user)``.

Scoping policy:
- ``scope_by_person(qs, person_field)`` filters a queryset by the Person UUIDs
  the user is allowed to see in that module, and by any date window.
- ``require(module, level)`` raises ``PermissionDenied`` when the user lacks
  the permission (optionally against a specific object).

Default stance: **deny-all**. Any read must go through ``scope_*`` or
``require`` — bare ``.objects.all()`` in selectors is a bug.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Iterable
from uuid import UUID

from django.core.exceptions import PermissionDenied
from django.db.models import Q, QuerySet
from django.http import HttpRequest

from .models import AccessGrant
from .permissions import LEVELS, MODULES, level_at_least

if TYPE_CHECKING:
    from apps.accounts.models import User


@dataclass(slots=True)
class Scope:
    allowed_level: str | None = None  # highest ALLOW level, after DENYs
    person_ids: set[UUID] | None = None  # None = all; empty set = none
    data_from: date | None = None
    data_to: date | None = None


@dataclass(slots=True)
class AccessContext:
    user_id: int | None
    person_id: UUID | None  # the User's own Person, if any
    is_admin: bool
    scopes: dict[str, Scope] = field(default_factory=dict)

    # ---- factories -----------------------------------------------------

    @classmethod
    def for_user(cls, user: "User") -> "AccessContext":
        if not user.is_authenticated:
            return cls(user_id=None, person_id=None, is_admin=False)
        person_id = getattr(getattr(user, "person", None), "id", None)
        ctx = cls(user_id=user.id, person_id=person_id, is_admin=bool(user.is_superuser))
        if ctx.is_admin:
            for m in MODULES:
                ctx.scopes[m] = Scope(allowed_level="manage", person_ids=None)
            return ctx
        ctx._load_from_db()
        return ctx

    # ---- loading -------------------------------------------------------

    def _load_from_db(self) -> None:
        from django.contrib.auth import get_user_model
        from django.utils import timezone

        U = get_user_model()
        user = U.objects.get(pk=self.user_id)
        group_ids = list(user.groups.values_list("id", flat=True))
        grants = AccessGrant.objects.filter(
            Q(user_id=self.user_id) | Q(group_id__in=group_ids)
        ).filter(Q(valid_until__isnull=True) | Q(valid_until__gt=timezone.now()))

        for module in MODULES:
            self.scopes[module] = self._merge_grants(
                [g for g in grants if g.module == module]
            )

    def _merge_grants(self, grants: list[AccessGrant]) -> Scope:
        allow_levels: set[str] = set()
        deny_levels: set[str] = set()
        allowed_persons: set[UUID] | None = None  # None = any; set = constrained to this
        has_allow = False
        data_from: date | None = None
        data_to: date | None = None
        for g in grants:
            if g.effect == AccessGrant.Effect.DENY:
                deny_levels.add(g.level)
                continue
            allow_levels.add(g.level)
            has_allow = True
            persons = self._grant_person_set(g)
            if persons is None:
                # unconstrained: widens the scope
                allowed_persons = None if allowed_persons is None else allowed_persons
            else:
                allowed_persons = persons if allowed_persons is None else (allowed_persons | persons)
            if g.data_from and (data_from is None or g.data_from < data_from):
                data_from = g.data_from
            if g.data_to and (data_to is None or g.data_to > data_to):
                data_to = g.data_to
        effective = allow_levels - deny_levels
        allowed_level = max(effective, key=LEVELS.index) if effective else None
        return Scope(
            allowed_level=allowed_level,
            person_ids=allowed_persons if has_allow else set(),
            data_from=data_from,
            data_to=data_to,
        )

    def _grant_person_set(self, g: AccessGrant) -> set[UUID] | None:
        if g.subjects == AccessGrant.Subjects.ALL:
            return None
        if g.subjects == AccessGrant.Subjects.SELF:
            return {self.person_id} if self.person_id else set()
        return {UUID(pid) for pid in g.person_ids}

    # ---- queries -------------------------------------------------------

    def has(self, module: str, level: str) -> bool:
        s = self.scopes.get(module)
        return bool(s and s.allowed_level and level_at_least(s.allowed_level, level))

    def require(self, module: str, level: str, obj: object | None = None) -> None:
        if not self.has(module, level):
            raise PermissionDenied(f"{module}:{level} denied")
        if obj is None:
            return
        person_field = getattr(obj, "_access_person_field", None) or getattr(
            type(obj)._meta, "access_person_field", None  # type: ignore[attr-defined]
        )
        if person_field:
            pid = getattr(obj, person_field + "_id", None)
            allowed = self.scopes[module].person_ids
            if allowed is not None and (pid is None or pid not in allowed):
                raise PermissionDenied(f"{module}:{level} denied for this person")

    def scope_by_person(
        self,
        *,
        module: str,
        qs: QuerySet,
        person_field: str,
        level: str = "view",
        date_field: str | None = None,
    ) -> QuerySet:
        if not self.has(module, level):
            return qs.none()
        s = self.scopes[module]
        if s.person_ids is not None:
            if not s.person_ids:
                return qs.none()
            qs = qs.filter(**{f"{person_field}__in": s.person_ids})
        if date_field:
            if s.data_from:
                qs = qs.filter(**{f"{date_field}__gte": s.data_from})
            if s.data_to:
                qs = qs.filter(**{f"{date_field}__lte": s.data_to})
        return qs

    # ---- summary (for /api/me/permissions) ----------------------------

    def module_summary(self) -> dict[str, dict[str, bool]]:
        out: dict[str, dict[str, bool]] = {}
        for m in MODULES:
            out[m] = {lvl: self.has(m, lvl) for lvl in LEVELS}
        return out

    def visible_person_ids(self) -> list[UUID]:
        ids: set[UUID] = set()
        unconstrained = False
        for m in MODULES:
            s = self.scopes.get(m)
            if not s or not s.allowed_level:
                continue
            if s.person_ids is None:
                unconstrained = True
                break
            ids |= s.person_ids
        if unconstrained:
            from apps.people.models import Person

            return list(Person.objects.values_list("id", flat=True))
        return sorted(ids)


def get_ctx(request: HttpRequest) -> AccessContext:
    ctx = getattr(request, "access_ctx", None)
    if ctx is None:
        ctx = AccessContext.for_user(request.user)
        request.access_ctx = ctx  # type: ignore[attr-defined]
    return ctx


__all__ = ["AccessContext", "Scope", "get_ctx"]
