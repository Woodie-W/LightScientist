# LightScientist 第三层最小实现方案

## 目标

这份方案的目标，是把当前的 [minimal_agent.py](/data/auto-research/LightScientist/src/esnext/minimal_agent.py:1) 从一个最小原型，收敛成 LightScientist 第三层的最小执行运行时。

这一阶段只关注第三层最小闭环，不追求完整平台能力。

本阶段保留的能力：

- LLM 调用
- action 解析
- 本地命令执行
- 异常恢复
- 终止机制
- 基础执行状态

本阶段明确不做：

- skills
- 工具注册系统
- 复杂上下文压缩
- MCP
- 多工具接口协议
- 多模型路由
- 并发执行

## 为什么从 minimal_agent 开始

你已经把最基础的代码放在了 [minimal_agent.py](/data/auto-research/LightScientist/src/esnext/minimal_agent.py:1)，而且它的结构与官方教程一致，适合作为第三层的起点。

从当前 LightScientist 的三层边界来看：

- 第一层负责阶段目标
- 第二层负责运行状态
- 第三层负责真正的执行运行时

因此，把 `minimal_agent` 演进成第三层的最小执行运行时，是自然且合理的路径。

## 当前代码的状态

当前 [minimal_agent.py](/data/auto-research/LightScientist/src/esnext/minimal_agent.py:1) 具备以下要素：

- 一个 `query_lm` 函数
- 一个 `parse_action` 函数
- 一个 `execute_action` 函数
- 一个直接写在文件底部的 `while True` 主循环

它已经足够证明“最小 agent 可以工作”，但还不适合作为系统里的第三层运行时。

当前存在的主要问题：

- 代码是脚本式结构，导入即运行，不适合系统接入
- 没有明确的输入输出接口
- 没有异常分类
- 没有格式错误处理
- 没有统一终止机制
- 没有最大步数限制
- 没有环境变量治理
- 还不能稳定向第二层返回结构化状态

## 参考来源

这份方案以官方教程的 robust 部分为直接参考：

- 官方主页：<https://minimal-agent.com/>
- “Let’s make it more robust”：<https://minimal-agent.com/#lets-make-it-more-robust>

重点参考的几部分包括：

- 异常在控制流中的处理
- malformatted output 的处理
- 环境变量设置

## 核心设计思路

这一阶段的核心目标不是让第三层变强，而是让它变稳。

换句话说：

- 不是先加更多能力
- 而是先让已有的最小能力可控、可恢复、可终止、可接入上层

因此第三层最小实现的原则是：

- 保持单一执行闭环
- 增加最少但关键的健壮性
- 把控制流从“demo 脚本”变成“系统运行时”

## 文件级修改计划

本阶段建议涉及以下文件。

### 1. [minimal_agent.py](/data/auto-research/LightScientist/src/esnext/minimal_agent.py:1)

这是本阶段的核心修改对象。

目标是：

- 从顶层 demo 脚本改成可调用的执行运行时模块
- 增加官方教程建议的健壮性处理

### 2. [models.py](/data/auto-research/LightScientist/src/esnext/models.py:1)

建议增加第三层执行结果结构，使其能表达：

- 正常完成
- 主动终止
- 异常失败
- 达到最大步数

### 3. [runtime.py](/data/auto-research/LightScientist/src/esnext/runtime.py:1)

第二层只做最小接线：

- 把任务目标交给第三层
- 接收第三层结构化结果
- 更新最小运行状态

本阶段不在第二层堆复杂逻辑。

### 4. [README.md](/data/auto-research/LightScientist/README.md:1)

建议补充：

- 第三层当前的能力范围
- 所需 API 或环境变量
- 如何单独运行第三层

### 5. [tests/test_smoke.py](/data/auto-research/LightScientist/tests/test_smoke.py:1)

建议增加针对第三层最小运行时的 smoke test。

## `minimal_agent.py` 内部改造计划

## 1. 去掉顶层直接执行的 `while True`

当前主循环如果直接写在文件底部，以后作为第三层是不合适的。

应改成显式入口，例如：

- `run_agent(...)`
- `run_session(...)`
- `execute_goal(...)`

目标是：

- 第三层可以被第二层调用
- 不再依赖导入即执行

## 2. 把消息初始化从脚本中抽离

当前 `messages` 是写死的：

- system prompt
- user prompt

应该改成：

- 外部传入任务目标
- 内部构造系统消息和初始用户消息
- 支持后续扩展工作目录、步数、模型名等输入

## 3. 保留 `query_lm`，但限定职责

`query_lm` 应只负责：

- 调用模型
- 返回文本输出

它不应负责：

- 控制循环
- 处理异常流程
- 管执行状态

这有助于第三层后续继续扩展。

## 4. 强化 `parse_action`

`parse_action` 如果在没有匹配时直接返回空字符串，会让第三层很难稳定恢复。

建议改成严格校验：

- 没有 action -> 抛格式异常
- 多于一个 action -> 抛格式异常
- 恰好一个 action -> 返回命令

同时异常信息中应包含明确示例，例如：

```text
Your output was malformatted.
Please include exactly 1 action formatted as:

```bash-action
ls -R
```
```

