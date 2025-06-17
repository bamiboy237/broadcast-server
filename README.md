# Broadcast Server

A real-time communication server built with FastAPI and WebSockets that supports room-based chat, file sharing, and private messaging.

## Features

- Real-time chat with WebSocket connections
- Room-based messaging (users can join different rooms)
- File upload and sharing
- Private messaging between users
- Message history storage
- Command-line interface for easy server management and client connections

## Requirements

- Python 3.13 or higher
- Redis (for message storage)

## Installation

1. Install dependencies using uv:
```bash
uv sync
```

## Usage

### Starting the Server

Start the server using the CLI:
```bash
uv run python cli.py start
```

By default, the server runs on `http://127.0.0.1:8000`. You can specify custom host and port:
```bash
uv run python cli.py start --host 0.0.0.0 --port 8080
```

### Connecting as a Client

Connect to a room using the CLI client:
```bash
uv run python cli.py connect --room general --user your_username
```

Options:
- `--room, -r`: Room ID to join (default: "general")
- `--user, -u`: Your user ID (default: "user")
- `--host`: Server host (default: "127.0.0.1")
- `--port`: Server port (default: 8000)

### Client Commands

Once connected, you can use these commands:
- Regular message: Just type your message
- Private message: `/pm <recipient> <message>`
- Help: `/help`

## API Endpoints

### WebSocket
- `GET /ws/{room_id}/{user_id}`: Connect to a room via WebSocket

### HTTP
- `POST /upload/{room_id}/{user_id}`: Upload a file to share in a room
- `GET /files/{file_id}`: Download a previously uploaded file

## Project Structure

- `main.py`: FastAPI application with WebSocket and HTTP endpoints
- `cli.py`: Command-line interface for server and client operations
- `room_manager.py`: Manages WebSocket connections and room logic
- `schemas.py`: Pydantic models for message types
- `uploads/`: Directory for uploaded files

## Message Types

The server supports several message types:
- `CHAT_MESSAGE`: Regular room messages
- `PRIVATE_MESSAGE`: Direct messages between users
- `USER_JOINED`: System notification when a user joins
- `USER_LEFT`: System notification when a user leaves
- `FILE_SHARED`: Notification when a file is uploaded

## Development

To run the server in development mode with auto-reload:
```bash
uv run uvicorn main:app --reload
```
