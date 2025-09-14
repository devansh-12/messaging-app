
import asyncio
import websockets
import json
import threading

class ClientLamportClock:
    def __init__(self):
        self.timestamp = 0
        self.lock = threading.Lock()

    def tick(self):
        """Increment clock for local events"""
        with self.lock:
            self.timestamp += 1
            return self.timestamp

    def update(self, received_time):
        """Update clock when receiving external timestamp"""
        with self.lock:
            self.timestamp = max(self.timestamp, received_time) + 1
            return self.timestamp

class ChatClient:
    def __init__(self):
        self.clock = ClientLamportClock()
        self.ws = None

    async def connect_and_chat(self, username, password):
        try:
            self.ws = await websockets.connect("ws://localhost:8765")

            # Send login with Lamport timestamp
            login_time = self.clock.tick()
            login_msg = {
                "type": "login",
                "username": username,
                "password": password,
                "lamport_time": login_time
            }

            await self.ws.send(json.dumps(login_msg))

            # Handle login response
            response = await self.ws.recv()
            data = json.loads(response)

            if "lamport_time" in data:
                self.clock.update(data["lamport_time"])

            if data.get("status") != "ok":
                print("Login failed:", data.get("reason", "unknown"))
                return

            print(f"✅ Logged in as {username}")
            print(f"[Client Lamport: {self.clock.timestamp}] Connected to chat")

            # Start receiving messages in background
            asyncio.create_task(self.listen_messages())

            # Chat input loop
            while True:
                message = input("Enter message (or 'quit' to exit): ")
                if message.lower() == 'quit':
                    break

                if message.startswith("/pm "):
                    # Private message: /pm username message
                    parts = message.split(" ", 2)
                    if len(parts) >= 3:
                        to_user = parts[1]
                        pm_text = parts[2]

                        pm_time = self.clock.tick()
                        pm_msg = {
                            "type": "pm",
                            "to": to_user,
                            "message": pm_text,
                            "lamport_time": pm_time
                        }
                        await self.ws.send(json.dumps(pm_msg))
                        print(f"[Client Lamport: {pm_time}] PM sent to {to_user}")
                else:
                    # Regular chat message
                    msg_time = self.clock.tick()
                    chat_msg = {
                        "type": "chat",
                        "message": message,
                        "lamport_time": msg_time
                    }
                    await self.ws.send(json.dumps(chat_msg))
                    print(f"[Client Lamport: {msg_time}] Message sent")

        except Exception as e:
            print(f"Connection error: {e}")
        finally:
            if self.ws:
                await self.ws.close()

    async def listen_messages(self):
        """Background task to receive and display messages"""
        try:
            async for message in self.ws:
                data = json.loads(message)

                # Update our clock with received timestamp
                if "lamport_time" in data:
                    old_time = self.clock.timestamp
                    new_time = self.clock.update(data["lamport_time"])
                    print(f"[Clock sync: {old_time} → {new_time}]", end=" ")

                # Display different message types
                if data["type"] == "chat":
                    print(f"💬 {data['from']}: {data['message']}")
                elif data["type"] == "pm":
                    print(f"📩 PM from {data['from']}: {data['message']}")
                elif data["type"] == "system":
                    print(f"🔔 {data['message']}")
                elif data["type"] == "error":
                    print(f"❌ Error: {data['error']}")

        except Exception as e:
            print(f"Listen error: {e}")

async def main():
    client = ChatClient()

    print("=== Chat Client with Lamport Clock ===")
    username = input("Username: ")
    password = input("Password: ")

    await client.connect_and_chat(username, password)

if __name__ == "__main__":
    asyncio.run(main())
