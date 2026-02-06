#!/usr/bin/env python3
import json
import os
import re
import sys
import urllib.request
import mimetypes
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
import webbrowser
from threading import Timer


# --- Paths ---

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
ASSETS_DIR = os.path.join(FRONTEND_DIR, "assets")
SKILLS_DIR = os.path.join(PROJECT_ROOT, "skills")

# --- Skill / Chat Logic (from run_skill.py) ---

def read_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def collect_reference_files(skill_dir):
    reference_dir = os.path.join(skill_dir, "reference")
    if not os.path.isdir(reference_dir):
        return []
    files = []
    for name in sorted(os.listdir(reference_dir)):
        path = os.path.join(reference_dir, name)
        if os.path.isfile(path):
            files.append((f"reference/{name}", read_text(path)))
    return files


def parse_skill_file(skill_path):
    lines = read_text(skill_path).splitlines()
    meta = {}
    body_lines = []
    idx = 0
    if lines and lines[0].strip() == "---":
        idx = 1
        for i in range(1, len(lines)):
            line = lines[i].strip()
            if line == "---":
                idx = i + 1
                break
            if ":" in line:
                key, value = line.split(":", 1)
                meta[key.strip()] = value.strip()
    body_lines = lines[idx:]
    return meta, "\n".join(body_lines).strip()


def build_system_prompt(skill_text, references):
    parts = [
        "你是一个助手。回答要清晰、分步骤。",
        "以下是技能指令（SKILL.md）：",
        skill_text,
    ]
    if references:
        parts.append("以下是参考资料：")
        for name, content in references:
            parts.append(f"### {name}\n{content}")
    return "\n\n".join(parts)


def list_skills(skills_root):
    if not os.path.isdir(skills_root):
        return []
    skills = []
    for name in sorted(os.listdir(skills_root)):
        skill_dir = os.path.join(skills_root, name)
        skill_file = os.path.join(skill_dir, "SKILL.md")
        if os.path.isdir(skill_dir) and os.path.isfile(skill_file):
            meta, _ = parse_skill_file(skill_file)
            skills.append({
                "name": meta.get("name", name),
                "description": meta.get("description", "无描述"),
                "dir": skill_dir,
                "file": skill_file,
            })
    return skills


def request_chat_ollama(host, payload):
    req = urllib.request.Request(
        f"{host}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = resp.read().decode("utf-8")
    data = json.loads(body)
    return data.get("message", {}).get("content", "")


def request_chat_deepseek(base_url, api_key, payload):
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = resp.read().decode("utf-8")
    data = json.loads(body)
    choices = data.get("choices", [])
    if not choices:
        return ""
    return choices[0].get("message", {}).get("content", "")


def choose_skill_by_model(request_fn, model, skills, user_text):
    if not skills:
        return None
    options = "\n".join(
        f"- {s['name']}: {s['description']}" for s in skills
    )
    selector_prompt = (
        "你是一个技能选择器。根据用户需求，只输出一个技能名称，"
        "如果没有合适技能，输出 NONE。\n\n"
        "可选技能列表：\n"
        f"{options}\n\n"
        f"用户输入：{user_text}"
    )
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": "只输出技能名称或 NONE，不要其他文字。"},
            {"role": "user", "content": selector_prompt},
        ],
    }
    choice = request_fn(payload).strip()
    choice = re.sub(r"[^a-zA-Z0-9_\-]+", "", choice)
    if not choice or choice.upper() == "NONE":
        return None
    for skill in skills:
        if skill["name"] == choice:
            return skill
    return None


def extract_city_by_model(request_fn, model, user_text):
    selector_prompt = (
        "从用户输入中提取城市名，只输出城市名或 NONE。"
        "不要输出其它文字。\n\n"
        f"用户输入：{user_text}"
    )
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": "只输出城市名或 NONE。"},
            {"role": "user", "content": selector_prompt},
        ],
    }
    try:
        choice = request_fn(payload).strip()
    except Exception:
        return None
    choice = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff\-]+", "", choice)
    if not choice or choice.upper() == "NONE":
        return None
    return choice


