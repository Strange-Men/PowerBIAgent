"""Real Chromium geometry/visual acceptance for executive report fixtures.

The target report remains static and JavaScript-free.  This harness drives an
installed Chrome/Edge process through the browser's DevTools protocol, records
DOM geometry for 18 scenarios at four viewports, and captures a bounded set of
full-page screenshots in an explicitly supplied automation-owned directory.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

import websockets

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.manual_smoke.executive_report_visual_smoke import SCENARIO_NAMES


VIEWPORTS = ((1440, 1080), (1024, 900), (768, 900), (430, 900))
SCREENSHOT_CASES = frozenset({
    ("full", 1440), ("full", 1024), ("full", 768), ("full", 430),
    ("points_18", 1440),
    ("points_60", 1440), ("points_60", 430),
    ("multiple_filters", 430), ("unknown_freshness", 430),
    ("long_product", 430), ("long_customer", 430),
    ("category_gt_8", 430),
})


def _browser_path() -> Path:
    candidates = (
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("installed Chromium browser not found")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_page(port: int, timeout_seconds: float = 15.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    endpoint = f"http://127.0.0.1:{port}/json/list"
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(endpoint, timeout=1) as response:
                targets = json.load(response)
            pages = [item for item in targets if item.get("type") == "page"]
            if pages and pages[0].get("webSocketDebuggerUrl"):
                return pages[0]
        except Exception as exc:
            last_error = exc
        time.sleep(0.1)
    raise RuntimeError(f"browser DevTools endpoint unavailable: {last_error}")


class _CDP:
    def __init__(self, websocket) -> None:
        self.websocket = websocket
        self.identifier = 0

    async def call(self, method: str, params: dict[str, object] | None = None):
        self.identifier += 1
        identifier = self.identifier
        await self.websocket.send(json.dumps({
            "id": identifier,
            "method": method,
            "params": params or {},
        }))
        while True:
            response = json.loads(await self.websocket.recv())
            if response.get("id") != identifier:
                continue
            if "error" in response:
                raise RuntimeError(f"CDP {method} failed: {response['error']}")
            return response.get("result", {})


_GEOMETRY_EXPRESSION = r"""
(() => {
  const visible = (el) => {
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  };
  const nodes = [...document.querySelectorAll('body *')].filter(visible);
  const overflowNodes = nodes.filter((el) => {
    const rect = el.getBoundingClientRect();
    return rect.left < -1 || rect.right > innerWidth + 1;
  }).map((el) => ({tag: el.tagName, cls: el.className?.toString().slice(0, 90), rect: {
    left: el.getBoundingClientRect().left, right: el.getBoundingClientRect().right,
    width: el.getBoundingClientRect().width
  }})).slice(0, 20);
  const sections = [...document.querySelectorAll('[data-section]')].filter(visible).map((el) => {
    const rect = el.getBoundingClientRect();
    return {name: el.dataset.section, top: rect.top + scrollY, bottom: rect.bottom + scrollY,
      left: rect.left, right: rect.right, width: rect.width, height: rect.height};
  });
  const sectionOverlaps = sections.slice(1).filter((item, index) => item.top < sections[index].bottom - 1);
  const html = document.documentElement;
  const body = document.body;
  const svg = document.querySelector('.executive-line-chart svg');
  const svgRect = svg?.getBoundingClientRect();
  const cardRect = svg?.closest('[data-section]')?.getBoundingClientRect();
  const context = document.querySelector('[data-section="reading_context"]');
  const kpis = document.querySelector('[data-section="kpi_summary"]');
  const header = document.querySelector('.executive-header');
  const trendSection = document.querySelector('[data-section="hero_sales_trend"]');
  const audit = document.querySelector('[data-section="audit_footer"]');
  const mainText = [...document.querySelector('main').children]
    .filter((el) => el !== audit)
    .map((el) => el.innerText || '')
    .join('\n');
  const rawTokens = [
    'local_desktop:', 'local_mcp', 'remote_mcp', 'cannot_determine',
    'UNKNOWN', 'semantic_measure'
  ].filter((token) => mainText.includes(token));
  if (/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+/.test(mainText)) {
    rawTokens.push('iso_microseconds');
  }
  const rectOf = (el) => {
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    return {top: rect.top + scrollY, bottom: rect.bottom + scrollY,
      left: rect.left, right: rect.right, width: rect.width, height: rect.height};
  };
  const businessRoles = [...document.querySelectorAll('[data-business-role]')]
    .map((el) => el.dataset.businessRole);
  if (trendSection) businessRoles.push('time_trend');
  const structure = document.querySelector('[data-section="business_structure"]');
  const customer = document.querySelector('[data-section="customer_analysis"]');
  const kpiCards = [...document.querySelectorAll('.executive-kpi')];
  const customerRanks = [...document.querySelectorAll('.rank-cell')]
    .map((el) => (el.textContent || '').trim());
  const chartTypes = {
    time_trend: !!trendSection?.querySelector('.executive-line-chart'),
    region_comparison: !!document.querySelector('[data-business-role="region_comparison"] .executive-columns'),
    category_contribution: !!document.querySelector('[data-business-role="category_contribution"] .executive-donut'),
    top_products: !!document.querySelector('[data-business-role="top_products"] .executive-hbars'),
    top_customers: !!customer?.querySelector('table'),
  };
  const prohibitedCurrencyTokens = ['销售额（元）', '人民币', '¥', '￥']
    .filter((token) => mainText.includes(token));
  const kpiRects = kpiCards.map((el) => el.getBoundingClientRect());
  const structureCards = [...(structure?.querySelectorAll(':scope > .structure-grid > .visual-card') || [])];
  const structureRects = structureCards.map((el) => el.getBoundingClientRect());
  const sameRow = (rects) => rects.length > 0 && rects.every(
    (rect) => Math.abs(rect.top - rects[0].top) <= 1
  );
  const structureGrid = structure?.querySelector('.structure-grid');
  const gridTracks = structureGrid
    ? getComputedStyle(structureGrid).gridTemplateColumns.split(/\s+/).filter(Boolean).length
    : 0;
  return {
    readyState: document.readyState,
    title: document.title,
    viewport: {width: innerWidth, height: innerHeight},
    document: {scrollWidth: html.scrollWidth, clientWidth: html.clientWidth,
      bodyScrollWidth: body.scrollWidth, height: Math.max(html.scrollHeight, body.scrollHeight)},
    rootOverflow: html.scrollWidth > html.clientWidth + 1 || body.scrollWidth > innerWidth + 1,
    overflowNodes,
    sections,
    sectionOverlaps,
    contextBeforeNumbers: !!context && (!kpis || context.getBoundingClientRect().top < kpis.getBoundingClientRect().top),
    product: {
      header: rectOf(header), context: rectOf(context), kpis: rectOf(kpis),
      trendSection: rectOf(trendSection), rawTokens, businessRoles,
      layoutContract: document.querySelector('main')?.dataset.layoutContract || '',
      sectionOrder: sections.map((item) => item.name),
      structureRoles: [...(structure?.querySelectorAll('[data-business-role]') || [])]
        .map((el) => el.dataset.businessRole),
      customerSeparated: !!customer && customer.querySelectorAll('[data-business-role="top_customers"]').length === 1,
      kpiIconCount: kpiCards.filter((el) => el.querySelector('.kpi-icon svg')).length,
      kpiTones: kpiCards.map((el) => el.dataset.kpiTone),
      chartTypes,
      customerRanks,
      prohibitedCurrencyTokens,
      donutLegendCount: document.querySelectorAll('[data-business-role="category_contribution"] .executive-legend li').length,
      donutOverflowNote: document.body.innerText.includes('项未在图例展开'),
      templateGeometry: {
        kpiCount: kpiRects.length,
        kpisSameRow: sameRow(kpiRects),
        structureCardCount: structureRects.length,
        structureSameRow: sameRow(structureRects),
        structureGridTracks: gridTracks,
        structureWidthSpread: structureRects.length
          ? Math.max(...structureRects.map((rect) => rect.width)) - Math.min(...structureRects.map((rect) => rect.width))
          : 0,
        heroWidthRatio: trendSection && context
          ? trendSection.getBoundingClientRect().width / context.getBoundingClientRect().width
          : 0,
      },
      kpisInFirstViewport: !!kpis && kpis.getBoundingClientRect().bottom <= innerHeight,
      hierarchyOrdered: !!header && !!context && !!kpis && !!trendSection &&
        header.getBoundingClientRect().top < context.getBoundingClientRect().top &&
        context.getBoundingClientRect().top < kpis.getBoundingClientRect().top &&
        kpis.getBoundingClientRect().top < trendSection.getBoundingClientRect().top,
    },
    trend: svg ? {points: document.querySelectorAll('.trend-point').length,
      width: svgRect.width, cardWidth: cardRect.width,
      withinCard: svgRect.left >= cardRect.left - 1 && svgRect.right <= cardRect.right + 1,
      desktopTickLabels: document.querySelectorAll('.trend-ticks--desktop text').length,
      tabletTickLabels: document.querySelectorAll('.trend-ticks--tablet text').length,
      mobileTickLabels: document.querySelectorAll('.trend-ticks--mobile text').length} : null,
    identity: document.querySelector('main')?.dataset.templateKey || '',
    staticRuntime: !document.querySelector('script, link[rel="stylesheet"], iframe, object, embed'),
    fontFamily: getComputedStyle(body).fontFamily,
    unknownFreshnessVisible: document.body.innerText.includes('暂不可获取'),
    noFilterVisible: document.body.innerText.includes('无额外筛选'),
    exceptionVisible: document.body.innerText.includes('暂无可验证异常基准'),
  };
})()
"""


async def _ready(cdp: _CDP) -> None:
    for _ in range(100):
        result = await cdp.call("Runtime.evaluate", {
            "expression": "document.readyState",
            "returnByValue": True,
        })
        if result["result"].get("value") == "complete":
            return
        await asyncio.sleep(0.05)
    raise RuntimeError("page did not reach readyState=complete")


def _case_failures(scenario: str, width: int, geometry: dict[str, object]) -> list[str]:
    failures: list[str] = []
    if geometry["identity"] != "sales_executive_report":
        failures.append("template_identity")
    if geometry["rootOverflow"]:
        failures.append("root_horizontal_overflow")
    if geometry["overflowNodes"]:
        failures.append("visible_node_outside_viewport")
    if geometry["sectionOverlaps"]:
        failures.append("section_overlap")
    if not geometry["contextBeforeNumbers"]:
        failures.append("reading_context_not_before_numbers")
    if not geometry["staticRuntime"]:
        failures.append("non_static_runtime")
    if not geometry["exceptionVisible"]:
        failures.append("exception_state_missing")
    product = geometry.get("product") or {}
    if product.get("rawTokens"):
        failures.append("technical_tokens_in_main_visual")
    if scenario == "full" and not product.get("hierarchyOrdered"):
        failures.append("product_hierarchy_invalid")
    if scenario == "full":
        required_roles = {
            "time_trend", "category_contribution", "region_comparison",
            "top_products", "top_customers",
        }
        if not required_roles.issubset(set(product.get("businessRoles") or [])):
            failures.append("full_available_section_missing")
        if product.get("layoutContract") != "executive-12-column":
            failures.append("fixed_layout_contract_missing")
        expected_order = [
            "executive_header", "reading_context", "kpi_summary",
            "hero_sales_trend", "business_structure", "customer_analysis",
            "audit_footer",
        ]
        if product.get("sectionOrder") != expected_order:
            failures.append("fixed_section_order_invalid")
        if product.get("structureRoles") != [
            "region_comparison", "category_contribution", "top_products"
        ]:
            failures.append("fixed_structure_slots_invalid")
        if not product.get("customerSeparated"):
            failures.append("customer_section_not_separated")
        if product.get("kpiIconCount") != 4 or product.get("kpiTones") != [
            "blue", "green", "purple", "orange"
        ]:
            failures.append("fixed_kpi_slots_invalid")
        if not all((product.get("chartTypes") or {}).values()):
            failures.append("fixed_visual_mapping_invalid")
        if product.get("prohibitedCurrencyTokens"):
            failures.append("generic_currency_guessed")
        if any("." in rank or not rank.isdigit() for rank in product.get("customerRanks") or []):
            failures.append("customer_rank_not_integer")
        if width == 1440:
            template_geometry = product.get("templateGeometry") or {}
            if (
                template_geometry.get("kpiCount") != 4
                or not template_geometry.get("kpisSameRow")
            ):
                failures.append("desktop_kpi_four_column_geometry_invalid")
            if (
                template_geometry.get("structureCardCount") != 3
                or not template_geometry.get("structureSameRow")
                or template_geometry.get("structureGridTracks") != 12
                or template_geometry.get("structureWidthSpread", 999) > 2
            ):
                failures.append("desktop_structure_three_column_geometry_invalid")
            if template_geometry.get("heroWidthRatio", 0) < 0.98:
                failures.append("desktop_hero_not_full_width")
        if width == 1440:
            context = product.get("context") or {}
            trend_section = product.get("trendSection") or {}
            if context.get("height", 10_000) > 180:
                failures.append("desktop_reading_context_not_compact")
            if not product.get("kpisInFirstViewport"):
                failures.append("desktop_kpis_not_in_first_viewport")
            if (
                trend_section.get("width", 0) < 1000
                or trend_section.get("height", 0) < 400
            ):
                failures.append("desktop_trend_not_hero_visual")
    if scenario == "unknown_freshness" and not geometry["unknownFreshnessVisible"]:
        failures.append("unknown_freshness_missing")
    if scenario == "no_filter" and not geometry["noFilterVisible"]:
        failures.append("no_filter_state_missing")
    trend = geometry.get("trend")
    if scenario.startswith("points_"):
        expected = int(scenario.removeprefix("points_"))
        if trend is None or trend["points"] != expected or not trend["withinCard"]:
            failures.append("trend_geometry_or_count")
        if trend is not None and trend.get("desktopTickLabels") != min(expected, 18):
            failures.append("desktop_trend_tick_policy_invalid")
    if scenario == "category_gt_8":
        if not (product.get("chartTypes") or {}).get("category_contribution"):
            failures.append("high_cardinality_category_not_donut")
        if product.get("donutLegendCount", 99) > 8 or not product.get("donutOverflowNote"):
            failures.append("high_cardinality_donut_legend_unbounded")
    if width == 430 and geometry["document"]["clientWidth"] != 430:
        failures.append("mobile_viewport_mismatch")
    return failures


async def _run_cases(
    websocket_url: str,
    base_url: str,
    output_dir: Path,
    single_url: str | None = None,
) -> dict[str, object]:
    records: list[dict[str, object]] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    async with websockets.connect(websocket_url, max_size=16 * 1024 * 1024) as websocket:
        cdp = _CDP(websocket)
        await cdp.call("Page.enable")
        await cdp.call("Runtime.enable")
        scenario_names = ("full",) if single_url is not None else SCENARIO_NAMES
        for scenario in scenario_names:
            for width, height in VIEWPORTS:
                await cdp.call("Emulation.setDeviceMetricsOverride", {
                    "width": width,
                    "height": height,
                    "deviceScaleFactor": 1,
                    "mobile": width <= 430,
                })
                await cdp.call("Page.navigate", {
                    "url": single_url or f"{base_url}/?scenario={scenario}"
                })
                await _ready(cdp)
                evaluated = await cdp.call("Runtime.evaluate", {
                    "expression": _GEOMETRY_EXPRESSION,
                    "returnByValue": True,
                    "awaitPromise": True,
                })
                if "value" not in evaluated.get("result", {}):
                    raise RuntimeError(
                        "geometry evaluation failed: "
                        + json.dumps(evaluated, ensure_ascii=False)
                    )
                geometry = evaluated["result"]["value"]
                failures = _case_failures(scenario, width, geometry)
                record = {
                    "scenario": scenario,
                    "viewport": f"{width}x{height}",
                    "geometry": geometry,
                    "failures": failures,
                }
                records.append(record)
                if (scenario, width) in SCREENSHOT_CASES:
                    shot = await cdp.call("Page.captureScreenshot", {
                        "format": "png",
                        "captureBeyondViewport": True,
                    })
                    (output_dir / f"{scenario}-{width}.png").write_bytes(
                        base64.b64decode(shot["data"])
                    )
    failed = [record for record in records if record["failures"]]
    return {
        "browser_engine": "installed_chromium",
        "scenario_count": len(scenario_names),
        "viewport_count": len(VIEWPORTS),
        "case_count": len(records),
        "failed_count": len(failed),
        "failed": failed,
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8766")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--single-url")
    args = parser.parse_args()
    browser = _browser_path()
    port = _free_port()
    profile = args.output_dir / f"chromium-profile-{port}"
    profile.mkdir(parents=True, exist_ok=True)
    command = [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-first-run",
        "--no-default-browser-check",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}",
        "about:blank",
    ]
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
    )
    try:
        target = _wait_for_page(port)
        evidence = asyncio.run(_run_cases(
            str(target["webSocketDebuggerUrl"]),
            args.base_url.rstrip("/"),
            args.output_dir,
            args.single_url,
        ))
        evidence["browser_path"] = str(browser)
        evidence_path = args.output_dir / "geometry-evidence.json"
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        summary = {
            key: evidence[key]
            for key in (
                "browser_engine", "browser_path", "scenario_count",
                "viewport_count", "case_count", "failed_count",
            )
        }
        summary["output_dir"] = str(args.output_dir.resolve())
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        if evidence["failed_count"]:
            print(json.dumps(evidence["failed"], ensure_ascii=False, indent=2))
            raise SystemExit(1)
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    main()
