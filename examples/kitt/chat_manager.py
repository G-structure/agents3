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
import sqlite3
from typing import Union
import uuid

_CHAT_TOPIC = "lk-chat-topic"
_CHAT_UPDATE_TOPIC = "lk-chat-update-topic"
_CHAT_HISTORY_UPDATE_TOPIC = "lk-chat-history-update-topic"
_NODE_TREE_INIT_TOPIC = "lk-node-tree-init-topic"
_NODE_TREE_UPDATE_TOPIC = "lk-node-tree-update-topic"

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
        self.alt_ids: List[str] = []

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
            "alt_ids": self.alt_ids, 
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

        self.db_name = 'chat_nodes.db'
        self.init_db()

    def init_db(self):
        """Initializes the database and creates the chat_nodes table if it doesn't exist."""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS chat_nodes (
                        id TEXT PRIMARY KEY,
                        timestamp INTEGER,
                        deleted BOOLEAN,
                        is_assistant BOOLEAN,
                        highlight_word_count INTEGER,
                        participant TEXT,
                        parent_id TEXT,
                        conversation_id TEXT,
                        character_id TEXT,
                        model TEXT,
                        type TEXT,
                        message TEXT,
                        alt_ids TEXT
                    );
                ''')
                conn.commit()
        except Exception as e:
            logging.error(f"Error initializing database: {e}")

    def get_nodes_by_id(self) -> Dict[str, ChatNode]:
        try:
            nodes_by_id = {}
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM chat_nodes WHERE character_id = ?', (self.character_id,))
                for row in cursor.fetchall():
                    node = ChatNode(
                        message=ChatMessage(text=row[11], role=ChatRole.USER),  # Assuming ChatMessage can be reconstructed this way
                        parent_id=row[6],
                        conversation_id=row[7],
                        character_id=row[8],
                        model=row[9],
                        type=row[10]
                    )
                    node.id = row[0]
                    node.timestamp = datetime.fromtimestamp(row[1])
                    node.deleted = row[2]
                    node.is_assistant = row[3]
                    node.highlight_word_count = row[4]
                    node.participant = row[5]
                    node.alt_ids = json.loads(row[12])  # Assuming alt_ids is stored as a JSON string
                    nodes_by_id[node.id] = node
            return nodes_by_id
        except Exception as e:
            logging.error(f"Error get_nodes_by_id database: {e}")

    def add_chat_node_to_db(self, node: ChatNode):
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO chat_nodes (id, timestamp, deleted, is_assistant, highlight_word_count, participant, parent_id, conversation_id, character_id, model, type, message, alt_ids)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    node.id, 
                    int(node.timestamp.timestamp()), 
                    node.deleted, 
                    node.is_assistant, 
                    node.highlight_word_count, 
                    node.participant, 
                    node.parent_id, 
                    node.conversation_id, 
                    node.character_id, 
                    node.model, 
                    node.type, 
                    node.message.text, 
                    json.dumps(node.alt_ids)
                ))
                conn.commit()
        except Exception as e:
            logging.error(f"Error add_chat_node_to_db database: {e}")
    
    def update_sibling_alt_ids(self, sibling_ids: List[str], new_node_id: str):
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                for sibling_id in sibling_ids:
                    cursor.execute('SELECT alt_ids FROM chat_nodes WHERE id = ?', (sibling_id,))
                    row = cursor.fetchone()
                    if row:
                        alt_ids = json.loads(row[0])
                        alt_ids.append(new_node_id)
                        cursor.execute('UPDATE chat_nodes SET alt_ids = ? WHERE id = ?', (json.dumps(alt_ids), sibling_id))
                conn.commit()
        except Exception as e:
            logging.error(f"Error update_sibling_alt_ids database: {e}")

    def add_message(self, message: ChatMessage, parent_id: Optional[str] = None, character_id: Optional[str] = None, model: str = "default_model", type: str = "chat", new_root: bool = False) -> ChatNode:
        try:
            if character_id is None:
                character_id = self.character_id

            new_node = ChatNode(message, parent_id, self.conversation_id, character_id, model, type)

            if not new_root and parent_id is not None:
                sibling_ids = [node.id for node in self.get_children_of_parent(parent_id)]
                self.update_sibling_alt_ids(sibling_ids, new_node.id)
                for sibling_id in sibling_ids:
                    new_node.alt_ids.append(sibling_id)

            new_node.alt_ids.append(new_node.id)  # Ensure the node's own ID is in its alt_ids
            self.add_chat_node_to_db(new_node)
            self.set_current_node(new_node.id)  # Update the current node reference
            return new_node
        except Exception as e:
            logging.error(f"Error adding message: {e}")

    def add_starting_message(self, message: ChatMessage, parent_id: Optional[str] = None, character_id: Optional[str] = None, model: str = "default_model", type: str = "chat") -> ChatNode:
        """
        Adds a starting message to the chat nodes database if it does not already exist.
        If the message already exists (based on text, character_id, and parent_id), it reuses the existing ChatNode.
        Additionally, if an existing node with no parent_id is found, it is appended to the root_nodes list.

        Args:
            message (ChatMessage): The message to add.
            parent_id (Optional[str]): The ID of the parent node, if any.
            character_id (Optional[str]): The character ID associated with the message. Defaults to the LoomManager's character_id if None.
            model (str): The model used for generating the message.
            type (str): The type of the message.

        Returns:
            ChatNode: The new or existing ChatNode.
        """
        try:
            if character_id is None:
                character_id = self.character_id

            existing_node = self.find_existing_node(message.text, parent_id, character_id)
            if existing_node:
                if existing_node.parent_id is None:
                    if existing_node not in self.root_nodes:
                        self.root_nodes.append(existing_node)  # Ensure the existing node is in the root_nodes list if it has no parent
                self.set_current_node(existing_node.id)  # Update the current node reference to the existing node
                return existing_node

            # If no existing node is found, proceed to add a new one.
            new_node = ChatNode(message, parent_id, self.conversation_id, character_id, model, type)
            self.add_chat_node_to_db(new_node)
            if parent_id is None:
                self.root_nodes.append(new_node)  # Add to root nodes if no parent_id is specified
            self.set_current_node(new_node.id)  # Update the current node reference to the new node
            return new_node
        except Exception as e:
            logging.error(f"Error add_starting_message: {e}")

    def find_existing_node(self, message_text: str, parent_id: Optional[str], character_id: str) -> Optional[ChatNode]:
        """
        Searches for an existing ChatNode based on message text, parent_id, and character_id.

        Args:
            message_text (str): The text of the message to search for.
            parent_id (Optional[str]): The parent ID of the node, if any.
            character_id (str): The character ID associated with the message.

        Returns:
            Optional[ChatNode]: The found ChatNode if it exists, otherwise None.
        """
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                if parent_id:
                    query = '''SELECT * FROM chat_nodes WHERE character_id = ? AND parent_id = ? AND message = ?'''
                    cursor.execute(query, (character_id, parent_id, message_text))
                else:
                    query = '''SELECT * FROM chat_nodes WHERE character_id = ? AND parent_id IS NULL AND message = ?'''
                    cursor.execute(query, (character_id, message_text))
                row = cursor.fetchone()
                if row:
                    node = ChatNode(
                        message=ChatMessage(text=row[11], role=ChatRole.USER),  # Assuming ChatMessage can be reconstructed this way
                        parent_id=row[6],
                        conversation_id=row[7],
                        character_id=row[8],
                        model=row[9],
                        type=row[10]
                    )
                    node.id = row[0]
                    node.timestamp = datetime.fromtimestamp(row[1] / 1000)
                    node.deleted = row[2]
                    node.is_assistant = row[3]
                    node.highlight_word_count = row[4]
                    node.participant = row[5]
                    node.alt_ids = json.loads(row[12])  # Assuming alt_ids is stored as a JSON string
                    return node
            return None
        except Exception as e:
            logging.error(f"Error find_existing_node database: {e}")

    def get_children_of_parent(self, parent_id: str) -> List[ChatNode]:
        try:
            return [node for node in self.get_nodes_by_id().values() if node.parent_id == parent_id]
        except Exception as e:
            logging.error(f"Error initializing database: {e}")

    def collect_all_nodes(self) -> List[ChatNode]:
        """Collects all nodes, starting from the root nodes and including all their descendants.

        Returns:
            List[ChatNode]: A list of all ChatNode objects in the tree.
        """
        try:
            all_nodes = []
            for root_node in self.get_root_nodes():
                all_nodes.extend(self.collect_child_nodes(root_node.id))
            return all_nodes
        except Exception as e:
            logging.error(f"Error initializing database: {e}")

    def get_current_chat_history(self) -> List[ChatMessage]:
        try:
            if self.current_node:
                history = []
                node = self.current_node
                while node:
                    history.append(node.message)
                    node = self.get_nodes_by_id().get(node.parent_id)
                return list(reversed(history))
            return []
        except Exception as e:
            logging.error(f"Error collect_all_nodes: {e}")
    
    def get_current_node_history(self) -> List[ChatNode]:
        """
        Retrieves the history of chat nodes leading up to the current node.
        
        Returns:
            List[ChatNode]: A list of ChatNode objects from the root to the current node, in chronological order.
        """
        try:
            if self.current_node:
                history_nodes = []
                node = self.current_node
                while node:
                    history_nodes.append(node)
                    node = self.get_nodes_by_id().get(node.parent_id)
                return list(reversed(history_nodes))
            return []
        except Exception as e:
            logging.error(f"Error retrieving node history: {e}")

    def set_current_node(self, node_id: str) -> bool:
        try:
            node = self.get_nodes_by_id().get(node_id)
            if node:
                self.current_node = node
                return True
            return False
        except Exception as e:
            logging.error(f"Error get_current_node_history: {e}")

    def get_root_nodes(self) -> List[ChatNode]:
        try:
            return self.root_nodes
        except Exception as e:
            logging.error(f"Error get_root_nodes: {e}")
    
    def get_parent_node(self, node_id: str) -> Optional[ChatNode]:
        try:
            node = self.get_nodes_by_id().get(node_id)
            if node and node.parent_id:
                return self.get_nodes_by_id().get(node.parent_id)
            return None
        except Exception as e:
            logging.error(f"Error get_parent_node: {e}")
    
    def update_node(self, node_id: str, text: Optional[str] = None, model: Optional[str] = None, type: Optional[str] = None, character_id: Optional[str] = None) -> bool:
        try:
            node = self.get_nodes_by_id().get(node_id)
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
        except Exception as e:
            logging.error(f"Error update_node: {e}")

    def collect_child_nodes(self, node_id: str) -> List[ChatNode]:
        """Recursively collects all child nodes of a given node ID."""
        try:
            nodes_to_send = []
            node = self.get_nodes_by_id().get(node_id)
            if node:
                nodes_to_send.append(node)
                child_nodes = self.get_children_of_parent(node_id)
                for child_node in child_nodes:
                    nodes_to_send.extend(self.collect_child_nodes(child_node.id))
            return nodes_to_send
        except Exception as e:
            logging.error(f"Error collect_child_nodes: {e}")
    
class ChatManager():
    """A utility class that sends and receives chat nodes in the active session.

    It implements LiveKit Chat Protocol, and serializes data to/from JSON data packets.
    """

    def __init__(self, room: Room):
        self._lp = room.local_participant
        self._room = room
        self.nodes_by_id: Dict[str, ChatNode] = {}

    async def send_message(self, node: ChatNode):
        """Send a chat node to the end user using LiveKit Chat Protocol.

        Args:
            node (ChatNode): the chat node to send

        This method does not return a value. It sends the provided chat node to the end user
        by publishing it to a specific topic using the LiveKit Chat Protocol.
        """
        try:
            await self._lp.publish_data(
                payload=json.dumps(node.asjsondict()),
                kind=DataPacketKind.KIND_RELIABLE,
                topic=_CHAT_TOPIC,
            )
        except Exception as e:
            logging.error(f"Error send_message: {e}")


    async def update_message(self, node_id: str):
        """Update a chat node that was previously sent.

        If node.deleted is set to True, we'll signal to remote participants that the node
        should be deleted.
        """
        try:
            node = self.nodes_by_id.get(node_id)
            if not node:
                logging.warning("Node with ID %s not found for update", node_id)
                return

            await self._lp.publish_data(
                payload=json.dumps(node.asjsondict()),
                kind=DataPacketKind.KIND_RELIABLE,
                topic=_CHAT_UPDATE_TOPIC,
            )
        except Exception as e:
            logging.error(f"Error update_message: {e}")

    async def send_current_node_history(self, nodes_to_send: List[ChatNode]):
        """Sends the entire chat node history as a single data structure.

        Args:
            nodes_to_send (List[ChatNode]): The list of ChatNode objects to send.
        """
        try:
            if not nodes_to_send:
                logging.warning("No nodes provided to send.")
                return

            node_history_data = [node.asjsondict() for node in nodes_to_send]

            await self._lp.publish_data(
                payload=json.dumps({"nodes": node_history_data}),
                kind=DataPacketKind.KIND_RELIABLE,
                topic=_CHAT_HISTORY_UPDATE_TOPIC,
            )
        except Exception as e:
            logging.error(f"Error send_current_node_history: {e}")

    async def send_node_tree(self, nodes_to_send: List[ChatNode], chunk_size: int = 25):
        try:
            if not nodes_to_send:
                logging.warning("No nodes provided to send.")
                return

            total_nodes = len(nodes_to_send)
            total_chunks = (total_nodes + chunk_size - 1) // chunk_size
            tree_id = str(uuid.uuid4())

            for i in range(total_chunks):
                start_index = i * chunk_size
                end_index = min((i + 1) * chunk_size, total_nodes)
                chunk_nodes = nodes_to_send[start_index:end_index]

                node_tree_data = [node.asjsondict() for node in chunk_nodes]

                await self._lp.publish_data(
                    payload=json.dumps({
                        "nodes": node_tree_data,
                        "chunk": i + 1,
                        "total_chunks": total_chunks,
                        "tree_id": tree_id
                    }),
                    kind=DataPacketKind.KIND_LOSSY,
                    topic=_NODE_TREE_INIT_TOPIC,
                )
        except Exception as e:
            logging.error(f"Error sending node tree: {e}")
    
    async def send_update_node_tree(self, node: ChatNode):
        try:
            # Convert the single ChatNode to its JSON dictionary representation
            node_data = node.asjsondict()

            # Send the node data to the client using the LiveKit Chat Protocol
            await self._lp.publish_data(
                payload=json.dumps(node_data),
                kind=DataPacketKind.KIND_LOSSY,
                topic=_NODE_TREE_UPDATE_TOPIC,
            )
        except Exception as e:
            logging.error(f"Error sending update node tree: {e}")