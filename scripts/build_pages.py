from __future__ import annotations

import argparse
import html
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:
    from .archive_pages_reports import validate_public_html
except ImportError:  # Direct script execution.
    from archive_pages_reports import validate_public_html


ARCHIVE_RE = re.compile(r"^(\d{4})/(\d{2})/(\d{8})/(morning|review)\.html$")
CST = timezone(timedelta(hours=8), name="CST")


@dataclass(frozen=True)
class SiteReport:
    report_date: str
    kind: str
    source: Path
    relative_target: Path


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name in {"href", "src"} and value:
                self.links.append(value)


def discover_site_reports(source: Path) -> list[SiteReport]:
    reports: list[SiteReport] = []
    if not source.is_dir():
        return reports
    for path in source.rglob("*.html"):
        relative = path.relative_to(source).as_posix()
        match = ARCHIVE_RE.fullmatch(relative)
        if not match:
            continue
        year, month, day, kind = match.groups()
        parsed = datetime.strptime(day, "%Y%m%d")
        if parsed.strftime("%Y") != year or parsed.strftime("%m") != month:
            continue
        validate_public_html(path)
        reports.append(
            SiteReport(
                report_date=parsed.strftime("%Y-%m-%d"),
                kind=kind,
                source=path,
                relative_target=Path("reports") / year / month / day / f"{kind}.html",
            )
        )
    return sorted(reports, key=lambda item: (item.report_date, item.kind), reverse=True)


def _safe_reset(output: Path) -> None:
    resolved = output.resolve()
    if resolved.name != "public" or resolved.parent == resolved:
        raise ValueError("Pages output must be an explicitly named public directory")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True)


def _placeholder(kind: str) -> str:
    title = "今日晨报尚未生成" if kind == "morning" else "今日收盘复盘尚未生成"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><link rel="stylesheet" href="../assets/site.css"></head>
<body><main class="empty"><p class="eyebrow">A股 Quant Research Dashboard</p><h1>{title}</h1>
<p>系统尚未归档对应的已发布报告。稍后刷新，或返回首页查看另一类报告。</p>
<a class="button" href="../index.html">返回首页</a></main></body></html>"""


def _index(reports: list[SiteReport], updated_at: str) -> str:
    by_date: dict[str, dict[str, SiteReport]] = {}
    for report in reports:
        by_date.setdefault(report.report_date, {})[report.kind] = report
    latest_date = max(by_date) if by_date else "暂无已归档报告"
    rows: list[str] = []
    for report_date in sorted(by_date, reverse=True):
        values = by_date[report_date]
        cells = []
        for kind, label in (("morning", "盘前晨报"), ("review", "收盘复盘")):
            report = values.get(kind)
            if report:
                href = "./" + report.relative_target.as_posix()
                cells.append(f'<a class="history-link" href="{html.escape(href)}">{label}<span>查看报告</span></a>')
            else:
                cells.append(f'<span class="history-link missing">{label}<span>尚未归档</span></span>')
        rows.append(f'<section class="history-row"><time>{report_date}</time><div>{"".join(cells)}</div></section>')
    history = "".join(rows) if rows else '<div class="empty-list">尚无公开历史报告。自动任务生成报告后会在这里出现。</div>'
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark"><title>A股 Quant Research Dashboard</title>
<link rel="stylesheet" href="./assets/site.css"></head><body>
<header class="hero"><div class="shell"><p class="eyebrow">INSTITUTIONAL QUANT · ASIA/SHANGHAI · UTC+8</p>
<h1>A股 Quant Research Dashboard</h1><p class="lede">盘前预测、收盘验证与模型治理的统一研究门户</p>
<dl><div><dt>最新交易日</dt><dd>{latest_date}</dd></div><div><dt>最后更新</dt><dd>{updated_at} CST</dd></div></dl></div></header>
<main class="shell"><section><h2>今日研究</h2><div class="cards">
<a class="card morning" href="./latest/morning.html"><span>08:00 · PREOPEN</span><strong>盘前晨报</strong><small>市场事实、Quant Forecast 与风险边界</small></a>
<a class="card review" href="./latest/review.html"><span>20:00 · VALIDATION</span><strong>收盘复盘</strong><small>预测评价、模型健康与次日交接</small></a>
</div></section><section><h2>历史报告</h2><div class="history">{history}</div></section></main>
<footer><div class="shell"><strong>System</strong><span>GitHub Actions automated research pipeline</span><span>上涨 <b class="up">红</b> · 下跌 <b class="down">绿</b></span></div></footer>
</body></html>"""


