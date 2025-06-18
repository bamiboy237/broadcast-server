import os
import shutil
import json
import uuid
import mimetypes
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Query, HTTPException
from fastapi.responses import FileResponse
from room_manager import RoomManager
from schemas import Message, MessageType
from config import settings, ensure_uploads_dir
import logging

# Ensure uploads directory exists
ensure_uploads_dir()

# Set up logging
logging.basicConfig(level=getattr(logging, settings.log_level))
logger = logging.getLogger(__name__)

app = FastAPI(title="Real-Time Hub with File Sharing")
manager = RoomManager()


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal and other issues."""
    if not filename:
        return "unnamed_file"
    
    filename = os.path.basename(filename)
    
    import re
    filename = re.sub(r'[^\w\-_\.]', '_', filename)
    
    if not filename or filename.startswith('.'):
        filename = f"file_{uuid.uuid4().hex[:8]}.bin"
    
    if len(filename) > 100:
        name, ext = os.path.splitext(filename)
        filename = f"{name[:90]}{ext}"
    
    return filename


def is_allowed_file_type(content_type: str, filename: str) -> bool:
    """Check if file type is allowed."""
    if content_type in settings.allowed_file_types:
        return True
    
    guessed_type, _ = mimetypes.guess_type(filename)
    return guessed_type in settings.allowed_file_types if guessed_type else False

# --- HTTP File Endpoints ---
@app.post("/upload/{room_id}/{user_id}")
async def upload_file(room_id: str, user_id: str, file: UploadFile = File(...)):
    """Handles file uploads via HTTP POST with security validation."""
    
    # Validate room and user IDs
    if not room_id.strip() or not user_id.strip():
        raise HTTPException(status_code=400, detail="Room ID and User ID cannot be empty")
    
    if len(room_id) > settings.max_room_id_length or len(user_id) > settings.max_user_id_length:
        raise HTTPException(status_code=400, detail="Room ID or User ID too long")
    
    # Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    # Check file size
    file_content = await file.read()
    if len(file_content) > settings.max_file_size:
        raise HTTPException(
            status_code=413, 
            detail=f"File too large. Maximum size is {settings.max_file_size // (1024*1024)}MB"
        )
    
    # Check file type
    if not is_allowed_file_type(file.content_type or "", file.filename):
        raise HTTPException(
            status_code=415, 
            detail=f"File type not allowed. Allowed types: {', '.join(settings.allowed_file_types)}"
        )
    
    # Sanitize filename and create unique name
    safe_filename = sanitize_filename(file.filename)
    unique_filename = f"{uuid.uuid4().hex}_{safe_filename}"
    file_path = os.path.join(settings.uploads_dir, unique_filename)
    
    # Ensure we're writing within uploads directory (additional security)
    if not os.path.abspath(file_path).startswith(os.path.abspath(settings.uploads_dir)):
        raise HTTPException(status_code=400, detail="Invalid file path")
    
    try:
        # Write file
        with open(file_path, "wb") as buffer:
            buffer.write(file_content)
        
        # Create file notification
        file_notification = Message(
            sender="System",
            type=MessageType.FILE_SHARED,
            content={
                "file_name": safe_filename,
                "file_id": unique_filename,
                "uploader": user_id,
                "download_url": f"/files/{unique_filename}",
                "file_size": len(file_content),
                "content_type": file.content_type
            }
        )
        
        await manager.broadcast_to_room(room_id, file_notification)
        
        return {
            "filename": safe_filename,
            "file_id": unique_filename,
            "size": len(file_content),
            "status": "uploaded"
        }
        
    except Exception as e:
        logger.error(f"Error saving file: {e}")
        # Clean up partial file if it exists
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        raise HTTPException(status_code=500, detail="Failed to save file")

@app.get("/files/{file_id}")
async def get_file(file_id: str):
    """Serves a previously uploaded file for download with security checks."""
    
    # Validate file_id format (should be UUID + filename)
    if not file_id or '..' in file_id or '/' in file_id or '\\' in file_id:
        raise HTTPException(status_code=400, detail="Invalid file ID")
    
    file_path = os.path.join(settings.uploads_dir, file_id)
    
    # Ensure file is within uploads directory
    if not os.path.abspath(file_path).startswith(os.path.abspath(settings.uploads_dir)):
        raise HTTPException(status_code=400, detail="Invalid file path")
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    # Check file size for additional security
    file_size = os.path.getsize(file_path)
    if file_size > settings.max_file_size:
        logger.warning(f"Attempted to download oversized file: {file_id}")
        raise HTTPException(status_code=400, detail="File too large")
    
    try:
        return FileResponse(
            file_path,
            filename=file_id.split('_', 1)[-1] if '_' in file_id else file_id
        )
    except Exception as e:
        logger.error(f"Error serving file {file_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to serve file")

# --- Health Check Endpoint ---
@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestration."""
    try:
        # Test Redis connection if available
        if manager.redis_client:
            manager.redis_client.ping()
            redis_status = "connected"
        else:
            redis_status = "in-memory-fallback"
        
        return {
            "status": "healthy",
            "redis": redis_status,
            "active_rooms": len(manager.rooms),
            "total_connections": sum(len(connections) for connections in manager.rooms.values())
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}

