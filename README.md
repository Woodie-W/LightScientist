# LightScientist

`LightScientist` 是一个独立于 `EvoScientist` 的三层结构实验项目，当前重点不是完整科研功能，而是把第三层 deepagent 会话跑通，并把边界收清楚。

当前结构：

1. 第一层：阶段管理层
2. 第二层：运行状态管理层
3. 第三层：能力执行层

## 当前第三层

第三层已经不是一次性函数，而是最小持久会话骨架：

- 有 `session_id`
- 有 `thread_id`
- 支持 `start_agent_session(...)`
- 支持 `resume_agent_session(...)`
- 第二层会保留第三层 session 引用
- 每轮运行会维护 `step_count` / `action_count` / `last_activity_at`

当前第三层状态只有：

- `running`
- `waiting`
- `background`
- `completed`
- `failed`
- `cancelled`

## waiting / background

当前已经把这两种挂起方式分开了：

- `waiting`
  - 用 LangGraph `interrupt()`
  - 第三层通过 `ask_input(question)` 工具向上层请求输入
  - 后续恢复走 `Command(resume=...)`
  - 第二层记录的 `resume_mode` 是 `interrupt`

- `background`
  - 当前轮正常结束，但第三层 session 保留在内存
  - 通过 `suspend_background(note)` 工具返回挂起状态
  - 后续恢复走同一个 `thread_id` 的普通消息继续
  - 第二层记录的 `resume_mode` 是 `message`
  - supervisor 可以通过 `schedule_worker_resume(agent_id, seconds, message)` 设置未来直接唤醒

worker prompt 约束：

- 只有在缺少明确的外部信息、并且无法通过 workspace/tools 自己获取时，才使用 `ask_input`
- `ask_input` 的问题应简短且具体
- 只有在已经启动了一个需要未来外部结果的工作时，才使用 `suspend_background`
- 正常还能继续推进的工作，不要用 `suspend_background`
- 收到取消请求后，第三层应整理当前成果、保留产物、写/更新交付文档，并调用 `finish_cancelled(summary)`

## 当前第二层

第二层现在是 `RuntimeSupervisor`：

- 一个二层只监督一个任务
- 每个任务下面可以有多个第三层 worker
- 每个 worker 有独立工作目录和 `agent-run.md`
- worker 状态变化会进入 supervisor 队列
- 普通 `running -> running` 进度只更新记录，不触发 supervisor 决策
- supervisor 空闲时，每次只处理队列中的一个事件
- supervisor 调用 `start_worker` / `resume_worker` 是非阻塞发射，worker 结果之后再作为事件回流
- 第二层用 `_results` 保存每个 worker 的交付结果

supervisor agent 复用第三层 deepagent 运行方式，但使用 supervisor prompt 和 runtime tools。

当前 runtime tools：

- `get_task()`
- `list_workers()`
- `get_worker(agent_id)`
- `start_worker(objective)`
- `resume_worker(agent_id, text)`
- `cancel_worker(agent_id)`
- `schedule_worker_resume(agent_id, seconds, message)`

`schedule_worker_resume` 的含义是：当前 supervisor 先做决定，写好未来要发给 worker 的文本；到时间后第二层直接 resume 对应 worker，不再先问 supervisor。

## cancel

当前 cancel 分两层：

- 第二层 `RuntimeSupervisor.cancel_worker(agent_id)`
  - 只负责调用第三层 `executor.cancel(agent_id)`
  - 保存返回的 `ExecutionResult`
  - 更新 worker 状态为 `cancelled`
  - 向 supervisor 队列发送取消事件

- 第三层 `ExecutionRuntime.cancel(agent_id)`
  - 优先让 worker agent 自己整理交付
  - 写回 `agent-run.md`
  - 删除 executor 内的 session，后续不能继续 resume
  - 如果收尾超时，会返回兜底 cancelled 结果
  - 如果当前有 `execute` 子进程，会终止登记的进程组

限制：

- Python 线程本身不会被强制杀掉，因为这不安全
- 取消会保留 `agent-run.md`、`agent-debug.log` 和 workspace 产物

## 结果字段语义

第三层一次 `start/resume` 周期里，关键结果字段含义如下：

- `last_model_output`
  - 模型最后一次原始输出
- `last_action`
  - 最后一次归一化动作摘要，例如 `execute: ...` 或 `ask_input: ...`
- `final_output`
  - 这一轮真正交付给上层的主文本
  - 可能是最终答案，也可能是 waiting 问题或 background 说明
- `command_outputs`
  - 这一轮 workspace tools 的输出日志片段

当前设计是纯内存版：

- 第三层 session 不落磁盘
- 第二层持有第三层 session
- 进程结束后会话丢失

## 进度和卡死检测

第三层通过 `RuntimeUpdate` 向第二层上传状态和进度：

- `step_count`
  第三层大模型轮次计数
- `action_count`
  模型生成和工具调用都会增加
- `last_activity_at`
  最近一次 action 更新时间

第二层只对 `running` worker 做简单卡死检测。`waiting` 和 `background` 是主动挂起状态，不按卡死处理。

## 当前顶层边界

顶层 CLI 现在只负责：

- 输入新任务
- 显示结果
- 最简单的 REPL

顶层暂时不暴露：

- resume
- agent 列表
- 第一层 LangGraph 会话恢复

也就是说，恢复能力现在只在第二层/第三层和测试里验证，不作为顶层产品接口。

## 运行

进入最小 REPL：

```bash
cd /data/auto-research/LightScientist
PYTHONPATH=src python -m esnext
```

单次运行：

```bash
cd /data/auto-research/LightScientist
PYTHONPATH=src python -m esnext run "你的工作目录是什么" --agent
```

## 测试

```bash
cd /data/auto-research/LightScientist
conda run -n auto-research python -m pytest -q
```

## 当前核心文件

```text
src/esnext/
├── backends.py
├── cli.py
├── data_models.py
├── executor.py
├── manager.py
├── minimal_agent.py
├── model_config.py
├── prompts/
└── runtime.py
```

含义：

- `cli.py`
  终端入口
- `manager.py`
  第一层最小入口
- `runtime.py`
  第二层，会话记录和恢复调度
- `executor.py`
  第三层外层封装
- `minimal_agent.py`
  第三层 deepagent 会话本体
- `backends.py`
  workspace backend 和自定义工具
- `model_config.py`
  OpenAI 兼容模型配置和日志包装
- `data_models.py`
  共享结构定义
- `prompts/`
  worker / supervisor prompt

## 当前完成度

已经完成：

- deepagents 接入第三层
- 第三层 session 化
- `thread_id` / `start` / `resume`
- `waiting -> interrupt`
- `background -> 保留 session 后续普通恢复`
- 第二层 supervisor agent
- 第二层 runtime tools
- `background` 定时直接恢复
- 简单进度计数和 running 卡死检测
- `cancel -> finish_cancelled`
- `execute` 子进程取消
- supervisor worker tools 非阻塞发射

还没做：

- 磁盘持久化
- 顶层 resume 功能
- 第一层真正的 LangGraph 化
