# GitHub Pages运行说明

## 架构

```text
晨报08:00 / 复盘20:00
  -> 原有本地不可变发布与Actions Artifact
  -> Windows归档Workflow仅提取已发布HTML
  -> published-reports完整历史
  -> Ubuntu Pages Builder
  -> GitHub Pages
```

Quant层与Pages层相互独立。Pages失败不改变报告、Forecast、Validation或Artifact状态。

## 自动触发

- `Archive sanitized reports` 每天UTC 00:05，即北京时间08:05，收集最新晨报。
- `A-share post-market review` 任一成功运行结束后触发归档；没有新报告时零变更退出。
- `published-reports/**`、Pages Builder或Pages Workflow变更后自动部署。
- 两个Workflow均保留 `workflow_dispatch`，可手动归档或重新部署。

归档Workflow继续使用现有Windows self-hosted runner及仓库Variables：`PYTHON_EXE`、`MORNING_REPORT_ROOT`、`REVIEW_REPORT_ROOT`。不新增业务密钥。

## 公开白名单

唯一允许从报告目录进入仓库和Pages的业务文件是最终HTML。归档器要求：

1. 同目录存在 `publication.json`；
2. 模式不是 `test`；
3. HTML SHA-256与READY或publication登记值一致；
4. HTML为UTF-8完整页面；
5. 不包含密钥特征、账户/本地绝对路径、脚本、事件处理器或JavaScript URL。

`public/`是临时构建目录并被Git忽略。站点每次从`published-reports/`的完整历史重建，不使用符号链接，也不向main提交构建产物。

## 固定地址

- Dashboard：`https://xunzhao6657.github.io/Richard_daily_done/`
- 最新晨报：`https://xunzhao6657.github.io/Richard_daily_done/latest/morning.html`
- 最新复盘：`https://xunzhao6657.github.io/Richard_daily_done/latest/review.html`

晨报与复盘分别选择各自最新日期。某类报告完全不存在时，固定地址显示友好占位页而不是404。

仓库Pages来源已于2026-09-11通过GitHub API设置为GitHub Actions，用户无需再到 `Settings -> Pages` 手动切换。

## 手动恢复

在Actions中先运行 `Archive sanitized reports`，再运行 `Deploy reports to GitHub Pages`。如果归档失败，查看被拒绝的具体HTML及规则；不要关闭敏感信息检查。若Pages部署失败，原报告和Artifact仍然有效，可在修复展示层后重新部署。
