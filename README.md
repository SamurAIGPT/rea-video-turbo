# Muapi Video Reverse

Reverse-engineer any video shot by shot: forensic attribution (live action, AI-generated, 3D, code motion graphics, digital avatar, screen capture), sound stem decomposition, and automated AI remakes powered by **[Muapi API](https://muapi.ai)** models.

Every breakdown outputs both:
- **`VIDEO.md`**: Layered, token-efficient specification for AI agents.
- **`report.html`**: Clean, visual report with storyboards, shot tables, and remake guides.
- **`remake.mp4` & `compare.mp4`**: Automated remake assembled on the original timeline and rendered side-by-side with the reference clip.

---

## Architecture: Free Local Processing + Muapi Generative Intelligence

- **Local & Free (Zero API cost)**:
  - `ffmpeg`: Video slicing, probing, audio extraction, retiming, and side-by-side assembly.
  - `scenedetect` + `opencv`: Cut boundary detection, camera motion physics, and Ken Burns still motion.
  - `onnxruntime`: Audio stem isolation (Vocals, Music, SFX) locally on CPU/GPU.
- **Muapi API Models**:
  - **Multimodal VLM** (`/v1/chat/completions`): Reverse-engineers camera moves, lighting, style, and prompts via Gemini 2.5 Flash / GPT-4o.
  - **Video Models** (`/api/v1/{slug}`): Kling (v3.0/o1), Seedance (2.5/2.0), Wan (2.1/2.2), Veo (3/3.1), Hailuo/Minimax.
  - **Image Models**: Flux 3, Midjourney, Seedream for keyframes and character consistency.
  - **Voice & Lip-Sync**: ElevenLabs, Kokoro, OmniHuman 2.0, Kling Avatar.

---

## Quick Start

### 1. Installation
```bash
pip install -e .
```

### 2. Configure API Key
Set your `MUAPI_API_KEY`:
```bash
export MUAPI_API_KEY="your_api_key"
# On Windows PowerShell:
$env:MUAPI_API_KEY="your_api_key"
```

### 3. Decompose a Video
```bash
muapi-video-reverse decompose path/to/video.mp4 -o out/my_breakdown --vlm
```

### 4. Plan a Remake
```bash
muapi-video-reverse plan out/my_breakdown --model seedance-2.5
```

### 5. Execute Remake & Compare
```bash
# Dry run (verify prompts and model slugs without calling API):
muapi-video-reverse remake out/my_breakdown --dry-run

# Run full generation with Muapi and assemble compare.mp4:
muapi-video-reverse remake out/my_breakdown
```

---

## Commands

- `muapi-video-reverse probe <video>`: Inspect container metadata (FPS, resolution, duration).
- `muapi-video-reverse decompose <video> -o <dir>`: Full shot breakdown and report generation.
- `muapi-video-reverse plan <dir> --model <model>`: Plan remake generation units for a specific model.
- `muapi-video-reverse remake <dir>`: Execute generation jobs and build `remake.mp4` & `compare.mp4`.
- `muapi-video-reverse models`: List supported Muapi generative models.
