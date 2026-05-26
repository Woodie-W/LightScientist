请只执行 paper 阶段，不要运行新的长时间实验。

任务背景：
这是一个 CORAL 的 MEOW 股票预测刷榜任务。目标是在固定 train/test 划分上最大化 test-set Pearson correlation against fret12。
当前工作区已经提供了：

- `source_task/`
- `source_seed/`
- `source_results/`

请基于现有代码、task 配置、grader、已有 attempts、日志和 notes，整理一份完整项目报告。

重要约束：
- `source_task/`、`source_seed/`、`source_results/` 及其指向的 CORAL 源目录都是只读参考材料。
- 不要修改这些目录中的文件。
- 只允许在当前 workspace 内写入报告、表格、总结和过程文件。

要求：
1. 在 `paper.plan` 阶段，先梳理任务定义、评分方式、代码结构、基线、限制条件和已有产物清单。
2. 在 `paper.figure` 阶段，从已有 attempts / logs / notes 中提取关键实验记录、得分变化、主要改动和证据表格。
3. 在 `paper.write` 阶段，写出报告草稿，明确区分：
   - benchmark 任务定义
   - 代码结构与主要模块
   - 评分与评测流程
   - 已有尝试与刷榜轨迹
   - 当前最强方案或主要方向
   - 已知瓶颈与后续建议
4. 在 `paper.review` 阶段，审查报告证据充分性，标出：
   - 哪些结论有明确代码或结果支持
   - 哪些结论只是推测
   - 哪些材料缺失，导致无法下结论

额外约束：
- 不要运行新的长时间实验。
- 允许做轻量文件检查、日志读取、JSON 解析、代码阅读。
- 优先使用已有结果目录中的 `attempts/*.json`、`logs/*.log`、`notes/*.md`。
- 读取时只允许使用当前 workspace 内可见的相对路径，不要使用任何绝对路径。
- 不要编辑 `source_task/`、`source_seed/`、`source_results/` 中的任何文件，也不要通过符号链接改动 CORAL 原目录。
- 报告里要明确指出：这是 benchmark / leaderboard 项目报告，不是传统论文复现。
- 每个阶段都要把结果写入工作区产物文件。
- 所有交付文件、报告文件、表格文件一律使用 workspace 内的相对路径，例如 `phase3-paper/PAPER_PLAN.md`，不要使用绝对路径写文件。
