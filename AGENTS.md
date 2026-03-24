# AGENT工作指引

## 工作内容留痕

鉴于我们的代码工作可能由不同的人类用户、不同的LLM Agents完成，同时也为了为保持长程工作中你的表现的稳定性，我们会在任何需要的时候，**显式地要求你**将你所做的修改或是思考、建议、调研等，以自然语言形式总结写在 agent_working_docs 文件夹下的特定子文件夹里（也就是说不是每一轮对话都需要你写markdown！）。我们也会将我们的思考、回应、建议等等写到子文件夹里。你编写的markdown文件的格式是 <日期>-agent名称-<文档版本号>.md；我们的回复的格式markdown文件格式是<日期>-user-<文档版本号>.md。

一些合法的文件命名样例为：

```markdown
20251120-cursor-v1.md
20251121-user-v2.md
20251121-codex-v1.md
20251121-kimi-v3.md
```

子文件夹以所涉及工作名称命名。例如要开发功能A，那么有关这个功能的工作交流记录就会放在 agent_working_doces/function-A-desc 下面（名字只是举个例子，具体每次给你的prompt里面，如果涉及到要开新工作主题的话，一般都会告诉你创建的文件夹是代表什么工作内容）。为了防止agent_working_docs下的子文件夹过多，如果用户**显式地要求你**写作工作总结文档，但却没有**显式地指定子文件夹（无论是已有的还是新建的）的名称**，那么请首先停下工作，询问用户子文件夹名称为何。

在编写工作文档时，不要写完所有代码之后再一次性写工作文档，而是边执行工作，边追加/修改工作文档的内容。

考虑到安全，agent_working_docs文件夹本身不被git仓库追踪。

在进行任何编码、调研、写作等操作时，请按需查看 agent_working_docs 文件夹下不同主题的子文件夹的内容。在延续同一主题的工作时，请务必至少查看按照时间线排序，最近三个markdown文件的内容。

## 联网搜索

当用户指定需要联网搜索时，检查是否有frogSearch这个MCP工具。如果有，总是优先使用这个MCP工具下的tool进行搜索。

## git提交规范

1. 用户要求提供“一行英文commit message”时，遵循格式： xxx:(xxx) xxx。例如 fix(agent-service): fix some bug.

2. 用户要求提供“一行总领，X行分点commit message”时，遵循格式：

```markdown
xxx:(xxx) xxx
- xxx
- xxx
...
```

## 为云端agent写作文档

### 为云端agent写作issue

在工作过程中，凡是涉及到需要为云端agent写issue的，请务必在写作前、后参考 `agent-guides/guide-for-writing-issues-for-cloud-agents.md` 这一文件，完整遵循其引导。