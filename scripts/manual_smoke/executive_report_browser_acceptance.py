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
    trend: svg ? {points: document.querySelectorAll('.trend-point').length,
      width: svgRect.width, cardWidth: cardRect.width,
      withinCard: svgRect.left >= cardRect.left - 1 && svgRect.right <= cardRect.right + 1} : null,
    identity: document.querySelector('main')?.dataset.templateKey || '',
    staticRuntime: !document.querySelector('script, link[rel="stylesheet"], iframe, object, embed'),
    fontFamily: getComputedStyle(body).fontFamily,
    unknownFreshnessVisible: document.body.innerText.includes('数据更新时间：模型未提供'),
    noFilterVisible: document.body.innerText.includes('无额外筛选'),
    exceptionVisible: document.body.innerText.includes('当前模型未提供可验证的目标、预测或异常判断基准'),
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
    if scenario == "unknown_freshness" and not geometry["unknownFreshnessVisible"]:
        failures.append("unknown_freshness_missing")
    if scenario == "no_filter" and not geometry["noFilterVisible"]:
        failures.append("no_filter_state_missing")
    trend = geometry.get("trend")
    if scenario.startswith("points_"):
        expected = int(scenario.removeprefix("points_"))
        if trend is None or trend["points"] != expected or not trend["withinCard"]:
            failures.append("trend_geometry_or_count")
    if width == 430 and geometry["document"]["clientWidth"] != 430:
        failures.append("mobile_viewport_mismatch")
    return failures


async def _run_cases(
    websocket_url: str,
    base_url: str,
    output_dir: Path,
) -> dict[str, object]:
    records: list[dict[str, object]] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    async with websockets.connect(websocket_url, max_size=16 * 1024 * 1024) as websocket:
        cdp = _CDP(websocket)
        await cdp.call("Page.enable")
        await cdp.call("Runtime.enable")
        for scenario in SCENARIO_NAMES:
            for width, height in VIEWPORTS:
                await cdp.call("Emulation.setDeviceMetricsOverride", {
                    "width": width,
                    "height": height,
                    "deviceScaleFactor": 1,
                    "mobile": width <= 430,
                })
                await cdp.call("Page.navigate", {
                    "url": f"{base_url}/?scenario={scenario}"
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
        "scenario_count": len(SCENARIO_NAMES),
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
