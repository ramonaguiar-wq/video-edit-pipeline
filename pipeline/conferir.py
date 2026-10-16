#!/usr/bin/env python3
"""conferir.py -- folha de frames de um preview (pro Claude olhar antes de mandar pro usuário).

Uso:
  python edicao/conferir.py previews/ep03_230207.mp4 1 5 9.5 12     # tempos em segundos
  python edicao/conferir.py previews/ep03_230207.mp4                 # 9 tempos espaçados
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

video = Path(sys.argv[1])
dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                     "-of", "csv=p=0", str(video)]).decode())
tempos = [float(t) for t in sys.argv[2:]] or [round(dur * (i + 0.5) / 9, 2) for i in range(9)]
fonte = ImageFont.truetype("/System/Library/Fonts/Supplemental/Futura.ttc", 28, index=2)
quadros = []
with tempfile.TemporaryDirectory() as tmp:
    for t in tempos:
        p = Path(tmp) / f"{t}.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(video), "-frames:v", "1",
                        "-vf", "scale=640:-2", str(p)], check=True)
        im = Image.open(p).convert("RGB")
        ImageDraw.Draw(im).text((8, 6), f"{t:.1f}s", font=fonte, fill="red")
        quadros.append(im)
w, h = quadros[0].size
folha = Image.new("RGB", (w * 3, h * ((len(quadros) + 2) // 3)))
for i, im in enumerate(quadros):
    folha.paste(im, ((i % 3) * w, (i // 3) * h))
saida = video.with_suffix(".folha.jpg")
folha.save(saida, quality=80)
print(saida)
