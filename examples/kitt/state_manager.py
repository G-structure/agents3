import asyncio
import json
import logging
from datetime import datetime
from typing import List, Optional

from livekit import agents, rtc
from livekit.agents.llm import ChatMessage, ChatRole
from chat_manager import ChatNode, LoomManager, ChatManager
from character_manager import CharacterManager

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
        self._character_manager = CharacterManager()
        # self._loom_manager.add_message(message=ChatMessage(role=ChatRole.SYSTEM, text=prompt), new_root=True)

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
        try:
            return self._loom_manager.get_current_chat_history()
        except Exception as e:
            logging.error(f"Error initializing database: {e}")


    def update_character(self, payload):
        try:
            if not self._character_manager.character_loaded:
                self._character_manager.update_from_card(payload)
                logging.info("Character card set.")
                self._loom_manager.character_id=self._character_manager.id
                self._loom_manager.add_starting_message(message=ChatMessage(role=ChatRole.SYSTEM, text=self._character_manager.character_prompt))
                messages = self._character_manager.starting_messages
                if len(messages) > 1:
                    for i, message in enumerate(messages[:-1]):  # Iterate through all but the last message
                        role = ChatRole.USER if i % 2 == 0 else ChatRole.ASSISTANT
                        original_node = self._loom_manager.current_node
                        self._loom_manager.add_starting_message(message=ChatMessage(role=role, text=message), parent_id=original_node.id)
                    last_message = messages[-1]  # Handle the last message separately
                else:
                    last_message = messages[0] if messages else None  # Handle the case with only one message

                # Here you can return the last_message or only message, or do additional processing if needed
                return last_message, self._character_manager.base_model
            else:
                logging.info("Character card already set.")
        except Exception as e:
            logging.error(f"Error updating character: {e}")

    def get_character(self) -> CharacterManager:
        return self._character_manager
        
    def store_user_char(self, chat_text: str):
        try:
            logging.info("Committing user chat: %s", chat_text)
            msg = ChatMessage(role=ChatRole.USER, text=chat_text)
            original_node = self._loom_manager.current_node
            node = self._loom_manager.add_message(msg, parent_id = original_node.id)
            asyncio.create_task(
                self.send_complete_node_tree()
            )
        except Exception as e:
            logging.error(f"Error store_user_char: {e}")


    def commit_user_transcription(self, transcription: str):
        try:
            logging.info("Committing user transcription: %s", transcription)
            msg = ChatMessage(role=ChatRole.USER, text=transcription)
            original_node = self._loom_manager.current_node
            node = self._loom_manager.add_message(msg, parent_id = original_node.id)
            asyncio.create_task(
                self._chat_manager.send_message(node=node)
            )
            asyncio.create_task(
                self.send_complete_node_tree()
            )
        except Exception as e:
            logging.error(f"Error commit_user_transcription: {e}")

    def commit_agent_response(self, response: str):
        try:
            logging.info("Committing agent response: %s", response)
            msg = ChatMessage(role=ChatRole.ASSISTANT, text=response)
            original_node = self._loom_manager.current_node
            node = self._loom_manager.add_message(msg, parent_id = original_node.id)
            asyncio.create_task(
                self._chat_manager.send_message(node=node)
            )
            asyncio.create_task(
                self.send_complete_node_tree()
            )
        except Exception as e:
            logging.error(f"Error commit_agent_response: {e}")
    
    # def commit_alt_reponse(self, response: str, node_id: str):
    #     logging.info("For parent_id: %s, committing alt response: %s", node_id, response)
    #     orginal_node = self._loom_manager.nodes_by_id.get(node_id)
    #     msg = ChatMessage(role=orginal_node.message.role, text=response)
    #     node = self._loom_manager.add_message(msg, parent_id=orginal_node.parent_id)
    #     node_tree = self._loom_manager.collect_child_nodes(self._loom_manager.current_node.id)
    #     asyncio.create_task(
    #         self._chat_manager.send_current_node_history(node_tree)
    #     )

    def change_active_node(self, node_id: str):
        try:
            print("Changing active node to ID: %s", node_id)
            node = self._loom_manager.set_current_node(node_id)
            node_history = self._loom_manager.get_current_node_history()
            asyncio.create_task(
                self._chat_manager.send_current_node_history(node_history)
            )
        except Exception as e:
            logging.error(f"Error change_active_node: {e}")
    
    def roll_back_to_parent(self, node_id: str) -> Optional[str]:
        """Changes the active node to the parent of the specified node.

        Args:
            node_id (str): The ID of the node whose parent will become the active node.

        Returns:
            Optional[str]: The ID of the parent node if found, None otherwise.
        """
        try:
            original_node = self._loom_manager.get_nodes_by_id().get(node_id)
            parent_node = self._loom_manager.get_nodes_by_id().get(original_node.parent_id)
            if original_node and parent_node:
                print(parent_node.id)
                self.change_active_node(parent_node.id)
                return parent_node.message.text
            return None
        except Exception as e:
            logging.error(f"Error roll_back_to_parent: {e}")

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

    async def send_complete_node_tree(self):
        """Grabs all nodes from the LoomManager and sends the complete node tree to the client."""
        try:
            all_nodes = self._loom_manager.collect_all_nodes()
            asyncio.create_task(
                self._chat_manager.send_node_tree(all_nodes)
            )
        except Exception as e:
            logging.error(f"Error send_complete_node_tree: {e}")
