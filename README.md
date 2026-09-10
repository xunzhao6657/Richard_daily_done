# Richard Daily Done

这是一个面向A股交易日的可审计盘后复盘系统。它在北京时间20:00发布Markdown、HTML和Word三件套，以Wind结构化收盘事实为主源，将同日已发表晨报的不可变预测作初步对照，再让DeepSeek V4 Flash只解释通过白名单、时间截点和证据校验的数据。

系统默认不补数。炸板率或严格60日同口径历史不完整时，情绪温度计返回空值；没有精确发布时间和授权范围的新闻源时，消息章节说明未获取；只有单日行业榜时只称“当日强势/弱势”，不判断持续主线。

## 工作流

```text
19:15 Wind预采集
   │  原始响应本地归档，记录SHA256与回执
19:40 刷新并构建快照
   │  19:45证据冻结，晚到数据标记LATE_CAPTURE
   │  确定性计算与晨报hash校验
   │  DeepSeek白名单DTO → claim/watch逐条校验
19:57 READY
   │  同一文档树导出MD / HTML / DOCX
20:00 唯一发布
   │  不覆盖同名文件，账本唯一键防重复
20:02 watchdog　20:15账本备份　次日06:30补评检查
```

GitHub Actions使用六个UTC cron表达式分别触发上述阶段。阶段间状态保存在runner主机的 `REVIEW_STATE_ROOT`，不会依赖短期checkout目录。非交易日返回 `SKIPPED`，未知日历日期硬失败。GitHub调度可能排队，报告始终记录真实发布时间和 `late` 状态，晚于60分钟拒绝正常发布。

## 数据和模型边界

- Wind market overview提供三指数、市场宽度、成交额、Wind行业板块榜、供应商大单分层、成交额锚点和连板梯队；指数日线只作为同供应商一致性复核，不称独立双源。
- 每次响应先写仓库外原始证据目录，并在SQLite账本登记请求哈希、响应哈希、时间、尝试次数和错误码。
- 发给DeepSeek的对象由字段白名单重建。Wind原始响应、API凭据、HTTP头、本地路径、供应商自然语言和未登记全文不能出站。
- 报告数字由代码生成。模型正文只能引用允许的证据ID；自由数字、未知token、错误章节、URL、无历史支持的高低位/放缩量措辞和供应商资金口径越界会被拒绝。
- DeepSeek端点固定为 `https://api.deepseek.com`，模型固定为 `deepseek-v4-flash`；模型不可用时仍生成确定性七节报告。

## 本地使用

```powershell
.\scripts\bootstrap.ps1
$env:WIND_CLI_PATH = "$env:USERPROFILE\.agents\skills\wind-mcp-skill\scripts\cli.mjs"
$env:DEEPSEEK_SECRET_FILE = 'E:\finance agent\finance\state\deepseek.key.dpapi'
$env:DEEPSEEK_BUDGET_ROOT = 'E:\finance agent\finance\state\llm-budget'
$env:MORNING_REPORT_ROOT = 'E:\finance agent\finance\daily-reports'
$env:REVIEW_STATE_ROOT = 'E:\finance agent\finance\state\post-market-review'
$env:REVIEW_REPORT_ROOT = 'E:\finance agent\finance\daily-reports'
.\scripts\runner_readiness.ps1
.\scripts\run_review.ps1 -Action run -Mode shadow
```

如需新建DeepSeek密钥，运行 `scripts\set_deepseek_secret.ps1`。输入不会回显，文件由当前Windows账户DPAPI加密并收紧ACL。不要把密钥写入配置、日志、命令行、issue或Actions Variable。Wind认证由现有Wind CLI管理，本仓库不保存Wind Key。

CLI支持 `doctor`、`collect`、`prepare`、`publish`、`watchdog`、`run`、`status`、`reconcile`、`handoff`、`replay --offline`、`revalidate` 和 `backup`。正式运行与影子运行使用不同发布唯一键和目录。

## GitHub Actions配置

工作流文件为 `.github/workflows/daily-review.yml`，仅接受 `schedule` 和手动触发，权限为 `contents: read`，checkout不保留Git凭据，任务只会投递给带 `post-market-review` 标签的Windows x64 self-hosted runner。仓库应配置以下Actions Variables：

|变量|建议值|
|---|---|
|`PYTHON_EXE`|runner上已验证的Python 3.11或更高版本绝对路径|
|`WIND_CLI_PATH`|`C:\Users\<账户>\.agents\skills\wind-mcp-skill\scripts\cli.mjs`|
|`DEEPSEEK_SECRET_FILE`|当前runner账户可解密的仓库外DPAPI文件|
|`DEEPSEEK_BUDGET_ROOT`|晨报与复盘共享的账户级预算目录|
|`REVIEW_STATE_ROOT`|独立且持久的复盘状态目录|
|`REVIEW_REPORT_ROOT`|正式报告根目录|
|`MORNING_REPORT_ROOT`|已发表晨报根目录|
|`REVIEW_MODE`|`production`；首轮验收可设 `shadow`|

也可使用Actions Secret `DEEPSEEK_API_KEY`，它优先于DPAPI文件；不要同时维护两份长期密钥。上传Artifact只读取 `.runtime/outbox` 的已发布净化副本，原始回执与模型原始响应不进入Artifact。

runner安装脚本使用一次性注册token和下载包SHA256，并创建当前用户登录后启动的隐藏任务。该模式可以复用当前用户的Wind认证和DPAPI，但主机必须开机、联网且保持登录；关机或注销时无法保证20:00执行。使用 `scripts\github_runner_status.ps1` 检查实际进程和任务结果。

## 目录

- `src/post_market_review`：采集、校验、研究、比较、报告、发布和恢复逻辑
- `schemas`：严格JSON契约
- `config`：运行参数、数据集白名单、外发授权与交易日历
- `prompts`：DeepSeek结构化研究约束
- `tests`：隔离目录中的验收测试
- `docs/design`：原设计包与实施裁决
- `IMPLEMENTATION_STATUS_REVIEW.md`：真实完成状态、探针和限制
- `REVIEW_USER_GUIDE.md`：日常操作和故障处理
- `review_requirements_traceability.csv`：需求到代码、测试和证据的映射

自动化研究产出不构成投资建议。
