from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest
from ninja import Router, Schema

from .models import NotificationPreference, PushSubscription

router = Router()


class VapidOut(Schema):
    public_key: str


@router.get("/webpush/vapid", response=VapidOut)
def vapid(request: HttpRequest) -> VapidOut:  # noqa: ARG001
    return VapidOut(public_key=settings.VAPID_PUBLIC_KEY)


class SubscribeIn(Schema):
    endpoint: str
    p256dh: str
    auth: str
    user_agent: str = ""


@router.post("/webpush/subscribe")
def subscribe(request: HttpRequest, payload: SubscribeIn) -> dict[str, bool]:
    PushSubscription.objects.update_or_create(
        endpoint=payload.endpoint,
        defaults={
            "user": request.user,
            "p256dh": payload.p256dh,
            "auth": payload.auth,
            "user_agent": payload.user_agent,
        },
    )
    return {"ok": True}


class PrefsOut(Schema):
    email_enabled: bool
    webpush_enabled: bool
    slack_enabled: bool


@router.get("/prefs", response=PrefsOut)
def get_prefs(request: HttpRequest) -> NotificationPreference:
    prefs, _ = NotificationPreference.objects.get_or_create(user=request.user)
    return prefs


class PrefsIn(Schema):
    email_enabled: bool
    webpush_enabled: bool
    slack_enabled: bool


@router.put("/prefs", response=PrefsOut)
def set_prefs(request: HttpRequest, payload: PrefsIn) -> NotificationPreference:
    prefs, _ = NotificationPreference.objects.get_or_create(user=request.user)
    for field, value in payload.dict().items():
        setattr(prefs, field, value)
    prefs.save()
    return prefs
