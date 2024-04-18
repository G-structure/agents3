from datetime import datetime
from typing import Dict, List, Optional

from livekit.agents.llm import ChatMessage, ChatRole
from livekit.rtc._utils import generate_random_base62

import json
import logging
from typing import Any, Callable, Dict, Literal, Optional

from livekit.rtc import Room, Participant, DataPacket
from livekit.rtc._event_emitter import EventEmitter
from livekit.rtc._proto.room_pb2 import DataPacketKind

_CHAT_TOPIC = "lk-chat-topic"
_CHAT_UPDATE_TOPIC = "lk-chat-update-topic"

EventTypes = Literal["message_received",]

class ChatNode:
    def __init__(self, message: ChatMessage, parent_id: Optional[str] = None, conversation_id: str = "", character_id: Optional[str] = None, model: str = "", type: str = "chat"):
        self.id: str = generate_random_base62()
        self.timestamp: datetime = datetime.now()
        self.deleted: bool = False
        self.is_assistant: bool = message.role == ChatRole.ASSISTANT
        self.highlight_word_count: int = 0
        self.participant: Optional[str] = None
        self.parent_id: Optional[str] = parent_id
        self.conversation_id: str = conversation_id
        self.character_id: Optional[str] = character_id
        self.model: str = model
        self.type: str = type
        self.message: ChatMessage = message
        self.children: List['ChatNode'] = []

    def asjsondict(self):
        """Returns a JSON serializable dictionary representation of the node."""
        return {
            "id": self.id,
            "message": self.message.text,
            "timestamp": int(self.timestamp.timestamp() * 1000),
            "deleted": self.deleted,
            "is_assistant": self.is_assistant,
            "highlight_word_count": self.highlight_word_count,
            "participant": self.participant,
            "parent_id": self.parent_id,
            "conversation_id": self.conversation_id,
            "character_id": self.character_id,
            "model": self.model,
            "type": self.type,
            "children_ids": [child.id for child in self.children]
        }

class LoomManager:
    def __init__(self, conversation_id: Optional[str] = None, character_id: Optional[str] = None):
        if conversation_id is None:
            conversation_id = generate_random_base62()
        self.conversation_id: str = conversation_id
        
        if character_id is None:
            character_id = generate_random_base62()
        self.character_id: Optional[str] = character_id

        self.root_nodes: List[ChatNode] = []
        self.current_node: Optional[ChatNode] = None
        self.nodes_by_id: Dict[str, ChatNode] = {}

    def add_message(self, message: ChatMessage, parent_id: Optional[str] = None, character_id: Optional[str] = None, model: str = "default_model", type: str = "chat", new_root: bool = False) -> ChatNode:
        if character_id is None:
            character_id = self.character_id

        new_node = ChatNode(message, parent_id, self.conversation_id, character_id, model, type)
        if new_root or (parent_id is None and self.current_node is None):
            self.root_nodes.append(new_node)
        else:
            parent_node = self.nodes_by_id.get(parent_id)
            if parent_node:
                parent_node.children.append(new_node)
        self.nodes_by_id[new_node.id] = new_node
        return new_node

    def get_children_of_parent(self, parent_id: str) -> List[ChatNode]:
        parent_node = self.nodes_by_id.get(parent_id)
        if parent_node:
            return parent_node.children
        return []

    def get_current_chat_history(self) -> List[ChatMessage]:
        if self.current_node:
            history = []
            node = self.current_node
            while node:
                history.append(node.message)
                node = self.nodes_by_id.get(node.parent_id)
            return list(reversed(history))
        return []

    def set_current_node(self, node_id: str) -> bool:
        node = self.nodes_by_id.get(node_id)
        if node:
            self.current_node = node
            return True
        return False

    def get_root_nodes(self) -> List[ChatNode]:
        return self.root_nodes
    
    def get_parent_node(self, node_id: str) -> Optional[ChatNode]:
        node = self.nodes_by_id.get(node_id)
        if node and node.parent_id:
            return self.nodes_by_id.get(node.parent_id)
        return None
    
    def update_node(self, node_id: str, text: Optional[str] = None, model: Optional[str] = None, type: Optional[str] = None, character_id: Optional[str] = None) -> bool:
        node = self.nodes_by_id.get(node_id)
        if not node:
            return False

        if text is not None:
            node.message.text = text

        if model is not None:
            node.model = model

        if type is not None:
            node.type = type

        if character_id is not None:
            node.character_id = character_id

        return True
    
class ChatManager(EventEmitter[EventTypes]):
    """A utility class that sends and receives chat nodes in the active session.

    It implements LiveKit Chat Protocol, and serializes data to/from JSON data packets.
    """

    def __init__(self, room: Room):
        super().__init__()
        self._lp = room.local_participant
        self._room = room
        self.nodes_by_id: Dict[str, ChatNode] = {}

        room.on("data_received", self._on_data_received)

    def close(self):
        self._room.off("data_received", self._on_data_received)

    async def send_message(self, node: ChatNode):
        """Send a chat node to the end user using LiveKit Chat Protocol.

        Args:
            node (ChatNode): the chat node to send

        This method does not return a value. It sends the provided chat node to the end user
        by publishing it to a specific topic using the LiveKit Chat Protocol.
        """
        
        await self._lp.publish_data(
            payload=json.dumps(node.asjsondict()),
            kind=DataPacketKind.KIND_RELIABLE,
            topic=_CHAT_TOPIC,
        )

    async def update_message(self, node_id: str):
        """Update a chat node that was previously sent.

        If node.deleted is set to True, we'll signal to remote participants that the node
        should be deleted.
        """
        node = self.nodes_by_id.get(node_id)
        if not node:
            logging.warning("Node with ID %s not found for update", node_id)
            return

        await self._lp.publish_data(
            payload=json.dumps(node.asjsondict()),
            kind=DataPacketKind.KIND_RELIABLE,
            topic=_CHAT_UPDATE_TOPIC,
        )

    # def on_message(self, callback: Callable[[ChatNode], None]):
    #     """Register a callback to be called when a chat node is received from the end user."""
    #     self._callback = callback

    # # TODO we must fix this
    # def _on_data_received(self, dp: DataPacket):
    #     if dp.topic == _CHAT_TOPIC or dp.topic == _CHAT_UPDATE_TOPIC:
    #         try:
    #             parsed = json.loads(dp.data)
    #             # Assuming ChatNode has a from_jsondict class method to reconstruct the node
    #             node = ChatNode.from_jsondict(parsed)
    #             if dp.participant:
    #                 node.participant = dp.participant.sid  # Assuming Participant has a sid attribute
    #             self.emit("message_received", node)
    #         except Exception as e:
    #             logging.warning("failed to parse chat node: %s", e, exc_info=e)