# CLI reference

Install (Python ≥ 3.10 and FFmpeg required):

```bash
git clone https://github.com/SamurAIGPT/rea-video-turbo.git
cd rea-video-turbo
pip install -e .
```

| Command | What it does |
|---|---|
| `probe VIDEO` | Print container metadata plus forensic clues (capture device, AIGC tags, C2PA, editor signature). |
| `models` | List supported generation models and limits. |
| `decompose VIDEO -o DIR [--vlm] [--stems] [--no-packaging]` | Also analyzes metadata clues, audio (BPM, sound-effect hits, speech/music segments; `--stems` needs optional `demucs`) and on-screen text/overlays/rhythm (`--no-packaging` skips; OCR needs `pip install -e ".[ocr]"`). Detect shots, save first/last frames, contact sheets and `storyboard.jpg`, label each shot, and write `breakdown.json`, `VIDEO.md`, `report.html`. |
| `summary DIR` | Print a compact conclusion and the low-confidence shots that need review. |
| `review DIR` | Write `review_tasks.json` (images and current labels per shot) and a `review_answers.json` template, for an agent or person who can look at the images. |
| `apply-review DIR [ANSWERS] [--by NAME]` | Merge answers into `breakdown.json` and regenerate the reports. Changed shots keep their `original_label`. |
| `correct DIR --shots 3,4 --label L [--note T]` | Override labels for given shots, regenerate reports, and save the correction to memory. |
| `prefs [KEY VALUE]` | Show or set preferences (`lang`, `vlm`, `reviewer`, `note`). |
| `memory` | Show saved preferences and corrections. |
| `plan DIR --model ID` | Batch shots into generation units and write `remake/jobs.json`. |
| `remake DIR [--dry-run]` | Run the generation jobs (spends credits unless `--dry-run`) and assemble `remake.mp4` and `compare.mp4`. |

Allowed labels: `ai_video`, `live_action`, `avatar`, `cg_3d`, `code_render`, `screen_capture`, `still_motion`, `static_hold`.

Memory lives in `~/.rea_video_turbo` (override with `REA_VIDEO_TURBO_HOME`).

Environment: `MUAPI_API_KEY` (generation and `--vlm`), `MUAPI_BASE_URL`, `MUAPI_VLM_MODEL`.
