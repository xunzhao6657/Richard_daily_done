# 任务：为 Richard_daily_done 接入 GitHub Pages 报告网站

你现在负责修改 GitHub 仓库：

```text
xunzhao6657/Richard_daily_done
```

当前仓库已经存在 GitHub Actions 自动任务，其中至少包括：

```text
A-share post-market review
```

现有 Action 已经能够生成每日 A 股报告。

你的任务是在**不破坏现有晨报、收盘复盘、Quant Engine、报告归档和 Artifact 流程**的前提下，为整个系统接入 GitHub Pages，使用户可以通过固定网页地址查看：

```text
https://xunzhao6657.github.io/Richard_daily_done/
```

目标不是创建一个独立的新报告系统，而是在现有系统后面增加：

```text
GitHub Actions
      ↓
现有晨报 / 收盘复盘生成
      ↓
现有归档
      ↓
Pages Site Builder
      ↓
GitHub Pages
```

---

# 一、第一步：先检查仓库，禁止直接覆盖

首先完整检查：

```text
.github/workflows/
```

重点找出：

1. 晨报 Workflow；
2. `A-share post-market review` 对应 Workflow；
3. 是否还有 backfill / Quant / deploy 等 Workflow；
4. 每个 Workflow 的 trigger；
5. runner 类型：
   - ubuntu-latest
   - windows-latest
   - self-hosted
6. 报告最终生成目录；
7. HTML / Markdown / DOCX 实际文件名；
8. 报告是否 commit 回仓库；
9. 是否仅保存为 Actions Artifact；
10. 是否已经存在 Pages / gh-pages / public / site / docs 相关配置。

同时检查：

```text
daily-reports/
scripts/
prompts/
.github/
```

以及现有：

```text
run-daily-*.ps1
convert_daily_report.py
```

等实际文件。

---

# 二、禁止事项

在确认现有结构以前：

不得：

- 删除现有 Workflow；
- 重命名现有 Workflow；
- 删除现有 trigger；
- 改变晨报/收盘复盘正常调度时间；
- 删除现有 Artifact；
- 删除报告归档；
- 重写 Quant Engine；
- 修改预测算法；
- 修改 Wind / AKShare 数据逻辑；
- 修改现有 Secrets 名；
- 修改现有 Windows/self-hosted runner 配置；
- 把原有流程强制迁移到 Ubuntu；
- 将敏感文件复制到 Pages。

Pages 接入属于：

> Presentation / Distribution Layer

而不是：

> Quant Engine Rewrite。

---

# 三、目标 Pages 地址

最终默认访问入口：

```text
https://xunzhao6657.github.io/Richard_daily_done/
```

同时必须建立稳定地址：

## 最新晨报

```text
https://xunzhao6657.github.io/Richard_daily_done/latest/morning.html
```

## 最新收盘复盘

```text
https://xunzhao6657.github.io/Richard_daily_done/latest/review.html
```

如果当日尚未生成对应报告：

页面不得 404。

应显示：

```text
今日晨报尚未生成
```

或：

```text
今日收盘复盘尚未生成
```

并允许访问上一交易日报告。

---

# 四、Pages 最终目录结构

Pages 构建阶段生成：

```text
public/
│
├── index.html
├── .nojekyll
│
├── latest/
│   ├── morning.html
│   └── review.html
│
├── reports/
│   ├── 2026/
│   │   ├── 09/
│   │   │   ├── 20260910/
│   │   │   │   ├── morning.html
│   │   │   │   └── review.html
│   │   │   ├── 20260909/
│   │   │   │   ├── morning.html
│   │   │   │   └── review.html
│   │   │   └── ...
│   │   └── ...
│   └── ...
│
└── assets/
    └── ...
```

如现有报告命名结构与此不同：

不要修改现有归档结构。

应该在 Pages Build 阶段：

> 将现有归档映射/复制到 public/reports。

---

# 五、不得依赖 Symbolic Link

不要用：

