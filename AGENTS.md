# AGNES API — Agent Knowledge Base

**Generated:** 2026-07-23
**Commit:** 062b51e
**Branch:** dev

## OVERVIEW

OpenCode agent skill for AGNES API (apihub.agnes-ai.com) — generate images/videos/animations. Pure Python stdlib + Pillow + edge-tts. All source in `scripts/`.

## STRUCTURE

```
./
├── AGENTS.md              # This file
├── CONTEXT.md             # Domain glossary (agent context)
├── SKILL.md               # Skill definition — PRIMARY ENTRY POINT
├── README.md              # Chinese README
├── README.en.md           # English README
├── .gitignore
├── docs/
│   ├── adr/               # Architecture decision records
│   │   ├── 0001-image-refine-tool.md
│   │   ├── 0002-story-video-architecture.md
│   │   ├── 0003-file-organization.md
│   │   ├── 0004-runtime-dependency-paths.md
│   │   └── 0005-consolidate-skills-under-agnes-api.md
│   └── pipelines/         # Pipeline documentation
│       ├── poem-video.md
│       ├── story-video.md
│       └── today-in-history.md
├── scripts/               # ALL code (flat, no package)
│   ├── utils.py           # Shared: API key, HTTP helpers, output dirs, KeyPool
│   ├── client.py          # Unified client: AgnesClient / ImageClient / VideoClient
│   ├── t2i.py             # T2I (example, runs on import)
│   ├── i2i.py             # I2I (example, runs on import)
│   ├── compose.py         # Multi-image composition (example)
│   ├── t2i_base64.py      # T2I → Base64 output (example)
│   ├── refine.py          # Core — image refinement (i2i-based)
│   ├── refine-cli.py      # CLI for refine.py
│   ├── comic.py           # Core — comic generation (t2i+i2i+Pillow)
│   ├── comic-cli.py       # CLI for comic.py
│   ├── comic-page-layout.py # Standalone page layout + bubble tool
│   ├── poem_video.py      # Core — poem→video (t2i+edge-tts+ffmpeg)
│   ├── poem-video-cli.py  # CLI for poem_video.py
│   ├── story_video.py     # Core — story→video (extends poem_video)
│   ├── story-video-cli.py # CLI for story_video.py
│   ├── t2v.py             # T2V (example, runs on import)
│   ├── i2v.py             # I2V (example, runs on import)
│   ├── keyframes.py       # Keyframe animation (example)
│   ├── poll_video.py      # Poll video result (example)
│   ├── query_video.py     # Query task status (example)
│   ├── check_key.py       # Verify API key
│   └── pipelines/         # Composite pipeline scripts
│       ├── poem-pipeline.py
│       ├── story-pipeline.py
│       └── today-in-history-pipeline.py
├── .omo/
│   └── run-continuation/  # OpenCode run continuation state
└── LICENSE                # Apache 2.0
```

## WHERE TO LOOK

| Task | File | Notes |
|------|------|-------|
| Image generation | `scripts/t2i.py`, `scripts/i2i.py` | Example scripts, run on import |
| Image refinement | `scripts/refine.py`, `scripts/refine-cli.py` | CLI: `--input --operation` |
| Comic creation | `scripts/comic.py`, `scripts/comic-cli.py` | YAML script → panels → page |
| Page layout | `scripts/comic-page-layout.py` | Standalone bubble + grid tool |
| Poem video | `scripts/poem_video.py`, `scripts/poem-video-cli.py` | t2i+edge-tts+ffmpeg pipeline |
| Story video | `scripts/story_video.py`, `scripts/story-video-cli.py` | Extends poem_video, multi-role TTS |
| Unified client | `scripts/client.py` | AgnesClient / ImageClient / VideoClient |
| Pipeline scripts | `scripts/pipelines/*.py` | End-to-end composite pipelines |
| Pipeline docs | `docs/pipelines/*.md` | Detailed pipeline flow docs |
| Video generation | `scripts/t2v.py`, `scripts/i2v.py`, `scripts/keyframes.py` | Async API, poll for result |
| Shared utilities | `scripts/utils.py` | `get_api_key()`, `api_post()`, output dirs, KeyPool |
| Preset styles | `~/.config/agnes/refine-presets.yaml`, `comic-presets.yaml` | YAML, outside repo |
| Glossary | `CONTEXT.md` | Domain terminology |
| Skill reference | `SKILL.md` | Full API reference, CLI examples |

## CONVENTIONS

- **Python 3 stdlib first** — urllib for HTTP, no `requests` lib
- **Docstrings in Chinese**, function names in English
- **Dual entry**: `*_video.py` / `*.py` = core module; `*-cli.py` = argparse CLI wrapper
- **CLI wrappers**: `sys.path.insert(0, parent)` → import sibling → main()
- **Private API**: prefix `_` for internal functions (`_t2i`, `_get_key`)
- **Config outside repo**: `~/.config/agnes/key` + YAML preset files
- **Output**: `~/agent/media/images/`, `~/agent/media/videos/`
- **Paths config**: `~/.config/agnes/paths.yaml` — all output/tool paths via `utils._cfg()`
- **Project isolation**: `--project name` → `~/agent/media/projects/<name>/` with scene/panel/audio subdirs
- **Pipeline scripts**: `scripts/pipelines/` — self-contained checkpoint-based pipelines (not library-safe)
- **API version**: `agnes-image-2.1-flash` (image), `agnes-video-v2.0` (video)
- **No tests, no requirements.txt, no CI**

## ANTI-PATTERNS

- **`sys.path.insert(0, ...)`** — needed because no package; never add to `sys.path` in library modules meant for agent import
- **Side-effect imports** — `t2i.py`, `i2i.py`, etc. execute on import (`no __name__ guard`); never import them, only run as `python3 scripts/xxx.py`
- **Duplicate API key logic** — every module reimplements key reading instead of using `utils.get_api_key()`
- **Hardcoded ffmpeg path** — `poem_video.py` has machine-specific absolute path; use `shutil.which("ffmpeg")` if modifying

## COMMANDS

```bash
# Verify API key
python3 scripts/check_key.py

# Image refine
python3 scripts/refine-cli.py --input photo.jpg --operation "去噪并调亮"

# Comic from YAML
python3 scripts/comic-cli.py --script my-comic.yaml --preset manga

# Poem video
python3 scripts/poem-video-cli.py --script my-poem.yaml

# Story video
python3 scripts/story-video-cli.py --title "三只小猪"

# T2I example (hardcoded prompt)
python3 scripts/t2i.py

# Pipeline: poem
python3 scripts/pipelines/poem-pipeline.py

# Pipeline: story
python3 scripts/pipelines/story-pipeline.py

# Pipeline: today-in-history
python3 scripts/pipelines/today-in-history-pipeline.py
```

## NOTES

- **edge-tts** must be `pip install`ed separately; `ffmpeg` must support drawtext (macOS built-in does NOT)
- **`story_video.py` depends on `poem_video.py`** — imports `_t2i`, `_i2i`, FFMPEG consts via `sys.path.insert`
- **Example scripts** are not library-safe — they run on import, hardcode prompts, use top-level side effects
- API is **async for video** — POST → get `task_id` → poll with `poll_video.py`
- Image sizes: 1K/2K/3K/4K at ratios 1:1 / 16:9 / 9:16 / 3:4 / 4:3; video frames must satisfy `8n + 1`
