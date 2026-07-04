# LightScientist 使用文档

这份文档讲的是整个 `LightScientist` 怎么用。  
`WebUI` 只是其中一个查看入口，不是主体。


## 1. 项目是什么

`LightScientist` 是一个三层结构的科研 Agent 原型：

1. 第一层：`ResearchController`
   - 控制科研阶段流转
   - 管理 `idea -> experiment -> paper -> done`
2. 第二层：`RuntimeSupervisor`
   - 监督当前阶段任务
   - 管理 worker
3. 第三层：`ExecutionRuntime + DeepAgent worker`
   - 真正执行读文件、写文件、跑命令、整理产物


## 2. 基本目录

项目根目录：

```text
/data/auto-research/LightScientist
```

主要源码：

```text
src/esnext/
```

主要文档：

```text
docs/
```


## 3. 环境准备

进入项目目录：

```bash
cd /data/auto-research/LightScientist
```

建议使用现有环境：

```bash
conda activate auto-research
```

如果只想临时运行，也可以直接：

```bash
conda run -n auto-research ...
```


## 4. 模型配置

默认走 DeepSeek OpenAI-compatible 接口。

至少需要：

```bash
export DEEPSEEK_API_KEY="你的 key"
```

如果你已经把配置写进 `.env`，运行前加载：

```bash
set -a
source .env
set +a
```


## 5. 最简单的单任务运行

这是最小的第三层 agent 调用方式。

```bash
PYTHONPATH=src python -m esnext run "列出当前工作目录" --agent
```

如果想实时看行为：

```bash
PYTHONPATH=src python -m esnext run "列出当前工作目录" --agent --watch
```

`--watch` 会打印结构化事件，比如：

- `L1`
- `L2`
- `L3`
- `model_call`
- `tool_call`
- `tool_result`


## 6. REPL 方式

进入最小交互模式：

```bash
PYTHONPATH=src python -m esnext
```

然后输入一句任务，例如：

```text
lightscientist> 列出当前目录并说明你看到了什么
```


## 7. 研究流程运行

如果要跑第一层科研流程，用 `research` 命令。

最基本形式：

```bash
PYTHONPATH=src python -m esnext research "你的研究目标"
```

常用参数：

- `--workspace`
  - 指定工作目录
- `--mode auto|manual`
  - 自动或人工 gate
- `--stage`
  - 指定从哪个阶段开始
- `--watch`
  - 实时打印运行事件

例子：

```bash
PYTHONPATH=src python -m esnext research \
  "复现某篇论文" \
  --workspace /tmp/lightscientist-demo \
  --mode auto \
  --stage experiment.setup \
  --watch
```


## 8. 手动回复 gate

如果当前项目停在人工决策点，可以用：

```bash
PYTHONPATH=src python -m esnext research \
  --workspace /tmp/lightscientist-demo \
  --reply "y 继续下一阶段"
```

或者：

```bash
PYTHONPATH=src python -m esnext research \
  --workspace /tmp/lightscientist-demo \
  --reply "n 先回退补材料"
```


## 9. 当前阶段体系

顶层流程是：

```text
idea -> experiment -> paper -> done
```

当前内置子阶段包括：

### idea

- `idea.survey`
- `idea.generate`
- `idea.evaluate`
- `idea.probe_batch`
- `idea.probe_collect`
- `idea.gate`

### experiment

- `experiment.setup`
- `experiment.loop`
- `experiment.analyze`
- `experiment.gate`

### paper

- `paper.plan`
- `paper.figure`
- `paper.write`
- `paper.review`


## 10. 运行时会生成什么

工作目录里常见文件：

```text
.lightscientist/project_state.json
.lightscientist/events.jsonl
.lightscientist/stage-runs/
PROCESS.md
phase1-idea/
phase2-experiment/
phase3-paper/
```

含义：

- `project_state.json`
  - 当前项目状态
- `events.jsonl`
  - 结构化事件流
- `stage-runs/`
  - 每个阶段的一次交付摘要
- `PROCESS.md`
  - 跨阶段长期摘要


## 11. 当前推荐样例：moew

样例目录：

```text
examples/moew/
```

它是一个只读整理报告的样例，不跑新的长时间实验。

直接运行：

```bash
cd /data/auto-research/LightScientist
conda run -n auto-research bash examples/moew/run_paper_report.sh
```

默认工作目录：

```text
examples/moew/workspace
```

这个样例主要展示：

- 第一层 `paper` 阶段流转
- 第二层 supervisor
- 第三层 worker
- skills / logs / artifacts


## 12. WebUI

WebUI 只是观察入口。

启动方式：

```bash
cd /data/auto-research/LightScientist
conda run -n auto-research python -m esnext webui \
  --workspace /data/auto-research/LightScientist/examples/moew/workspace \
  --host 127.0.0.1 \
  --port 8765
```

访问：

```text
http://127.0.0.1:8765/
```


## 13. 当前协议约束

当前有两个重要约束：

### 读路径

只允许通过 workspace 内可见路径读取，例如：

- `PROCESS.md`
- `source_task/...`
- `source_seed/...`
- `source_results/...`
- `phase3-paper/...`

不要用绝对路径。

### 写路径

所有写入一律使用 workspace 相对路径，例如：

- `phase3-paper/PAPER_PLAN.md`
- `phase2-experiment/worklog.md`


## 14. 当前适合做什么

当前最稳的用途：

- 调试三层结构
- 做论文/项目报告整理
- 读代码、读已有结果、生成文档
- 做阶段流转演示

当前不建议直接拿来做：

- 超长全自动科研闭环
- 大规模并行实验
- 强依赖复杂系统环境的重任务


## 15. 测试

运行测试：

```bash
cd /data/auto-research/LightScientist
conda run -n auto-research python -m pytest -q
```


## 16. 常用命令汇总

单任务：

```bash
PYTHONPATH=src python -m esnext run "列出当前目录" --agent --watch
```

科研流程：

```bash
PYTHONPATH=src python -m esnext research "复现某篇论文" --mode auto --stage experiment.setup --watch
```

人工回复：

```bash
PYTHONPATH=src python -m esnext research --workspace /tmp/lightscientist-demo --reply "y 继续"
```

样例：

```bash
conda run -n auto-research bash examples/moew/run_paper_report.sh
```

WebUI：

```bash
conda run -n auto-research python -m esnext webui \
  --workspace /data/auto-research/LightScientist/examples/moew/workspace \
  --host 127.0.0.1 \
  --port 8765
```
