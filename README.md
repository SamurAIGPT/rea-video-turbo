<div align="center">

# muapi-rea-video

**Reverse-engineer any video.**

Shot by shot: was it filmed, AI-generated, or coded — and how to remake it with **[Muapi API](https://muapi.ai)**.

Every breakdown is written in **[VIDEO.md](https://videomd.github.io/videomd/)**, an open format that agents and models read layer by layer.

[![Python](https://img.shields.io/badge/python-%E2%89%A53.10-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)
[![Output: VIDEO.md](https://img.shields.io/badge/output-VIDEO.md-3d4fd6)](https://videomd.github.io/videomd/)
[![Models: Muapi Unified](https://img.shields.io/badge/models-Seedance%20%7C%20Kling%20%7C%20Veo%20%7C%20Wan-8A2BE2)](https://muapi.ai)
[![Runs in](https://img.shields.io/badge/runs%20in-Claude%20Code%20%7C%20Antigravity%20%7C%20Codex-orange)](https://github.com/SamurAIGPT/muapi-rea-video)

---

### What it does in 3 steps:
1. **Deconstruct**: Scans any video to detect scene cuts, camera motion, audio stems (vocals, music, SFX), and typography.
2. **Attribution**: Multimodal AI determines if each shot was shot on a phone, generated with AI, 3D animated, or built with code.
3. **Automated Remake**: Batches the breakdown into generation units, dispatches calls to Muapi's unified API models, retimes each clip to the original cuts, and renders a side-by-side comparison video.

</div>

---

## Quick Start

### 1. Installation
Requires **Python ≥ 3.10** and **FFmpeg**:
```bash
git clone https://github.com/SamurAIGPT/muapi-rea-video.git
cd muapi-rea-video
pip install -e .
```

### 2. Configure Your Muapi API Key
One single API key connects to 500+ AI models across video, image, audio, and vision:
```bash
# On Linux / macOS:
export MUAPI_API_KEY="your_muapi_api_key"

# On Windows PowerShell:
$env:MUAPI_API_KEY="your_muapi_api_key"
```

### 3. Break Down Any Video
```bash
muapi-rea-video decompose /path/to/video.mp4 -o out/my_video
```
Outputs:
- **`report.html`**: Visual report with storyboards, shot tables, camera moves, and lighting analysis.
- **`VIDEO.md`**: Layered, token-efficient specification for AI agents.
- **`breakdown.json`**: Complete machine-readable forensics.
- **`storyboard.jpg`**: Visual contact sheet grid of all shots.

### 4. Plan the Remake
Plan generation units mapped to your model of choice:
```bash
muapi-rea-video plan out/my_video --model seedance-2.5
# Or Kling:
muapi-rea-video plan out/my_video --model kling-4.0
```

### 5. Execute & Render Side-by-Side Comparison
```bash
# Dry run (inspect prompts & model payloads with zero cost):
muapi-rea-video remake out/my_video --dry-run

# Live generation (dispatches to Muapi, downloads clips, and builds side-by-side compare):
muapi-rea-video remake out/my_video
```
Outputs:
- **`remake.mp4`**: All generated clips retimed to the original shot durations and synced with audio.
- **`compare.mp4`**: Side-by-side comparison video (**Original Video | AI Remake**).

---

## What It Can Break Down

| Video Type | Examples | What You Get |
|---|---|---|
| **Live Footage** | Tabletop product demos, talking-heads, vlogs, store visits | Camera setups, framing (close-up/medium/wide), motion physics, lighting analysis, and color grading. |
| **AI Video** | Text/image-to-video, AI short dramas, AI music videos | Evidence, reverse-engineered prompts per shot, and batching strategy for generation models. |
| **Digital Avatar** | Audio-driven portraits, lip-sync | Identifies avatar shots, character reference requirements, and audio driving tracks. |
| **3D / Animation** | Product animations, Blender/C4D explainers, 2D animation | Whether to regenerate with video models or render from 3D code. |
| **Code / Template** | Kinetic typography, UI walkthroughs, animated cards | Text, layout, and motion timing ready to rebuild as a Remotion project. |
| **Screen Recording** | Software tutorials, web demos | Separates real UI recordings you need to supply from code-renderable elements. |
| **Mixed / Edits** | AI character + code UI + real screen recording | Each shot evaluated independently and reassembled on the master timeline. |

---

## The Three Layers of Video Forensics

Every breakdown separates the video into three independent layers:

```
┌────────────────────────────────────────────────────────┐
│  3. AUDIO LAYER: Vocals (TTS/Clone) + BGM + SFX Sync   │
├────────────────────────────────────────────────────────┤
│  2. PACKAGING LAYER: Subtitles + Kinetic Text + UI     │
├────────────────────────────────────────────────────────┤
│  1. VISUAL LAYER: Shot Type (Live / AI / 3D / Code)    │
└────────────────────────────────────────────────────────┘
```

1. **Visual Layer (Bottom)**: What was captured or generated.
2. **Packaging Layer (Middle)**: Overlaid subtitles, text styling, and stickers (reproducible with Remotion or local code).
3. **Audio Layer (Top)**: Human vs. TTS voiceover, background music tempo/BPM, and sound effects synced to text/action beats.

---

## Zero-Cost Local Processing + Muapi Generative Cloud

To keep execution blazing fast and cost-efficient, standard media operations run **100% locally and free**:

- **Free & Local Infrastructure (Zero API Cost)**:
  - **`ffmpeg`**: Slicing, probing, retiming, audio stem isolation, and side-by-side `compare.mp4` rendering.
  - **`scenedetect` & `opencv`**: Frame-accurate shot boundary detection and motion tracking.
  - **Local Ken Burns Engine**: Still-image zoom/pan shots (`still_motion`) are rebuilt locally using affine warp transforms without wasting video generation credits.
  - **`remotion`**: Motion graphics and typography rendering.
- **Muapi API Models (Cloud Generative Intelligence)**:
  - **Video Models**: `seedance-2.5`, `kling-4.0`, `veo-3.1`, `wan-2.2`, `minimax-hailuo`.
  - **Image / Keyframe Models**: `flux-dev`, `flux-pro`, `midjourney`, `seedream`.
  - **Character & Lip-Sync**: `omnihuman-2.0`, `kling-avatar`, `sync-3`.
  - **Voice & Narration**: `elevenlabs-tts`, Kokoro.
  - **Multimodal VLM**: `gemini-2.5-flash`, `gpt-4o`.

---

## Supported Models Catalog

List all available models at any time with `muapi-rea-video models`:

```text
[VIDEO]
  • seedance-2.5           Seedance 2.5                     (3-30s)
  • seedance-2.0           Seedance 2.0                     (3-15s)
  • kling-v3.0-pro         Kling 3.0 Pro                    (5-10s)
  • kling-4.0              Kling 4.0 / 3.0 Omni             (5-15s)
  • veo-3.1                Veo 3.1                          (3-8s)
  • wan-2.2                Wan 2.2 / 2.1                    (3-10s)
  • minimax-hailuo         MiniMax Hailuo 2.3               (5-10s)

[IMAGE]
  • flux-dev               FLUX.1 Dev
  • flux-pro               FLUX Kontext Pro

[CHARACTER]
  • omnihuman-2.0          OmniHuman 2.0 Lip-Sync
  • kling-avatar           Kling Avatar v2

[AUDIO]
  • elevenlabs             ElevenLabs TTS

[VLM]
  • gemini-2.5-flash       Gemini 2.5 Flash Multimodal
  • gpt-4o                 GPT-4o Multimodal
```

---

## CLI Command Reference

| Command | Description |
| :--- | :--- |
| `muapi-rea-video probe <video>` | Quick inspection of video metadata (codec, FPS, resolution, duration). |
| `muapi-rea-video models` | List all supported Muapi generative models, limits, and pricing. |
| `muapi-rea-video decompose <video> -o <dir>` | Shot boundary detection, contact sheets, and forensic attribution. |
| `muapi-rea-video plan <dir> --model <model>` | Batch shots into model generation units and write `jobs.json`. |
| `muapi-rea-video remake <dir> [--dry-run]` | Execute generation tasks on Muapi and render `remake.mp4` & `compare.mp4`. |

---

## License

Apache-2.0 License. See [LICENSE](LICENSE) for details.