CSS = """
:root{color-scheme:dark;--bg:#07111f;--panel:#0d1c2f;--line:#243a54;--text:#edf4fc;--muted:#93a8bf;--accent:#5eb8ff;--up:#ef4444;--down:#22c55e}
*{box-sizing:border-box}html,body{max-width:100%;overflow-x:hidden}body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,"Segoe UI","Microsoft YaHei",sans-serif;line-height:1.6}.shell{width:calc(100% - 32px);max-width:1100px;margin:auto;min-width:0}
.hero{padding:68px 0 42px;background:radial-gradient(circle at 75% 5%,#123b5d 0,transparent 42%),linear-gradient(150deg,#0a1a2d,#07111f);border-bottom:1px solid var(--line)}.eyebrow{color:var(--accent);font-size:.76rem;letter-spacing:.13em;font-weight:700}.hero h1{max-width:100%;overflow-wrap:anywhere;font-size:clamp(2rem,5vw,3.8rem);line-height:1.08;margin:.25em 0}.lede{color:var(--muted);font-size:1.08rem}.hero dl{display:flex;gap:42px;margin:32px 0 0}.hero dl div{display:grid}.hero dt{color:var(--muted);font-size:.8rem}.hero dd{margin:0;font-weight:650}
main{padding:42px 0 70px}h2{font-size:1.15rem;margin:0 0 18px}.cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-bottom:48px}.card{min-width:0;display:grid;gap:8px;padding:24px;border:1px solid var(--line);border-radius:16px;background:linear-gradient(145deg,#11253c,#0b192a);color:var(--text);text-decoration:none;transition:transform .15s,border-color .15s}.card:hover{transform:translateY(-2px);border-color:var(--accent)}.card span,.card small{color:var(--muted)}.card strong{font-size:1.5rem}.history{border-top:1px solid var(--line)}.history-row{min-width:0;display:grid;grid-template-columns:150px minmax(0,1fr);gap:20px;padding:16px 0;border-bottom:1px solid var(--line)}.history-row time{font-variant-numeric:tabular-nums;font-weight:700}.history-row>div{min-width:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.history-link{min-width:0;display:flex;justify-content:space-between;gap:10px;padding:10px 14px;border-radius:9px;background:var(--panel);color:var(--text);text-decoration:none}.history-link span{color:var(--muted);font-size:.86rem}.history-link.missing{opacity:.55}.empty-list{padding:30px;color:var(--muted)}footer{border-top:1px solid var(--line);color:var(--muted);padding:24px 0}footer .shell{display:flex;gap:18px;flex-wrap:wrap}.up{color:var(--up)}.down{color:var(--down)}.empty{width:calc(100% - 32px);max-width:650px;margin:18vh auto;padding:32px;border:1px solid var(--line);border-radius:16px;background:var(--panel)}.button{display:inline-block;margin-top:14px;padding:10px 16px;border-radius:8px;background:#176aa0;color:#fff;text-decoration:none}
@media(max-width:680px){.hero{padding-top:42px}.hero h1{font-size:clamp(1.75rem,8vw,2.2rem)}.hero dl{display:grid;gap:12px}.cards{grid-template-columns:minmax(0,1fr)}.history-row{grid-template-columns:minmax(0,1fr)}.history-row>div{grid-template-columns:minmax(0,1fr)}main{padding-top:30px}}
""".strip()


def build_site(source: Path, output: Path, now: datetime | None = None) -> list[SiteReport]:
    reports = discover_site_reports(source)
    _safe_reset(output)
    (output / "assets").mkdir()
    (output / "assets" / "site.css").write_text(CSS, encoding="utf-8")
    (output / ".nojekyll").write_text("", encoding="utf-8")
    for report in reports:
        target = output / report.relative_target
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(report.source, target)
    latest_dir = output / "latest"
    latest_dir.mkdir()
    for kind in ("morning", "review"):
        matches = [report for report in reports if report.kind == kind]
        if matches:
            shutil.copyfile(matches[0].source, latest_dir / f"{kind}.html")
        else:
            (latest_dir / f"{kind}.html").write_text(_placeholder(kind), encoding="utf-8")
    current = now or datetime.now(CST)
    updated_at = current.astimezone(CST).strftime("%Y-%m-%d %H:%M")
    (output / "index.html").write_text(_index(reports, updated_at), encoding="utf-8")
    validate_site_links(output)
    return reports


def validate_site_links(output: Path) -> None:
    root = output.resolve()
    for page in output.rglob("*.html"):
        parser = _LinkCollector()
        parser.feed(page.read_text(encoding="utf-8-sig"))
        for link in parser.links:
            parsed = urlsplit(link)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            if parsed.path.startswith("/"):
                raise ValueError(f"Project Pages link must be relative: {page}: {link}")
            target = (page.parent / unquote(parsed.path)).resolve()
            if target != root and root not in target.parents:
                raise ValueError(f"link escapes Pages root: {page}: {link}")
            if not target.exists():
                raise ValueError(f"broken local Pages link: {page}: {link}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the static GitHub Pages report portal.")
    parser.add_argument("--source", type=Path, default=Path("published-reports"))
    parser.add_argument("--output", type=Path, default=Path("public"))
    args = parser.parse_args()
    reports = build_site(args.source, args.output)
    required = (args.output / "index.html", args.output / ".nojekyll", args.output / "latest" / "morning.html", args.output / "latest" / "review.html")
    if not all(path.is_file() for path in required):
        raise SystemExit("Pages integrity check failed")
    print(f"Built {len(reports)} report pages in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
