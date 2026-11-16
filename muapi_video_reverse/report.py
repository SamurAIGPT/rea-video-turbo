"""Generates VIDEO.md specification and human-readable HTML reports."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def generate_reports(breakdown_data: dict[str, Any], out_dir: str | Path) -> tuple[Path, Path]:
    """Writes breakdown.json, VIDEO.md, and report.html to out_dir."""
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    json_path = out / "breakdown.json"
    json_path.write_text(json.dumps(breakdown_data, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = out / "VIDEO.md"
    html_path = out / "report.html"

    # Write VIDEO.md
    md_content = _build_video_md(breakdown_data)
    md_path.write_text(md_content, encoding="utf-8")

    # Write HTML Report
    html_content = _build_html_report(breakdown_data)
    html_path.write_text(html_content, encoding="utf-8")

    return md_path, html_path


def _build_video_md(b: dict[str, Any]) -> str:
    source = b.get("source", {})
    summary = b.get("summary", {})
    shots = b.get("shots", [])

    lines = [
        f"# VIDEO.md Breakdown: {source.get('filename', 'video.mp4')}",
        "",
        "## Summary",
        f"- **Duration**: {source.get('duration')}s",
        f"- **Resolution**: {source.get('width')}x{source.get('height')} ({source.get('aspect_ratio')})",
        f"- **FPS**: {source.get('fps')}",
        f"- **Total Shots**: {len(shots)}",
        f"- **Production Mix**: {summary.get('production_mix_str', 'N/A')}",
        "",
        "## Shot Timeline",
        "| Shot | Start | End | Duration | Type | Framing | Camera Move | Reverse-Engineered Prompt |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for s in shots:
        v = s.get("vlm", {})
        prompt = v.get("prompt", "").replace("|", "-")
        lines.append(
            f"| #{s['index']} | {s['start']}s | {s['end']}s | {s['duration']}s | "
            f"`{v.get('label', s.get('label', 'unknown'))}` | {v.get('framing', '-')} | "
            f"{v.get('camera_move', s.get('camera_motion', '-'))} | {prompt} |"
        )

    lines += [
        "",
        "## Remake Recommendations (Powered by Muapi)",
        f"- **AI Video Shots**: Generate using Muapi's `seedance-2.5-image-to-video` or `kling-v3.0-pro-text-to-video`.",
        "- **Still Shots**: Rebuilt locally via Ken Burns zoom/pan in FFmpeg.",
        "- **Audio & Voiceover**: Retain original or generate via Muapi `elevenlabs-tts`.",
    ]

    return "\n".join(lines)


def _build_html_report(b: dict[str, Any]) -> str:
    source = b.get("source", {})
    shots = b.get("shots", [])

    rows_html = []
    for s in shots:
        v = s.get("vlm", {})
        rows_html.append(f"""
        <tr>
            <td><strong>#{s['index']}</strong></td>
            <td>{s['start']}s - {s['end']}s ({s['duration']}s)</td>
            <td><span class="badge badge-{v.get('label', 'ai')}">{v.get('label', 'ai_video')}</span></td>
            <td>{v.get('framing', '-')} / {v.get('camera_move', '-')}</td>
            <td>{v.get('lighting', '-')}</td>
            <td class="prompt-cell">{v.get('prompt', '-')}</td>
        </tr>
        """)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Video Breakdown Report - {source.get('filename')}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 2rem; margin: 0; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #38bdf8; }}
        .card {{ background: #1e293b; border-radius: 8px; padding: 1.5rem; margin-bottom: 2rem; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3); }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; }}
        .stat {{ font-size: 1.5rem; font-weight: bold; color: #38bdf8; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
        th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #334155; }}
        th {{ background: #0f172a; color: #94a3b8; }}
        .badge {{ padding: 3px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: bold; }}
        .badge-ai_video {{ background: #818cf8; color: #fff; }}
        .badge-live_action {{ background: #34d399; color: #fff; }}
        .badge-still_motion {{ background: #fbbf24; color: #000; }}
        .badge-code_render {{ background: #f472b6; color: #fff; }}
        .prompt-cell {{ font-size: 0.9rem; color: #cbd5e1; font-family: monospace; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Video Reverse-Engineering Report</h1>
        <p>Source: <code>{source.get('filename')}</code></p>
        
        <div class="card">
            <h2>Overview</h2>
            <div class="grid">
                <div>Duration: <div class="stat">{source.get('duration')}s</div></div>
                <div>Resolution: <div class="stat">{source.get('width')}x{source.get('height')}</div></div>
                <div>Aspect Ratio: <div class="stat">{source.get('aspect_ratio')}</div></div>
                <div>Total Shots: <div class="stat">{len(shots)}</div></div>
            </div>
        </div>

        <div class="card">
            <h2>Shot-by-Shot Forensics & Prompts</h2>
            <table>
                <thead>
                    <tr>
                        <th>Shot</th>
                        <th>Timing</th>
                        <th>Type</th>
                        <th>Camera</th>
                        <th>Lighting</th>
                        <th>Reverse-Engineered Prompt</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(rows_html)}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>"""
