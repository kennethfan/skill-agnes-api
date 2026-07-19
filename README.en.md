# AGNES API — Agent Skill

<p align="right">
  <a href="README.md">🇨🇳 中文</a>
</p>

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

> An OpenCode agent skill for generating images and videos via the [AGNES API](https://apihub.agnes-ai.com) (Sapiens AI).
> Designed to be called by AI agents — covers text-to-image, image-to-image, video generation, comic creation, poem-to-video with TTS, and children's story animation.

---

## Features

- **Image Generation** — Text-to-Image (T2I), Image-to-Image (I2I), multi-image composition
- **Image Refinement** — I2I-based enhancement, style transfer, localized edits with preset styles
- **Comic Creation** — Panel-by-panel comic generation from YAML scripts, speech bubbles, multi-layout page assembly
- **Poem Video** — Poetry → AGNES scene images + edge-tts narration + ffmpeg composition, ink-wash vertical video
- **Story Animation** — Multi-character story videos for children (ages 3-6) with consistent character appearance
- **Video Generation** — Text-to-Video (T2V), Image-to-Video (I2V), keyframe animation (async polling)
- **Pure Python stdlib** — Uses `urllib` only, no `requests` dependency

---

## Prerequisites

1. **API Key** — Obtain from [AGNES API](https://agnes-ai.com)
2. **Python 3.10+**
3. Optional dependencies (install as needed):

```bash
pip install edge-tts          # Poem/story video (TTS voiceover)
pip install Pillow            # Comic speech bubbles / title cards
pip install PyYAML            # YAML script parsing
# ffmpeg (full build with drawtext + libfontconfig) — video composition
```

### API Key Setup

```bash
# Option 1: Config file
echo "your-api-key" > ~/.config/agnes/key

# Option 2: Environment variable
export AGNES_API_KEY="your-api-key"

# Verify
python3 scripts/check_key.py
```

---

## Directory Structure

```
├── README.md                 # This file (Chinese)
├── README.en.md              # English version
├── AGENTS.md                 # Agent knowledge base
├── SKILL.md                  # Skill definition (agent entry point)
├── CONTEXT.md                # Domain glossary
├── docs/adr/                 # Architecture Decision Records
│   ├── 0001-image-refine-tool.md
│   └── 0002-story-video-architecture.md
├── scripts/                  # All code (flat structure, no package)
│   ├── utils.py              # Shared utilities: API key, HTTP helpers, output dirs
│   ├── t2i.py                # Text-to-Image (example, runs on import)
│   ├── i2i.py                # Image-to-Image (example, runs on import)
│   ├── compose.py            # Multi-image composition (example)
│   ├── refine.py             # Core — image refinement
│   ├── refine-cli.py         # CLI wrapper
│   ├── comic.py              # Core — comic generation
│   ├── comic-cli.py          # CLI wrapper
│   ├── poem_video.py         # Core — poem-to-video
│   ├── poem-video-cli.py     # CLI wrapper
│   ├── story_video.py        # Core — story video (extends poem_video)
│   ├── story-video-cli.py    # CLI wrapper
│   ├── t2v.py                # Text-to-Video (example)
│   ├── i2v.py                # Image-to-Video (example)
│   ├── keyframes.py          # Keyframe animation (example)
│   ├── poll_video.py         # Poll video result
│   └── query_video.py        # Query task status
├── LICENSE                   # Apache 2.0
└── .gitignore
```

---

## Output Directories

| Type | Path |
|------|------|
| Images | `~/agent/media/images/` |
| Videos | `~/agent/media/videos/` |

Filename format: `agnes-<type>-<timestamp>.<ext>`

---

## Quick Start

### Verify API Key

```bash
python3 scripts/check_key.py
```

### Image Generation

```bash
# Text-to-Image
python3 scripts/t2i.py

# Image refinement
python3 scripts/refine-cli.py --input photo.jpg --operation "denoise and brighten"

# Use preset style
python3 scripts/refine-cli.py --input photo.jpg --preset ghibli
```

### Comic Creation

```bash
# List available styles
python3 scripts/comic-cli.py --list-presets

# Generate from YAML script
python3 scripts/comic-cli.py --script my-comic.yaml --preset manga
```

### Poem Video

```bash
# Generate from YAML script
python3 scripts/poem-video-cli.py --script my-poem.yaml

# Specify voice
python3 scripts/poem-video-cli.py --script my-poem.yaml --voice zh-CN-YunxiaNeural
```

### Story Animation Video

```bash
# Auto-search story → fully automatic generation
python3 scripts/story-video-cli.py --title "Three Little Pigs"

# Specify visual style
python3 scripts/story-video-cli.py --title "Three Little Pigs" --style ink-wash

# Generate from text file
python3 scripts/story-video-cli.py --textfile my-story.txt
```

### Video Generation (Async)

```bash
# Text-to-Video
python3 scripts/t2v.py

# Poll result
python3 scripts/poll_video.py <task_id>
```

---

## API Reference

| Item | Value |
|------|-------|
| Base URL | `https://apihub.agnes-ai.com` |
| Image Model | `agnes-image-2.1-flash` |
| Video Model | `agnes-video-v2.0` |
| Auth | `Authorization: Bearer <API_KEY>` |

### Image Sizes

| ratio | 1K | 2K | 3K | 4K |
|-------|-----|-----|-----|-----|
| `1:1` | 1024×1024 | 2048×2048 | 3072×3072 | 4096×4096 |
| `16:9` | 1312×736 | 2624×1472 | 3936×2208 | 5248×2944 |
| `9:16` | 736×1312 | 1472×2624 | 2208×3936 | 2944×5248 |

### Video Parameters

| Param | Description |
|-------|-------------|
| `num_frames` | Total frames, ≤ 441, must satisfy `8n + 1` |
| `frame_rate` | 1-60 fps |
| Duration ref | ~3s (81f/24fps) / ~5s (121f/24fps) / ~10s (241f/24fps) / ~18s (441f/24fps) |

---

## Advanced Usage

### As Python Modules

```python
# Image refinement
from scripts.refine import refine
path = refine("photo.jpg", "Make it Ghibli style")

# Comic generation
from scripts.comic import create_comic
path = create_comic("my-comic.yaml", preset="manga")

# Poem video
from scripts.poem_video import create_poem_video
path = create_poem_video("my-poem.yaml")

# Story video
from scripts.story_video import create_story_video
path = create_story_video("my-story.yaml")
```

### YAML Script Format

**Poem script** (`my-poem.yaml`):
```yaml
title: "静夜思"
author: "李白"
voice: "zh-CN-YunxiaNeural"  # optional
lines:
  - text: "床前明月光"
    description: "A little scholar in ancient Chinese clothing sits by his bed, moonlight streaming through the window..."
  - text: "疑是地上霜"
    description: "The moonlight on the floor looks like frost, a little scholar gazing at it curiously..."
```

**Story script** (`my-story.yaml`):
```yaml
title: "Three Little Pigs"
source: "Classic Tale"
style: "american"
scenes:
  - description: "Three little piglets saying goodbye to their mother..."
    dialogues:
      - character: "Narrator"
        text: "Once upon a time there were three little pigs..."
      - character: "Big Bad Wolf"
        text: "Little pig, little pig, let me come in!"
        voice: "zh-CN-YunjianNeural"   # optional, overrides auto-map
```

---

## Comic Presets

| Preset | Description |
|--------|-------------|
| `manga` | Black & white manga, high contrast, Japanese linework |
| `manga-color` | Colored manga, Japanese anime coloring |
| `american` | American comic style, bold lines, saturated |
| `strip-4koma` | 4-panel comic, cute & clean |
| `webtoon` | Webtoon style, mobile-friendly |
| `ink-wash` | Chinese ink-wash painting style |
| `retro-american` | Retro American comic, halftone effects |
| `minimalist` | Minimalist line-art style |

---

## Character Voice Mapping

Automatic edge-tts voice assignment for story characters (overridable in YAML):

| Character Type | Auto-assigned Voice | Example |
|----------------|-------------------|---------|
| Narrator | `zh-CN-YunxiaNeural` child-like | Narrator |
| Adult male | `zh-CN-YunjianNeural` deep | Wolf, Father, Hunter |
| Adult female | `zh-CN-XiaoxiaoNeural` gentle | Mother, Grandma |
| Animal/Kid | `zh-CN-YunxiNeural` lively | Pig, Bunny, Chick |
| Lively girl | `zh-CN-XiaoyiNeural` bright | Red Riding Hood, Sister |

---

## Error Codes

| Code | Meaning |
|------|---------|
| 400 | Invalid request parameters |
| 401 | Invalid API key |
| 404 | Task/video not found |
| 500 | Server error |
| 503 | Service busy, retry later |

---

## Architecture Decisions

- [ADR 0001: Image Refinement Tool Based on AGNES I2I](docs/adr/0001-image-refine-tool.md)
- [ADR 0002: Story Video Architecture](docs/adr/0002-story-video-architecture.md)

---

## License

[Apache License 2.0](LICENSE)
