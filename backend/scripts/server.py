#!/usr/bin/env python3
import base64
import io
import cgi
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

from PIL import Image, ImageEnhance
import numpy as np


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


def request_ollama_raw(host, payload):
    req = urllib.request.Request(
        f"{host}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


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


CATEGORY_LABELS = {
    "landscape": "风景",
    "people": "人物",
    "portrait": "人像",
    "car_model": "车模",
    "model": "模型",
    "unknown": "未识别",
}


def normalize_category(text):
    if not text:
        return "unknown"
    text = text.strip().lower()
    alias_map = {
        "landscape": "landscape",
        "scenery": "landscape",
        "scene": "landscape",
        "people": "people",
        "person": "people",
        "portrait": "portrait",
        "car_model": "car_model",
        "car-model": "car_model",
        "car": "car_model",
        "model": "model",
        "figure": "model",
        "unknown": "unknown",
        "none": "unknown",
    }
    return alias_map.get(text, "unknown")


def classify_image_ollama(host, model, image_bytes):
    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    prompt = (
        "你是图像分类器。只输出一个标签："
        "landscape, people, portrait, car_model, model, unknown。"
        "不要输出其它文字。"
    )
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [b64_image],
            }
        ],
    }
    data = request_ollama_raw(host, payload)
    content = data.get("message", {}).get("content", "")
    return normalize_category(content)


def classify_image_fallback(filename=""):
    lower = (filename or "").lower()
    if any(k in lower for k in ["portrait", "head", "face", "人像"]):
        return "portrait"
    if any(k in lower for k in ["people", "person", "人物", "合影", "group"]):
        return "people"
    if any(k in lower for k in ["landscape", "scenery", "风景", "mountain", "sea"]):
        return "landscape"
    if any(k in lower for k in ["car", "汽车", "车模", "auto"]):
        return "car_model"
    if any(k in lower for k in ["model", "模型", "figure"]):
        return "model"
    return "unknown"


def classify_image(image_bytes, filename=""):
    provider = HOST_CFG.get("provider", "ollama")
    if provider == "ollama":
        host = HOST_CFG.get("host")
        model = HOST_CFG.get("vision_model") or HOST_CFG.get("model")
        try:
            return classify_image_ollama(host, model, image_bytes)
        except Exception:
            return classify_image_fallback(filename)
    return classify_image_fallback(filename)


# --- Server Logic ---

# Global State
HISTORY = []
HOST_CFG = {}
HTTPD = None
LAST_HEARTBEAT = time.time()
HEARTBEAT_TIMEOUT_SEC = 60
ACTIVE_REQUESTS = 0
ACTIVE_REQUESTS_LOCK = threading.Lock()
ACTIVE_MODE = None

# Mode control
BOYFRIEND_SKILL_NAME = "boyfriend-mode"
MODE_ON_PHRASES = {"开启男友模式","男友模式"}
MODE_OFF_PHRASES = {"结束男友模式", "终止男友模式", "结束"}


def detect_mode_command(text):
    normalized = (text or "").strip()
    if normalized in MODE_ON_PHRASES:
        return "on"
    if normalized in MODE_OFF_PHRASES:
        return "off"
    return None


def mark_request_start():
    global ACTIVE_REQUESTS, LAST_HEARTBEAT
    with ACTIVE_REQUESTS_LOCK:
        ACTIVE_REQUESTS += 1
    LAST_HEARTBEAT = time.time()


def mark_request_end():
    global ACTIVE_REQUESTS
    with ACTIVE_REQUESTS_LOCK:
        ACTIVE_REQUESTS = max(0, ACTIVE_REQUESTS - 1)


def should_request_more_info(text):
    if not text:
        return False
    return re.search(r"(需要更多信息|信息不足|请提供|请补充|补充信息|无法提供)", text) is not None


def parse_range_value(text):
    if not text:
        return None
    m = re.search(r"([+\-]?\d+(?:\.\d+)?)\s*(?:~|-|—|至)\s*([+\-]?\d+(?:\.\d+)?)", text)
    if m:
        a = float(m.group(1))
        b = float(m.group(2))
        return (a + b) / 2
    m = re.search(r"([+\-]?\d+(?:\.\d+)?)", text)
    if m:
        return float(m.group(1))
    return None


def derive_warmth_from_text(text):
    if not text:
        return None
    m = re.search(r"(\d{4,5})\s*K", text, re.IGNORECASE)
    if m:
        kelvin = float(m.group(1))
        delta = (kelvin - 6500) / 6500
        return max(0.85, min(1.15, 1 + delta * 0.15))
    if "冷" in text:
        return 0.97
    if "暖" in text:
        return 1.03
    return None


