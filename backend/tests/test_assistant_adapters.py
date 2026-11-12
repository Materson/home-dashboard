"""Provider adapters build the right requests and read responses back —
with fake SDK clients (no network). Gemini responses use the SDK's own types."""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace as NS

from google.genai import types

from apps.assistant.llm import ChatMessage, Image, ToolResult, ToolSpec
from apps.assistant.llm.anthropic_adapter import FALLBACK_BETA, AnthropicAdapter
from apps.assistant.llm.google_adapter import GoogleAdapter
from apps.assistant.llm.openai_adapter import OpenAIAdapter

TOOLS = [ToolSpec("cars_status", "Car status", {"type": "object", "properties": {}})]
HISTORY = [ChatMessage("user", "Ile km do oleju?")]


class Recorder:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(
            copy.copy(kwargs) | {"messages_snapshot": copy.deepcopy(kwargs.get("messages"))}
        )
        return self.responses.pop(0)


# ---- Anthropic ----


def _anthropic_response(content, stop="end_turn"):
    return NS(content=content, stop_reason=stop, usage=NS(input_tokens=10, output_tokens=5))


def test_anthropic_tool_round_trip_with_fallbacks_and_effort():
    tool_use = NS(type="tool_use", id="tu_1", name="cars_status", input={})
    thinking = NS(type="thinking", thinking="", signature="sig")
    first = _anthropic_response([thinking, tool_use], "tool_use")
    second = _anthropic_response([NS(type="text", text="Za 1200 km.")])
    beta = Recorder(first, second)
    client = NS(beta=NS(messages=NS(create=beta)), messages=NS(create=Recorder()))
    session = AnthropicAdapter(api_key="k", model="claude-opus-5-5", client=client).start(
        "SYS", TOOLS, HISTORY
    )

    turn = session.step()
    assert [c.name for c in turn.tool_calls] == ["cars_status"]
    call = beta.calls[0]
    assert call["betas"] == [FALLBACK_BETA] and call["fallbacks"] == "default"
    assert call["output_config"] == {"effort": "medium"} and "thinking" not in call
    assert call["system"] == "SYS" and call["tools"][0]["input_schema"] == TOOLS[0].parameters

    session.add_tool_results([ToolResult(turn.tool_calls[0], '{"km_left": 1200}')])
    turn = session.step()
    assert turn.text == "Za 1200 km." and not turn.tool_calls
    sent = beta.calls[1]["messages_snapshot"]
    assert sent[1]["content"] is not None and sent[1]["content"][0].type == "thinking"  # unchanged
    assert sent[2]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "tu_1",
        "content": '{"km_left": 1200}',
        "is_error": False,
    }


def test_anthropic_older_model_without_effort_or_fallbacks():
    plain = Recorder(_anthropic_response([NS(type="text", text="ok")]))
    client = NS(beta=NS(messages=NS(create=Recorder())), messages=NS(create=plain))
    AnthropicAdapter(api_key="k", model="claude-haiku-4-5", client=client).start(
        "S", [], HISTORY
    ).step()
    assert "output_config" not in plain.calls[0] and "fallbacks" not in plain.calls[0]


def test_anthropic_refusal_and_files():
    beta = Recorder(_anthropic_response([], "refusal"))
    client = NS(beta=NS(messages=NS(create=beta)), messages=NS(create=Recorder()))
    history = [
        ChatMessage("user", "paragon", [Image("image/png", b"x"), Image("application/pdf", b"y")])
    ]
    turn = (
        AnthropicAdapter(api_key="k", model="claude-opus-5-5", client=client)
        .start("S", [], history)
        .step()
    )
    assert turn.refused
    blocks = beta.calls[0]["messages"][0]["content"]
    assert [b["type"] for b in blocks] == ["image", "document", "text"]


# ---- OpenAI / Ollama ----


def test_openai_tool_calls_and_results():
    tc = NS(id="c1", function=NS(name="cars_status", arguments='{"car": "Octavia"}'))
    first = NS(choices=[NS(message=NS(content=None, tool_calls=[tc], refusal=None))], usage=None)
    second = NS(
        choices=[NS(message=NS(content="Gotowe", tool_calls=None, refusal=None))], usage=None
    )
    rec = Recorder(first, second)
    client = NS(chat=NS(completions=NS(create=rec)))
    session = OpenAIAdapter(api_key="k", model="gpt-x", client=client).start("SYS", TOOLS, HISTORY)
    turn = session.step()
    assert turn.tool_calls[0].args == {"car": "Octavia"}
    assert rec.calls[0]["messages"][0] == {"role": "system", "content": "SYS"}
    assert "max_completion_tokens" in rec.calls[0]
    session.add_tool_results([ToolResult(turn.tool_calls[0], "{}")])
    assert session.step().text == "Gotowe"
    sent = rec.calls[1]["messages_snapshot"]
    assert sent[-1] == {"role": "tool", "tool_call_id": "c1", "content": "{}"}
    assert sent[-2]["tool_calls"][0]["function"]["name"] == "cars_status"


def test_ollama_defaults_to_the_local_url():
    adapter = OpenAIAdapter(api_key="", model="llama3", kind="ollama")
    assert "11434" in str(adapter.client.base_url)
    assert not adapter.official


# ---- Gemini ----


def _gemini(parts):
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(content=types.Content(role="model", parts=parts), finish_reason="STOP")
        ],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=7, candidates_token_count=3
        ),
    )


def test_gemini_function_calling_with_sdk_types():
    first = _gemini([types.Part.from_function_call(name="cars_status", args={"car": "Octavia"})])
    second = _gemini([types.Part.from_text(text="Za 1200 km.")])
    rec = Recorder(first, second)
    client = NS(models=NS(generate_content=rec))
    session = GoogleAdapter(api_key="k", model="gemini-x", client=client).start(
        "SYS", TOOLS, HISTORY
    )
    turn = session.step()
    assert turn.tool_calls[0].name == "cars_status" and turn.tool_calls[0].args == {
        "car": "Octavia"
    }
    assert turn.input_tokens == 7
    config = rec.calls[0]["config"]
    assert config.automatic_function_calling.disable is True
    assert config.tools[0].function_declarations[0].name == "cars_status"
    session.add_tool_results([ToolResult(turn.tool_calls[0], json.dumps({"km_left": 1200}))])
    assert session.step().text == "Za 1200 km."
    responses = [
        p.function_response
        for c in rec.calls[1]["contents"]
        for p in c.parts
        if p.function_response
    ]
    assert responses[0].response == {"result": {"km_left": 1200}}
    assert responses[0].name == "cars_status"
