# A股盘后复盘使用手册

## 日常结果在哪里

正式模式按以下不可覆盖路径发布：

```text
<REVIEW_REPORT_ROOT>\YYYY年M月分析\YYYY年M月D日分析\
  YYYY年M月D日A股收盘总结.md
  YYYY年M月D日A股收盘总结.html
  YYYY年M月D日A股收盘总结.docx
  audit.json
  handoff.json
  READY.json
  publication.json
```

影子模式位于 `<REVIEW_REPORT_ROOT>\review\shadow\YYYY-MM-DD\<run_id>`。看到 `publication.json` 才表示一次发布完成；只有READY或单个文件不能视为已发表。

## 看懂状态

- `COMPLETE`：当前启用的完整指标都满足同口径、时间和历史窗口要求。
- `PARTIAL`：核心收盘事实可用，但有明确缺项。例如当前炸板率和60日严格历史不足，所以不显示情绪温度计。
- `FAILURE_BULLETIN`：主行情源不可用，仍产出七节故障报告，但不包含猜测行情。
- `DEEPSEEK_VALIDATED`：至少一条模型解释通过所有结构和证据规则。
- `TEMPLATE_FALLBACK`：模型不可用或所有句子被拒绝，正文由确定性模板完成。
- `LATE_CAPTURE`：实际取数晚于19:45；数据保留，但限制说明会明确标记。

## 手动检查

```powershell
.\scripts\github_runner_status.ps1
.\scripts\runner_readiness.ps1
.\scripts\run_review.ps1 -Action status -Mode production
```

如需补跑当天，先执行 `prepare`，确认READY后在20:00至21:00之间执行 `publish`。系统拒绝提前发布和超过最大补发窗口的普通发布。重复触发返回已有publication，不会覆盖文件。

```powershell
.\scripts\run_review.ps1 -Action prepare -Mode production -ReportDate 2026-09-10
.\scripts\run_review.ps1 -Action publish -Mode production -ReportDate 2026-09-10
```

## 恢复与审计

`replay --offline`只检查已有文件和账本哈希，不访问网络。`revalidate`用保存的证据DTO和模型原始JSON套用当前校验器，生成新的READY运行，不改旧报告。`backup`调用SQLite在线备份并执行 `integrity_check`。

```powershell
.\.venv\Scripts\python.exe -m post_market_review --config config\runtime.json replay --run-id <run_id> --offline
.\.venv\Scripts\python.exe -m post_market_review --config config\runtime.json revalidate --run-id <run_id>
.\.venv\Scripts\python.exe -m post_market_review --config config\runtime.json backup
```

原始Wind响应、DeepSeek原始JSON和SQLite位于 `REVIEW_STATE_ROOT`，不要上传或移动到公开仓库。公开Artifact只应来自 `.runtime/outbox`。

## 常见故障

|现象|检查|
|---|---|
|任务一直排队|runner是否online，标签是否含`post-market-review`|
|DPAPI无法解密|runner是否由创建密钥的同一Windows账户运行|
|Wind失败|当前用户Wind CLI认证、联网和CLI路径|
|没有晨报对照|`MORNING_REPORT_ROOT`是否指向已发表目录，forecast hash是否匹配|
|情绪分数为空|确认炸板率、同口径60日历史和20日成交额基线，不要手工补分|
|发布被拒绝|检查是否早于20:00、晚于21:00或目标目录已有同名文件|

停用runner使用 `scripts\disable_github_runner.ps1`；恢复使用 `scripts\enable_github_runner.ps1`。卸载脚本只解除GitHub注册与启动任务，保留runner文件和证据，避免误删审计资产。
