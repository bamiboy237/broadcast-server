from fastapi import WebSocket, HTTPException
from schemas import Message
from config import settings
import logging
import redis
import json
import secrets
import string
from typing import Dict, List

# logging for error tracking
logging.basicConfig(level=getattr(logging, settings.log_level))
logger = logging.getLogger(__name__)

class RoomManager:
    def __init__(self):
        """Initializes the RoomManager with configuration-based settings."""
        self.rooms: Dict[str, List[WebSocket]] = {}
        self.user_connections: Dict[str, List[WebSocket]] = {}
        self.message_history: Dict[str, List[str]] = {}  # Fallback storage
        self.room_codes: Dict[str, str] = {}  # Fallback storage for room codes
        
        # Connection tracking for rate limiting
        self.connection_counts: Dict[str, int] = {}  # room_id -> connection count
        self.user_connection_counts: Dict[str, int] = {}  # user_id -> connection count
        
        # Initialize Redis connection
        self._init_redis()
        
        self.ROOM_CODE_KEY_PREFIX = "room_codes:"
    
    def _init_redis(self):
        """Initialize Redis connection with proper error handling."""
        try:
            self.redis_client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                password=settings.redis_password,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            # Test connection
            self.redis_client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.warning(f"Redis not available, using in-memory storage: {e}")
            self.redis_client = None

    def _generate_room_code(self, length: int = 5) -> str:
        """Generate a simple, shareable, random alphanumeric code."""
        alphabet = string.ascii_uppercase + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    async def get_room_code(self, room_id: str) -> str | None:
        """Get the room code for a given room."""
        try:
            if self.redis_client:
                return self.redis_client.get(f"{self.ROOM_CODE_KEY_PREFIX}{room_id}")
            else:
                # Fallback to in-memory storage
                return self.room_codes.get(room_id)
        except Exception as e:
            logger.warning(f"Error getting room code from Redis, using fallback: {e}")
            return self.room_codes.get(room_id)
    
    async def set_room_code(self, room_id: str) -> str:
        """Set a new room code for a room and return it."""
        new_code = self._generate_room_code()
        try:
            if self.redis_client:
                self.redis_client.set(f"{self.ROOM_CODE_KEY_PREFIX}{room_id}", new_code)
            else:
                # Fallback to in-memory storage
                self.room_codes[room_id] = new_code
        except Exception as e:
            logger.warning(f"Error setting room code in Redis, using fallback: {e}")
            self.room_codes[room_id] = new_code
        return new_code
    
    async def is_code_valid(self, room_id: str, code: str) -> bool:
        """Check if the provided code is valid for the room."""
        if not code:
            return False
        stored_code = await self.get_room_code(room_id)
        return stored_code is not None and stored_code == code

    async def connect(self, websocket: WebSocket, room_id: str, user_id: str):
        """Client connects to a specific room with connection limits."""
        
        # Check room connection limit
        current_room_connections = len(self.rooms.get(room_id, []))
        if current_room_connections >= settings.max_connections_per_room:
            await websocket.close(code=4003, reason="Room is full")
            raise HTTPException(status_code=429, detail="Room is full")
        
        # Check user connection limit
        current_user_connections = len(self.user_connections.get(user_id, []))
        if current_user_connections >= settings.max_connections_per_user:
            await websocket.close(code=4004, reason="Too many connections for user")
            raise HTTPException(status_code=429, detail="Too many connections for this user")
        
        await websocket.accept()

        # Add to room
        if room_id not in self.rooms:
            self.rooms[room_id] = []
            self.connection_counts[room_id] = 0
        
        self.rooms[room_id].append(websocket)
        self.connection_counts[room_id] += 1
        
        # Add to user connections
        if user_id not in self.user_connections:
            self.user_connections[user_id] = []
            self.user_connection_counts[user_id] = 0
        
        self.user_connections[user_id].append(websocket)
        self.user_connection_counts[user_id] += 1
        
        logger.info(f"Client {websocket.client} connected to room '{room_id}' as '{user_id}'")
        logger.info(f"Room '{room_id}' now has {self.connection_counts[room_id]} connections")
        logger.info(f"User '{user_id}' now has {self.user_connection_counts[user_id]} connections")   

    def disconnect(self, websocket: WebSocket, room_id: str, user_id: str):
        """A client disconnects from a specific room with proper cleanup."""
        # Clean up room connections
        if room_id in self.rooms:
            if websocket in self.rooms[room_id]:
                self.rooms[room_id].remove(websocket)
                self.connection_counts[room_id] = max(0, self.connection_counts[room_id] - 1)
                logger.info(f"Client {websocket.client} disconnected from '{room_id}' as '{user_id}'")

                if not self.rooms[room_id]:
                    del self.rooms[room_id]
                    if room_id in self.connection_counts:
                        del self.connection_counts[room_id]
                    # Clean up room code from in-memory storage
                    if room_id in self.room_codes:
                        del self.room_codes[room_id]
                    logger.info(f"Room '{room_id}' is now empty and has been closed.")
            else:
                logger.warning(f"Client {websocket.client} was not in room '{room_id}' during disconnect")
        else:
            logger.warning(f"Tried to disconnect from a non-existent room '{room_id}'")

        # Clean up user connections
        if user_id in self.user_connections:
            if websocket in self.user_connections[user_id]:
                self.user_connections[user_id].remove(websocket)
                self.user_connection_counts[user_id] = max(0, self.user_connection_counts[user_id] - 1)
                
                if not self.user_connections[user_id]:
                    del self.user_connections[user_id]
                    if user_id in self.user_connection_counts:
                        del self.user_connection_counts[user_id]

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
            # Clean up room code from in-memory storage
            if room_id in self.room_codes:
                del self.room_codes[room_id]
            logger.info(f"Room '{room_id}' is now empty and has been closed.")

    async def store_message(self, room_id: str, message: Message):
        """Stores messages in Redis or in-memory history for a given room."""
        json_message = message.model_dump_json()
        
        try:
            if self.redis_client:
                history_key = f"history:{room_id}"
                self.redis_client.lpush(history_key, json_message)
                self.redis_client.ltrim(history_key, 0, settings.message_history_length - 1)
                logger.debug(f"Stored message in Redis for room '{room_id}'")
            else:
                # Fallback to in-memory storage
                if room_id not in self.message_history:
                    self.message_history[room_id] = []
                self.message_history[room_id].insert(0, json_message)
                self.message_history[room_id] = self.message_history[room_id][:settings.message_history_length]
                logger.debug(f"Stored message in memory for room '{room_id}'")
        except Exception as e:
            logger.error(f"Error storing message for room '{room_id}': {e}")
            # Fallback to in-memory if Redis fails
            if room_id not in self.message_history:
                self.message_history[room_id] = []
            self.message_history[room_id].insert(0, json_message)
            self.message_history[room_id] = self.message_history[room_id][:settings.message_history_length]

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
        """Send message to a specific user with error handling."""
        if recipient_id not in self.user_connections:
            logger.warning(f"Attempted to send message to non-existent user: {recipient_id}")
            return False
        
        json_message = message.model_dump_json()
        dead_connections = []
        sent_count = 0
        
        for connection in self.user_connections[recipient_id][:]:  # Copy list to avoid modification during iteration
            try:
                await connection.send_text(json_message)
                sent_count += 1
            except Exception as e:
                logger.warning(f"Failed to send personal message to {recipient_id}: {e}")
                dead_connections.append(connection)
        
        # Clean up dead connections
        for dead_connection in dead_connections:
            if dead_connection in self.user_connections[recipient_id]:
                self.user_connections[recipient_id].remove(dead_connection)
                logger.info(f"Removed dead connection for user {recipient_id}")
        
        # Clean up empty user connection list
        if not self.user_connections[recipient_id]:
            del self.user_connections[recipient_id]
            if recipient_id in self.user_connection_counts:
                del self.user_connection_counts[recipient_id]
        
        logger.debug(f"Personal message sent to {recipient_id} ({sent_count} connections)")
        return sent_count > 0