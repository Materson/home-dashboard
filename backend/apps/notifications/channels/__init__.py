from __future__ import annotations

from .base import Channel
from .email import EmailChannel
from .webpush import WebPushChannel

REGISTRY: dict[str, Channel] = {
    EmailChannel.name: EmailChannel(),
    WebPushChannel.name: WebPushChannel(),
}

__all__ = ["REGISTRY", "Channel"]
