# LightScientist

`LightScientist` 是一个面向长周期科研任务的三层多智能体系统。它把一条完整的科研任务拆成“阶段管理、运行监督、具体执行”三层来推进，让系统不仅能完成单步代码或实验操作，还能围绕选题理解、实验组织、结果分析和论文写作形成连续工作流。最终目标不是只把某个脚本跑通，而是把一条科研任务真正沉淀为可恢复、可审查、可交付的研究过程。

当前仓库提供的是 `LightScientist` 的参考实现：包含三阶段科研流程控制、持久 worker 会话、事件流观察、样例任务、WebUI 和一套以 workspace 为中心的科研交付约定。

## Overview

`LightScientist` 将科研任务组织为一条标准研究管线：

```text
idea -> experiment -> paper -> done
```

其中每个大阶段都可以继续细分为更小的子阶段，例如：

- `idea`
  - 文献调研
  - 候选方向生成
  - 选题评估
- `experiment`
  - 实验准备
  - 基线复现
  - 调优迭代
  - 结果分析
- `paper`
  - 论文规划
  - 图表生成
  - 正文写作

这套设计面向的是完整科研流程，而不只是“给定代码仓库后做一次调试”。

## Features

- 三层 Agent 架构
  - 第一层负责科研阶段流转与项目状态
  - 第二层负责监督当前阶段任务与 worker 调度
  - 第三层负责读写文件、运行命令、执行实验和产出交付
- 面向科研任务的阶段化工作流
  - 从 idea、experiment 到 paper 的完整三阶段推进
  - 每个阶段都有明确的输入、约束、交付和转阶段条件
- 持久化的执行会话
  - worker 使用 `session_id` 和 `thread_id` 维护可恢复会话
  - 支持 `waiting`、`background`、`cancelled` 等长任务状态
- 可观察的研究过程
  - 事件流、阶段交付文档、workspace 产物、运行日志都保留在工作目录
  - 支持 `--watch` 终端观察和 WebUI 浏览
- OpenAI-compatible 模型接口
  - 默认使用 DeepSeek
  - 也可切换到 LM Studio 或其他兼容接口

## Scientific Workflow

`LightScientist` 的核心不是单次工具调用，而是一条“可推进、可暂停、可恢复、可交付”的科研链路。

典型流程如下：

1. 第一层根据当前阶段生成阶段目标与约束
2. 第二层围绕该阶段创建或恢复 worker
3. 第三层在 workspace 中执行具体任务
4. 第二层根据 worker 状态和交付结果决定继续推进、恢复、挂起或结束
5. 第一层验证阶段交付并执行转阶段

这使得系统可以把以下任务纳入同一套框架：

- 论文复现
- 有限范围的算法优化
- 数据分析与可视化
- 基于实验结果的技术报告或论文写作

## Architecture

`LightScientist` 采用三层结构：

1. 第一层：`ResearchController`
   - 维护项目状态机
   - 生成阶段 prompt
   - 校验阶段交付
   - 决定阶段切换
2. 第二层：`RuntimeSupervisor`
   - 管理当前阶段的 worker
   - 维护 worker 状态记录
   - 处理 `waiting`、`background`、`cancelled`、`stalled` 等事件
   - 调用 supervisor agent 做阶段内调度决策
3. 第三层：`ExecutionRuntime + DeepAgent worker`
   - 负责真实工具调用
   - 维护可恢复 agent session
   - 在 workspace 内读文件、写文件、编辑文件、执行命令、整理产物

第三层当前的核心状态：

- `running`
- `waiting`
- `background`
- `completed`
- `failed`
- `cancelled`

其中：

- `waiting`
  - 用于请求上层补充信息
  - 通过 `interrupt()` 和 `Command(resume=...)` 恢复
- `background`
  - 用于当前轮结束，但任务依赖未来外部结果
  - 保留同一 session，后续继续恢复

## Installation

建议使用 Python 3.11+。

```bash
cd /data/auto-research/LightScientist
```

如果使用 `uv`：

```bash
uv sync
```

如果使用现有 conda 环境：

```bash
conda run -n auto-research python -m pip install -e .
```

默认模型接口为 DeepSeek 的 OpenAI-compatible API，至少需要：

```bash
export DEEPSEEK_API_KEY="your_api_key"
```

也可以改用任意 OpenAI-compatible 服务：

```bash
export LIGHTSCIENTIST_BASE_URL="http://localhost:1234/v1"
export LIGHTSCIENTIST_MODEL="your-model-name"
export LIGHTSCIENTIST_API_KEY="dummy-or-real-key"
```

## Quick Start

最小 REPL：

