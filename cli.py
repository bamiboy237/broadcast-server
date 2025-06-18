import asyncio
import websockets
import typer 
import uvicorn
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
import json
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.align import Align
from rich.box import ROUNDED, SIMPLE
from rich.live import Live
from rich.layout import Layout
import time
import sys

cli = typer.Typer(
    name="Broadcast Server",
    help="A real-time broadcast server with WebSocket support",
    add_completion=False,
)

# Simple console configuration to avoid ANSI escape code issues
console = Console(
    color_system=None,  # Disable colors to prevent escape codes
    force_terminal=False,  # Let Rich auto-detect
    width=80,  # Fixed width for consistency
    legacy_windows=False
)

@cli.command()
def start(
    host: str = typer.Option("127.0.0.1", help="The host to bind the server to."),
    port: int = typer.Option(8000, help="The port to run the server on.")
):
    
    # startup banner
    banner = Panel.fit(
        Text("🎯 BROADCAST SERVER", style="bold cyan", justify="center") + "\n" +
        Text("Real-time WebSocket Communication Hub", style="dim", justify="center"),
        border_style="bright_blue",
        padding=(1, 2)
    )
    
    console.print("\n")
    console.print(Align.center(banner))
    console.print("\n")
    
    # Server configuration table
    config_table = Table(box=ROUNDED, show_header=False, expand=False)
    config_table.add_column("Setting", style="bold cyan")
    config_table.add_column("Value", style="bright_white")
    config_table.add_row("🌐 Host", f"[bright_green]{host}[/bright_green]")
    config_table.add_row("🔌 Port", f"[bright_green]{port}[/bright_green]")
    config_table.add_row("🔗 URL", f"[bright_blue]http://{host}:{port}[/bright_blue]")
    config_table.add_row("📡 WebSocket", f"[bright_blue]ws://{host}:{port}/ws[/bright_blue]")
    
    config_panel = Panel(
        Align.center(config_table),
        title="⚙️  Server Configuration",
        border_style="green",
        padding=(1, 2)
    )
    
    console.print(config_panel)
    console.print("\n")
    
    # Starting message with spinner
    with console.status("[bold green]🚀 Starting server...", spinner="dots"):
        time.sleep(1) 
    
    console.print("✅ [bold green]Server starting successfully![/bold green]")
    console.print("📝 [dim]Press Ctrl+C to stop the server[/dim]\n")
    
    try:
        uvicorn.run("main:app", host=host, port=port, reload=True)
    except KeyboardInterrupt:
        console.print("\n")
        console.print("🛑 [bold red]Server stopped by user[/bold red]")
        console.print("👋 [dim]Goodbye![/dim]")
        raise typer.Exit()

# --- Client Logic ---


async def listen_to_server(websocket):
    """Listens for messages from the server and prints them."""
    try:
        async for message_str in websocket:
            message = json.loads(message_str)

            sender = message.get("sender")
            content = message.get("content")
            msg_type = message.get("type")
            timestamp = time.strftime("%H:%M:%S")

            
            print() 
            if msg_type == "user_joined":
                print(f"🎉 [{timestamp}] System: 👋 {content}")
                
            elif msg_type == "user_left":
                print(f"📤 [{timestamp}] System: 👋 {content}")

            elif msg_type == "file_shared":
                file_info = content
                print(f"📁 [{timestamp}] File shared by {file_info['uploader']}: {file_info['file_name']}")
                print(f"📥 Download: http://127.0.0.1:8000{file_info['download_url']}")
                
            elif msg_type == "chat_message":
                print(f"💬 [{timestamp}] {sender}: {content}")
                
            elif msg_type == "private_message":
                print(f"📩 [{timestamp}] Private from {sender}: {content}")
                
            elif msg_type == "private_message_error":
                print(f"❌ [{timestamp}] Private message error: {content}")
            
            elif msg_type == "system_info":
                print(f"🔔 [{timestamp}] System Info: {content}")
                if "code to join is:" in content:
                    print(f"💡 [{timestamp}] Save this code to share with others!")
            
            print()  

    except websockets.exceptions.ConnectionClosed:
        print()
        print("❌ Connection to server lost!")
        print("💡 The server may have stopped or there's a network issue.")
        print()

async def send_to_server(websocket, session):
    """Gets client input and sends it to server."""
    try:
        while True:
            message = await session.prompt_async("💬 ")
            if message.strip():  # Only send non-empty messages
                # Check if this is a private message command
                if message.strip().startswith('/pm '):
                    # Parse the private message command
                    parts = message.strip().split(' ', 2)  # Split into max 3 parts
                    
                    if len(parts) < 3:
                        print("❌ Invalid private message format!")
                        print("💡 Usage: /pm <recipient> <message>")
                        print("📝 Example: /pm userB Hey, can we talk privately?")
                        print()
                        continue
                    
                    recipient = parts[1]
                    content = parts[2]
                    
                    # Construct the private message JSON payload
                    pm_payload = {
                        "type": "private_message",
                        "content": content,
                        "recipient": recipient
                    }
                    
                    # Send as JSON string
                    await websocket.send(json.dumps(pm_payload))
                    
                    # Show confirmation to sender
                    timestamp = time.strftime("%H:%M:%S")
                    print()
                    print(f"📩 [{timestamp}] Private message sent to {recipient}: {content}")
                    print()
                    
                elif message.strip().startswith('/help'):
                    # Show help information
                    print()
                    print("🔧 Available Commands:")
                    print("💬 Regular message: Just type your message")
                    print("📩 Private message: /pm <recipient> <message>")
                    print("❓ Help: /help")
                    print()
                    print("🔐 Room Code Info:")
                    print("• Creating room: Connect without --code parameter")
                    print("• Joining room: Use --code parameter with the room code")
                    print("• Codes are 5-character alphanumeric (e.g., A3K9P)")
                    print()
                    
                else:
                    # Regular message - send as plain text
                    await websocket.send(message)
                    
    except(EOFError, KeyboardInterrupt):
        print()
        print("👋 Goodbye!")
        print("🔌 Closing connection...")
        print()
        return
    