def get_city_by_ip():
    try:
        req = urllib.request.Request(
            "https://ipinfo.io/json",
            headers={"User-Agent": "skill-client"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
        data = json.loads(body)
        return data.get("city")
    except Exception:
        return None


def build_skill_prompt(skill_file, skill_dir, user_text, request_fn, model):
    skill_text = read_text(skill_file)
    references = collect_reference_files(skill_dir)
    system_prompt = build_system_prompt(skill_text, references)

    meta, _ = parse_skill_file(skill_file)
    if meta.get("name") == "weather":
        city = extract_city_by_model(request_fn, model, user_text)
        if not city:
            city = get_city_by_ip() or "当前位置"
        system_prompt += (
            "\n\n[系统提示] 如果用户未指定城市，请使用解析到的城市："
            f"{city}。"
        )
    return system_prompt


# --- Server Logic ---

# Global State
HISTORY = []
HOST_CFG = {}
HTTPD = None
LAST_HEARTBEAT = time.time()
HEARTBEAT_TIMEOUT_SEC = 30

class ChatHandler(BaseHTTPRequestHandler):
    def _send_response(self, status, content_type, content):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            try:
                with open(os.path.join(FRONTEND_DIR, 'index.html'), 'rb') as f:
                    self._send_response(200, 'text/html', f.read())
            except FileNotFoundError:
                self._send_response(404, 'text/plain', b'index.html not found')
        elif self.path.startswith('/assets/'):
            rel_path = os.path.normpath(self.path[len('/assets/'):])
            if rel_path.startswith('..') or rel_path.startswith('/'):
                self._send_response(403, 'text/plain', b'Forbidden')
                return
            asset_path = os.path.join(ASSETS_DIR, rel_path)
            if not os.path.isfile(asset_path):
                self._send_response(404, 'text/plain', b'Asset not found')
                return
            content_type, _ = mimetypes.guess_type(asset_path)
            if not content_type:
                content_type = 'application/octet-stream'
            try:
                with open(asset_path, 'rb') as f:
                    self._send_response(200, content_type, f.read())
            except Exception:
                self._send_response(500, 'text/plain', b'Failed to load asset')
        elif self.path == '/skills':
            skills = list_skills(SKILLS_DIR)
            # Simplify for frontend
            simple_skills = [{"name": s["name"], "description": s["description"]} for s in skills]
            self._send_response(200, 'application/json', json.dumps(simple_skills).encode('utf-8'))
        elif self.path == '/heartbeat':
            global LAST_HEARTBEAT
            LAST_HEARTBEAT = time.time()
            self._send_response(200, 'text/plain', b'OK')
        elif self.path == '/shutdown':
            self._send_response(200, 'text/plain', b'OK')
            if HTTPD:
                threading.Thread(target=HTTPD.shutdown, daemon=True).start()
        else:
            self._send_response(404, 'text/plain', b'Not Found')

    def do_POST(self):
        if self.path == '/chat':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data)
                user_msg = data.get('message', '')
                selected_skill = data.get('skill', None) # Get selected skill

                if not user_msg:
                    raise ValueError("Empty message")

                reply, skill_name = self.process_chat(user_msg, selected_skill)
                
                resp = json.dumps({'reply': reply, 'skill': skill_name}).encode('utf-8')
                self._send_response(200, 'application/json', resp)
            except Exception as e:
                resp = json.dumps({'error': str(e)}).encode('utf-8')
                self._send_response(500, 'application/json', resp)

    def process_chat(self, user_text, selected_skill_name=None):
        global HISTORY
        request_fn = HOST_CFG['request_fn']
        model = HOST_CFG['model']
        skills_root = SKILLS_DIR
        base_prompt = "你是一个助手。回答要清晰、分步骤。"

        # 1. Choose Skill
        skills = list_skills(skills_root)
        chosen = None
        
        # If manual selection is provided and valid (not "auto")
        if selected_skill_name and selected_skill_name != "auto":
            for s in skills:
                if s["name"] == selected_skill_name:
                    chosen = s
                    break
        else:
            # Auto selection
            chosen = choose_skill_by_model(request_fn, model, skills, user_text)
        
        skill_name = None
        if chosen:
            skill_name = chosen['name']
            system_prompt = build_skill_prompt(
                chosen["file"], chosen["dir"], user_text, request_fn, model
            )
        else:
            system_prompt = base_prompt

        # 2. Build Messages
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(HISTORY)
        messages.append({"role": "user", "content": user_text})

        # 3. Call Model
        payload = {
            "model": model,
            "stream": False,
            "messages": messages,
        }
        
        reply = request_fn(payload) or ""
        
        # 4. Update History
        HISTORY.append({"role": "user", "content": user_text})
        HISTORY.append({"role": "assistant", "content": reply})
        HISTORY = HISTORY[-6:]  # Keep last 3 turns

        return reply, skill_name


def load_env_file():
    """Simple .env loader to avoid dependencies"""
    # Look for .env in cwd, project root, or alongside this script
    candidates = [
        ".env",
        os.path.join(PROJECT_ROOT, ".env"),
        os.path.join(os.path.dirname(__file__), ".env"),
    ]
    
    env_path = None
    for c in candidates:
        if os.path.exists(c):
            env_path = c
            break
            
    if not env_path:
        return

    print(f"Loading environment from {os.path.abspath(env_path)}...")
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    # Remove surrounding quotes
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    
                    if key not in os.environ:
                        os.environ[key] = value
    except Exception as e:
        print(f"Warning: Failed to read .env file: {e}")


def init_config():
    load_env_file()
    
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL", "deepseek-r1:7b")
    provider = os.getenv("LLM_PROVIDER", "").lower()
    deepseek_base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
    
    if not provider:
        provider = "deepseek" if deepseek_api_key else "ollama"

    print("-" * 30)
    print(f"Config Initialized:")
    print(f"  Provider: {provider}")
    print(f"  Model: {model if provider == 'ollama' else os.getenv('DEEPSEEK_MODEL', 'deepseek-chat')}")
    print(f"  OLLAMA_HOST: {host}")
    print(f"  DEEPSEEK_BASE_URL: {deepseek_base_url}")
    if provider == "deepseek":
         print(f"  API Key: {'*' * 6 if deepseek_api_key else 'MISSING'}")
    print("-" * 30)

    if provider == "deepseek":
        model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        if not deepseek_api_key:
            print("Error: DEEPSEEK_API_KEY not found.")
            sys.exit(1)
        request_fn = lambda payload: request_chat_deepseek(
            deepseek_base_url, deepseek_api_key, payload
        )
    else:
        request_fn = lambda payload: request_chat_ollama(host, payload)
        
    return {'request_fn': request_fn, 'model': model}


def open_browser():
    webbrowser.open("http://localhost:8000")


def monitor_inactivity():
    while True:
        time.sleep(2)
        if HTTPD is None:
            continue
        if time.time() - LAST_HEARTBEAT > HEARTBEAT_TIMEOUT_SEC:
            HTTPD.shutdown()
            break


if __name__ == '__main__':
    HOST_CFG = init_config()
    server_address = ('', 8000)
    print("Starting server on http://localhost:8000")
    if "--no-browser" not in sys.argv:
        print("Auto-opening browser...")
        Timer(1, open_browser).start()
    else:
        print("Browser auto-open disabled (--no-browser).")
    
    HTTPD = HTTPServer(server_address, ChatHandler)
    threading.Thread(target=monitor_inactivity, daemon=True).start()
    try:
        HTTPD.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        HTTPD.server_close()
