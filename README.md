学习 Agent Skills（DeepSeek 云模型）

这是一个最小可运行的 Skills 学习项目，用来帮你理解如何编写 Skill、加载 Skill、让云模型读 Skill。

## 你需要准备
- DeepSeek API Key
- Python 3（系统自带即可）

## 快速运行（云模型）
1. 设置环境变量：
   - `export DEEPSEEK_API_KEY="你的Key"`
   - `export DEEPSEEK_MODEL=deepseek-chat`
2. 用脚本加载 Skill 并对话（在本项目根目录）：
   - 自动匹配技能：`python3 scripts/run_skill.py --auto "把这段话做成摘要和 TODO：..."`
   - 模型自动选技能：`python3 scripts/run_skill.py --model-auto "把这段话做成摘要和 TODO：..."`
   - 指定技能：`python3 scripts/run_skill.py --skill summary-skill "把这段话做成摘要和 TODO：..."`
   - 查看技能列表：`python3 scripts/run_skill.py --list`
   - 连续对话（自动选技能）：`python3 scripts/run_skill.py --chat-auto`
   - 连续对话（指定技能）：`python3 scripts/run_skill.py --chat-skill meeting-notes-skill`

## 当前内置技能
- `summary-skill`：摘要 + 要点 + TODO
- `meeting-notes-skill`：会议纪要整理
- `weather`：天气查询（输出 4 行摘要）

## 一步步实现（新手版）
1. **理解 Skill 结构**
   - 每个技能是一个文件夹，核心文件是 `SKILL.md`。
2. **写第一个 Skill**
   - 复制 `skills/summary-skill` 当模板修改。
3. **让模型读取 Skill**
   - 用脚本把 `SKILL.md` + `reference/` 发给模型。
4. **验证输出**
   - 输入一段文本，看是否按模板输出。

## 技能目录结构示例
```
skills/
  summary-skill/
    SKILL.md
    reference/
      summary-format.md
```


## 常用配置（云模型）
- `DEEPSEEK_API_KEY`：你的 Key
- `DEEPSEEK_MODEL`：默认 `deepseek-chat`

## 学习路线建议（面向新手）
1. **先跑通调用**：确保你能看到模型回复。
2. **学会写提示词**：修改系统提示，观察输出风格变化。
3. **理解对话结构**：`messages` 里不同 `role` 的作用。
4. **加入“技能”概念**：为不同任务加上固定前缀或模板提示词。
5. **做一个小任务**：如“读一段文本->总结->提炼 TODO”。

如果你想做“真正的智能体技能”（工具调用/任务拆解/流程协作），下一步我可以帮你加上：
- 简单工具调用（比如时间、计算、文件读取）
- 基于 JSON 的“行动指令”输出格式
- 一个最小任务分解循环

## 提速建议
- 尽量缩短 `SKILL.md` 和参考资料。
- 控制输入/输出长度，避免长文本。
- 优先使用 `deepseek-chat`（非思考模式）。