## PostTrainAgent

一个本地运行的“小型 Claude Code 风格”代码代理，支持多工具调用、子 Agent（Task）和技能（Skill）机制，并在终端用不同颜色区分输出。

### 功能概览

- **对话式 REPL**：运行 `python main.py`，在命令行交互，提示符为 `You: `。
- **Tool 调用**：支持 `bash`（含 `background=true` 后台任务）、`read_file`、`write_file`（支持 `append=true` 追加写）、`edit_file`、`TodoWrite`、`wait` 等工具。
- **子 Agent（Tasks）**：内置 `explore` / `code` / `plan` 三种子 agent，通过 `Task` 工具为子任务单独开一轮对话。
- **技能（Skills）**：通过 `Skill` 工具按需加载某个领域的 SKILL 文档，本仓库中保留了一个 `pdf` 示例技能。
- **后台任务与时间感知**：`bash(background=True)` 可启动后台任务，`JobManager` 追踪 PID 与日志，主循环在每轮注入“当前时间 + 后台任务状态”，并提供 `wait` 工具让 Agent 主动选择等待。
- **彩色输出**：用户输入、助手回复、工具调用、子 agent 活动、技能加载、后台任务状态等都有不同的 ANSI 颜色，方便在终端快速分辨。

### 环境变量

运行前需要在 shell 或 `.env` 中设置三个变量（`config.py` 只依赖这三个）：

- `API_KEY`：后端模型的 API key  
- `BASE_URL`：后端 API 地址（例如 `http://localhost:3000/v1`）  
- `MODEL`：模型名称（例如 `deepseek-v3`）

### 主要文件结构

- **`main.py`**：入口脚本  
  - 构造系统提示 `SYSTEM`  
  - 维护对话 `messages`  
  - 调用 OpenAI/DeepSeek 接口和 `ALL_TOOLS`  
  - 实现主循环和 REPL。

- **`config.py`**：全局配置  
  - `API_KEY`、`BASE_URL`、`MODEL`  
  - `WORKDIR`、`SKILLS_DIR`  
  - 共享的 `client` 实例。

- **`utils/colors.py`**：终端颜色工具  
  - ANSI 颜色常量  
  - `color(text, *codes)` 帮助函数。

- **`tools/base.py`**：工具 schema 注册中心  
  - 定义基础工具的 OpenAI tool schema：`bash`（支持 `background`）、`read_file`、`write_file`（支持 `append`）、`edit_file`、`TodoWrite`、`wait`  
  - 从 `tasks.task_tool` 引入 `TASK_TOOL`，从 `skills.skill_tool` 引入 `SKILL_TOOL`  
  - 暴露统一的 `ALL_TOOLS` 和 `get_tools_for_agent()`。

- **`tools/impl.py`**：工具实现  
  - `run_bash`（支持后台任务 + JobManager 注册） / `run_read` / `run_write`（支持追加写） / `run_edit` / `run_todo` / `run_skill` / `run_task` / `run_wait`  
  - `execute_tool(name, args)`：统一分发入口（分发到各个 run\_* 实现）  
  - 内部使用 `tasks.agent_types` 中的 `AGENT_TYPES`、`tools.base.get_tools_for_agent()`、以及 `tools.job_manager.JOBS` 和 `tools.todo_manager.TODO`。

- **`tasks/agent_types.py`**：子 Agent 配置  
  - `AGENT_TYPES`：定义 `explore` / `code` / `plan` 的描述、可用工具和提示词  
  - `get_agent_descriptions()`：用于在系统提示中列出子 agent。

- **`tasks/task_tool.py`**：Task 工具 schema  
  - 定义 `Task` 工具的参数结构（`description` / `prompt` / `agent_type`）。

- **`skills/loader.py`**：技能加载器  
  - `SkillLoader`：扫描 `skills/*/SKILL.md`，解析 frontmatter 和正文  
  - `SKILLS`：全局实例，提供 `get_descriptions()` / `get_skill_content()` / `list_skills()`。

- **`skills/skill_tool.py`**：Skill 工具 schema  
  - 定义 `Skill` 工具的参数结构（`skill` 名称），并在描述中嵌入当前可用技能列表。

- **`skills/pdf/SKILL.md`**：示例技能  
  - 展示一个典型 `SKILL.md` 的结构和用法，用于 PDF 相关任务的说明示例。

- **`tools/job_manager.py`**：后台任务管理  
  - `JobManager` / 全局单例 `JOBS`，负责记录后台任务的 `PID`、命令、日志路径、运行时长和状态，并在每轮对话中为 Agent 提供“后台任务状态摘要”。

- **`tools/todo_manager.py`**：待办事项管理  
  - `TodoManager` / 全局单例 `TODO`，用于 `TodoWrite` 工具更新和渲染当前的待办任务列表。