```text
ln -s
```

实现：

```text
latest/morning.html
latest/review.html
```

GitHub Pages Artifact 对符号链接存在限制。

应该：

> 复制最新 HTML 文件到 latest 目录。

---

# 六、历史报告必须持久存在

这是硬性要求。

不能出现：

```text
今天 Pages 有 9 月 10 日
明天重新部署以后只剩 9 月 11 日
```

Pages 每次部署必须包含：

```text
所有已归档历史报告
+
本次最新报告
```

根据实际仓库结构选择正确实现。

---

# 七、根据仓库现状选择持久化方案

## 情况 A：报告已经 commit 回仓库

这是优先方案。

直接从仓库：

```text
daily-reports/
```

构建完整 Pages。

新增一个独立 Pages Workflow，例如：

```text
.github/workflows/pages.yml
```

由报告文件变更触发。

---

## 情况 B：报告没有 commit，仅存在于 Actions Artifact

不要假装历史报告存在。

检查是否可以：

1. 保留现有 Artifact；
2. 将最终 HTML 报告安全 commit 到专用报告目录；

或者：

3. 在 Pages workflow 中下载需要的历史 Artifact。

优先选择：

> 简单、稳定、可恢复的方案。

如果将 HTML commit 回仓库不会破坏现有架构，则可以考虑建立：

```text
published-reports/
```

作为 Pages 历史事实层。

但：

> 不要 commit Secrets、原始 Wind 数据、模型私密文件或大体积原始数据。

---

# 八、优先建立独立 Pages Workflow

除非现有架构明确更适合直接接入，否则优先新增：

```text
.github/workflows/pages.yml
```

而不要将大量 Pages 逻辑塞入：

```text
A-share post-market review
```

Pages Workflow 职责只包括：

```text
Checkout
↓
Build public/
↓
Configure Pages
↓
Upload Pages Artifact
↓
Deploy Pages
```

实现关注点分离。

---

# 九、GitHub Pages 官方 Action

使用当前 GitHub Pages 官方方式。

推荐：

```yaml
actions/checkout@v6
actions/configure-pages@v5
actions/upload-pages-artifact@v4
actions/deploy-pages@v4
```

不要使用已经明显过时的第三方：

```text
peaceiris/actions-gh-pages
```

除非仓库现有架构具有必须使用它的明确原因。

优先官方 Pages Artifact Deployment。

---

# 十、Pages Workflow 权限

必须正确设置：

```yaml
permissions:
  contents: read
  pages: write
  id-token: write
```

Deploy Job：

```yaml
environment:
  name: github-pages
  url: ${{ steps.deployment.outputs.page_url }}
```

如果 Build 和 Deploy 分离：

Deploy 必须正确：

```yaml
needs: build
```

避免 deploy job 在 Pages Artifact 尚未产生时运行。

---

# 十一、并发控制

晨报和收盘复盘可能都触发 Pages。

必须防止两个 Deployment 同时修改 Pages。

加入合理：

```yaml
concurrency:
  group: pages
  cancel-in-progress: false
```

或符合当前 GitHub Pages 推荐实践的等价方式。

目标：

> 不因为晨报和收盘复盘短时间连续完成导致 Pages 部署互相覆盖。

---

# 十二、推荐触发策略

根据仓库实际结构选择。

如果报告 commit 回 main：

推荐：

```yaml
on:
  push:
    branches:
      - main
    paths:
      - 'daily-reports/**'
      - 'scripts/build_pages.py'
      - '.github/workflows/pages.yml'

  workflow_dispatch:
```

必须保留：

```text
workflow_dispatch
```

方便手动重新发布 Pages。

---

# 十三、避免 Workflow 无限循环

如果报告 Action：

```text
生成报告
↓
git commit
↓
push main
```

而 Pages Workflow：

```text
push main
↓
部署
```

这是正常的。

但是 Pages Workflow：

> 不应该再次向 main commit Pages 构建产物。

否则容易形成：

