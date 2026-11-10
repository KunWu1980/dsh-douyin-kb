# Add KunWu1980/dsh-douyin-kb

| field | value |
| --- | --- |
| repo | https://github.com/KunWu1980/dsh-douyin-kb |
| category | `tools` |
| entry file | `data/plugins/KunWu1980__dsh-douyin-kb.yml` |
| diff | +1 file, no generated files touched |

Douyin (抖音) holds a lot of Chinese-language explainer video but offers no usable
transcript export. This plugin takes a share link, downloads the video, transcribes
the speech **offline** with SenseVoice (sherpa-onnx), and writes a timestamped
Markdown note into the user's Obsidian vault — so the content lands in the user's
knowledge base instead of staying trapped in a video.

It registers a left-sidebar panel in the harness UI (link box + "开始抓取" button +
usage notes), a `/douyin` slash command, and a host tool (`douyin_kb`).

## Checklist

- [x] `package.json` declares `dsh.bundle` (`./cordis.patch.yml`)
- [x] Zero npm runtime dependencies and no build step, so installing from source needs no `allowBuilds` approval
- [x] Repository is public, not archived, and carries the `dsh-plugin` topic
- [x] Entry validated with this repo's own `scripts/lib/entries.mjs` — `validateEntries(...)` returns `[]`
- [x] `description.en` and `description.zh`, both single-line
- [x] Only one file added under `data/plugins/`; the generated README is left alone
