#!/usr/bin/env python3
import json
import os
import re
import sys
import urllib.request


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


def score_skill(skill, user_text):
    name = skill["name"].lower()
    desc = skill["description"].lower()
    text = user_text.lower()

    score = 0
    if name in text:
        score += 4
    if desc in text:
        score += 3

    tokens = re.split(r"[^a-z0-9\u4e00-\u9fff]+", f"{name} {desc}")
    tokens = [t for t in tokens if len(t) >= 2]
    for t in tokens:
        if t and t in text:
            score += 1
    return score


def choose_skill_auto(skills, user_text):
    best = None
    best_score = 0
    for skill in skills:
        score = score_skill(skill, user_text)
        if score > best_score:
            best = skill
            best_score = score
    return best


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


def load_ollama_options():
    raw = os.getenv("OLLAMA_OPTIONS", "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print("警告: OLLAMA_OPTIONS 不是有效 JSON，将忽略。")
        return {}


def chat_loop(request_fn, model, system_prompt, options, assistant_label):
    print("进入连续对话模式，输入 /exit 退出。")
    history = []
    while True:
        try:
            user_text = input("你> ").strip()
        except EOFError:
            break
        if not user_text:
            continue
        if user_text.lower() in ("/exit", "exit", "quit", "/quit"):
            break

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_text})

        payload = {
            "model": model,
            "stream": False,
            "messages": messages,
            **options,
        }
        try:
            reply = request_fn(payload) or ""
        except Exception as exc:
            print("请求失败:", exc)
            continue
        print(f"\n{assistant_label}> {reply}\n")
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": reply})
        history = history[-6:]


