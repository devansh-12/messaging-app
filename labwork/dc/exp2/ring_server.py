import asyncio
import json
import subprocess
import time
import threading
import pathlib
from websockets import serve, WebSocketServerProtocol
from xmlrpc.server import SimpleXMLRPCServer
from dataclasses import dataclass
from typing import Optional, Dict, List
import uuid

# Lamport Clock (existing code)
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

@dataclass
class ServerNode:
    node_id: int
    address: str
    port: int
    is_alive: bool = True
    last_heartbeat: float = 0

class RingElectionManager:
    def __init__(self, my_id: int, my_port: int):
        self.my_id = my_id
        self.my_port = my_port
        self.leader_id: Optional[int] = None
        self.is_leader = False
        self.election_in_progress = False
        self.ring_nodes: Dict[int, ServerNode] = {}
        self.next_node_id: Optional[int] = None
        self.lock = threading.Lock()
        
        # Add self to ring
        self.ring_nodes[my_id] = ServerNode(my_id, "localhost", my_port)
        
    def add_node(self, node_id: int, address: str, port: int):
        """Add a new node to the ring"""
        with self.lock:
            self.ring_nodes[node_id] = ServerNode(node_id, address, port)
            self._update_ring_topology()
    
    def remove_node(self, node_id: int):
        """Remove a failed node from the ring"""
        with self.lock:
            if node_id in self.ring_nodes:
                del self.ring_nodes[node_id]
                self._update_ring_topology()
                
                # If removed node was leader, start election
                if self.leader_id == node_id:
                    self.leader_id = None
                    self.is_leader = False
                    return True  # Signal to start election
        return False
    
    def _update_ring_topology(self):
        """Update the logical ring structure"""
        sorted_ids = sorted(self.ring_nodes.keys())
        if not sorted_ids:
            self.next_node_id = None
            return
            
        # Find next node in ring
        my_index = sorted_ids.index(self.my_id) if self.my_id in sorted_ids else -1
        if my_index >= 0:
            next_index = (my_index + 1) % len(sorted_ids)
            self.next_node_id = sorted_ids[next_index]
    
    def start_election(self):
        """Initiate ring election"""
        with self.lock:
            if self.election_in_progress:
                return False
                
            self.election_in_progress = True
            print(f"[Node {self.my_id}] Starting election")
            
        # Create election message with our ID
        election_msg = {
            "type": "election",
            "candidate_ids": [self.my_id],
            "initiator_id": self.my_id
        }
        
        # Send to next node in ring
        asyncio.create_task(self._send_election_message(election_msg))
        return True
    
    async def _send_election_message(self, msg: dict):
        """Send election message to next node"""
        if not self.next_node_id or self.next_node_id == self.my_id:
            # We're the only node, become leader
            await self._become_leader()
            return
            
        try:
            # In real implementation, send via network to next node
            # For simulation, we'll handle it locally
            await self._handle_election_message(msg)
        except Exception as e:
            print(f"[Node {self.my_id}] Failed to send election message: {e}")
            # Remove failed node and retry
            if self.next_node_id:
                should_elect = self.remove_node(self.next_node_id)
                if should_elect and not self.election_in_progress:
                    self.start_election()
    
    async def _handle_election_message(self, msg: dict):
        """Handle incoming election message"""
        candidate_ids = msg.get("candidate_ids", [])
        initiator_id = msg.get("initiator_id")
        
        # If message returned to initiator, elect highest ID
        if initiator_id == self.my_id:
            highest_id = max(candidate_ids)
            await self._announce_coordinator(highest_id)
            return
        
        # Add our ID if we're higher than all current candidates
        if not candidate_ids or self.my_id > max(candidate_ids):
            candidate_ids.append(self.my_id)
        
        # Forward message to next node
        msg["candidate_ids"] = candidate_ids
        await self._send_election_message(msg)
    
    async def _announce_coordinator(self, leader_id: int):
        """Announce the new coordinator"""
        with self.lock:
            self.leader_id = leader_id
            self.is_leader = (leader_id == self.my_id)
            self.election_in_progress = False
        
        print(f"[Node {self.my_id}] New leader elected: {leader_id}")
        
        if self.is_leader:
            await self._become_leader()
        
        # Send coordinator message around ring
        coordinator_msg = {
            "type": "coordinator",
            "leader_id": leader_id,
            "initiator_id": self.my_id
        }
        
        # Broadcast to all nodes (in real implementation)
        await self._handle_coordinator_message(coordinator_msg)
    
    async def _become_leader(self):
        """Actions when becoming leader"""
        print(f"[Node {self.my_id}] I am now the LEADER!")
        self.is_leader = True
        # Start leader-specific tasks
        asyncio.create_task(self._leader_heartbeat())
        asyncio.create_task(self._coordinate_global_operations())
    
    async def _handle_coordinator_message(self, msg: dict):
        """Handle coordinator announcement"""
        leader_id = msg.get("leader_id")
        initiator_id = msg.get("initiator_id")
        
        with self.lock:
            self.leader_id = leader_id
            self.is_leader = (leader_id == self.my_id)
            self.election_in_progress = False
    
    async def _leader_heartbeat(self):
        """Leader sends periodic heartbeats"""
        if not self.is_leader:
            return
            
        while self.is_leader:
            # Send heartbeat to all nodes
            heartbeat_msg = {
                "type": "leader_heartbeat",
                "leader_id": self.my_id,
                "timestamp": time.time()
            }
            
            # Broadcast heartbeat (implementation depends on your network setup)
            await asyncio.sleep(5)  # Heartbeat every 5 seconds
    
    async def _coordinate_global_operations(self):
        """Leader coordinates global chat operations"""
        if not self.is_leader:
            return
            
        print(f"[Leader {self.my_id}] Starting coordination duties")
        # Leader-specific coordination tasks will be implemented here

