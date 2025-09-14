import asyncio
import json
import subprocess
from websockets import serve, WebSocketServerProtocol
from xmlrpc.server import SimpleXMLRPCServer
import threading
import pathlib
import time  # Added import for real time

# Lamport Clock implementation
class LamportClock:
    def __init__(self):
        self.timestamp = 0
        self.lock = threading.Lock()
    def tick(self):
        with self.lock:
            self.timestamp += 1
            return self.timestamp
    def update(self, received_time):
        with self.lock:
            self.timestamp = max(self.timestamp, received_time) + 1
            return self.timestamp
    def get_time(self):
        with self.lock:
            return self.timestamp

global_clock = LamportClock()

clients = {}  # ws -> {"username": str, "token": str, "last_seen": int}
username_to_ws = {}  # username -> ws
event_log = []  # Logs with Lamport timestamps

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Helper to log events with Lamport timestamps
def log_event(event_type: str, details: dict):
    timestamp = global_clock.tick()
    event = {
        "timestamp": timestamp,
        "type": event_type,
        "details": details,
        "real_time": time.time()   # Changed to use time.time()
    }
    event_log.append(event)
    print(f"[Lamport: {timestamp}] {event_type}: {details}")
    return timestamp

# RMI Login Bridge
def rmi_login(username: str, password: str) -> str | None:
    try:
        out = subprocess.check_output(
            ["java", "exp2.AuthClient", username, password],
            cwd=PROJECT_ROOT,
            stderr=subprocess.STDOUT,
            timeout=5,
            text=True,
        ).strip()
        if out in ("AUTH_FAIL", "AUTH_ERROR"):
            return None
        return out
    except Exception as e:
        print("AuthClient failed:", e)
        return None

async def broadcast(payload: dict, exclude: WebSocketServerProtocol | None = None, timestamp: int = None):
    if timestamp is None:
        timestamp = global_clock.tick()
    payload["lamport_time"] = timestamp

    dead = []
    for ws in list(clients.keys()):
        if ws is exclude:
            continue
        try:
            await ws.send(json.dumps(payload))
        except Exception:
            dead.append(ws)
    for ws in dead:
        try:
            u = clients[ws]["username"]
            del username_to_ws[u]
        except Exception:
            pass
        clients.pop(ws, None)

async def handle_ws(ws: WebSocketServerProtocol):
    try:
        hello = await asyncio.wait_for(ws.recv(), timeout=15)
        msg = json.loads(hello)

        if msg.get("type") != "login":
            await ws.send(json.dumps({"type": "error", "error": "expected login"}))
            return

        username = str(msg.get("username", "")).strip()
        password = str(msg.get("password", ""))

        login_timestamp = log_event("LOGIN_ATTEMPT", {"username": username})

        token = rmi_login(username, password)
        if not token:
            log_event("LOGIN_FAIL", {"username": username})
            await ws.send(json.dumps({"type": "login", "status": "fail", "reason": "invalid"}))
            return

        clients[ws] = {"username": username, "token": token, "last_seen": login_timestamp}
        username_to_ws[username] = ws
        log_event("USER_JOIN", {"username": username})

        await ws.send(json.dumps({
            "type": "login",
            "status": "ok",
            "token": token,
            "lamport_time": login_timestamp
        }))

        await broadcast({"type": "system", "message": f"🔔 {username} joined"}, exclude=ws)

        async for raw in ws:
            try:
                data = json.loads(raw)
                if "lamport_time" in data:
                    global_clock.update(data["lamport_time"])
            except Exception:
                await ws.send(json.dumps({"type": "error", "error": "bad_json"}))
                continue

            if data.get("type") == "chat":
                text = str(data.get("message", ""))
                timestamp = log_event("CHAT_MESSAGE", {"from": username, "message": text})
                await broadcast({"type": "chat", "from": username, "message": text}, timestamp=timestamp)

            elif data.get("type") == "pm":
                to = data.get("to")
                text = str(data.get("message", ""))
                target = username_to_ws.get(to)
                if target:
                    timestamp = log_event("PRIVATE_MESSAGE", {"from": username, "to": to, "message": text})
                    await target.send(json.dumps({"type": "pm", "from": username, "message": text, "lamport_time": timestamp}))
                else:
                    await ws.send(json.dumps({"type": "error", "error": "user_not_online"}))
            else:
                await ws.send(json.dumps({"type": "error", "error": "unknown_type"}))
    except Exception:
        pass
    finally:
        if ws in clients:
            username = clients[ws]["username"]
            log_event("USER_LEAVE", {"username": username})
            clients.pop(ws, None)
            username_to_ws.pop(username, None)
            await broadcast({"type": "system", "message": f"👋 {username} left"})

# XML-RPC Admin server functions
def rpc_list_users():
    log_event("ADMIN_LIST_USERS", {})
    return sorted([meta["username"] for meta in clients.values()])

def rpc_announce(message):
    timestamp = log_event("ADMIN_ANNOUNCE", {"message": message})
    asyncio.run_coroutine_threadsafe(
        broadcast({"type": "system", "message": f"[ADMIN] {message}"}, timestamp=timestamp), main_loop
    )
    return True

def rpc_kick(username):
    timestamp = log_event("ADMIN_KICK", {"username": username})
    ws = username_to_ws.get(username)
    if not ws:
        return False
    asyncio.run_coroutine_threadsafe(ws.close(code=4000, reason="kicked"), main_loop)
    return True

def rpc_get_event_log(limit=50):
    return event_log[-limit:] if event_log else []

def start_rpc_server(loop):
    srv = SimpleXMLRPCServer(("0.0.0.0", 8000), allow_none=True, logRequests=False)
    srv.register_function(rpc_list_users, "list_users")
    srv.register_function(rpc_announce, "announce")
    srv.register_function(rpc_kick, "kick")
    srv.register_function(rpc_get_event_log, "get_event_log")
    print("XML-RPC admin listening on http://localhost:8000")
    srv.serve_forever()

async def main_ws():
    async with serve(handle_ws, "0.0.0.0", 8765):
        print("WebSocket chat on ws://localhost:8765")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    main_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(main_loop)

    # Start XML-RPC admin server in background thread, passing main_loop
    t = threading.Thread(target=start_rpc_server, args=(main_loop,), daemon=True)
    t.start()

    main_loop.run_until_complete(main_ws())

