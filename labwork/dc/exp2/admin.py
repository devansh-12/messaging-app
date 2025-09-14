
import xmlrpc.client
from datetime import datetime

def main():
    proxy = xmlrpc.client.ServerProxy("http://localhost:8000/")

    while True:
        print("\n--- Enhanced Admin Menu (with Lamport Clock Support) ---")
        print("1. List online users")
        print("2. Announce a message")
        print("3. Kick a user")
        print("4. View event log (with Lamport timestamps)")
        print("5. Exit")

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
                    print(f"\n--- Last {len(events)} Events (Ordered by Lamport Timestamp) ---")
                    for event in events:
                        timestamp = event["timestamp"]
                        event_type = event["type"]
                        details = event["details"]
                        real_time = datetime.fromtimestamp(event["real_time"]).strftime("%H:%M:%S")

                        print(f"[Lamport: {timestamp:3d}] [{real_time}] {event_type}: {details}")

            except Exception as e:
                print("Error:", e)

        elif choice == "5":
            print("Exiting admin client.")
            break

        else:
            print("Invalid choice, try again.")

if __name__ == "__main__":
    main()
