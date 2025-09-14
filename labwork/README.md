# Experiment 2 - Authentication Server with Frontend

This experiment demonstrates a simple authentication workflow using:
- A **Java Authentication Server**
- A **Python backend server**
- A **static HTML frontend**

---

## Requirements

- Java JDK 8+
- Python 3.6+
- Any modern web browser (Chrome, Firefox, Edge, etc.)
- Linux or Windows environment

---

## Running on Linux

### Terminal 1 – Compile and Run the Java Authentication Server
javac exp2/*.java
java exp2.AuthServer

### Terminal 2 – Run the Python Server
python3 exp2/server.py

### Terminal 3 – Open the Frontend
xdg-open exp2/index.html

---

## Running on Windows

### Command Prompt / PowerShell 1 – Compile and Run the Java Authentication Server
javac exp2\*.java
java exp2.AuthServer

### Command Prompt / PowerShell 2 – Run the Python Server
python exp2\server.py

### Command Prompt / PowerShell 3 – Open the Frontend
start exp2\index.html

---

## Notes

- Keep all three processes running simultaneously.
- On Linux, use python3; on Windows, python should work if Python 3 is installed correctly.
- start (Windows) and xdg-open (Linux) open the HTML file in the default browser.
- If you face issues with ports, make sure no other service is running on the same port as your servers.

---

## Example Workflow

1. Compile and start the AuthServer (Java).
2. Run the Python server to handle requests.
3. Open the index.html file in your browser.
4. Interact with the system through the web interface.

---

## Project Structure

exp2/
├── AuthServer.java
├── OtherJavaFiles.java
├── server.py
└── index.html

---

Happy experimenting 🚀