@cli.command()
def connect(
    room_id: str = typer.Option("general", "--room", "-r", help="Room ID to join"),
    user_id: str = typer.Option("user", "--user", "-u", help="Your user ID"),
    host: str = typer.Option("127.0.0.1", "--host", help="Server host"),
    port: int = typer.Option(8000, "--port", help="Server port"),
    code: str = typer.Option(None, "--code", "-c", help="Room code (required for existing rooms)")
):
    """
    🔗 Connects to the broadcast server as a client with beautiful interface
    """
    
    # Construct the WebSocket URI with optional room code
    if code:
        uri = f"ws://{host}:{port}/ws/{room_id}/{user_id}?code={code}"
    else:
        uri = f"ws://{host}:{port}/ws/{room_id}/{user_id}"
    
    connect_banner = Panel.fit(
        Text("🔗 CLIENT CONNECTION", style="bold magenta", justify="center") + "\n" +
        Text("Connecting to Broadcast Server", style="dim", justify="center"),
        border_style="bright_magenta",
        padding=(1, 2)
    )
    
    console.print("\n")
    console.print(Align.center(connect_banner))
    console.print("\n")
    
    # Connection info
    info_table = Table(box=ROUNDED, show_header=False, expand=False)
    info_table.add_column("Info", style="bold magenta")
    info_table.add_column("Value", style="bright_white")
    info_table.add_row("🌐 Server", f"[bright_blue]{host}:{port}[/bright_blue]")
    info_table.add_row("🏠 Room", f"[bright_green]{room_id}[/bright_green]")
    info_table.add_row("👤 User", f"[bright_yellow]{user_id}[/bright_yellow]")
    
    # Show different status based on whether code is provided
    if code:
        info_table.add_row("🔐 Mode", f"[bright_cyan]Joining existing room[/bright_cyan]")
        info_table.add_row("🗝️  Code", f"[bright_red]{code}[/bright_red]")
    else:
        info_table.add_row("🔐 Mode", f"[bright_cyan]Creating new room[/bright_cyan]")
        info_table.add_row("🗝️  Code", f"[dim]Will be generated[/dim]")
    
    info_table.add_row("⏰ Time", f"[bright_cyan]{time.strftime('%Y-%m-%d %H:%M:%S')}[/bright_cyan]")
    
    info_panel = Panel(
        Align.center(info_table),
        title="📡 Connection Details",
        border_style="blue",
        padding=(1, 2)
    )
    
    console.print(info_panel)
    console.print("\n")
    
    async def client_logic():
        session = PromptSession()
        
        try: 
            with console.status("[bold blue]🔄 Connecting to server...", spinner="dots"):
                websocket = await websockets.connect(uri)
            
            success_panel = Panel(
                "✅ [bold green]Successfully connected![/bold green]\n" +
                f"🎯 Connected to: [bright_blue]{uri}[/bright_blue]\n" +
                "📝 [dim]Type messages and press Enter to send[/dim]\n" +
                "📩 [dim]Private messages: /pm <user> <message>[/dim]\n" +
                "❓ [dim]Commands: /help for more info[/dim]\n" +
                "🚪 [dim]Press Ctrl+C to exit[/dim]",
                title="🎉 Connection Established",
                border_style="green",
                box=ROUNDED
            )
            console.print(success_panel)
            console.print("\n")

            with patch_stdout():
                try:
                    # Create two concurrent tasks
                    listen_task = asyncio.create_task(listen_to_server(websocket))
                    send_task = asyncio.create_task(send_to_server(websocket, session))

                    await asyncio.gather(listen_task, send_task)
                finally:
                    await websocket.close()
                    
        except websockets.exceptions.ConnectionClosedError as e:
            if e.code == 4001:
                error_panel = Panel(
                    "❌ [bold red]Room Code Authentication Failed![/bold red]\n" +
                    f"🎯 Room: [dim]{room_id}[/dim]\n" +
                    "🔐 [yellow]The room code is invalid or missing[/yellow]\n" +
                    "💡 [dim]Ask the room creator for the correct code[/dim]\n" +
                    "🔧 [dim]Try: python cli.py connect --room {room} --code {code}[/dim]",
                    title="🚫 Authentication Error",
                    border_style="red",
                    box=ROUNDED
                )
                console.print(error_panel)
                raise typer.Exit(1)
            else:
                error_panel = Panel(
                    f"❌ [bold red]Connection closed unexpectedly![/bold red]\n" +
                    f"🔧 Code: [dim]{e.code}[/dim]\n" +
                    f"💬 Reason: [dim]{e.reason}[/dim]",
                    title="🚫 Connection Error",
                    border_style="red",
                    box=ROUNDED
                )
                console.print(error_panel)
                raise typer.Exit(1)
                    
        except (ConnectionRefusedError, websockets.exceptions.InvalidURI):
            error_panel = Panel(
                "❌ [bold red]Connection failed![/bold red]\n" +
                f"🎯 Target: [dim]{uri}[/dim]\n" +
                "💡 [yellow]Is the server running?[/yellow]\n" +
                "🔧 [dim]Try: python cli.py start[/dim]",
                title="🚫 Connection Error",
                border_style="red",
                box=ROUNDED
            )
            console.print(error_panel)
            raise typer.Exit(1)

    asyncio.run(client_logic())


if __name__ == "__main__":
    cli()