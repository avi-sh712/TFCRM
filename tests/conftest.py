from __future__ import annotations

import asyncio
import os
import sys
import types
from types import SimpleNamespace

import pytest


os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://talentforge_test:talentforge_test@localhost:5432/talentforge_test",
)
os.environ.setdefault("JWT_SECRET_KEY", "t" * 48)
os.environ.setdefault("WEBHOOK_SECRET_TOKEN", "w" * 48)


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