```bash
cd /data/auto-research/LightScientist
PYTHONPATH=src python -m esnext
```

运行一个最小单任务：

```bash
PYTHONPATH=src python -m esnext run "你的工作目录是什么" --agent --watch
```

运行完整科研流程入口：

```bash
PYTHONPATH=src python -m esnext research "复现并分析某篇论文" \
  --workspace ./workspace \
  --mode auto \
  --stage idea.survey \
  --watch
```

启动 WebUI：

```bash
PYTHONPATH=src python -m esnext webui \
  --workspace ./workspace \
  --host 127.0.0.1 \
  --port 8765
```

## Examples

`examples/` 目录提供了几类不同科研任务样例：

- `examples/chemprop`
  - 药物发现相关论文复现、实验调优与报告生成
- `examples/scCAD`
  - 单细胞 rare cell / anomaly detection 任务
- `examples/Rumor`
  - 超图 rumor propagation 经验结果复现与整理
- `examples/moew`
  - 基于现有 benchmark 结果的论文式报告生成

对应启动脚本：

```bash
bash examples/chemprop/run_reproduce_optimize.sh
bash examples/scCAD/run_reproduce_optimize.sh
bash examples/Rumor/run_reproduce_optimize.sh
bash examples/moew/run_paper_report.sh
```

说明：

- 部分样例不会直接附带完整数据集、上游仓库或权重
- 外部材料的位置请查看各样例目录下的 `README.md`、`任务说明.md`、`task_prompt.md` 或相关工作区说明

## Repository Structure

```text
LightScientist/
├── docs/                  # 架构与使用文档
├── examples/              # 样例任务
├── skills/                # 阶段技能与流程提示
├── src/esnext/            # 核心实现
├── templates/             # 模板文件
├── tests/                 # 测试
└── tools/                 # 辅助脚本
```

核心源码：

```text
src/esnext/
├── backends.py
├── cli.py
├── context_compaction.py
├── data_models.py
├── events.py
├── executor.py
├── manager.py
├── minimal_agent.py
├── model_config.py
├── prompts/
├── research_controller.py
├── research_stages.py
└── runtime.py
```

主要文件说明：

- `research_controller.py`
  - 第一层科研阶段控制器
- `runtime.py`
  - 第二层 supervisor 运行时
- `executor.py`
  - 第三层执行层封装
- `minimal_agent.py`
  - 第三层 DeepAgent 会话包装
- `context_compaction.py`
  - 长会话上下文压缩与 handoff
- `backends.py`
  - workspace backend 与自定义工具
- `events.py`
  - 事件流和 `--watch` 输出
- `model_config.py`
  - OpenAI-compatible 模型配置

## Observability

`LightScientist` 将研究过程显式写入工作目录，便于恢复、审查和展示。

常见输出包括：

- `.lightscientist/project_state.json`
- `.lightscientist/events.jsonl`
- `.lightscientist/stage-runs/*/agent-run.md`
- `PROCESS.md`
- `phase1-idea/`
- `phase2-experiment/`
- `phase3-paper/`

运行时可以通过 `--watch` 查看事件流。终端只显示可观察行为，不显示隐藏推理。

## Documentation

详细说明见 [`docs/`](docs/)：

- [`docs/system-architecture.md`](docs/system-architecture.md)
  - 系统整体架构
- [`docs/first-layer-research-controller.md`](docs/first-layer-research-controller.md)
  - 第一层阶段管理
- [`docs/second-layer-runtime-supervisor.md`](docs/second-layer-runtime-supervisor.md)
  - 第二层 supervisor 与 worker 管理
- [`docs/third-layer-execution-runtime.md`](docs/third-layer-execution-runtime.md)
  - 第三层执行层与会话机制
- [`docs/lightscientist-usage.md`](docs/lightscientist-usage.md)
  - CLI、workspace 和样例使用说明
- [`docs/lightscientist-webui-design.md`](docs/lightscientist-webui-design.md)
  - WebUI 设计
- [`docs/webui-quickstart.md`](docs/webui-quickstart.md)
  - WebUI 快速启动

## Development

运行测试：

```bash
cd /data/auto-research/LightScientist
conda run -n auto-research python -m pytest -q
```

## Acknowledgement

`LightScientist` 的定位是面向科研任务的长周期三层工作流系统。它在整体方向上受到了多智能体科研与自动研究系统的启发，尤其包括：

- [CORAL](https://github.com/Human-Agent-Society/CORAL)
- [EvoScientist](https://github.com/EvoScientist/EvoScientist)

当前实现更强调以 workspace 为中心的阶段化研究推进、监督式 worker 管理和可交付的研究过程沉淀。
