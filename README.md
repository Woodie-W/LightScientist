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
  - 通过 `BACKGROUND: ...` 轻协议返回挂起状态
  - 后续恢复走同一个 `thread_id` 的普通消息继续
  - 第二层记录的 `resume_mode` 是 `message`

当前设计是纯内存版：

- 第三层 session 不落磁盘
- 第二层持有第三层 session
- 进程结束后会话丢失

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
conda run -n auto-research pytest -q
```

## 当前核心文件

```text
src/esnext/
├── cli.py
├── executor.py
├── manager.py
├── minimal_agent.py
├── models.py
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
- `models.py`
  共享结构定义

## 当前完成度

已经完成：

- deepagents 接入第三层
- 第三层 session 化
- `thread_id` / `start` / `resume`
- `waiting -> interrupt`
- `background -> 保留 session 后续普通恢复`
- 第二层记录 `resume_mode`

还没做：

- 磁盘持久化
- 顶层 resume 功能
- 自动后台任务回流
- 第一层真正的 LangGraph 化
