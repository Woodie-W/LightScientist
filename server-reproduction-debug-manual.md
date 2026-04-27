# 服务器复现调试手册

这份手册只保留一条推荐路径：在服务器上用 Docker 跑 `LightScientist`，挂载持久工作目录，使用 DeepSeek API，并用 `--watch` 实时查看 Agent 行为。

## 目标

用于调试“复现论文实验”任务。

这条流程固定使用：

- 一个 Docker 容器
- 一个挂载工作目录
- 一个第二层 supervisor
- 一个第三层 worker
- `--watch` 实时查看 Agent 事件

## 快速操作

在本机把 `LightScientist` 源码压缩成一个包，放到 `/data/auto-research/`：

```bash
cd /data/auto-research
tar \
  --exclude='LightScientist/.git' \
  --exclude='LightScientist/__pycache__' \
  --exclude='LightScientist/.pytest_cache' \
  --exclude='LightScientist/.lightscientist' \
  --exclude='LightScientist/agent-run.md' \
  --exclude='LightScientist/agent-debug.log' \
  -czf LightScientist-source.tar.gz LightScientist
```

生成文件：

```text
/data/auto-research/LightScientist-source.tar.gz
```

## 1. 准备服务器目录

在服务器上执行：

```bash
mkdir -p /data/lightscientist-runs/paper-repro-debug
cd /data/auto-research/LightScientist
```

挂载的运行目录会保存：

```text
.lightscientist/events.jsonl
PROCESS.md
research.md
research.jsonl
phase2-experiment/
agent-run.md
agent-debug.log
```

## 2. 构建 Docker 镜像

在 `LightScientist` 项目根目录执行：

```bash
docker build -t lightscientist:debug .
```

当前 Dockerfile 会用 `pip install -e ".[dev]"` 安装项目。

## 3. 启动容器

先确保服务器上已经有 DeepSeek key：

```bash
export DEEPSEEK_API_KEY="你的 DeepSeek API Key"
```

启动一个交互式容器：

```bash
docker run --rm -it \
  --name lightscientist-paper-repro-debug \
  -e DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" \
  -v /data/auto-research/LightScientist:/app/LightScientist \
  -v /data/lightscientist-runs/paper-repro-debug:/workspace \
  -w /app/LightScientist \
  lightscientist:debug \
  bash
```

进入容器后执行：

```bash
export PYTHONPATH=/app/LightScientist/src
```

## 4. 先做短任务冒烟测试

先跑一个很短的 Agent 任务，确认模型、工具、事件输出都正常：

```bash
python -m esnext run \
  "列出当前目录，说明你能看到哪些文件，然后结束。" \
  --workspace /workspace \
  --agent \
  --watch
```

正常情况下你应该能看到类似输出：

```text
[L2 worker_created] ...
[L3 model_call] ...
[L3 tool_call] ...
[L3 tool_result] ...
status: completed
```

如果失败，先看这两个位置：

```bash
cat /workspace/.lightscientist/events.jsonl
find /workspace -name agent-debug.log -print
```

## 5. 跑“复现论文实验”调试任务

从 `experiment.setup` 阶段开始：

```bash
python -m esnext research \
  "复现论文实验：请根据用户提供的论文信息完成实验环境准备、基线运行、结果记录和复现实验总结。先在工作区建立清晰的实验记录文件。" \
  --workspace /workspace \
  --mode auto \
  --stage experiment.setup \
  --watch
```

这一步的首要目标不是直接得到完美论文结果，而是确认系统闭环：

- supervisor 只创建一个 worker
- worker 能读写文件
- 工具调用能实时看到
- 实验记录写入挂载目录
- `events.jsonl` 记录完整可观察行为

## 6. 查看运行过程和产物

可以在另一个服务器 shell 里实时看事件：

```bash
tail -f /data/lightscientist-runs/paper-repro-debug/.lightscientist/events.jsonl
```

常用检查命令：

```bash
find /data/lightscientist-runs/paper-repro-debug -maxdepth 4 -type f | sort
cat /data/lightscientist-runs/paper-repro-debug/PROCESS.md
cat /data/lightscientist-runs/paper-repro-debug/research.md
cat /data/lightscientist-runs/paper-repro-debug/research.jsonl
cat /data/lightscientist-runs/paper-repro-debug/phase2-experiment/worklog.md
cat /data/lightscientist-runs/paper-repro-debug/phase2-experiment/EXPERIMENT_RESULTS.md
```

## 7. 停止容器

在服务器宿主机上执行：

```bash
docker stop lightscientist-paper-repro-debug
```

因为 `/workspace` 是挂载目录，结果会保留在：

```text
/data/lightscientist-runs/paper-repro-debug
```

## 8. 跑完后重点检查

检查 worker 创建次数：

```bash
grep -n '"type": "worker_created"' /data/lightscientist-runs/paper-repro-debug/.lightscientist/events.jsonl
```

检查模型和工具行为：

```bash
grep -n '"type": "model_call"' /data/lightscientist-runs/paper-repro-debug/.lightscientist/events.jsonl
grep -n '"type": "tool_call"' /data/lightscientist-runs/paper-repro-debug/.lightscientist/events.jsonl
grep -n '"type": "tool_result"' /data/lightscientist-runs/paper-repro-debug/.lightscientist/events.jsonl
```

检查最终项目状态：

```bash
cat /data/lightscientist-runs/paper-repro-debug/.lightscientist/project_state.json
```

## 说明

这份手册故意只保留一条运行路径，方便服务器调试。

默认使用 DeepSeek：

```bash
export DEEPSEEK_API_KEY="你的 DeepSeek API Key"
```

代码仍然支持其他 OpenAI-compatible API 覆盖，但这份调试手册不展开其他分支。