这样才能按官方方案，把错误信息反馈回模型。

## 5. 强化 `execute_action`

当前 `execute_action` 直接调用 `subprocess.run` 并返回 stdout。

建议增加：

- 超时异常包装
- `exit` 终止逻辑
- 非交互环境变量
- 更明确的返回与错误边界

这一阶段依然只保留命令行能力，不引入其他工具。

## 6. 增加主循环异常处理

当前主循环对异常没有统一处理逻辑。

建议按官方 robust 方案改成：

- 可恢复错误：追加回消息历史
- 终止错误：正常结束
- 未知错误：记录并失败

这一步是第三层从 demo 变成 runtime 的关键。

## 7. 增加最大步数限制

第三层必须具备最小步数上限，避免模型无限循环。

建议支持：

- `max_steps`
- 达到上限后的明确状态返回

## 建议引入的异常类型

建议引入以下异常层次：

- `AgentRuntimeError`
- `NonTerminatingError`
- `ActionFormatError`
- `ActionTimeoutError`
- `TerminationRequested`

建议的语义如下：

### `AgentRuntimeError`

第三层内部基础异常父类。

### `NonTerminatingError`

表示可恢复错误，可以反馈给模型继续处理。

### `ActionFormatError`

表示模型输出格式不合法。

### `ActionTimeoutError`

表示命令执行超时。

### `TerminationRequested`

表示模型主动请求结束执行。

## 控制流建议

建议第三层的控制流统一改成下面这种结构：

1. 调用模型
2. 解析 action
3. 执行 action
4. 如果出现 `NonTerminatingError`
   把错误信息追加回消息历史
5. 继续下一轮
6. 如果出现 `TerminationRequested`
   正常结束
7. 如果达到最大步数
   返回上限状态

这样第二层才能稳定消费第三层的结果。

## 命令超时处理建议

官方 robust 部分建议：不要让命令超时直接变成原始异常，而应包装成更适合模型理解的错误信息。

建议的处理方式：

- 捕获 subprocess 的 timeout
- 抛出 `ActionTimeoutError`
- 错误文本明确说明：
  - 上一条命令超时
  - 可能调用了交互式工具
  - 建议改用非交互命令或更短命令

这样能提高第三层的自恢复能力。

## `exit` 的处理建议

当前代码直接：

- `if action == "exit": break`

建议改成：

- `exit` -> 抛 `TerminationRequested`
- 由统一控制流捕获并结束

这样终止路径会更清晰，也更容易反馈给第二层。

## 环境变量建议

按官方 robust 教程，命令执行应增加一组环境变量，尽量避免交互式行为卡住 agent：

- `PAGER=cat`
- `MANPAGER=cat`
- `LESS=-R`
- `PIP_PROGRESS_BAR=off`
- `TQDM_DISABLE=1`

这些变量建议只在第三层命令执行时注入，不需要由第二层管理细节。

## 第三层的最小输入输出接口建议

## 输入建议

第三层的最小输入至少应包括：

- `goal`
- `working_dir`
- `max_steps`
- `model`
- `extra_env` 可选

## 输出建议

第三层的最小输出至少应包括：

- `status`
- `messages`
- `last_model_output`
- `last_action`
- `final_output`
- `step_count`
- `error` 可选

这一步的重点不是接口优雅，而是让第二层可接。

## 第二层如何接第三层

本阶段第二层不做复杂逻辑，只做最小接线：

- 接收任务
- 传任务目标给第三层
- 传工作目录
- 传最大步数
- 直接把任务交给第三层
- 接收第三层结构化结果
- 更新最小任务状态

第二层此时不应理解第三层内部完整消息历史，只消费第三层的结果摘要和最终状态。

## 测试清单

建议增加下面这些测试。

### 1. 正常 action 解析

输入合法 `bash-action`，应能正确提取命令。

### 2. 非法格式处理

没有 action 或出现多个 action 时，应抛 `ActionFormatError`。

### 3. `exit` 终止

模型输出 `exit` 时，应走正常终止流程。

### 4. timeout 包装

命令超时时，应转成 `ActionTimeoutError`，而不是直接炸掉。

### 5. 可恢复异常回流

`NonTerminatingError` 应被追加到消息历史中，而不是直接停止运行。

### 6. 最大步数限制

达到 `max_steps` 后，应返回明确状态。

### 7. 环境变量生效

命令执行时应使用合并后的环境变量。

## 本阶段明确不做的内容

为了避免第三层过早膨胀，这一阶段明确不做：

- skills 接入
- tool registry
- 复杂上下文压缩
- 多任务并发
- 多模型路由
- 权限细粒度沙箱
- MCP
- prompt 模板体系化拆分

## 完成标志

这一阶段完成后，第三层应达到如下标准：

- 能接收一个目标
- 能循环调用模型
- 能解析 action
- 能执行命令
- 能把可恢复错误反馈给模型
- 能在终止、失败、步数耗尽三种情况下返回明确状态

做到这一步，就可以认为第三层“初步实现”了。

虽然它还不是完整的类 Codex / Claude Code 执行层，但已经不再是 demo 脚本，而是一个可以纳入 LightScientist 三层结构的最小执行运行时。
