#!/usr/bin/env python3
import os
import sys
import time
import socket
import threading
import subprocess
import platform
from http.server import BaseHTTPRequestHandler, HTTPServer

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

MANAGER_PORT = 8010
SERVER_PORT = 8000
SERVER_CMD = [sys.executable, os.path.join(SCRIPT_DIR, "server.py"), "--no-browser"]


def is_port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def kill_port_process(port):
    system = platform.system().lower()
    if system.startswith("win"):
        try:
            output = subprocess.check_output(["netstat", "-ano"], text=True)
        except Exception:
            return
        pids = set()
        for line in output.splitlines():
            if f":{port} " in line and ("LISTEN" in line.upper()):
                parts = line.split()
                if parts:
                    pids.add(parts[-1])
        for pid in pids:
            subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return

    try:
        output = subprocess.check_output(["lsof", "-ti", f"tcp:{port}"]).decode().strip()
    except Exception:
        return
    if not output:
        return
    for pid in output.split():
        subprocess.run(["kill", pid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start_server():
    if is_port_open(SERVER_PORT):
        return True
    kill_port_process(SERVER_PORT)
    try:
        subprocess.Popen(
            SERVER_CMD,
            cwd=PROJECT_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        return False
    for _ in range(20):
        if is_port_open(SERVER_PORT):
            return True
        time.sleep(0.3)
    return False


class ManagerHandler(BaseHTTPRequestHandler):
    def _send(self, code=200, body=b"OK"):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, b"")

    def do_GET(self):
        if self.path == "/status":
            status = b"OK" if is_port_open(SERVER_PORT) else b"DOWN"
            self._send(200, status)
        else:
            self._send(404, b"Not Found")

    def do_POST(self):
        if self.path == "/restart":
            self._send(200, b"OK")
            threading.Thread(target=start_server, daemon=True).start()
        else:
            self._send(404, b"Not Found")


def run():
    start_server()
    server = HTTPServer(("127.0.0.1", MANAGER_PORT), ManagerHandler)
    server.serve_forever()


if __name__ == "__main__":
    run()