def chat_auto_loop(request_fn, model, skills, options, assistant_label):
    print("进入连续对话模式（自动选技能），输入 /exit 退出。")
    history = []
    base_prompt = "你是一个助手。回答要清晰、分步骤。"
    while True:
        try:
            user_text = input("你> ").strip()
        except EOFError:
            break
        if not user_text:
            continue
        if user_text.lower() in ("/exit", "exit", "quit", "/quit"):
            break

        chosen = choose_skill_by_model(request_fn, model, skills, user_text)
        if chosen:
            print(f"[CHAT-AUTO] 使用技能：{chosen['name']}")
            skill_text = read_text(chosen["file"])
            references = collect_reference_files(chosen["dir"])
            system_prompt = build_system_prompt(skill_text, references)
        else:
            system_prompt = base_prompt

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_text})

        payload = {
            "model": model,
            "stream": False,
            "messages": messages,
            **options,
        }
        try:
            reply = request_fn(payload) or ""
        except Exception as exc:
            print("请求失败:", exc)
            continue
        print(f"\n{assistant_label}> {reply}\n")
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": reply})
        history = history[-6:]


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 scripts/run_skill.py --list")
        print("  python3 scripts/run_skill.py --auto \"用户输入\"")
        print("  python3 scripts/run_skill.py --model-auto \"用户输入\"")
        print("  python3 scripts/run_skill.py --skill <skill-name> \"用户输入\"")
        print("  python3 scripts/run_skill.py --chat-auto")
        print("  python3 scripts/run_skill.py --chat-skill <skill-name>")
        sys.exit(1)

    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL", "deepseek-r1:7b")
    provider = os.getenv("LLM_PROVIDER", "").lower()
    deepseek_base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not provider:
        provider = "deepseek" if deepseek_api_key else "ollama"

    if provider == "deepseek":
        model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    assistant_label = "DeepSeek" if provider == "deepseek" else "AI"

    skills_root = "skills"
    options = load_ollama_options()
    if provider == "deepseek":
        if not deepseek_api_key:
            print("请设置 DEEPSEEK_API_KEY 环境变量。")
            sys.exit(1)
        request_fn = lambda payload: request_chat_deepseek(
            deepseek_base_url, deepseek_api_key, payload
        )
        options = {}
    else:
        request_fn = lambda payload: request_chat_ollama(host, payload)

    if sys.argv[1] == "--list":
        skills = list_skills(skills_root)
        if not skills:
            print("未发现任何技能。请在 skills/ 下添加技能文件夹。")
            sys.exit(0)
        for skill in skills:
            print(f"- {skill['name']}: {skill['description']}")
        sys.exit(0)

    mode = sys.argv[1]
    if mode == "--chat-auto":
        skills = list_skills(skills_root)
        print("[CHAT-AUTO] 将在每次对话中自动选择技能。")
        chat_auto_loop(request_fn, model, skills, options, assistant_label)
        sys.exit(0)
    elif mode == "--chat-skill":
        if len(sys.argv) < 3:
            print("用法: python3 scripts/run_skill.py --chat-skill <skill-name>")
            sys.exit(1)
        skill_name = sys.argv[2]
        skill_dir = os.path.join(skills_root, skill_name)
        skill_file = os.path.join(skill_dir, "SKILL.md")
        if not os.path.isfile(skill_file):
            print("未找到 SKILL.md:", skill_file)
            sys.exit(1)
        skill_text = read_text(skill_file)
        references = collect_reference_files(skill_dir)
        system_prompt = build_system_prompt(skill_text, references)
        chat_loop(request_fn, model, system_prompt, options, assistant_label)
        sys.exit(0)
    elif mode == "--auto":
        if len(sys.argv) < 3:
            print("用法: python3 scripts/run_skill.py --auto \"用户输入\"")
            sys.exit(1)
        user_text = sys.argv[2]
        skills = list_skills(skills_root)
        chosen = choose_skill_auto(skills, user_text)
        if chosen:
            print(f"[AUTO] 使用技能：{chosen['name']}")
            skill_dir = chosen["dir"]
            skill_file = chosen["file"]
            meta, body = parse_skill_file(skill_file)
            skill_text = read_text(skill_file)
            references = collect_reference_files(skill_dir)
            system_prompt = build_system_prompt(skill_text, references)
        else:
            print("[AUTO] 未匹配技能，使用默认提示。")
            system_prompt = "你是一个助手。回答要清晰、分步骤。"
    elif mode == "--model-auto":
        if len(sys.argv) < 3:
            print("用法: python3 scripts/run_skill.py --model-auto \"用户输入\"")
            sys.exit(1)
        user_text = sys.argv[2]
        skills = list_skills(skills_root)
        chosen = choose_skill_by_model(request_fn, model, skills, user_text)
        chosen = choose_skill_by_model(request_fn, model, skills, user_text)
        if chosen:
            print(f"[MODEL-AUTO] 使用技能：{chosen['name']}")
            skill_dir = chosen["dir"]
            skill_file = chosen["file"]
            skill_text = read_text(skill_file)
            references = collect_reference_files(skill_dir)
            system_prompt = build_system_prompt(skill_text, references)
        else:
            print("[MODEL-AUTO] 未匹配技能，使用默认提示。")
            system_prompt = "你是一个助手。回答要清晰、分步骤。"
    elif mode == "--skill":
        if len(sys.argv) < 4:
            print("用法: python3 scripts/run_skill.py --skill <skill-name> \"用户输入\"")
            sys.exit(1)
        skill_name = sys.argv[2]
        user_text = sys.argv[3]
        skill_dir = os.path.join(skills_root, skill_name)
        skill_file = os.path.join(skill_dir, "SKILL.md")
        if not os.path.isfile(skill_file):
            print("未找到 SKILL.md:", skill_file)
            sys.exit(1)
        skill_text = read_text(skill_file)
        references = collect_reference_files(skill_dir)
        system_prompt = build_system_prompt(skill_text, references)
    else:
        print("未知参数。使用 --list / --auto / --model-auto / --skill")
        sys.exit(1)

    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        **options,
    }

    try:
        body = request_fn(payload) or ""
    except Exception as exc:
        print("请求失败:", exc)
        sys.exit(1)

    print(body)


if __name__ == "__main__":
    main()
