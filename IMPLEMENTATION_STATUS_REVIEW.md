# 盘后复盘实施状态

更新时间：2026-09-10（Asia/Shanghai）

## 已完成

- 已建立独立Python包、SQLite账本、交易日历、配置校验、数据集白名单和出站授权契约。
- 已实测Wind `stock_get_market_realtime_analysis` 和三指数 `get_index_kline`，保存原始回执、请求哈希、响应哈希和时间。指数复核明确标记为同供应商一致性检查。
- 已实测DeepSeek最小 `/chat/completions` 和真实收盘证据DTO。请求固定为 `deepseek-v4-flash`；供应商当前返回后端标识 `deepseek-flash`，两者以精确白名单关联，请求/返回标识和finish reason均审计，其他返回模型拒绝。
- 已实现字段白名单重建、嵌套路径/凭据拦截、模型自由数字/URL/未知引用/章节错配/无历史比较语句/资金口径越界拒绝。
- 已读取同日已发表晨报forecast并验证SHA256。当天forecast目标为未预测，因此报告显示 `NOT_PREDICTED`，没有事后设阈值。
- 已兼容 `forecast.v2` 的嵌套 `target.values`，并修正收益率decimal return及成交额元/亿元换算；每个可评价目标生成适用的Proper Scoring。
- 已把Forecast Quality与Trading Quality分离。没有真实执行数据时交易质量明确为 `NOT_EVALUATED`，不再合并成单一总分。
- 已生成独立 `institutional-review.json`，包含模型身份、Calibration、Monitoring和确定性Research Queue；队列只提出必需回测，不直接修改模型。
- 已实现七节同文档树导出Markdown、HTML和DOCX，HTML与Word使用涨红跌绿和箭头；Word四页完成逐页视觉检查。
- 已实现READY、唯一发布、文件不覆盖、20:00至21:00发布窗口、watchdog、离线重放、离线重校验、交接包和SQLite完整性备份。
- 已实现GitHub Actions六阶段UTC调度和Windows self-hosted runner运维脚本，workflow最小权限且只上传净化outbox。
- 已将完整Institutional Quant提示词及Pages实施需求按SHA-256归档；运行短Prompt增加公开分发边界，保持严格JSON输出契约。
- 已上线统一GitHub Pages门户。Windows归档层只提交已发布、哈希一致、非`test`且通过安全扫描的最终HTML；Ubuntu展示层从完整历史无状态重建站点。
- 自动测试23项通过：原12项业务合同测试不变，新增11项Pages测试覆盖空目录、单类/双类报告、跨月、跨年、中文文件名、无关HTML、Latest选择、Project Pages链接和敏感内容拒绝。

## 真实验收记录

|项目|结果|
|---|---|
|交易日|2026-09-09|
|最终影子运行|`revalidated-5e80e4410e8d4414adc2d3f353f29eae`|
|Wind市场主源|OK|
|Wind三指数同源复核|OK，SAME_PROVIDER_NOT_INDEPENDENT|
|晨报forecast|OK，PUBLISHED_HASH_VERIFIED|
|标准化观测|41条|
|报告事实|11条，证据覆盖率100%|
|DeepSeek|DEEPSEEK_VALIDATED|
|模型拒绝|4条；无历史比较或资金口径越界，未进入正文|
|报告状态|PARTIAL|
|时间状态|LATE_CAPTURE；验收在收市后人工执行，未冒充19:45准点运行|
|Word视觉验收|4页，中文、颜色、表格和重复表头通过|

## 仍然缺失或待观察

- 没有同口径炸板率、严格60日因子历史和每个历史日的20日成交额基线，情绪温度计按规则返回空值。
- 行业榜是Wind行业板块口径，尚未验证为申万一级全样本，报告明确保留该限制。
- 新闻、公告、两融、北向和港股数据集未登记为本版本自动源，对应能力不补写。
- 当前只有一次真实影子报告，尚未完成连续3个适用交易日的定时稳定性观察，因此不能声明调度SLA已验收。
- 本次重校验使用旧运行保存的审计输入；旧审计没有保存完整 `forecast.v2`，因此该历史成品无法补算评分。后续正常运行会直接保存新制度化工件。
- GitHub runner、仓库Variables和默认分支Actions已经完成实机验收；仍需以连续交易日观察确认长期调度稳定性。

## GitHub在线部署

- 仓库：`xunzhao6657/Richard_daily_done`，默认分支 `main`。
- 原复盘Workflow保持`contents: read`且不能批准PR；独立归档Workflow仅为提交`published-reports/`使用`contents: write`；Pages Workflow使用官方`pages: write`与OIDC权限。
- self-hosted runner `LAPTOP-B1VMJBGF-richard-daily` 已在线，标签为 `self-hosted`、`Windows`、`X64`、`post-market-review`。
- 首次验证发现 `setup-python` 在低权限runner上等待系统安装，因此已取消该运行；工作流改用 `PYTHON_EXE` 指向已验证的本机运行时，避免每日管理员安装与解释器下载。
- 第二次验证发现系统只有Windows PowerShell，工作流已改用 `powershell`；随后把合同测试状态与生产账本隔离，避免测试读到历史发布记录。
- GitHub doctor运行 [`34469700847`](https://github.com/xunzhao6657/Richard_daily_done/actions/runs/34469700847) 已在Institutional Quant升级提交 `1100801` 上成功完成：检出、Python、锁定依赖、12项合同测试、北京时间路由、DPAPI、Wind入口、状态目录和DeepSeek真实探测全部通过。
- Pages来源已通过GitHub API设置为`workflow`，无需手工修改Settings。首次部署 [`34502143620`](https://github.com/xunzhao6657/Richard_daily_done/actions/runs/34502143620) 成功，首页、Latest晨报、Latest复盘和历史复盘均返回HTTP 200，Latest文件SHA-256与本地发布登记值一致。
- 独立归档Workflow手动验收 [`34502211684`](https://github.com/xunzhao6657/Richard_daily_done/actions/runs/34502211684) 成功；当前公开历史包含2份晨报和1份复盘。
- runner在成功作业后已恢复 `online` 且空闲；连续3个适用交易日观察仍未完成。

专业能力以可核验证据、透明缺失和可重放规则为准，测试通过不代表投资判断经过收益验证。
