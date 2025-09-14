import xmlrpc.client
from datetime import datetime

def main():
    proxy = xmlrpc.client.ServerProxy("http://localhost:8000/")
    
    while True:
        print("\n--- Ring Election Chat Admin ---")
        print("1. List online users")
        print("2. Announce a message")
        print("3. Kick a user")
        print("4. View event log (with leader coordination)")
        print("5. Get leader information")
        print("6. Trigger election (testing)")
        print("7. Exit")
        
        choice = input("Enter choice: ").strip()
        
        if choice == "1":
            try:
                users = proxy.list_users()
                print("Online users:", users if users else "(none)")
            except Exception as e:
                print("Error:", e)
        
        elif choice == "2":
            msg = input("Enter message to announce: ").strip()
            if msg:
                try:
                    ok = proxy.announce(msg)
                    print("Announcement sent." if ok else "Failed to send.")
                except Exception as e:
                    print("Error:", e)
        
        elif choice == "3":
            try:
                users = proxy.list_users()
                if not users:
                    print("No users online to kick.")
                    continue
                
                print("Online users:", users)
                username = input("Enter username to kick: ").strip()
                
                if username not in users:
                    print(f"Invalid user: '{username}'. Must be one of {users}.")
                    continue
                
                ok = proxy.kick(username)
                print(f"User '{username}' kicked." if ok else f"Failed to kick '{username}'.")
            except Exception as e:
                print("Error:", e)
        
        elif choice == "4":
            try:
                limit = input("Enter number of recent events to show (default 20): ").strip()
                limit = int(limit) if limit.isdigit() else 20
                
                events = proxy.get_event_log(limit)
                if not events:
                    print("No events in log.")
                else:
                    print(f"\n--- Last {len(events)} Events (with Leader Coordination) ---")
                    for event in events:
                        timestamp = event["timestamp"]
                        event_type = event["type"]
                        details = event["details"]
                        coordinator = event.get("coordinator_id", "N/A")
                        real_time = datetime.fromtimestamp(event["real_time"]).strftime("%H:%M:%S")
                        print(f"[Lamport: {timestamp:3d}] [{real_time}] [Leader: {coordinator}] {event_type}: {details}")
            except Exception as e:
                print("Error:", e)
        
        elif choice == "5":
            try:
                info = proxy.get_leader_info()
                if "error" in info:
                    print("Error:", info["error"])
                else:
                    print("\n--- Ring Election Status ---")
                    print(f"Current Leader: {info['current_leader']}")
                    print(f"My Node ID: {info['my_id']}")
                    print(f"Am I Leader: {'YES' if info['is_leader'] else 'NO'}")
                    print(f"Ring Nodes: {len(info['ring_nodes'])}")
                    for node in info['ring_nodes']:
                        print(f"  - Node {node['id']}: {node['address']}:{node['port']}")
            except Exception as e:
                print("Error:", e)
        
        elif choice == "6":
            try:
                result = proxy.trigger_election()
                if "error" in result:
                    print("Error:", result["error"])
                else:
                    print("Election triggered:", "Success" if result["election_started"] else "Already in progress")
            except Exception as e:
                print("Error:", e)
        
        elif choice == "7":
            print("Exiting admin client.")
            break
        
        else:
            print("Invalid choice, try again.")

if __name__ == "__main__":
    main()