```text
push
→ Pages
→ commit
→ push
→ Pages
→ ...
```

`public/` 默认只作为临时构建目录。

不要 commit `public/`，除非当前架构明确需要。

---

# 十四、新增 Pages Builder

建议新增：

```text
scripts/build_pages.py
```

负责：

1. 扫描已有晨报；
2. 扫描已有收盘复盘；
3. 提取日期；
4. 建立历史目录；
5. 找到最新晨报；
6. 找到最新复盘；
7. 复制到 latest；
8. 自动生成首页；
9. 自动生成历史报告索引。

不得把这些复杂逻辑全部写成几十行 Bash。

因为仓库可能同时在：

```text
Windows
Linux GitHub Runner
```

运行。

Python 更适合跨平台处理。

---

# 十五、自动识别现有中文报告文件名

当前报告可能采用类似：

```text
2026年9月10日A股盘前分析.html
2026年9月10日A股收盘总结.html
```

Builder 必须按照实际仓库文件进行匹配。

不要假定文件名一定完全等于示例。

优先：

1. 分析现有归档；
2. 找出稳定命名模式；
3. 写容错匹配。

需要区分：

```text
Morning
Review
```

禁止把收盘总结识别成晨报。

---

# 十六、首页 Dashboard

自动生成：

```text
public/index.html
```

首页标题：

```text
A股 Quant Research Dashboard
```

页面必须至少包含：

```text
最新交易日
```

并提供两个最明显入口：

```text
今日盘前晨报
今日收盘复盘
```

---

# 十七、首页内容

建议结构：

```text
A股 Quant Research Dashboard

最后更新：
2026-09-10 20:xx CST

━━━━━━━━━━━━━━━━

今日研究

[ 盘前晨报 ]
[ 收盘复盘 ]

━━━━━━━━━━━━━━━━

历史报告

2026-09-10
  盘前晨报
  收盘复盘

2026-09-09
  盘前晨报
  收盘复盘

...

━━━━━━━━━━━━━━━━

System
GitHub Actions automated research pipeline
```

---

# 十八、首页设计要求

风格：

```text
专业
简洁
金融终端感
桌面/手机响应式
```

不要做：

```text
花哨动画
复杂前端框架
React/Vue 大型依赖
Node 构建链
```

优先：

```text
Static HTML + CSS
```

确保 GitHub Pages 零后端即可运行。

---

# 十九、A 股颜色规范

保持现有报告：

```text
上涨 = 红
下跌 = 绿
```

首页如果展示涨跌数据，也必须：

```text
A股涨红跌绿
```

不得套用欧美：

```text
Green Up / Red Down
```

---

# 二十、链接必须适配 Project Pages

因为站点不是：

```text
xunzhao6657.github.io/
```

根站点，而是：

```text
xunzhao6657.github.io/Richard_daily_done/
```

所以：

禁止错误硬编码：

```html
<a href="/latest/morning.html">
```

因为这可能跳到：

```text
xunzhao6657.github.io/latest/morning.html
```

应该使用：

```html
<a href="./latest/morning.html">
```

或者其他正确的 repo-relative URL。

所有：

```text
CSS
报告链接
历史目录
返回首页
```

都必须适配：

```text
/Richard_daily_done/
```

base path。

---

# 二十一、报告页面导航增强

不要修改原报告正文内容。

但 Pages 构建时可选择给 HTML 包装简单导航：

```text
← 返回首页
盘前晨报
收盘复盘
历史报告
```

如果修改原 HTML 风险过高：

不要动正文。

优先保持现有转换结果原样。

---

# 二十二、Latest 逻辑

`latest/morning.html`：

必须指向最新成功生成的晨报 HTML。

`latest/review.html`：

必须指向最新成功生成的收盘复盘 HTML。

两者日期不要求永远相同。

例如：

```text
上午：
Morning = 2026-09-11
Review  = 2026-09-10
```

这是正常状态。

