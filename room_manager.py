from fastapi import WebSocket
from schemas import Message
import logging
import redis
import json

MESSAGE_HISTORY_LENGTH = 50

# logging for error tracking
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RoomManager:
    def __init__(self):
        """Initializes the RoomManager.
        
        The `rooms` dictionary will store connections on a per-room basis.
        e.g., {"room1": [websocket1, websocket2], "room2": [websocket3]}
        """
        self.rooms: dict[str, list[WebSocket]] = {}
        self.user_connections: dict[str, list[WebSocket]] = {}
        try:
            self.redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
            # Test connection
            self.redis_client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.warning(f"Redis not available, using in-memory storage: {e}")
            self.redis_client = None
            self.message_history = {}  # Fallback to in-memory storage
        

    async def connect(self, websocket: WebSocket, room_id: str, user_id: str):
        """client connects to a specific room."""
        await websocket.accept()

        if room_id not in self.rooms:
            self.rooms[room_id] = []

        self.rooms[room_id].append(websocket)
        logger.info(f"Client {websocket.client} connected to room '{room_id}'.")
        logger.info(f"Total clients in room '{room_id}': {len(self.rooms[room_id])}")

        if user_id not in self.user_connections:
            self.user_connections[user_id] = []     
        self.user_connections[user_id].append(websocket)   

    def disconnect(self, websocket: WebSocket, room_id: str, user_id: str):
        """A client disconnects from a specific room."""
        if room_id in self.rooms:
            if websocket in self.rooms[room_id]:
                self.rooms[room_id].remove(websocket)
                logger.info(f"Client {websocket.client} disconnected from '{room_id}'.")

                if not self.rooms[room_id]:
                    del self.rooms[room_id]
                    logger.info(f"Room '{room_id}' is now empty and has been closed.")
            else:
                logger.warning(f"Client {websocket.client} was not in room '{room_id}' during disconnect")
        else:
            logger.warning(f"Tried to disconnect from a non-existent room '{room_id}'")

        if user_id in self.user_connections:
            self.user_connections[user_id].remove(websocket)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]

    async def broadcast_to_room(self, room_id: str, message: Message):
        """Broadcasts a pydantic message object to all clients in a specified room."""
        if room_id not in self.rooms:
            logger.warning(f"Attempted to broadcast to non-existent room '{room_id}'")
            return

        json_message = message.model_dump_json()
        dead_connections = []

        
        for connection in self.rooms[room_id][:]:
            try: 
                await connection.send_text(json_message)
            except Exception as e:
                logger.warning(f"Failed to send message to client {connection.client}: {e}")
                dead_connections.append(connection)

        # Clean up dead connections
        for dead_connection in dead_connections:
            if dead_connection in self.rooms[room_id]:
                self.rooms[room_id].remove(dead_connection)
                logger.info(f"Removed dead connection {dead_connection.client} from room '{room_id}'")

        # Clean up empty rooms
        if not self.rooms[room_id]:
            del self.rooms[room_id]
            logger.info(f"Room '{room_id}' is now empty and has been closed.")

    async def store_message(self, room_id: str, message: Message):
       """Stores messages in redis history for a given room."""
       json_message = message.model_dump_json()
       
       if self.redis_client:
           history_key = f"history:{room_id}"
           self.redis_client.lpush(history_key, json_message)
           self.redis_client.ltrim(history_key, 0, MESSAGE_HISTORY_LENGTH - 1)
       else:
           # Fallback to in-memory storage
           if room_id not in self.message_history:
               self.message_history[room_id] = []
           self.message_history[room_id].insert(0, json_message)
           self.message_history[room_id] = self.message_history[room_id][:MESSAGE_HISTORY_LENGTH]
       
       print(f"Stored message in history for room '{room_id}'")

    async def get_message_history(self, room_id: str) -> list[Message]:
        """Retrieves message history for a room."""
        if self.redis_client:
            history_key = f"history:{room_id}"
            history_json = self.redis_client.lrange(history_key, 0, -1)
            history_json.reverse()
        else:
            # Fallback to in-memory storage
            history_json = self.message_history.get(room_id, [])
            history_json = list(reversed(history_json))
        
        history_message = [Message.model_validate_json(msg_json) for msg_json in history_json]
        return history_message
    
    async def send_personal_message(self, message: Message, recipient_id: str):
        """Send message to a specific user."""
        if recipient_id in self.user_connections:
            json_message = message.model_dump_json()
            for connection in self.user_connections[recipient_id]:
                await connection.send_text(json_message)
            print(f"message send to {recipient_id}")