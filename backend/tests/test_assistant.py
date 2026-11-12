"""Assistant: tools offered by permission and privacy policy, aliases on the
way out and back, proposals confirmed / cancelled / undone, photos policy,
privacy of conversations, admin-only settings. A scripted fake model stands
in for the providers (no network)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404

from apps.access.context import AccessContext
from apps.access.models import AccessGrant
from apps.assistant import actions, llm, services
from apps.assistant.llm import ToolCall, Turn
from apps.assistant.loop import available_tools
from apps.assistant.models import AISettings, LLMCall, PendingAction, ProviderProfile
from apps.assistant.policy import policies
from apps.finance.models import Category, Transaction
from apps.household.models import ShoppingEntry

from .factories import AccessGrantFactory, PersonFactory, UserFactory

pytestmark = pytest.mark.django_db


class FakeSession:
    def __init__(self, fake, system, tools, history):
        fake.sessions.append(self)
        self.fake, self.system, self.history = fake, system, history
        self.tools = [t.name for t in tools]
        self.results: list = []

    def step(self) -> Turn:
        return self.fake.turns.pop(0)

    def add_tool_results(self, results) -> None:
        self.results.append(results)


class FakeAdapter:
    supported_files = frozenset({"image/jpeg", "image/png"})

    def __init__(self, *turns: Turn):
        self.turns = list(turns)
        self.sessions: list[FakeSession] = []

    def start(self, system, tools, history):
        return FakeSession(self, system, tools, history)

    def ping(self) -> str:
        return "ok"


@pytest.fixture
def fake(monkeypatch):
    def use(*turns: Turn) -> FakeAdapter:
        adapter = FakeAdapter(*turns)
        monkeypatch.setattr(llm, "TEST_ADAPTER", adapter)
        return adapter

    return use


@pytest.fixture
def home():
    parent, child = UserFactory(), UserFactory()
    for module in ("finance", "household", "notes", "health", "assistant"):
        AccessGrantFactory(user=parent, module=module, level="edit")
    AccessGrantFactory(user=parent, module="people", level="view")
    AccessGrantFactory(user=child, module="assistant", level="view")
    AccessGrantFactory(
        user=child, module="health", level="view", subjects=AccessGrant.Subjects.SELF
    )
    PersonFactory(display_name="Mama", user=parent)
    PersonFactory(display_name="Zosia", user=child)
    cloud = ProviderProfile.objects.create(
        name="Claude", kind="anthropic", model="claude-opus-5-5", api_key="k"
    )
    local = ProviderProfile.objects.create(
        name="Ollama", kind="ollama", model="llama", location="local", base_url="http://pc:11434/v1"
    )
    AISettings.objects.create(pk=1, chat_profile=cloud, local_profile=local)
    return {
        "parent": AccessContext.for_user(parent),
        "child": AccessContext.for_user(child),
        "parent_user": parent,
        "cloud": cloud,
        "local": local,
    }


def ask(ctx, text, *, private=False, files=None, page=""):
    conv = services.create_conversation(ctx, private=private)
    _, answer = services.send_message(ctx, conv.id, text=text, files=files, page=page)
    return conv, answer


def test_not_configured_gives_a_readable_error(home, fake):
    AISettings.objects.filter(pk=1).update(chat_profile=None)
    _, answer = ask(home["parent"], "hej")
    assert answer.error and "Ustawienia" in answer.text


def test_tools_follow_permissions_and_privacy_policy(home):
    pol = policies()
    parent_cloud = {t.name for t in available_tools(home["parent"], home["cloud"], pol)}
    assert "finance_search" in parent_cloud and "add_to_shopping_list" in parent_cloud
    # health and notes are local-only by default → never offered to a cloud model
    assert "cabinet_find" not in parent_cloud and "notes_search" not in parent_cloud
    parent_local = {t.name for t in available_tools(home["parent"], home["local"], pol)}
    assert {"cabinet_find", "notes_search", "finance_search"} <= parent_local
    # a child never gets finance tools, nor write tools without the grant
    child = {t.name for t in available_tools(home["child"], home["local"], pol)}
    assert "finance_search" not in child and "propose_transaction" not in child
    assert "cabinet_find" in child


def test_names_are_aliased_for_cloud_and_restored_for_the_user(home, fake):
    model = fake(
        Turn(text="", tool_calls=[ToolCall("1", "family_members", {})]),
        Turn(text="[P1] ma 4 lata, a Mama jest tutaj jako [P2].", tool_calls=[]),
    )
    conv, answer = ask(home["parent"], "Ile lat ma Zosia? Tel. 600 100 200")
    sent_question = model.sessions[0].history[-1].text
    assert "Zosia" not in sent_question and "600 100 200" not in sent_question
    tool_output = model.sessions[0].results[0][0].content
    assert "Zosia" not in tool_output and "Mama" not in tool_output
    assert "Zosia" in answer.text and "[P" not in answer.text
    logged = str([c.sent for c in LLMCall.objects.filter(conversation=conv)])
    assert "Zosia" not in logged and "600 100 200" not in logged
    assert any("people" in c.modules for c in LLMCall.objects.filter(conversation=conv))


def test_local_model_sees_real_names(home, fake):
    model = fake(Turn(text="ok", tool_calls=[]))
    ask(home["parent"], "Co z Zosią?", private=True)
    assert "Zosią" in model.sessions[0].history[-1].text


def test_proposed_transaction_waits_for_confirmation(home, fake):
    cat = Category.objects.filter(kind="expense").first()
    fake(
        Turn(
            text="",
            tool_calls=[
                ToolCall(
                    "1",
                    "propose_transaction",
                    {
                        "kind": "expense",
                        "amount": "45,50",
                        "name": "Biedronka",
                        "category": cat.name,
                    },
                )
            ],
        ),
        Turn(text="Czeka na potwierdzenie.", tool_calls=[]),
    )
    _, answer = ask(home["parent"], "Dodaj zakupy 45,50")
    [action] = answer.actions.all()
    assert action.status == PendingAction.Status.PROPOSED and not Transaction.objects.exists()

    actions.confirm(home["parent"], action.id)
    tx = Transaction.objects.get()
    assert tx.amount == Decimal("45.50") and tx.category == cat
    with pytest.raises(ValueError):
        actions.confirm(home["parent"], action.id)  # not twice
    actions.undo(home["parent"], action.id)
    assert not Transaction.objects.exists()


def test_someone_else_cannot_confirm_my_proposal(home, fake):
    cat = Category.objects.filter(kind="expense").first()
    fake(
        Turn(
            text="",
            tool_calls=[
                ToolCall(
                    "1",
                    "propose_transaction",
                    {"kind": "expense", "amount": 5, "name": "x", "category": cat.name},
                )
            ],
        ),
        Turn(text="ok", tool_calls=[]),
    )
    _, answer = ask(home["parent"], "x")
    action = answer.actions.get()
    with pytest.raises(PermissionDenied):
        actions.confirm(home["child"], action.id)
    actions.cancel(home["parent"], action.id)
    assert PendingAction.objects.get().status == PendingAction.Status.CANCELLED


def test_shopping_lines_are_added_at_once_and_can_be_undone(home, fake):
    fake(
        Turn(
            text="",
            tool_calls=[
                ToolCall(
                    "1", "add_to_shopping_list", {"items": [{"name": "Mleko", "quantity": "2 l"}]}
                )
            ],
        ),
        Turn(text="Dodane.", tool_calls=[]),
    )
    _, answer = ask(home["parent"], "dopisz mleko")
    action = answer.actions.get()
    assert action.auto and action.status == PendingAction.Status.DONE
    assert ShoppingEntry.objects.filter(name="Mleko").exists()
    actions.undo(home["parent"], action.id)
    assert not ShoppingEntry.objects.exists()


def test_tool_not_offered_cannot_be_called(home, fake):
    model = fake(
        Turn(text="", tool_calls=[ToolCall("1", "cabinet_find", {"query": "gorączka"})]),
        Turn(text="Nie mam dostępu.", tool_calls=[]),
    )
    ask(home["parent"], "co na gorączkę?")  # cloud model: health is local-only
    result = model.sessions[0].results[0][0]
    assert result.is_error and "not available" in result.content


def test_photos_respect_the_documents_policy_and_vision(home, fake):
    photo = SimpleUploadedFile("paragon.jpg", b"\xff\xd8\xff", content_type="image/jpeg")
    settings = AISettings.objects.get(pk=1)
    settings.policies = {"documents": "local"}
    settings.save()
    _, answer = ask(home["parent"], "dodaj tankowanie", files=[photo])
    assert answer.error and "zdjęć" in answer.text

    settings.policies = {"documents": "cloud"}
    settings.save()
    model = fake(Turn(text="Widzę paragon.", tool_calls=[]))
    photo.seek(0)
    _, answer = ask(home["parent"], "dodaj tankowanie", files=[photo])
    assert not answer.error
    assert model.sessions[0].history[-1].images[0].mime == "image/jpeg"


def test_conversations_are_private(home, fake, client):
    fake(Turn(text="ok", tool_calls=[]))
    conv, _ = ask(home["parent"], "hej")
    with pytest.raises(Http404):
        services.send_message(home["child"], conv.id, text="podgląd?")
    client.force_login(UserFactory(is_superuser=True))  # not even an admin
    assert client.get(f"/api/assistant/conversations/{conv.id}/messages").status_code == 404


def test_api_send_and_see_what_was_sent(home, fake, client):
    fake(Turn(text="Cześć!", tool_calls=[]))
    client.force_login(home["parent_user"])
    conv = client.post("/api/assistant/conversations", {}, content_type="application/json").json()
    resp = client.post(
        f"/api/assistant/conversations/{conv['id']}/messages",
        {"text": "hej Zosia", "page": "/cars"},
    )
    assert resp.status_code == 200, resp.content
    answer = resp.json()["answer"]
    assert answer["text"] == "Cześć!" and answer["has_calls"]
    [call] = client.get(f"/api/assistant/messages/{answer['id']}/calls").json()
    assert call["provider"] == "anthropic" and call["location"] == "cloud"
    assert "Zosia" not in str(call["sent"]) and "Samochody" in str(call["sent"])


def test_settings_are_admin_only_and_keys_never_returned(home, client):
    with pytest.raises(PermissionDenied):
        services.save_settings(home["parent"], {"policies": {"health": "cloud"}})
    client.force_login(UserFactory(is_superuser=True))
    body = client.get("/api/assistant/settings").json()
    claude = next(p for p in body["profiles"] if p["name"] == "Claude")
    assert claude["has_key"] is True and "api_key" not in claude
    resp = client.put(
        "/api/assistant/settings",
        {"policies": {"health": "cloud"}},
        content_type="application/json",
    )
    assert resp.json()["policies"]["health"] == "cloud"
    bad = client.put(
        "/api/assistant/settings",
        {"policies": {"health": "everywhere"}},
        content_type="application/json",
    )
    assert bad.status_code == 422
    # the private-conversation model has to be a local one
    resp = client.put(
        "/api/assistant/settings",
        {"local_profile_id": str(home["cloud"].id)},
        content_type="application/json",
    )
    assert resp.status_code == 422
