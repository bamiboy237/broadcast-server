# Broadcast Server

A real-time communication server built with FastAPI and WebSockets that supports room-based chat, secure file sharing, private messaging, and room access control with authentication codes.

## Features

- **Real-time Chat**: WebSocket-based messaging with instant delivery
- **Room Authentication**: Secure room access with 5-character alphanumeric codes
- **File Sharing**: Secure file uploads with type validation and size limits
- **Private Messaging**: Direct user-to-user messaging
- **Message History**: Persistent message storage with Redis or in-memory fallback
- **Connection Management**: Configurable limits and resource management
- **Security Hardening**: Input validation, path traversal protection, and rate limiting
- **Configuration Management**: Environment-based configuration with sensible defaults
- **Command-line Interface**: Easy server management and client connections

## Requirements

- Python 3.13 or higher
- Redis (recommended for message storage and room code management)

## Installation

1. Install dependencies using uv:
```bash
uv sync
```

2. Ensure Redis is running on your system:
```bash
# On macOS with Homebrew
brew services start redis

# On Ubuntu/Debian
sudo systemctl start redis-server

# On Windows (with Redis installed)
redis-server
```

## Configuration

The server uses environment-based configuration. You can customize settings by creating a `.env` file or setting environment variables with the `BROADCAST_` prefix:

```bash
# Server settings
BROADCAST_HOST=127.0.0.1
BROADCAST_PORT=8000
BROADCAST_DEBUG=false

# Redis settings
BROADCAST_REDIS_HOST=localhost
BROADCAST_REDIS_PORT=6379
BROADCAST_REDIS_DB=0
BROADCAST_REDIS_PASSWORD=your_password_if_needed

# Connection limits
BROADCAST_MAX_CONNECTIONS_PER_ROOM=100
BROADCAST_MAX_CONNECTIONS_PER_USER=5
BROADCAST_MESSAGE_HISTORY_LENGTH=50

# File upload settings
BROADCAST_MAX_FILE_SIZE=10485760  # 10MB in bytes
BROADCAST_UPLOADS_DIR=uploads

# Security settings
BROADCAST_MAX_MESSAGE_LENGTH=1000
BROADCAST_MAX_ROOM_ID_LENGTH=50
BROADCAST_MAX_USER_ID_LENGTH=50

# Logging
BROADCAST_LOG_LEVEL=INFO
```

### Default Settings

| Setting | Default Value | Description |
|---------|---------------|-------------|
| Host | `127.0.0.1` | Server bind address |
| Port | `8000` | Server port |
| Redis Host | `localhost` | Redis server address |
| Redis Port | `6379` | Redis server port |
| Max File Size | `10MB` | Maximum upload file size |
| Room Code Length | `5` | Length of generated room codes |
| Max Connections/Room | `100` | Maximum connections per room |
| Max Connections/User | `5` | Maximum connections per user |
| Message History | `50` | Messages stored per room |

## Usage

### Starting the Server

```bash
# Start with default settings
uv run python main.py

# Or using the CLI
uv run python cli.py server --host 0.0.0.0 --port 8080
```

### Room Authentication System

The server implements a secure room access system:

1. **Creating a Room**: When someone connects to a room that doesn't exist, a new room is created and a 5-character code is generated (e.g., `A3K9P`)
2. **Joining a Room**: Subsequent users must provide the correct room code to join existing rooms
3. **Code Storage**: Room codes are stored in Redis with in-memory fallback for reliability
4. **Code Format**: Codes are alphanumeric (uppercase + digits), case-sensitive, and designed to be easily shareable
5. **Authentication**: Wrong or missing codes result in immediate connection rejection with clear error messages

### Connecting as a Client

#### CLI Connection (Recommended)

**Creating a new room:**
```bash
uv run python cli.py connect --room general --user your_username
```

**Joining an existing room with a code:**
```bash
uv run python cli.py connect --room general --user your_username --code A3K9P
```

#### WebSocket Connection (Direct)
When connecting via WebSocket directly, include the room code as a query parameter:

**Creating a new room:**
```
ws://127.0.0.1:8000/ws/{room_id}/{user_id}
```

**Joining an existing room:**
```
ws://127.0.0.1:8000/ws/{room_id}/{user_id}?code={room_code}
```

### Client Options

CLI client options:
- `--room, -r`: Room ID to join (default: "general")
- `--user, -u`: Your user ID (default: "user")
- `--host`: Server host (default: "127.0.0.1")
- `--port`: Server port (default: 8000)
- `--code, -c`: Room code (required for existing rooms)

### File Sharing

#### Uploading Files

**Via HTTP POST:**
```bash
curl -X POST "http://127.0.0.1:8000/upload/room_name/user_name" \
     -F "file=@path/to/your/file.jpg"
```

**Supported File Types:**
- Images: JPEG, PNG, GIF, WebP
- Documents: PDF, TXT, CSV, JSON
- Archives: ZIP

**Security Features:**
- File type validation
- Size limits (10MB default)
- Filename sanitization
- Path traversal protection
- Unique file IDs to prevent conflicts

#### Downloading Files

Files are accessible via:
```
http://127.0.0.1:8000/files/{file_id}
```

File sharing notifications are automatically broadcast to all users in the room.

### Private Messaging

Send private messages using the CLI or JSON format:

**CLI Format:**
```
/pm recipient_user Hello, this is a private message!
```

