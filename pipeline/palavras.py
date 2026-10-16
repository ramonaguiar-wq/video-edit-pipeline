#!/usr/bin/env python3
"""palavras.py -- timestamps por PALAVRA de um trecho de clipe (Whisper, com cache).

Os segments do resultado_audio.json têm limites aproximados (às vezes blocos
fixos de 2s), bons pra ler mas ruins pra cortar silêncio. Aqui transcrevemos
só o trecho usado no plano, com word_timestamps, e guardamos em
cache/palavras/<clipe>_<in>_<out>.json. Tempos devolvidos são absolutos no clipe.

Uso:
  python edicao/palavras.py iPhone15001_10051520_C300 199 220
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from projeto import CFG, RAIZ, achar_clipe  # noqa: E402

CACHE = RAIZ / "cache" / "palavras"
_modelo = None


def arquivo_do_clipe(clipe: str) -> Path:
    return achar_clipe(clipe, ("brutos_corrigidos", "brutos", "brutos_proxy"))


def palavras(clipe: str, ini: float, fim: float, idioma: str = "pt"):
    CACHE.mkdir(parents=True, exist_ok=True)
    sufixo = "" if CFG["whisper_modelo"] == "large-v3-turbo" else f"_{CFG['whisper_modelo']}"
    chave = CACHE / f"{clipe}_{ini:.2f}_{fim:.2f}_{idioma}{sufixo}.json"
    if chave.exists():
        return json.loads(chave.read_text())

    global _modelo
    if _modelo is None:
        import whisper
        _modelo = whisper.load_model(CFG["whisper_modelo"], device=CFG["whisper_device"])

    with tempfile.NamedTemporaryFile(suffix=".wav") as wav:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(ini), "-to", str(fim),
                        "-i", str(arquivo_do_clipe(clipe)), "-vn", "-ac", "1", "-ar", "16000",
                        wav.name], check=True)
        res = _modelo.transcribe(wav.name, language=idioma, word_timestamps=True,
                                 condition_on_previous_text=False, fp16=False)
    out = [{"w": w["word"].strip(), "start": round(ini + w["start"], 3), "end": round(ini + w["end"], 3)}
           for s in res["segments"] for w in s.get("words", [])]
    chave.write_text(json.dumps(out, ensure_ascii=False))
    return out


if __name__ == "__main__":
    c, a, b = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
    idioma = sys.argv[4] if len(sys.argv) > 4 else "pt"
    for p in palavras(c, a, b, idioma):
        print(f"{p['start']:8.2f} {p['end']:8.2f}  {p['w']}")
