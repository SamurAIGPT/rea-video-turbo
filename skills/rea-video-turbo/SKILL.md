---
name: rea-video-turbo
description: Break a video down shot by shot (live action, AI-generated, 3D, code-rendered, screen capture), review the verdicts visually, and plan or run an AI remake. Use when the user asks to reverse-engineer, analyze or remake a video.
---

# rea-video-turbo

Requires Python ≥ 3.10, FFmpeg, and `pip install -e .` from the repo. Remake generation needs `MUAPI_API_KEY`; breakdown alone does not.

## Workflow

1. **Check memory.** Run `rea-video-turbo memory` to see saved preferences (report language, reviewer name) and past corrections. Respect them.
2. **Decompose.** `rea-video-turbo decompose VIDEO -o out/NAME` (add `--vlm` if a key is configured and the user wants model-written labels and prompts). Outputs `breakdown.json`, `VIDEO.md`, `report.html`, `storyboard.jpg`, `shots/`.
3. **Visual review.** Run `rea-video-turbo review out/NAME`, open each image listed in `review_tasks.json` (first frame, contact sheet, last frame), fill in `review_answers.json` (one `label` per shot from the allowed list, optional `note`), then `rea-video-turbo apply-review out/NAME --by <your name>`. Pay most attention to shots whose confidence is low or whose label came from the heuristic fallback.
4. **User corrections.** If the user says a verdict is wrong: `rea-video-turbo correct out/NAME --shots 3,4 --label still_motion --note "..."`.
5. **Deliver.** Summarize the production mix, point to `report.html` and `VIDEO.md`, and say which shots were reviewed by you vs. only measured.
6. **Remake (only if asked).** `plan out/NAME --model <id>`, then `remake out/NAME --dry-run`, show the user the jobs, and only run `remake out/NAME` (which spends credits) after they confirm.

## Rules

- Say plainly what was measured by tools and what was your visual judgment.
- Don't reuse other people's footage, music or likeness in a remake without the user having the rights.
