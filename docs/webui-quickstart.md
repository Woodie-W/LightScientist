# LightScientist WebUI 快速使用

这份文档只讲最简单的使用方式：  
直接查看 `moew` 样例 workspace 的 WebUI。


## 1. 这个 WebUI 在看什么

当前 WebUI 是一个**只读观察界面**，不是控制台。

它主要读取这些文件：

- `.lightscientist/project_state.json`
- `.lightscientist/events.jsonl`
- `.lightscientist/stage-runs/*/agent-run.md`
- `PROCESS.md`
- `phase1-idea/`
- `phase2-experiment/`
- `phase3-paper/`

当前页面有 4 个：

- `Overview`
  - 当前 phase / stage / status
  - 最近事件
  - 当前 worker
  - 最近产物
- `Pipeline`
  - 三层结构 `L1 / L2 / L3`
  - 阶段流转 `idea -> experiment -> paper -> done`
- `Knowledge`
  - 当前阶段 skill
  - 全部 skills
  - `PROCESS.md`
- `Logs`
  - `.lightscientist/events.jsonl` 里的结构化事件


## 2. 当前样例 workspace

当前默认查看的是：

```text
/data/auto-research/LightScientist/examples/moew/workspace
```

这是一个只读整理报告的样例 workspace，里面已经有：

- `source_task/`
- `source_seed/`
- `source_results/`
- `phase3-paper/`
- `.lightscientist/`


## 3. 启动 WebUI

进入项目目录：

```bash
cd /data/auto-research/LightScientist
```

启动 WebUI：

```bash
conda run -n auto-research python -m esnext webui \
  --workspace /data/auto-research/LightScientist/examples/moew/workspace \
  --host 127.0.0.1 \
  --port 8765
```

启动后访问：

```text
http://127.0.0.1:8765/
```


## 4. 如果你想先运行样例任务

如果你想先让样例 workspace 里产生或刷新内容，再看 WebUI，可以先跑：

```bash
cd /data/auto-research/LightScientist
conda run -n auto-research bash examples/moew/run_paper_report.sh
```

然后再启动 WebUI。


## 5. 你会看到什么

以当前 `moew` 样例为例，页面里通常会看到：

- 当前项目处于 `paper` phase
- 当前 stage 可能是 `paper.plan` / `paper.figure` / `paper.write`
- 事件流里能看到 `L1`、`L2`、`L3` 的行为
- `Knowledge` 页能看到当前阶段 skill
- `Overview` 页能看到最近生成的：
  - `PAPER_PLAN.md`
  - `FIGURES_REPORT.md`
  - `main.tex`
  - 图表和表格文件


## 6. 停止 WebUI

在启动 WebUI 的终端里按：

```text
Ctrl+C
```


## 7. 当前限制

这还是第一版最简 WebUI。

当前特点：

- 只读
- 轮询刷新，不是 SSE
- 没有控制按钮
- 适合看状态、日志、skills、产物

还没有做：

- 浏览器里直接控制 agent
- 多项目切换页
- 完整文件树
- 实时推送
