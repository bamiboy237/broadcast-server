import os
import shutil
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import FileResponse
from room_manager import RoomManager
from schemas import Message, MessageType
import logging

# file dir
UPLOADS_DIR = "uploads"
os.makedirs(UPLOADS_DIR, exist_ok=True)

# Set up logging
logger = logging.getLogger(__name__)

app = FastAPI(title="Real-Time Hub with File Sharing")
manager = RoomManager()

# --- HTTP File Endpoints ---
@app.post("/upload/{room_id}/{user_id}")
async def upload_file(room_id: str, user_id: str, file: UploadFile = File(...)):
    """handles file uploads via HTTP POST.
        Saves the file and then broadcasts a room notif
    """
    file_path = os.path.join(UPLOADS_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    file_notification = Message(
        sender="System",
        type=MessageType.FILE_SHARED,
        content={
            "file_name": file.filename,
            "uploader": user_id,
            "download_url": f"/files/{file.filename}"
        }
    )

    await manager.broadcast_to_room(room_id, file_notification)
    return {"filename": file.filename, "status": "uploaded"}

@app.get("/files/{file_id}")
async def get_file(file_id: str):
    """Serves a previously uploaded file for download."""
    file_path = os.path.join(UPLOADS_DIR, file_id)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return {"error": "File not found"}, 404

# --- Websocket Endpoints

@app.websocket("/ws/{room_id}/{user_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, user_id: str):
    """
    The main WebSocket endpoint for clients to connect to a room.
    - Path parameter `room_id` determines which room the client joins.
    """
    try:
        await manager.connect(websocket, room_id, user_id)

        history = await manager.get_message_history(room_id)
        for msg in history:
            await websocket.send_text(msg.model_dump_json())

        join_message = Message(
            sender="System",
            type=MessageType.USER_JOINED,
            content=f"{user_id} has joined the room."
        )

        await manager.broadcast_to_room(room_id, join_message)

        try:
            while True:
                raw_data = await websocket.receive_text()
                try:
                    # Try to parse as JSON first (for structured messages like private messages)
                    try:
                        # First check if it's valid JSON
                        json_data = json.loads(raw_data)
                        logger.info(f"Received JSON message from {user_id}: {json_data}")
                        
                        # Handle different message types
                        if json_data.get("type") == "private_message":
                            recipient = json_data.get("recipient", "")
                            pm = Message(
                                sender=user_id,
                                type=MessageType.PRIVATE_MESSAGE,
                                content=json_data.get("content", ""),
                                recipient=recipient
                            )
                            logger.info(f"Sending private message from {user_id} to {recipient}")
                            await manager.send_personal_message(pm, recipient)
                            
                        elif json_data.get("type") == "chat_message":
                            broadcast_msg = Message(
                                sender=user_id,
                                type=MessageType.CHAT_MESSAGE,
                                content=json_data.get("content", "")
                            )
                            logger.info(f"Broadcasting message from {user_id} to room {room_id}")
                            await manager.broadcast_to_room(room_id, broadcast_msg)
                            await manager.store_message(room_id, broadcast_msg)
                            
                    except (json.JSONDecodeError, ValueError):
                        # Handle plain text messages (regular chat)
                        logger.info(f"Received plain text message from {user_id}: {raw_data}")
                        broadcast_msg = Message(
                            sender=user_id,
                            type=MessageType.CHAT_MESSAGE,
                            content=raw_data
                        )
                        await manager.broadcast_to_room(room_id, broadcast_msg)
                        await manager.store_message(room_id, broadcast_msg)
                        
                except Exception as e:
                    logger.error(f"Error processing message from {user_id}: {e}")
        except WebSocketDisconnect:
            logger.info(f"Client {user_id} disconnected from room {room_id}")
        except Exception as e:
            logger.warning(f"Unexpected error in WebSocket connection for {user_id}: {e}")
        
    except Exception as e:
        logger.error(f"Error in WebSocket endpoint for {user_id}: {e}")
    finally:
        try:
            manager.disconnect(websocket, room_id, user_id)
            left_message = Message(
                sender="System",
                type=MessageType.USER_LEFT,
                content=f"{user_id} has left the room"
            )
            await manager.broadcast_to_room(room_id, left_message)
        except Exception as e:
            logger.warning(f"Error during cleanup for {user_id}: {e}")
            manager.disconnect(websocket, room_id, user_id)