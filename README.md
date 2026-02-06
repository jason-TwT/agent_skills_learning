Agent Skills Learning (DeepSeek Cloud)

最小可运行的 Skills 学习项目：用 DeepSeek 云模型读取本地 Skill 文档，体验“技能驱动”的 Agent 交互。

## 环境要求
- DeepSeek API Key
- Python 3（系统自带即可）

## 快速开始
1. 设置环境变量：
```
export DEEPSEEK_API_KEY="你的Key"
export DEEPSEEK_MODEL=deepseek-chat
```
2. 运行示例（在项目根目录）：
```
python3 scripts/run_skill.py --model-auto "把这段话做成摘要和 TODO：..."
```

## 常用命令
- 查看技能列表：`python3 scripts/run_skill.py --list`
- 自动匹配技能：`python3 scripts/run_skill.py --auto "..."`  
- 模型自动选技能：`python3 scripts/run_skill.py --model-auto "..."`  
- 指定技能：`python3 scripts/run_skill.py --skill summary-skill "..."`  
- 连续对话（自动选技能）：`python3 scripts/run_skill.py --chat-auto`  
- 连续对话（指定技能）：`python3 scripts/run_skill.py --chat-skill summary-skill`

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

## 新手上手步骤
1. **理解结构**：每个技能是一个文件夹，核心文件是 `SKILL.md`。
2. **复制模板**：从 `skills/summary-skill` 复制一份改名。
3. **编写说明**：补充目标、流程、输出格式。
4. **运行验证**：使用 `--skill <name>` 测试输出。

## 配置说明
- `DEEPSEEK_API_KEY`：你的 Key
- `DEEPSEEK_MODEL`：默认 `deepseek-chat`（非思考模式）

## 提速建议
- 精简 `SKILL.md` 与参考资料。
- 控制输入/输出长度，避免长文本。
- 优先使用 `deepseek-chat`。

## 下一步可扩展
- 工具调用（时间/计算/文件读取）
- JSON 行动指令输出
- 最小任务分解循环