# Global instances
global_clock = LamportClock()
election_manager: Optional[RingElectionManager] = None
clients = {}
username_to_ws = {}
event_log = []
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Enhanced event logging with leader coordination
def log_event(event_type: str, details: dict):
    timestamp = global_clock.tick()
    event = {
        "timestamp": timestamp,
        "type": event_type,
        "details": details,
        "real_time": time.time(),
        "coordinator_id": election_manager.leader_id if election_manager else None
    }
    event_log.append(event)
    
    # If we're the leader, coordinate this event globally
    if election_manager and election_manager.is_leader:
        print(f"[LEADER-{election_manager.my_id}] [Lamport: {timestamp}] {event_type}: {details}")
    else:
        print(f"[Node-{election_manager.my_id if election_manager else '?'}] [Lamport: {timestamp}] {event_type}: {details}")
    
    return timestamp

# RMI Login (existing)
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

# Enhanced broadcast with leader coordination
async def broadcast(payload: dict, exclude: WebSocketServerProtocol | None = None, timestamp: int = None):
    # If we're the leader, we coordinate all broadcasts
    if election_manager and election_manager.is_leader:
        if timestamp is None:
            timestamp = global_clock.tick()
        payload["lamport_time"] = timestamp
        payload["coordinated_by"] = election_manager.my_id
        
        # Leader ensures ordered delivery
        log_event("LEADER_COORDINATED_BROADCAST", {
            "message_type": payload.get("type"),
            "timestamp": timestamp
        })
    
    # Regular broadcast logic
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

# Enhanced WebSocket handler
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

        # Inform client about current leader
        leader_info = {
            "type": "login",
            "status": "ok",
            "token": token,
            "lamport_time": login_timestamp,
            "current_leader": election_manager.leader_id if election_manager else None,
            "node_id": election_manager.my_id if election_manager else None
        }
        await ws.send(json.dumps(leader_info))

        await broadcast({"type": "system", "message": f"🔔 {username} joined"}, exclude=ws)

        async for raw in ws:
            try:
                data = json.loads(raw)
                if "lamport_time" in data:
                    global_clock.update(data["lamport_time"])
            except Exception:
                await ws.send(json.dumps({"type": "error", "error": "bad_json"}))
                continue

            # Handle election-related messages
            if data.get("type") == "election":
                if election_manager:
                    await election_manager._handle_election_message(data)
                continue
            elif data.get("type") == "coordinator":
                if election_manager:
                    await election_manager._handle_coordinator_message(data)
                continue

            # Regular chat messages - coordinated by leader if available
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
                    await target.send(json.dumps({
                        "type": "pm", 
                        "from": username, 
                        "message": text, 
                        "lamport_time": timestamp,
                        "coordinated_by": election_manager.my_id if election_manager and election_manager.is_leader else None
                    }))
                else:
                    await ws.send(json.dumps({"type": "error", "error": "user_not_online"}))

    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        if ws in clients:
            username = clients[ws]["username"]
            log_event("USER_LEAVE", {"username": username})
            clients.pop(ws, None)
            username_to_ws.pop(username, None)
            await broadcast({"type": "system", "message": f"👋 {username} left"})

# Enhanced RPC functions
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

def rpc_get_leader_info():
    """New RPC function to get current leader information"""
    if election_manager:
        return {
            "current_leader": election_manager.leader_id,
            "my_id": election_manager.my_id,
            "is_leader": election_manager.is_leader,
            "ring_nodes": [{"id": nid, "address": node.address, "port": node.port} 
                          for nid, node in election_manager.ring_nodes.items()]
        }
    return {"error": "Election manager not initialized"}

def rpc_trigger_election():
    """New RPC function to manually trigger election (for testing)"""
    if election_manager:
        success = election_manager.start_election()
        return {"election_started": success}
    return {"error": "Election manager not initialized"}

def start_rpc_server(loop):
    srv = SimpleXMLRPCServer(("0.0.0.0", 8000), allow_none=True, logRequests=False)
    srv.register_function(rpc_list_users, "list_users")
    srv.register_function(rpc_announce, "announce")
    srv.register_function(rpc_kick, "kick")
    srv.register_function(rpc_get_event_log, "get_event_log")
    srv.register_function(rpc_get_leader_info, "get_leader_info")
    srv.register_function(rpc_trigger_election, "trigger_election")
    print("XML-RPC admin listening on http://localhost:8000")
    srv.serve_forever()

async def main_ws():
    async with serve(handle_ws, "0.0.0.0", 8765):
        print(f"WebSocket chat on ws://localhost:8765 (Node ID: {election_manager.my_id})")
        
        # Start election after a brief delay
        await asyncio.sleep(2)
        if election_manager:
            election_manager.start_election()
        
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    # Initialize election manager with unique node ID
    node_id = int(time.time()) % 10000  # Simple unique ID based on startup time
    election_manager = RingElectionManager(node_id, 8765)
    
    main_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(main_loop)

    # Start XML-RPC admin server in background thread
    t = threading.Thread(target=start_rpc_server, args=(main_loop,), daemon=True)
    t.start()

    print(f"Starting Ring Election Chat Server (Node ID: {node_id})")
    main_loop.run_until_complete(main_ws())

