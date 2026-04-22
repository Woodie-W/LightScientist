# LightScientist

这是一个独立于原 `EvoScientist` 的新项目目录，用来按阶段验证新的三层控制结构。

目标结构已经调整为：

1. 阶段管理层
2. 运行状态管理层
3. 能力执行层

当前实现的是最小三层直通骨架版：

- 第一层已有上层阶段管理入口
- 第二层只做最小运行记录和转发
- 第三层已有执行层占位实现
- 第三层当前只暴露本地命令行能力
- 还没有接入 LLM、skills、复杂上下文和工具编排

## 当前实现状态

当前代码已经调整成最小三层直通骨架版：

```text
用户请求
  -> 阶段管理层
  -> 运行状态管理层
  -> 能力执行层
  -> 结构化结果
```

这一步的意义不是提供完整科研能力，而是先验证新的三层职责边界已经进入主路径。

## 当前支持的输入形态

- 已存在文件：自动走文件汇总
- 已存在目录：自动走目录检查
- 其他文本：默认写成笔记
- 加 `--agent`：交给第三层 `minimal_agent`

其中前 3 种不依赖外部模型，用来验证三层骨架主路径。`--agent` 会使用第三层的 `minimal_agent` 执行运行时，需要你先配置模型 API。

## 运行方式

### 1. 汇总一个文本文件

```bash
cd /data/auto-research/LightScientist
PYTHONPATH=src python -m esnext run README.md --output outputs/readme-summary.md
```

### 2. 检查一个目录

```bash
cd /data/auto-research/LightScientist
PYTHONPATH=src python -m esnext run src --output outputs/src-inspect.md
```

### 3. 写一份笔记

```bash
cd /data/auto-research/LightScientist
PYTHONPATH=src python -m esnext run "阶段 2 完成，三层直通骨架已跑通。" --output outputs/stage2-note.md
```

## 运行测试

```bash
cd /data/auto-research/LightScientist
PYTHONPATH=src pytest -q
```

## 当前核心目录结构

```text
LightScientist/
├── README.md
├── pyproject.toml
├── src/
│   └── esnext/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── executor.py
│       ├── manager.py
│       ├── minimal_agent.py
│       ├── models.py
│       └── runtime.py
└── tests/
    └── test_smoke.py
```

说明：

- 上面列的是当前三层主路径相关的核心文件
- 目录里如果还有其他实验脚本，不属于当前主路径实现

## 下一步

下一阶段会继续增强第三层执行状态，同时暂时保持第三层只使用本地命令行能力。
