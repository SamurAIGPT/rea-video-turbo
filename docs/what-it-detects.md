# What it detects

This page lists what the code actually does. Items marked *(optional/newer)* depend on modules that may not be present in every build; run `rea-video-turbo --help` to see which commands exist.

## Always

- **Shot boundaries:** PySceneDetect content detector, falling back to one whole-video shot if it fails.
- **Per-shot frames:** first, middle and last frame, a three-frame contact sheet, and a combined `storyboard.jpg`.
- **Camera motion:** a rough estimate from comparing first and last frame (e.g. static vs. moving). It is a heuristic, not tracking.
- **Container metadata:** codec, FPS, resolution, aspect ratio, duration via FFmpeg probe.
- **Shot label:** one of `ai_video`, `live_action`, `avatar`, `cg_3d`, `code_render`, `screen_capture`, `still_motion`, `static_hold`.
  - Without a vision model the label is a heuristic from camera motion only (moving → `ai_video`, static → `still_motion`). Treat it as a starting point and review it.
  - With `--vlm` a multimodal model also returns confidence, description, framing, camera move, lighting, narrative role and a generation prompt.

## Review loop

`review` / `apply-review` / `correct` let an agent or person look at the frames and overwrite labels; reviewed shots are marked with who reviewed them. Corrections are remembered across runs.

## Optional / newer modules

- **Metadata forensics:** extra container clues such as encoder and AI-generation tags.
- **Audio:** tempo (BPM) estimate and candidate sound-effect moments.
- **Packaging:** OCR of on-screen text with SRT/ASS export.

## Not done

Voice/music/effects stem separation, speaker identification, speech transcription, lighting-rig or color-grade analysis, and Remotion project generation are **not** implemented.
