from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime, UTC
from typing import Any
import uuid

class MessageType(str, Enum):
    CHAT_MESSAGE = "chat_message"
    USER_JOINED = "user_joined"
    USER_LEFT = "user_left"
    SYSTEM_INFO = "system_info"
    PRIVATE_MESSAGE = "private_message"
    FILE_SHARED = "file_shared"

class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))  
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sender: str = Field(min_length=1, max_length=50)  
    type: MessageType
    content: Any
    recipient: str | None = None
    
    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat()  
        }