def parse_adjustments(reply):
    if not reply:
        return {}
    adjustments = {}

    def match_value(pattern):
        m = re.search(pattern, reply)
        return parse_range_value(m.group(1)) if m else None

    exposure = match_value(r"曝光[^0-9+\-]*([^\n，。]*)")
    if exposure is not None:
        adjustments["exposure"] = max(-0.5, min(0.5, exposure / 100))

    contrast = match_value(r"对比度?[^0-9+\-]*([^\n，。]*)")
    if contrast is not None:
        adjustments["contrast"] = max(0.5, min(1.5, 1 + contrast / 100))

    saturation = match_value(r"饱和度[^0-9+\-]*([^\n，。]*)")
    if saturation is not None:
        adjustments["saturation"] = max(0.5, min(1.5, 1 + saturation / 100))

    warmth_text = re.search(r"色温[^0-9+\-]*([^\n，。]*)", reply)
    warmth_delta = parse_range_value(warmth_text.group(1)) if warmth_text else None
    if warmth_delta is not None:
        adjustments["warmth"] = max(0.85, min(1.15, 1 + warmth_delta / 100))
    else:
        warmth = derive_warmth_from_text(warmth_text.group(1) if warmth_text else reply)
        if warmth is not None:
            adjustments["warmth"] = max(0.85, min(1.15, warmth))

    highlights = match_value(r"高光[^0-9+\-]*([^\n，。]*)")
    if highlights is not None:
        adjustments["highlights"] = max(-100, min(100, highlights))

    shadows = match_value(r"阴影[^0-9+\-]*([^\n，。]*)")
    if shadows is not None:
        adjustments["shadows"] = max(-100, min(100, shadows))

    whites = match_value(r"白色[^0-9+\-]*([^\n，。]*)")
    if whites is not None:
        adjustments["whites"] = max(-100, min(100, whites))

    blacks = match_value(r"黑色[^0-9+\-]*([^\n，。]*)")
    if blacks is not None:
        adjustments["blacks"] = max(-100, min(100, blacks))

    clarity = match_value(r"清晰度[^0-9+\-]*([^\n，。]*)")
    if clarity is not None:
        adjustments["clarity"] = max(-100, min(100, clarity))

    return adjustments


def apply_adjustments(image_bytes, adjustments):
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    arr = np.asarray(image).astype(np.float32)

    exposure = adjustments.get("exposure", 0)
    contrast = adjustments.get("contrast", 1)
    saturation = adjustments.get("saturation", 1)
    warmth = adjustments.get("warmth", 1)
    highlights = adjustments.get("highlights", 0)
    shadows = adjustments.get("shadows", 0)
    whites = adjustments.get("whites", 0)
    blacks = adjustments.get("blacks", 0)
    clarity = adjustments.get("clarity", 0)

    arr = arr * (1 + exposure)
    arr = (arr - 128) * contrast + 128

    luma = (arr[:, :, 0] * 0.2126 + arr[:, :, 1] * 0.7152 + arr[:, :, 2] * 0.0722) / 255.0
    if highlights:
        delta = (highlights / 100) * 80
        arr[luma > 0.5] += delta
    if shadows:
        delta = (shadows / 100) * 80
        arr[luma < 0.5] += delta
    if whites:
        delta = (whites / 100) * 60
        arr[luma > 0.5] += delta
    if blacks:
        delta = (blacks / 100) * 60
        arr[luma < 0.5] += delta
    if clarity:
        clarity_factor = 1 + (clarity / 100) * 0.3
        arr = (arr - 128) * clarity_factor + 128

    arr[:, :, 0] *= warmth
    arr[:, :, 2] *= (2 - warmth)

    arr = np.clip(arr, 0, 255).astype(np.uint8)
    image = Image.fromarray(arr, mode="RGB")
    if saturation != 1:
        image = ImageEnhance.Color(image).enhance(saturation)

    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()

