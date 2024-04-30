from __future__ import annotations

import asyncio
import logging
import uuid
from enum import Enum
from typing import List

from attr import define
from livekit import agents, rtc
from livekit.agents.llm import ChatContext, ChatMessage, ChatRole
from livekit.plugins.openai import LLM
import openai

class CanvasJob:
    def __init__(
        self,
        chat_history: List[ChatMessage],
        llm_model: str,
        prompt: str,
    ):
        self._id = uuid.uuid4()
        self._current_response = ""
        self._chat_history = chat_history
        self._llm = LLM(client=openai.AsyncOpenAI(base_url="https://openrouter.ai/api/v1"), model=llm_model)
        self._run_task = asyncio.create_task(self._run())
        self._output_queue = asyncio.Queue[rtc.AudioFrame | None]()
        self._finished_generating = False
        self._event_queue = asyncio.Queue[Event | None]()
        self._done_future = asyncio.Future()
        self._cancelled = False
        self.prompt = prompt

    @property
    def id(self):
        return self._id

    @property
    def current_response(self):
        return self._current_response

    @current_response.setter
    def current_response(self, value: str):
        self._current_response = value
        if not self._cancelled:
            self._event_queue.put_nowait(
                Event(
                    type=EventType.AGENT_RESPONSE,
                    finished_generating=self.finished_generating,
                )
            )

    @property
    def finished_generating(self):
        return self._finished_generating

    @finished_generating.setter
    def finished_generating(self, value: bool):
        self._finished_generating = value
        if not self._cancelled:
            self._event_queue.put_nowait(
                Event(
                    finished_generating=value,
                    type=EventType.AGENT_RESPONSE,
                )
            )

    async def acancel(self):
        logging.info("Cancelling inference job")
        self._cancelled = True
        self._run_task.cancel()
        await self._done_future
        logging.info("Cancelled inference job")


    async def _run(self):
        logging.info(
            "Running inference for canvas generation: %s", self.prompt
        )
        try:
            await asyncio.gather(
                self._llm_task(),
            )
        except asyncio.CancelledError:
            # Flush audio packets
            while True:
                try:
                    self._output_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            self._output_queue.put_nowait(None)
        except Exception as e:
            logging.exception("Exception in canvas generation %s", e)

    async def _llm_task(self):

        chat_context = ChatContext(
            messages=self._chat_history
            + [ChatMessage(role=ChatRole.USER, text=self.prompt)]
        )

        async for chunk in await self._llm.chat(history=chat_context):
            delta = chunk.choices[0].delta.content
            if delta is None:
                break
            self.current_response += delta
        self.finished_generating = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        e = await self._event_queue.get()
        if e is None:
            raise StopAsyncIteration
        return e

class EventType(Enum):
    AGENT_RESPONSE = 1

@define(kw_only=True)
class Event:
    type: EventType
    finished_generating: bool