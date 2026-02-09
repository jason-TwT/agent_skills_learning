Agent Skills Learning (DeepSeek Cloud)

面向技能驱动的 Agent 学习项目，提供可视化聊天界面，支持本地 Skill 文档解析、自动选择技能与图片调色能力。

## 环境要求
- Python 3
- DeepSeek API Key

## 快速开始（可视化界面）
1. 设置环境变量（推荐写到项目根目录的 `.env`）：
```
DEEPSEEK_API_KEY=你的Key
DEEPSEEK_MODEL=deepseek-chat
```
2. 在项目根目录启动：
```
./start_mac.sh
```
或在 Windows：
```
start_windows.bat
```
3. 浏览器会自动打开 `http://localhost:8000`。

## 使用方法（界面）
1. 右上角选择技能（或保持“自动识别”）。
2. 在输入框输入内容并发送（可上传图片进行调色）。
3. 长时间无操作会自动断开并请求关闭服务。

## 当前内置技能
- `summary-skill`：摘要 + 要点 + TODO
- `weather`：天气查询（仅输出 4 行摘要）
- `color-grading`：调色基础与大师风格学习（质感提升）

## Skill 目录结构
```
skills/
  summary-skill/
    SKILL.md
    reference/
      summary-format.md
```

## 配置说明
- `DEEPSEEK_API_KEY`：你的 Key
- `DEEPSEEK_MODEL`：默认 `deepseek-chat`
- `DEEPSEEK_BASE_URL`：默认 `https://api.deepseek.com`

## 端口与日志
- `8000`：聊天服务
- `8010`：管理器（负责拉起/重启服务）
- `backend/logs/server.log`：服务启动失败时的日志

## 添加/扩展技能
1. 在 `skills/` 下新建目录。
2. 添加 `SKILL.md`，可在文件头部使用 `---` 元信息（如 `name`、`description`）。
3. 可选添加 `reference/` 目录放参考资料，内容会注入到系统提示中。

## 直接启动服务
```
python3 backend/scripts/server.py
```
如不想自动打开浏览器：
```
python3 backend/scripts/server.py --no-browser
```