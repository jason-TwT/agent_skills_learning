Agent Skills Learning (DeepSeek Cloud)

面向技能驱动的 Agent 学习项目，提供可视化聊天界面，支持本地 Skill 文档解析与自动选择技能。

## 环境要求
- Python 3
- DeepSeek API Key

## 快速开始（可视化界面）
1. 设置环境变量（推荐直接写到项目根目录的 `.env` 文件）：
```
DEEPSEEK_API_KEY=你的Key
DEEPSEEK_MODEL=deepseek-chat
```
如果你用终端启动，也可以用 `export` 的方式设置。
2. 启动界面（在项目根目录）：
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
2. 在输入框输入内容并发送。
3. 关闭浏览器页面后，服务会在约 30 秒内自动终止。

## 当前内置技能
- `summary-skill`：摘要 + 要点 + TODO
- `weather`：天气查询（仅输出 4 行摘要）

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