不要因为今天收盘报告尚未生成而删除昨天 latest review。

---

# 二十三、历史索引

首页必须根据实际归档自动生成。

不能手写：

```text
2026-09-10
2026-09-09
```

每次部署：

自动扫描。

排序：

```text
日期降序
```

最新日期在最前。

---

# 二十四、缺失报告处理

某天只有晨报：

```text
2026-09-10
Morning ✅
Review  —
```

某天只有 Review：

也必须正常显示。

不要因为缺一个报告导致整个站点构建失败。

---

# 二十五、首页不要依赖网络 API

首页构建完成以后应该完全静态。

禁止要求客户端调用：

```text
GitHub REST API
Wind API
DeepSeek API
外部数据库
```

用户浏览 Pages 时：

只访问静态文件。

---

# 二十六、敏感信息保护

Pages 为静态发布层。

严禁将以下文件复制进：

```text
public/
```

包括但不限于：

```text
.env
Secrets
API Keys
GitHub PAT
WIND_APP_ID
WIND_APP_SECRET
DeepSeek Key
模型 credential
完整原始 Wind 数据
账户信息
原始内部日志
```

必须明确设置 Pages allowlist。

即：

> 只复制明确允许发布的文件。

不要：

```bash
cp -r . public/
```

不要把整个仓库发布。

---

# 二十七、默认允许发布内容

优先仅发布：

```text
最终 HTML 晨报
最终 HTML 收盘复盘
index.html
静态 CSS/assets
```

如果确认没有授权/敏感问题，可以额外发布：

```text
DOCX
MD
非敏感 summary JSON
```

但默认不要公开：

```text
Raw Wind Data
Feature Snapshot
完整 Forecast Feature JSON
模型日志
Secrets
```

---

# 二十八、Wind 数据授权边界

不要因为 Pages 需要 Dashboard 就把：

```text
Wind 原始数据表
完整原始历史行情数据库
```

发布到网站。

Pages 应展示：

> 最终研究报告。

而不是：

> 原始授权数据库镜像。

---

# 二十九、保留原 Actions Artifact

如果现有 Workflow 已经：

```text
upload-artifact
```

必须保留。

最终分工：

```text
GitHub Pages
=
日常阅读 HTML

Actions Artifact
=
DOCX / MD / JSON / 日志 / 调试 / 备份
```

两者不要互相替代。

---

# 三十、晨报和收盘复盘使用同一个 Pages

禁止建立：

```text
Morning Pages site
Review Pages site
```

应统一：

```text
Richard_daily_done
```

一个研究门户。

---

# 三十一、推荐 Pages Workflow 基本结构

最终代码应遵循类似：

```yaml
name: Deploy reports to GitHub Pages

on:
  workflow_dispatch:
  push:
    branches:
      - main
    paths:
      - 'daily-reports/**'
      - 'scripts/build_pages.py'
      - '.github/workflows/pages.yml'

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v6

      - name: Setup Python
        uses: actions/setup-python@v6
        with:
          python-version: '3.12'

      - name: Build Pages site
        run: python scripts/build_pages.py

      - name: Configure Pages
        uses: actions/configure-pages@v5

      - name: Upload Pages artifact
        uses: actions/upload-pages-artifact@v4
        with:
          path: public

  deploy:
    needs: build
    runs-on: ubuntu-latest

    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}

    steps:
      - name: Deploy Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

这是参考结构。

最终必须根据仓库实际情况调整。

不要机械覆盖现有 YAML。

---

# 三十二、Pages Settings

代码修改完成以后，明确告诉用户还需要手动完成：

```text
Repository
→ Settings
→ Pages
→ Build and deployment
→ Source
→ GitHub Actions
```

如果已经设置：

明确报告：

> 无需再次设置。

---

# 三十三、Pages 部署成功后输出 URL

Workflow 成功以后：

必须能得到：

```text
steps.deployment.outputs.page_url
```

同时在 Job Summary 中输出：

```text
Dashboard:
https://xunzhao6657.github.io/Richard_daily_done/

