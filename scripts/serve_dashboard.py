from __future__ import annotations

import argparse
import html
import json
import math
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "config" / "dashboard.yaml"
DEFAULT_SLO = REPO_ROOT / "config" / "slo.yaml"
DEFAULT_LOG = REPO_ROOT / "data" / "logs.jsonl"


def _timestamp(record: dict[str, Any]) -> datetime | None:
    value = record.get("ts")
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _records(path: Path, cutoff: datetime) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = _timestamp(record) if isinstance(record, dict) else None
        if ts is not None and ts >= cutoff:
            records.append(record)
    return records


def _percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered) / 100) - 1)
    return ordered[index]


def _number(value: float | int | None, decimals: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value:,.{decimals}f}"


def _threshold(panel: dict[str, Any]) -> tuple[str, float, str]:
    item = panel["threshold"]
    operator = "≤" if item["operator"] == "lte" else "≥"
    return str(item["aggregation"]), float(item["value"]), operator


def _bar_chart(values: list[float], unit: str) -> str:
    width, height = 600, 132
    left, top, plot_height, bar_width, gap = 4, 10, 88, 34, 14
    max_value = max(values, default=0) or 1
    bars = []
    for index, value in enumerate(values):
        bar_height = max(2, plot_height * value / max_value) if value else 2
        x = left + index * (bar_width + gap)
        y = top + plot_height - bar_height
        bars.append(
            f'<rect x="{x}" y="{y:.1f}" width="{bar_width}" '
            f'height="{bar_height:.1f}" rx="5"><title>{_number(value)} {html.escape(unit)}</title></rect>'
        )
    return (
        f'<svg class="bars" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Recent values in {html.escape(unit)}">'
        f'<line x1="0" y1="{top + plot_height}" x2="{width}" '
        f'y2="{top + plot_height}" />{"".join(bars)}'
        f'<text x="0" y="122">60m ago</text><text x="545" y="122">now</text></svg>'
    )


def _panel_html(
    panel: dict[str, Any],
    metrics: list[tuple[str, str]],
    chart: str,
    threshold_value: float | None,
) -> str:
    aggregation, configured_value, operator = _threshold(panel)
    unit = str(panel["unit"])
    threshold_text = f"{aggregation} {operator} {_number(configured_value)} {unit}"
    threshold_passed = threshold_value is None or (
        threshold_value <= configured_value
        if operator == "≤"
        else threshold_value >= configured_value
    )
    status = "Within threshold" if threshold_passed else "Outside threshold"
    status_class = "ok" if threshold_passed else "alert"
    cards = "".join(
        f'<div class="metric"><span>{html.escape(label)}</span>'
        f'<strong>{html.escape(value)}</strong></div>'
        for label, value in metrics
    )
    return (
        f'<section class="panel"><div class="panel-heading"><h2>{html.escape(panel["title"])}</h2>'
        f'<span class="status {status_class}">{status}</span></div>'
        f'<div class="metrics">{cards}</div>{chart}'
        f'<div class="threshold">Threshold: {html.escape(threshold_text)}</div></section>'
    )


