import asyncio
import json
import logging
from datetime import datetime
from typing import List

from livekit import agents, rtc
from livekit.agents.llm import ChatMessage, ChatRole
from chat_manager import ChatNode, LoomManager, ChatManager

class StateManager:
    """Helper class to update the UI for the Agent Playground."""

    def __init__(self, room: rtc.Room, prompt: str):
        self._room = room
        self._agent_speaking = False
        self._agent_thinking = False
        self._current_transcription = ""
        self._current_response = ""
        self._chat_manager = ChatManager(room)
        self._loom_manager = LoomManager()

        self._loom_manager.add_message(message=ChatMessage(role=ChatRole.SYSTEM, text=prompt), new_root=True)

    @property
    def agent_speaking(self):
        self._update_state()

    @agent_speaking.setter
    def agent_speaking(self, value: bool):
        self._agent_speaking = value
        self._update_state()

    @property
    def agent_thinking(self):
        self._update_state()

    @agent_thinking.setter
    def agent_thinking(self, value: bool):
        self._agent_thinking = value
        self._update_state()

    @property
    def chat_history(self):
        return self._loom_manager.get_current_chat_history()
    
    def store_user_char(self, chat_text: str):
        logging.info("Committing user chat: %s", chat_text)
        msg = ChatMessage(role=ChatRole.USER, text=chat_text)
        node = self._loom_manager.add_message(msg)

    def commit_user_transcription(self, transcription: str):
        logging.info("Committing user transcription: %s", transcription)
        msg = ChatMessage(role=ChatRole.USER, text=transcription)
        node = self._loom_manager.add_message(msg)
        asyncio.create_task(
            self._chat_manager.send_message(node=node)
        )

    def commit_agent_response(self, response: str):
        logging.info("Committing agent response: %s", response)
        msg = ChatMessage(role=ChatRole.ASSISTANT, text=response)
        node = self._loom_manager.add_message(msg)
        asyncio.create_task(
            self._chat_manager.send_message(node=node)
        )

    def _update_state(self):
        state = "listening"
        if self._agent_speaking:
            state = "speaking"
        elif self._agent_thinking:
            state = "thinking"
        asyncio.create_task(
            self._room.local_participant.update_metadata(
                json.dumps({"agent_state": state})
            )
        )
