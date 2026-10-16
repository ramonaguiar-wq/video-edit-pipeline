# Video Edit Pipeline

A plan-driven pipeline that turns raw clips into a fast preview and a Premiere-ready timeline. It handles the mechanical part of editing (silence trimming, cutaways, captions, titles) so the craft work can happen in Premiere.

Built for a personal video project. I edit episodes and reels from hours of raw footage, and I wanted the repetitive decisions to live in a file I can diff, not in a timeline I can't.

![Contact sheet from the demo preview](docs/contact-sheet.jpg)

*Preview frames from the bundled demo: title, captions from word-level transcription, and a cutaway anchored to the word "pauses". All material is synthetic.*

## How it works

```
 raw clips ──► plan (JSON) ──► montar.py ──► timeline ──► preview.py ──► you approve ──► xml_premiere.py
                 you edit      silence cuts,   resolved     fast mp4 +                    Final Cut XML + SRT
                 this only     word anchors    seconds      frame sheet                   for Premiere
```

- **The plan is the single source of truth.** Each block lists `falas` (clip, in, out), `cobertura` (cutaways), `textos` (titles, lower thirds) and options. I never edit the generated timeline; I change the plan and regenerate.
- **Silence trimming by profile.** `longform` only cuts long pauses and lets speech breathe. `shorts` cuts tight and fast. Cuts come from word timestamps, not from audio level alone.
- **Anchor to words, not seconds.** `"na_palavra": "pauses"` places a cutaway or title on the first time that word is spoken. If the word isn't in the transcript, the item is skipped with a warning instead of landing in the wrong place.
- **Preview before XML.** The preview renders in a fraction of the video's length. The XML takes minutes, so it only runs after the preview is approved.
- **Premiere handoff, not replacement.** Output is a Final Cut Pro XML (File > Import) plus an SRT. Grading, music and final polish stay in Premiere.

## Run the demo

Needs macOS (the demo voice uses `say`), `ffmpeg`, and Python 3.10+.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./examples/demo/make_demo.sh                       # synthetic clips + plan
VENV=$PWD/.venv ./pipeline/novo_projeto.sh demo examples/demo/brutos
cp examples/demo/plano_demo.json projects/demo/edicao/
cd projects/demo
.venv/bin/python edicao/montar.py edicao/plano_demo.json       # 16.5 s of speech -> 9.7 s, 5 cuts
.venv/bin/python edicao/preview.py edicao/timeline_demo.json   # renders in ~3 s
.venv/bin/python edicao/conferir.py previews/demo_*.mp4 0.9 2.2 4.6   # frame sheet
.venv/bin/python edicao/xml_premiere.py edicao/timeline_demo.json      # XML + SRT
```

I ran exactly this: the demo cuts 16.5 s of padded speech to 9.7 s, and the XML validates with `xmllint`.

## Plan format (excerpt)

```json
{
  "perfil": "shorts",
  "formato": "16:9",
  "config": {"whisper_modelo": "base", "whisper_device": "cpu"},
  "blocos": [{
    "nome": "demo",
    "falas": [{"clipe": "fala", "in": 0.0, "out": 16.5, "idioma": "en"}],
    "cobertura": [{"clipe": "paisagem", "in": 1.0, "na_palavra": "pauses", "dur": 2.5}],
    "textos": [{"estilo": "titulo", "texto": "PIPELINE\nDEMO", "em": 0.3, "dur": 2.5}]
  }]
}
```

Other plan fields: `zooms` (punch-in on a source window), `espelhar` (flip clips), `narracao` (voiceover), `correcoes_legenda` (fix recurring transcription errors), vertical `"formato": "9:16"`. The config table is in `pipeline/projeto.py`.

## Lessons baked into the code

- Whisper on Apple GPU (`mps`) crashes in autocast, so the default is CPU with `large-v3-turbo`. The small model garbles fast Spanish and Portuguese.
- Clip ids use the full file name, because camera counters repeat across days.
- Vertical sequences scale to fill the height. A horizontal clip in a vertical sequence is rotated, not letterboxed, unless you choose `encaixar_com_fundo` (blurred background).
- Unknown config keys print a warning instead of being silently ignored.

## Layout

| Path | Role |
|---|---|
| `pipeline/montar.py` | plan to timeline: silence cuts, word anchors, zooms |
| `pipeline/palavras.py` | word-level transcription with a disk cache |
| `pipeline/preview.py` | fast preview render |
| `pipeline/conferir.py` | frame contact sheet for review |
| `pipeline/xml_premiere.py` | timeline to Premiere XML + SRT |
| `pipeline/grafismos.py` | title and lower-third graphics as code |
| `pipeline/novo_projeto.sh` | new project folder linked to these scripts |

## Status

Personal tool, published as a case study. Code comments and plan keys are in Portuguese. macOS only. Premiere import of the zoom's `center` parameter is not verified. My own series branding (intro, end cards, fonts) is not included.

MIT license.