def build_dashboard_html(
    config_path: Path = DEFAULT_CONFIG,
    slo_path: Path = DEFAULT_SLO,
    log_path: Path = DEFAULT_LOG,
    now: datetime | None = None,
) -> str:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))["dashboard"]
    slo = yaml.safe_load(slo_path.read_text(encoding="utf-8"))["primary_slo"]
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    minutes = int(config["time_range_minutes"])
    cutoff = current - timedelta(minutes=minutes)
    records = _records(log_path, cutoff)
    requests = [row for row in records if row.get("event") == "request_received"]
    responses = [row for row in records if row.get("event") == "response_sent"]
    failures = [row for row in records if row.get("event") == "request_failed"]
    retrieval = [row.get("tool_success") for row in records if isinstance(row.get("tool_success"), bool)]

    latencies = [float(row["latency_ms"]) for row in responses if isinstance(row.get("latency_ms"), (int, float))]
    ttft_values = [float(row["ttft_ms"]) for row in responses if isinstance(row.get("ttft_ms"), (int, float))]
    latency_p50 = _percentile(latencies, 50)
    latency_p95 = _percentile(latencies, 95)
    latency_p99 = _percentile(latencies, 99)
    ttft_p95 = _percentile(ttft_values, 95)
    error_rate = len(failures) * 100 / len(requests) if requests else 0.0
    retrieval_success = sum(value is True for value in retrieval) * 100 / len(retrieval) if retrieval else 0.0
    total_cost = sum(float(row.get("cost_usd", 0)) for row in responses)
    input_tokens = sum(int(row.get("tokens_in", 0)) for row in responses)
    output_tokens = sum(int(row.get("tokens_out", 0)) for row in responses)
    qualities = [float(row["quality_score"]) for row in responses if isinstance(row.get("quality_score"), (int, float))]
    quality_mean = sum(qualities) / len(qualities) if qualities else 0.0
    successful = sum(
        float(row.get("latency_ms", math.inf)) <= 3000 for row in responses
    )
    slo_pct = successful * 100 / len(requests) if requests else 0.0

    traffic_buckets = [0.0] * 12
    cost_buckets = [0.0] * 12
    for row in records:
        ts = _timestamp(row)
        if ts is None:
            continue
        age_minutes = max(0, int((current - ts).total_seconds() // 60))
        bucket = 11 - min(11, age_minutes // 5)
        if row.get("event") == "request_received":
            traffic_buckets[bucket] += 1 / 5
        if row.get("event") == "response_sent":
            cost_buckets[bucket] += float(row.get("cost_usd", 0))
    last_minute_rate = sum(
        1 for row in requests
        if (ts := _timestamp(row)) is not None and current - ts <= timedelta(minutes=1)
    )

    values: dict[str, tuple[list[tuple[str, str]], str, float | None]] = {
        "latency": (
            [("P50", f"{_number(latency_p50)} ms"), ("P95", f"{_number(latency_p95)} ms"),
             ("P99", f"{_number(latency_p99)} ms"), ("TTFT P95", f"{_number(ttft_p95)} ms")],
            _bar_chart(latencies[-12:], "ms"), latency_p95,
        ),
        "traffic": (
            [("Requests / 60m", str(len(requests))), ("Last minute", f"{last_minute_rate} req/min")],
            _bar_chart(traffic_buckets, "req/min"), float(last_minute_rate),
        ),
        "errors": (
            [("Error rate", f"{_number(error_rate)}%"), ("Retrieval success", f"{_number(retrieval_success)}%")],
            _bar_chart([error_rate, retrieval_success], "%"), error_rate,
        ),
        "cost": (
            [("Total cost", f"${_number(total_cost, 4)}")],
            _bar_chart(cost_buckets, "USD / 5m"), total_cost,
        ),
        "tokens": (
            [("Input", f"{input_tokens:,}"), ("Output", f"{output_tokens:,}")],
            _bar_chart([float(input_tokens), float(output_tokens)], "tokens"),
            float(input_tokens + output_tokens),
        ),
        "quality": (
            [("Mean score", _number(quality_mean, 2)), ("SLO success", f"{_number(slo_pct)}%")],
            _bar_chart(qualities[-12:], "score"), quality_mean,
        ),
    }
    panels_html = "".join(
        _panel_html(panel, *values[panel["id"]]) for panel in config["panels"]
    )
    updated = current.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    good_target = float(slo["target_percent"])
    budget = float(slo["error_budget_percent"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="{int(config['refresh_seconds'])}">
  <title>{html.escape(config['title'])}</title>
  <style>
    :root {{ color-scheme: dark; font-family: Inter, Segoe UI, sans-serif; background: #0b1120; color: #e5edf8; }}
    * {{ box-sizing: border-box; }} body {{ margin: 0; padding: 28px; }}
    header {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; margin: 0 auto 22px; max-width: 1500px; }}
    h1 {{ margin: 0 0 8px; font-size: 26px; }} .sub {{ color: #9caec5; font-size: 13px; }}
    .slo {{ min-width: 265px; border: 1px solid #293b55; border-radius: 12px; padding: 14px 18px; background: #111c2d; }}
    .slo strong {{ display: block; margin-bottom: 6px; color: #c4d7f2; }} .slo span {{ font-size: 13px; color: #9caec5; }}
    main {{ display: grid; grid-template-columns: repeat(3, minmax(260px, 1fr)); gap: 16px; max-width: 1500px; margin: auto; }}
    .panel {{ min-height: 250px; padding: 18px; background: #111c2d; border: 1px solid #253751; border-radius: 14px; box-shadow: 0 8px 28px #03081155; }}
    .panel-heading {{ display: flex; justify-content: space-between; align-items: center; gap: 8px; }}
    h2 {{ margin: 0; font-size: 16px; line-height: 1.35; }} .status {{ white-space: nowrap; font-size: 10px; border-radius: 99px; padding: 5px 8px; }}
    .ok {{ background: #123d36; color: #66e0bb; }} .alert {{ background: #4a3022; color: #ffbb80; }}
    .metrics {{ display: flex; flex-wrap: wrap; gap: 16px; margin: 22px 0 4px; }}
    .metric {{ display: flex; flex-direction: column; gap: 5px; min-width: 90px; }} .metric span {{ color: #94a8c1; font-size: 11px; }} .metric strong {{ font-size: 21px; font-weight: 650; }}
    .bars {{ display: block; width: 100%; height: 91px; margin-top: 7px; overflow: visible; }}
    .bars rect {{ fill: #51c6a2; }} .bars line {{ stroke: #344863; stroke-width: 1; }} .bars text {{ fill: #879bb4; font-size: 10px; }}
    .threshold {{ margin-top: 5px; padding-top: 9px; border-top: 1px solid #24364e; color: #91a5be; font-size: 11px; }}
    footer {{ max-width: 1500px; margin: 16px auto; color: #7489a4; font-size: 11px; }}
    @media(max-width: 1050px) {{ main {{ grid-template-columns: repeat(2, minmax(250px, 1fr)); }} }}
    @media(max-width: 650px) {{ body {{ padding: 16px; }} header {{ display: block; }} .slo {{ margin-top: 16px; }} main {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <header>
    <div><h1>{html.escape(config['title'])}</h1><div class="sub">Last {minutes} minutes · refresh {int(config['refresh_seconds'])}s · updated {updated}</div></div>
    <div class="slo"><strong>{html.escape(slo['name'])}</strong><span>Target {good_target:g}% · error budget {budget:g}% · {len(requests)} requests in window</span></div>
  </header>
  <main>{panels_html}</main>
  <footer>Source: {html.escape(str(DEFAULT_LOG.relative_to(REPO_ROOT)))} · all displayed values are aggregated from structured logs.</footer>
</body>
</html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    config_path = DEFAULT_CONFIG
    slo_path = DEFAULT_SLO
    log_path = DEFAULT_LOG

    def do_GET(self) -> None:
        if self.path not in {"/", "/dashboard"}:
            self.send_error(404)
            return
        content = build_dashboard_html(self.config_path, self.slo_path, self.log_path).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"dashboard: {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the local six-panel Day 13 dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--slo", type=Path, default=DEFAULT_SLO)
    parser.add_argument("--logs", type=Path, default=DEFAULT_LOG)
    args = parser.parse_args()
    DashboardHandler.config_path = args.config
    DashboardHandler.slo_path = args.slo
    DashboardHandler.log_path = args.logs
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"Dashboard ready at http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