Latest Morning:
https://xunzhao6657.github.io/Richard_daily_done/latest/morning.html

Latest Review:
https://xunzhao6657.github.io/Richard_daily_done/latest/review.html
```

---

# 三十四、增加 GitHub Actions Job Summary

Pages Deployment 完成以后写：

```markdown
## 📊 A股 Quant Research Dashboard

- Dashboard: ...
- Latest Morning Brief: ...
- Latest Post-Market Review: ...
```

这样用户打开 Actions Run 就可以直接点击网站。

---

# 三十五、失败处理

Pages 构建失败不能影响原 Quant Report 的事实结果。

如果：

```text
报告生成成功
Pages 发布失败
```

应明确区分：

```text
REPORT_STATUS = SUCCESS
PAGES_STATUS = FAILED
```

不要让用户误以为报告生成失败。

---

# 三十六、Builder 测试

至少增加自动测试：

```text
tests/test_build_pages.py
```

覆盖：

### Case 1

同时有晨报和复盘。

### Case 2

只有晨报。

### Case 3

只有复盘。

### Case 4

跨月份。

### Case 5

跨年份。

### Case 6

中文文件名。

### Case 7

目录为空。

### Case 8

存在无关 HTML。

### Case 9

latest 正确选择最新报告。

---

# 三十七、构建完整性检查

Pages Artifact 上传前检查：

```text
public/index.html exists
public/.nojekyll exists
```

并至少满足：

如果历史有 Morning：

```text
public/latest/morning.html exists
```

如果历史有 Review：

```text
public/latest/review.html exists
```

否则：

Builder 应生成友好的 placeholder 页面。

---

# 三十八、编码要求

所有 HTML：

```text
UTF-8
```

必须正确显示：

```text
中文
↑
↓
%
亿元
万亿元
```

不得出现乱码。

---

# 三十九、时区

网站显示：

```text
Asia/Shanghai
UTC+8
```

不要直接显示 GitHub Runner UTC 时间而不转换。

首页：

```text
最后更新：YYYY-MM-DD HH:mm CST
```

---

# 四十、首页日期逻辑

不要简单：

```text
datetime.now()
```

作为“最新交易日”。

应该：

> 根据实际报告文件日期确定。

例如周六：

首页仍应显示最近交易日：

```text
2026-09-11
```

而不是：

```text
2026-09-12
```

---

# 四十一、避免破坏现有 Windows 路径

现有量化系统可能含：

```text
E:\finance agent\
C:\Users\寻昭\
PowerShell
```

Pages Builder 自身应该尽量使用：

```text
pathlib.Path
```

处理仓库内相对路径。

不要要求已有 Windows Quant 流程修改为 Linux path。

Pages Layer 与 Quant Layer 解耦。

---

# 四十二、Self-hosted Runner 兼容

如果现有晨报/复盘运行于：

```text
self-hosted Windows
```

不要改变。

推荐：

```text
Quant / Wind
=
Windows self-hosted

Pages build/deploy
=
ubuntu-latest
```

前提是报告已经进入仓库或可以由 Pages Job 安全获得。

这是首选架构。

---

# 四十三、最终推荐架构

目标：

```text
GitHub Schedule
      ↓
Windows Self-hosted Runner
      ↓
Wind / AKShare / Quant Engine
      ↓
Morning / Review HTML
      ↓
Report Archive
      ↓
Repository / Persistent Report Store
      ↓
ubuntu-latest
      ↓
build_pages.py
      ↓
public/
      ↓
upload-pages-artifact
      ↓
deploy-pages
      ↓
GitHub Pages
      ↓
