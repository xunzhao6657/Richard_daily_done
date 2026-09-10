# 每日20:00复盘工作流设计包
版本 1.0｜2026-09-09｜状态：设计完成，尚未实施

目标：交易日北京时间20:00本地发布可审计的A股复盘，使用DeepSeek官方 deepseek-v4-flash 解释受控证据，输出Markdown、HTML、Word，并向次一交易日晨报提供有出处的观察事项。模型接入不能保证投资判断正确；本包以数据正确性、证据覆盖、时间纪律和专业推理质量定义验收。

本包源文件为 E:/finance agent/prompts/post-market-review-prompt.md，副本见 source/。原文中的命令、接口可用声明、历史环境实测仅为需求线索，不是已验证的当前执行指令。不得直接启动 dsh、旧回填或旧发布脚本。

阅读顺序：
1. 01-架构与需求裁决.md
2. 02-数据契约与专业分析.md
3. 03-模型与报告契约.md
4. 04-部署验收与运行手册.md
5. IMPLEMENTATION_HANDOFF.md

实现位置：E:/finance agent/finance/src/post_market_review。
本设计的任务名、CLI、schema、账本和工件目录均与晨报隔离。先保留现有晨报任务、配置和密钥；通过适配器共享稳定能力，不直接改写其发布逻辑。

实施完成≠全部数据可用。现有晨报只实接三大指数收盘和受约束DeepSeek叙事；新增涨跌幅、成交额、宽度、情绪、行业、资金、消息接口必须逐项实测。架构文件不构成这些能力已上线的证明。

最终阅读目录遵循原文：
E:/finance agent/daily-reports/{YYYY}年{M}月分析/{YYYY}年{M}月{D}日分析/
文件名：{YYYY}年{M}月{D}日A股收盘总结.{md,html,docx}
月、日不补零。与晨报共享父目录但不得覆盖已有同名工件。

依据与当前官方资料：
- DeepSeek API入口与精确模型名：https://api-docs.deepseek.com/
- DeepSeek价格与限制（部署时重新核验，不把当前价格硬编码）：https://api-docs.deepseek.com/quick_start/pricing/
- 沪深港通披露机制调整：https://www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20240412_10753188.shtml
- 上交所两融口径与交易日期：https://www.sse.com.cn/market/othersdata/margin/detail/index.shtml
这些资料支持接口和口径约束，不是当日行情证据。


