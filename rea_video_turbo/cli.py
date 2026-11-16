"""CLI entrypoint for rea-video-turbo."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .detector import detect_shots, probe_video
from .models_catalog import MODELS, resolve_model
from .planner import plan_remake
from .remake import assemble_remake, execute_remake
from .report import generate_reports
from .vlm import MuapiVLM


def cmd_probe(args: argparse.Namespace) -> int:
    meta = probe_video(args.video)
    print(json.dumps(meta, indent=2))
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    print(f"Muapi Supported Models (rea-video-turbo v{__version__}):\n")
    for cat in ("video", "image", "character", "audio", "vlm"):
        print(f"[{cat.upper()}]")
        for k, v in MODELS.items():
            if v.get("category") == cat:
                name = v.get("name", k)
                limits = v.get("limits") or {}
                lim_str = f"({limits.get('duration_min', 0)}-{limits.get('duration_max', 0)}s)" if limits else ""
                print(f"  • {k:22s} {name:32s} {lim_str}")
        print()
    return 0


def cmd_decompose(args: argparse.Namespace) -> int:
    video_path = Path(args.video).resolve()
    if not video_path.is_file():
        print(f"Error: Video file not found: {video_path}", file=sys.stderr)
        return 1

    out_dir = Path(args.out or f"out/{video_path.stem}").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"1. Probing metadata for {video_path.name}...")
    meta = probe_video(video_path)
    print(f"   Duration: {meta['duration']}s | Resolution: {meta['width']}x{meta['height']} ({meta['aspect_ratio']}) | FPS: {meta['fps']}")

    print(f"2. Detecting shots and generating keyframe contact sheets...")
    shots = detect_shots(video_path, out_dir)
    print(f"   Detected {len(shots)} shot(s). Storyboard saved to {out_dir / 'storyboard.jpg'}")

    # VLM Analysis
    vlm = MuapiVLM(api_key=args.api_key, model=args.vlm_model)
    use_vlm = args.vlm and not args.no_vlm and (vlm.is_configured or args.dry_run)
    print(f"3. Forensic Analysis ({'Muapi VLM: ' + vlm.model if use_vlm else 'Deterministic Heuristics'})...")

    type_counts: dict[str, int] = {}
    for idx, sh in enumerate(shots, 1):
        if use_vlm and not args.dry_run:
            first_frame = sh.get("first_frame")
            analysis = vlm.analyze_shot(first_frame, shot_meta=sh)
        else:
            analysis = vlm._heuristic_fallback(sh)

        sh["vlm"] = analysis
        lbl = analysis.get("label", "ai_video")
        type_counts[lbl] = type_counts.get(lbl, 0) + 1
        print(f"   Shot #{idx} ({sh['duration']}s): {lbl.upper():14s} - Move: {analysis.get('camera_move', '-')}")

    mix_str = ", ".join(f"{k}: {v}" for k, v in type_counts.items())
    breakdown_data = {
        "source": meta,
        "summary": {
            "total_shots": len(shots),
            "production_mix": type_counts,
            "production_mix_str": mix_str,
            "vlm_model": vlm.model if use_vlm else "heuristic",
        },
        "shots": shots,
    }

    print("4. Writing specifications and reports...")
    md_path, html_path = generate_reports(breakdown_data, out_dir)
    print(f"   VIDEO.md:   {md_path}")
    print(f"   Report:     {html_path}")
    print(f"   Breakdown:  {out_dir / 'breakdown.json'}")

    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    out_dir = Path(args.dir).resolve()
    b_file = out_dir / "breakdown.json" if (out_dir / "breakdown.json").is_file() else out_dir

    print(f"Planning remake using Muapi model: {args.model}...")
    jobs_file = plan_remake(b_file, model_name=args.model)
    print(f"Remake jobs written to: {jobs_file}")

    data = json.loads(jobs_file.read_text(encoding="utf-8"))
    print(f"Generated {len(data.get('jobs', []))} generation unit(s):")
    for j in data.get("jobs", []):
        shots_str = ",".join(str(s) for s in j.get("shots", []))
        print(f"  • Job '{j['id']}': Shots [{shots_str}] ({j.get('duration')}s) -> {j.get('model_slug', j.get('executor'))}")

    return 0


def cmd_remake(args: argparse.Namespace) -> int:
    target = Path(args.target).resolve()
    if target.is_dir():
        jobs_file = target / "remake" / "jobs.json"
        breakdown_file = target / "breakdown.json"
    else:
        jobs_file = target
        breakdown_file = target.parent.parent / "breakdown.json"

    if not jobs_file.is_file():
        print(f"Error: jobs.json not found at {jobs_file}. Run 'plan' first.", file=sys.stderr)
        return 1

    print(f"Executing remake for: {jobs_file.name} (Dry-run: {args.dry_run})...")
    results = execute_remake(jobs_file, dry_run=args.dry_run)

    if not args.dry_run:
        results_file = jobs_file.with_name("results.json")
        print("\nAssembling final remake video & side-by-side comparison...")
        remake_mp4, compare_mp4 = assemble_remake(breakdown_file, results_file)
        print(f"Done! Remake video:   {remake_mp4}")
        print(f"Side-by-side compare: {compare_mp4}")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rea-video-turbo",
        description="Reverse-engineer videos and execute AI remakes with Muapi API models.",
    )
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # probe
    p_probe = sub.add_parser("probe", help="Probe video metadata.")
    p_probe.add_argument("video", help="Path to video file")
    p_probe.set_defaults(func=cmd_probe)

    # models
    p_models = sub.add_parser("models", help="List supported Muapi models.")
    p_models.set_defaults(func=cmd_models)

    # decompose
    p_dec = sub.add_parser("decompose", help="Reverse-engineer and break down a video.")
    p_dec.add_argument("video", help="Path to reference video file")
    p_dec.add_argument("-o", "--out", help="Output directory")
    p_dec.add_argument("--vlm", action="store_true", default=True, help="Enable Muapi VLM analysis (default: true)")
    p_dec.add_argument("--no-vlm", action="store_true", help="Disable VLM and use local heuristics")
    p_dec.add_argument("--vlm-model", default="gemini-2.5-flash", help="VLM model ID on Muapi (default: gemini-2.5-flash)")
    p_dec.add_argument("--dry-run", action="store_true", help="Skip external API calls")
    p_dec.add_argument("--api-key", default="", help="Muapi API key")
    p_dec.set_defaults(func=cmd_decompose)

    # plan
    p_plan = sub.add_parser("plan", help="Plan generation units for a video remake.")
    p_plan.add_argument("dir", help="Breakdown directory or breakdown.json file")
    p_plan.add_argument("--model", default="seedance-2.5", help="Target Muapi model (default: seedance-2.5)")
    p_plan.set_defaults(func=cmd_plan)

    # remake
    p_remake = sub.add_parser("remake", help="Execute remake generation and assemble final video.")
    p_remake.add_argument("target", help="Breakdown directory or jobs.json file")
    p_remake.add_argument("--dry-run", action="store_true", help="Print task payloads without calling API")
    p_remake.set_defaults(func=cmd_remake)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