手机 / PC 浏览器
```

---

# 四十四、完成后必须实际验证

不要只修改文件。

必须执行能够执行的测试：

```text
python scripts/build_pages.py
pytest
```

然后检查：

```text
public/index.html
public/latest/morning.html
public/latest/review.html
```

以及至少几个历史 URL。

---

# 四十五、检查 HTML 内链接

自动或人工检查：

```text
index → latest morning
index → latest review
index → history
history → morning/review
```

不得出现：

```text
404
错误绝对路径
Windows 本地路径
file:///
E:\...
```

---

# 四十六、提交前 Git Diff 审计

完成后检查：

```text
git diff
```

确认：

没有：

```text
Secret
Credential
Token
.env
Raw Data
```

意外进入 Pages 或 commit。

---

# 四十七、不要无关重构

只修改接入 Pages 所必须的内容。

优先新增：

```text
.github/workflows/pages.yml
scripts/build_pages.py
tests/test_build_pages.py
```

必要时小幅修改：

```text
晨报 Workflow
收盘 Workflow
.gitignore
README
```

不要进行无关代码格式化和项目大重构。

---

# 四十八、最终交付说明

完成以后必须向用户明确报告：

## 1. 检查到了什么

例如：

```text
Morning workflow:
...

Review workflow:
...

报告归档路径:
...

报告是否 commit:
...
```

---

## 2. 修改了哪些文件

逐项列出。

---

## 3. Pages 如何触发

说明：

```text
晨报生成后
收盘复盘生成后
手动 workflow_dispatch
```

哪些情况下会部署。

---

## 4. 用户还需要手工做什么

特别检查：

```text
Settings → Pages → Source → GitHub Actions
```

---

## 5. 最终访问地址

明确输出：

```text
首页
https://xunzhao6657.github.io/Richard_daily_done/

最新晨报
https://xunzhao6657.github.io/Richard_daily_done/latest/morning.html

最新收盘复盘
https://xunzhao6657.github.io/Richard_daily_done/latest/review.html
```

---

## 6. 测试结果

必须说明：

```text
Builder Test
Workflow Syntax
Link Validation
Sensitive File Check
```

哪些通过。

---

# 四十九、验收标准

只有同时满足以下条件才算完成：

- [ ] 现有 Morning Workflow 未被破坏；
- [ ] 现有 Review Workflow 未被破坏；
- [ ] 现有 Quant Engine 未被修改；
- [ ] 现有 Artifact 保留；
- [ ] GitHub Pages 使用官方 Pages Actions；
- [ ] `public/index.html` 自动生成；
- [ ] 最新晨报具有固定 URL；
- [ ] 最新收盘复盘具有固定 URL；
- [ ] 历史报告不会被下一次部署删除；
- [ ] Morning / Review 共用一个 Dashboard；
- [ ] Project Pages base path 正确；
- [ ] 手机可正常阅读；
- [ ] 中文无乱码；
- [ ] A 股涨红跌绿；
- [ ] 不发布 Secrets；
- [ ] 不发布原始 Wind 数据；
- [ ] Pages 失败不会被误判为 Quant 报告失败；
- [ ] 支持手动重新部署；
- [ ] Pages workflow 无无限触发循环；
- [ ] 并发部署不会互相覆盖；
- [ ] 首页历史列表自动生成；
- [ ] Latest 自动更新；
- [ ] 用户最终只需要收藏一个 Dashboard 地址。

---

# 五十、最终原则

不要把 GitHub Pages 设计成新的分析系统。

它只负责：

```text
PUBLISH
NAVIGATE
ARCHIVE
READ
```

分析事实仍来自：

```text
Wind / AKShare
↓
Quant Engine
↓
Morning Brief / Post-Market Review
```

最终架构必须保持：

```text
Quant Layer
      ↓
Report Layer
      ↓
Pages Layer
```

而不是：

```text
Pages
↓
重新计算 Quant 数据
```

Pages 必须是无状态、静态、可重复构建的展示层。

完成目标：

> 用户每天不需要进入 GitHub Actions 下载 Artifact，只需要打开

```text
https://xunzhao6657.github.io/Richard_daily_done/
```

> 即可查看最新晨报、最新收盘复盘和所有历史报告。