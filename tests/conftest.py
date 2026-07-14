from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace

import pytest


class FakeChatOpenAI:
    instances: list["FakeChatOpenAI"] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.args = args
        self.kwargs = kwargs
        self.bound_tools: list[object] = []
        self.calls: list[object] = []
        type(self).instances.append(self)

    def bind_tools(self, tools: list[object]) -> "FakeChatOpenAI":
        self.bound_tools = list(tools)
        return self

    async def ainvoke(self, messages: object) -> SimpleNamespace:
        self.calls.append(messages)
        if self.bound_tools:
            return SimpleNamespace(content="", tool_calls=[])
        return SimpleNamespace(content="Mocked frontier response", tool_calls=[])


@pytest.fixture
def event_loop() -> asyncio.AbstractEventLoop:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.run_until_complete(loop.shutdown_asyncgens())
    loop.close()
    asyncio.set_event_loop(None)


@pytest.fixture(autouse=True)
def mock_chat_openai(monkeypatch: pytest.MonkeyPatch) -> type[FakeChatOpenAI]:
    FakeChatOpenAI.instances.clear()
    fake_module = types.ModuleType("langchain_openai")
    fake_module.ChatOpenAI = FakeChatOpenAI
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_module)
    return FakeChatOpenAI