class ChatHandler(BaseHTTPRequestHandler):
    def _send_response(self, status, content_type, content):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        global LAST_HEARTBEAT
        mark_request_start()
        try:
            if self.path == '/' or self.path == '/index.html':
                LAST_HEARTBEAT = time.time()
                try:
                    with open(os.path.join(FRONTEND_DIR, 'index.html'), 'rb') as f:
                        self._send_response(200, 'text/html', f.read())
                except FileNotFoundError:
                    self._send_response(404, 'text/plain', b'index.html not found')
            elif self.path.startswith('/assets/'):
                LAST_HEARTBEAT = time.time()
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
                LAST_HEARTBEAT = time.time()
                skills = list_skills(SKILLS_DIR)
                # Simplify for frontend
                simple_skills = [{"name": s["name"], "description": s["description"]} for s in skills]
                self._send_response(200, 'application/json', json.dumps(simple_skills).encode('utf-8'))
            elif self.path == '/heartbeat':
                LAST_HEARTBEAT = time.time()
                self._send_response(200, 'text/plain', b'OK')
            elif self.path == '/shutdown':
                LAST_HEARTBEAT = time.time()
                self._send_response(200, 'text/plain', b'OK')
                if HTTPD:
                    threading.Thread(target=HTTPD.shutdown, daemon=True).start()
            else:
                self._send_response(404, 'text/plain', b'Not Found')
        finally:
            mark_request_end()

    def do_POST(self):
        global LAST_HEARTBEAT
        mark_request_start()
        try:
            if self.path == '/chat':
                LAST_HEARTBEAT = time.time()
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                try:
                    data = json.loads(post_data)
                    user_msg = data.get('message', '')
                    selected_skill = data.get('skill', None) # Get selected skill
                    image_data = data.get('image_data', '') or ''

                    image_bytes = None
                    if image_data:
                        if image_data.startswith("data:"):
                            _, image_data = image_data.split(",", 1)
                        image_bytes = base64.b64decode(image_data)
                        if "[[IMAGE_ATTACHED]]" not in user_msg:
                            user_msg = f"{user_msg}\n[[IMAGE_ATTACHED]]"

                    if not user_msg:
                        raise ValueError("Empty message")

                    reply, skill_name = self.process_chat(user_msg, selected_skill)

                    image_base64 = None
                    if image_bytes and not should_request_more_info(reply):
                        adjustments = parse_adjustments(reply)
                        graded_bytes = apply_adjustments(image_bytes, adjustments)
                        image_base64 = base64.b64encode(graded_bytes).decode("utf-8")

                    resp = json.dumps({
                        'reply': reply,
                        'skill': skill_name,
                        'image_base64': image_base64,
                    }).encode('utf-8')
                    self._send_response(200, 'application/json', resp)
                except Exception as e:
                    resp = json.dumps({'error': str(e)}).encode('utf-8')
                    self._send_response(500, 'application/json', resp)
            elif self.path == '/analyze-image':
                LAST_HEARTBEAT = time.time()
                try:
                    content_type = self.headers.get('Content-Type', '')
                    ctype, _ = cgi.parse_header(content_type)
                    if ctype != 'multipart/form-data':
                        raise ValueError("Invalid content type")

                    form = cgi.FieldStorage(
                        fp=self.rfile,
                        headers=self.headers,
                        environ={'REQUEST_METHOD': 'POST'},
                        keep_blank_values=True,
                    )
                    if 'image' not in form:
                        raise ValueError("Missing image")
                    file_item = form['image']
                    if not file_item.file:
                        raise ValueError("Invalid image data")

                    filename = file_item.filename or ""
                    image_bytes = file_item.file.read()
                    if not image_bytes:
                        raise ValueError("Empty image data")

                    category = classify_image(image_bytes, filename)
                    label = CATEGORY_LABELS.get(category, CATEGORY_LABELS["unknown"])
                    resp = json.dumps({
                        "category": category,
                        "label": label,
                    }).encode('utf-8')
                    self._send_response(200, 'application/json', resp)
                except Exception as e:
                    resp = json.dumps({'error': str(e)}).encode('utf-8')
                    self._send_response(400, 'application/json', resp)
            else:
                self._send_response(404, 'application/json', b'{}')
        finally:
            mark_request_end()

    def process_chat(self, user_text, selected_skill_name=None):
        global HISTORY, ACTIVE_MODE
        request_fn = HOST_CFG['request_fn']
        model = HOST_CFG['model']
        skills_root = SKILLS_DIR
        base_prompt = "你是一个助手。回答要清晰、分步骤。"

        # 0. Update mode state
        mode_command = detect_mode_command(user_text)
        if mode_command == "on":
            ACTIVE_MODE = BOYFRIEND_SKILL_NAME
        elif mode_command == "off":
            ACTIVE_MODE = None

        # 1. Choose Skill
        skills = list_skills(skills_root)
        chosen = None
        
        # If manual selection is provided and valid (not "auto")
        if selected_skill_name and selected_skill_name != "auto":
            for s in skills:
                if s["name"] == selected_skill_name:
                    chosen = s
                    break
        elif ACTIVE_MODE:
            for s in skills:
                if s["name"] == ACTIVE_MODE:
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
    vision_model = os.getenv("OLLAMA_VISION_MODEL", "")
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
        
    return {
        'request_fn': request_fn,
        'model': model,
        'vision_model': vision_model,
        'provider': provider,
        'host': host,
    }


def open_browser():
    webbrowser.open("http://localhost:8000")


def monitor_inactivity():
    while True:
        time.sleep(2)
        if HTTPD is None:
            continue
        with ACTIVE_REQUESTS_LOCK:
            active = ACTIVE_REQUESTS
        if active > 0:
            continue
        if time.time() - LAST_HEARTBEAT > HEARTBEAT_TIMEOUT_SEC:
            HTTPD.shutdown()
            break


if __name__ == '__main__':
    HOST_CFG = init_config()
    server_host = os.getenv("SERVER_HOST", "127.0.0.1")
    server_address = (server_host, 8000)
    print(f"Starting server on http://{server_host}:8000")
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