# --- Websocket Endpoints

@app.websocket("/ws/{room_id}/{user_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, user_id: str, code: str | None = Query(None)):
    """
    The main WebSocket endpoint for clients to connect to a room.
    - Path parameter `room_id` determines which room the client joins.
    """
    # Input validation
    if not room_id.strip() or not user_id.strip():
        await websocket.close(code=4000, reason="Room ID and User ID cannot be empty")
        return
    
    # Limit room/user ID length for security
    if len(room_id) > 50 or len(user_id) > 50:
        await websocket.close(code=4000, reason="Room ID or User ID too long")
        return
    
    try:
        # --- Auth logic ---
        existing_code = await manager.get_room_code(room_id)
        is_new_room = False

        if existing_code:
            # Room exists, code required
            if not await manager.is_code_valid(room_id, code):
                await websocket.close(code=4001, reason="Invalid or missing room code")
                return
        else:
            # New room, generate code
            is_new_room = True
            existing_code = await manager.set_room_code(room_id)

        await manager.connect(websocket, room_id, user_id)
        
        # Only send creation message if this is a new room
        if is_new_room:
            creation_message = Message(
                sender="System",
                type=MessageType.SYSTEM_INFO,
                content=f"You created room '{room_id}'. The code to join is: {existing_code}"
            )
            await manager.send_personal_message(creation_message, user_id)
        
        # Send message history
        history = await manager.get_message_history(room_id)
        for msg in history:
            await websocket.send_text(msg.model_dump_json())

        # Notify room of new user
        join_message = Message(
            sender="System",
            type=MessageType.USER_JOINED,
            content=f"{user_id} has joined the room."
        )
        await manager.broadcast_to_room(room_id, join_message)

        # Main message loop
        try:
            while True:
                raw_data = await websocket.receive_text()
                
                # Validate message length
                if len(raw_data) > 1000:  # 1KB limit per message
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "content": "Message too long (max 1000 characters)"
                    }))
                    continue
                
                try:
                    # Try to parse as JSON first (for structured messages)
                    json_data = json.loads(raw_data)
                    logger.info(f"Received JSON message from {user_id}: {json_data}")
                    
                    # Handle different message types
                    if json_data.get("type") == "private_message":
                        recipient = json_data.get("recipient", "").strip()
                        content = json_data.get("content", "").strip()
                        
                        if not recipient or not content:
                            await websocket.send_text(json.dumps({
                                "type": "error",
                                "content": "Private message requires recipient and content"
                            }))
                            continue
                            
                        pm = Message(
                            sender=user_id,
                            type=MessageType.PRIVATE_MESSAGE,
                            content=content,
                            recipient=recipient
                        )
                        logger.info(f"Sending private message from {user_id} to {recipient}")
                        await manager.send_personal_message(pm, recipient)
                        
                    elif json_data.get("type") == "chat_message":
                        content = json_data.get("content", "").strip()
                        if content:
                            broadcast_msg = Message(
                                sender=user_id,
                                type=MessageType.CHAT_MESSAGE,
                                content=content
                            )
                            logger.info(f"Broadcasting message from {user_id} to room {room_id}")
                            await manager.broadcast_to_room(room_id, broadcast_msg)
                            await manager.store_message(room_id, broadcast_msg)
                            
                except (json.JSONDecodeError, ValueError):
                    # Handle plain text messages (regular chat)
                    content = raw_data.strip()
                    if content:
                        logger.info(f"Received plain text message from {user_id}: {content}")
                        broadcast_msg = Message(
                            sender=user_id,
                            type=MessageType.CHAT_MESSAGE,
                            content=content
                        )
                        await manager.broadcast_to_room(room_id, broadcast_msg)
                        await manager.store_message(room_id, broadcast_msg)
                        
                except Exception as e:
                    logger.error(f"Error processing message from {user_id}: {e}")
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "content": "Failed to process message"
                    }))
                    
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
            try:
                manager.disconnect(websocket, room_id, user_id)
            except:
                pass