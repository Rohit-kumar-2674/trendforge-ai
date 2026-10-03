import html
import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from trendforge.config import Settings
from trendforge.db import Report
from trendforge.schemas import utcnow
from trendforge.services import DISCLAIMER, events, provider_status, trend_list


def report_mode(demo_mode: bool) -> str:
    return "MOCK/DEMO — synthetic data" if demo_mode else "Configured provider data"


def generate_report(session: Session, settings: Settings) -> Report:
    now = utcnow()
    # Archival reports must not retain expiring raw-only API data indefinitely.
    trends = [t for t in trend_list(session, settings) if t["analytics_allowed"]]
    mode = report_mode(settings.demo_mode)
    sections: dict[str, list[Any]] = {
        "Top trend scores": trends[:5],
        "Early signal watch": sorted(
            trends, key=lambda t: t["score"].get("early_signal_score", 0), reverse=True
        )[:5],
        "Fastest acceleration": sorted(
            trends, key=lambda t: t["score"].get("relative_acceleration", 0), reverse=True
        )[:5],
        "Cooling trends": [
            t
            for t in sorted(trends, key=lambda t: t["score"].get("growth_7_periods", 0))
            if t["score"].get("growth_7_periods", 0) < 0
        ][:5],
    }
    payload: dict[str, Any] = {
        "generated_at": now.isoformat(),
        "timezone": "UTC",
        "mode": mode,
        "scope": "Analytics-enabled entities only; raw-only API data is excluded from archival reports",
        "sections": sections,
        "providers": provider_status(session, settings),
        "events": events(session, settings),
        "disclaimer": DISCLAIMER,
    }
    lines = [
        "# TrendForge Intelligence Report",
        "",
        f"Generated: {now.isoformat()} (UTC)",
        "",
        f"**{mode}**",
        "",
    ]
    for name, rows in sections.items():
        lines.extend([f"## {name}", ""])
        if not rows:
            lines.append("No qualifying observations.")
        for t in rows:
            score = t["score"]
            lines.append(
                f"- {t['name']}: score {score.get('current_score', 'unavailable')}; {score.get('lifecycle_stage', 'raw statistics')}; 7-period change {score.get('growth_7_periods', 'unavailable')}%; data {t['freshness']['status']}; observed {t['last_updated']}."
            )
            if t["forecast"]:
                f = t["forecast"]
                lines.append(
                    f"  Forecast: {f['horizon']} {f['horizon_unit']}; up {f['probabilities']['up']:.1%}, sideways {f['probabilities']['sideways']:.1%}, down {f['probabilities']['down']:.1%}; confidence {f['confidence']}; {f['analogue_count']} analogues. Estimates may be wrong."
                )
        lines.append("")
    lines.extend(["## Provider freshness", ""])
    lines.extend(
        f"- {p['name']}: {p['status']}; last successful retrieval {p['last_success'] or 'never'}."
        for p in payload["providers"]
    )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "No supported live fashion/search/news provider is enabled by default. No fabricated headlines or causal explanations are supplied.",
            "",
            DISCLAIMER,
        ]
    )
    markdown = "\n".join(lines)
    document = f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TrendForge report</title><style>body{{background:#0b0e10;color:#e7edef;font:16px/1.7 system-ui;max-width:960px;margin:auto;padding:36px}}pre{{white-space:pre-wrap;font:inherit}}h1{{color:#c4f66b}}a{{color:#65d6d4}}</style><h1>TrendForge • Daily Intelligence</h1><pre>{html.escape(markdown)}</pre></html>'
    report = Report(
        id=str(uuid.uuid4()), mode=mode, payload=payload, markdown=markdown, html=document
    )
    session.add(report)
    session.commit()
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    stem = f"trendforge-{now.strftime('%Y-%m-%dT%H%M%S')}-{report.id[:8]}"
    for suffix, content in [
        ("md", markdown),
        ("json", json.dumps(payload, indent=2)),
        ("html", document),
    ]:
        (settings.reports_dir / f"{stem}.{suffix}").write_text(content, encoding="utf-8")
    return report
