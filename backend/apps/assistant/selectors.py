"""Assistant reads. Conversations are private to their owner — no grant,
admin included, shows someone else's."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import Http404

from .models import Conversation, LLMCall, Message

if TYPE_CHECKING:
    from apps.access.context import AccessContext


def require_use(ctx: AccessContext) -> None:
    if not ctx.user_id or not ctx.has("assistant", "view"):
        raise PermissionDenied("assistant:view denied")


def list_conversations(ctx: AccessContext) -> QuerySet[Conversation]:
    require_use(ctx)
    return Conversation.objects.filter(owner_id=ctx.user_id)


def get_conversation(ctx: AccessContext, conversation_id: UUID) -> Conversation:
    require_use(ctx)
    conv = Conversation.objects.filter(pk=conversation_id, owner_id=ctx.user_id).first()
    if conv is None:
        raise Http404
    return conv


def list_messages(ctx: AccessContext, conversation_id: UUID) -> QuerySet[Message]:
    conv = get_conversation(ctx, conversation_id)
    return conv.messages.prefetch_related("actions")


def calls_for(ctx: AccessContext, message_id: UUID) -> QuerySet[LLMCall]:
    """What was sent to the model(s) to produce one answer."""
    message = Message.objects.select_related("conversation").filter(pk=message_id).first()
    if message is None or message.conversation.owner_id != ctx.user_id:
        raise Http404
    return LLMCall.objects.filter(message=message).order_by("created_at")