**JSON Format (via WebSocket):**
```json
{
  "type": "private_message",
  "recipient": "recipient_user",
  "content": "Hello, this is a private message!"
}
```

### Available Commands (CLI Client)

- `💬 Regular message`: Just type your message
- `📩 Private message`: `/pm <recipient> <message>`
- `❓ Help`: `/help`

## API Endpoints

### WebSocket Endpoints

- `GET /ws/{room_id}/{user_id}?code={room_code}` - WebSocket connection for real-time chat

### HTTP Endpoints

- `POST /upload/{room_id}/{user_id}` - Upload files to a room
- `GET /files/{file_id}` - Download uploaded files

## Message Types

The server handles various message types:

- `chat_message`: Regular room messages
- `private_message`: Direct user-to-user messages
- `user_joined`: System notification when user joins
- `user_left`: System notification when user leaves
- `file_shared`: System notification for file uploads
- `system_info`: System information (like room codes)

## Error Handling

The server includes comprehensive error handling:

- **4000**: Invalid room/user ID
- **4001**: Invalid or missing room code
- **4003**: Room is full
- **4004**: Too many connections for user
- **400**: Bad request (file validation errors)
- **413**: File too large
- **415**: Unsupported file type
- **500**: Internal server error

## Security Features

- **Input Validation**: All user inputs are validated and sanitized
- **Connection Limits**: Prevents resource exhaustion
- **File Security**: Type validation, size limits, and path traversal protection
- **Room Authentication**: Secure access control with codes
- **Error Handling**: Comprehensive error handling without information leakage

## Recent Fixes & Improvements

### Authentication Bug Fixes (Latest)

Several critical authentication bugs have been resolved:

**Fixed Room Code Authentication Bypass:**
- **Issue**: Clients could join rooms with wrong codes due to flawed authentication logic
- **Fix**: Corrected room authentication flow to properly validate codes before allowing connections
- **Impact**: Room security is now properly enforced

**Fixed Redis Fallback for Room Codes:**
- **Issue**: Room codes only worked with Redis; when Redis was unavailable, authentication was completely bypassed
- **Fix**: Added in-memory fallback storage for room codes with proper cleanup
- **Impact**: Room authentication now works reliably even without Redis

**Improved Error Handling:**
- **Issue**: Authentication failures weren't clearly reported to clients
- **Fix**: Added specific WebSocket close codes (4001) for authentication failures with user-friendly CLI error messages
- **Impact**: Users get clear feedback when room codes are invalid

**Room Creation Logic Fixed:**
- **Issue**: Room creation messages were sent incorrectly based on flawed logic
- **Fix**: Introduced `is_new_room` flag to properly track room creation vs joining
- **Impact**: Users only receive room creation messages when they actually create new rooms

**Code Length Correction:**
- **Updated**: Room codes are now 5 characters (was previously 8) for better usability
- **Format**: Uppercase letters + digits (e.g., `A3K9P`)

## Development

### Project Structure

```
broadcast-server/
├── main.py              # FastAPI application and WebSocket handlers
├── room_manager.py      # Room and connection management
├── schemas.py           # Pydantic data models
├── config.py            # Configuration management
├── cli.py              # Command-line interface
├── pyproject.toml      # Project dependencies
└── uploads/            # File upload directory
```

### Dependencies

- **FastAPI**: Web framework and WebSocket support
- **Redis**: Message storage and room code persistence
- **Pydantic**: Data validation and settings management
- **Typer**: CLI framework
- **WebSockets**: Real-time communication

## Monitoring and Logging

The server includes comprehensive logging:
- Connection events
- Message processing
- Error tracking
- File operations
- Redis operations

Configure log level with `BROADCAST_LOG_LEVEL` environment variable.

## Docker Deployment

### Development with Docker Compose

Start the entire stack (server + Redis) with:

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Production Deployment

For production, use the production override:

```bash
# Production deployment
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Set Redis password
export REDIS_PASSWORD=your-secure-password
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Building the Docker Image

```bash
# Build the image
docker build -t broadcast-server .

# Run with custom settings
docker run -d \
  --name broadcast-server \
  -p 8000:8000 \
  -e BROADCAST_REDIS_HOST=your-redis-host \
  -e BROADCAST_LOG_LEVEL=INFO \
  broadcast-server
```

### Health Checks

The Docker image includes health checks:
- **Endpoint**: `GET /health`
- **Response**: JSON with status, Redis connection, and connection stats
- **Interval**: Every 30 seconds
- **Timeout**: 10 seconds

## Production Deployment

For production use:

1. **Environment Variables**: Set appropriate environment variables
2. **Redis**: Use a production Redis instance with authentication
3. **Reverse Proxy**: Use nginx/traefik for SSL termination and load balancing
4. **File Storage**: Consider cloud storage for scalability
5. **Monitoring**: Set up monitoring and alerting
6. **Resource Limits**: Configure appropriate CPU/memory limits
7. **Security**: Use production docker-compose.prod.yml for security hardening

## Troubleshooting

**Redis Connection Issues:**
- Ensure Redis is running and accessible
- Check Redis host/port configuration
- Server falls back to in-memory storage if Redis is unavailable

**File Upload Issues:**
- Check file size limits
- Verify file type is in allowed list
- Ensure uploads directory has write permissions

**Connection Issues:**
- Verify room codes are correct
- Check if room/user connection limits are reached
- Review server logs for detailed error information
