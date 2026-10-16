#!/usr/bin/env python3
"""preview.py -- timeline resolvida -> MP4 leve (540p) pra revisar em segundos.

Não é o render final: é o rascunho que a gente assiste, comenta e corrige.
Usa o proxy 1080p quando existe (decodifica bem mais rápido que o 4K) e o
encoder de hardware do Mac (VideoToolbox). Grafismos vêm de grafismos.py
(as mesmas fontes e medidas do Premiere); a legenda ainda é a de apoio (fase 2).

Uso:
  python edicao/preview.py edicao/timeline_ep03.json                # -> previews/ep03_<hora>.mp4
  python edicao/preview.py edicao/timeline_ep03.json --bloco gancho # só um bloco
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grafismos  # noqa: E402

from projeto import RAIZ, achar_clipe, configurar  # noqa: E402

FORMATOS = {"16:9": (960, 540), "9:16": (540, 960), "4:3": (720, 540)}
FPS = "24000/1001"


def fonte_do_clipe(clipe: str) -> Path:
    # corrigidos primeiro (rotação certa), depois o proxy (rápido), depois o original
    return achar_clipe(clipe, ("brutos_corrigidos", "brutos/Proxy", "brutos_proxy", "brutos"))


def arquivo_audio(caminho: str) -> Path:
    p = Path(caminho).expanduser()
    return p if p.is_absolute() else RAIZ / p


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, args)], check=True)


def trecho(item, w, h, saida, com_audio=True):
    """Um pedaço da timeline em 540p. item: {clipe|None, in, out, mudo?, espelhar?, cor?}"""
    dur = item["out"] - item["in"]
    if h > w:  # vertical: preenche o quadro e corta no centro (igual ao XML, escala que cobre a altura)
        enquadra = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
    else:
        enquadra = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
    if item.get("zoom"):  # punch-in: recorta a fonte em volta do ponto (cx, cy) antes do enquadramento
        z = item["zoom"]
        f = z["fator"]
        cw, ch = f"iw/{f}", f"ih/{f}"
        x = f"max(0\\,min(iw-iw/{f}\\,iw*{z['cx']}-iw/{2*f}))"  # vírgula escapada: separador do filtro
        y = f"max(0\\,min(ih-ih/{f}\\,ih*{z['cy']}-ih/{2*f}))"
        enquadra = f"crop={cw}:{ch}:{x}:{y}," + enquadra
    vf = (enquadra
          + ("hflip," if item.get("espelhar") else "") + f"fps={FPS},format=yuv420p")
    if item.get("clipe") is None:  # tela de cor (encerramento)
        video = ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", f"color=c={item.get('cor', 'black')}:s={w}x{h}"]
    else:
        video = ["-hwaccel", "videotoolbox", "-ss", f"{item['in']:.3f}", "-t", f"{dur:.3f}",
                 "-i", fonte_do_clipe(item["clipe"])]
    saida_v = ["-vf", vf, "-c:v", "h264_videotoolbox", "-b:v", "2500k"]
    if item.get("mudo") or item.get("clipe") is None:  # áudio em silêncio, pro concat não desalinhar
        ff(*video, "-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo", *saida_v,
           "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "128k", "-shortest", saida)
    elif com_audio:
        fade = min(0.015, dur / 4)
        ff(*video, *saida_v, "-af", f"aresample=48000,volume={item.get('volume', 1.0)},afade=t=in:d={fade},afade=t=out:st={dur - fade:.3f}:d={fade}",
           "-c:a", "aac", "-b:a", "128k", "-ac", "2", saida)
    else:
        ff(*video, *saida_v, "-an", saida)


LEGENDA_FONTE = grafismos.FONTES["texto"]


def png_texto(tx, w, h, saida):
    estilo = tx.get("estilo", "legenda")
    if estilo == "titulo":
        img = grafismos.titulo(tx["texto"], w, h, tx.get("lado", "direita"))
    elif estilo in grafismos.GERADORES:
        img = grafismos.GERADORES[estilo](w, h)
    elif estilo == "gancho":  # cartão de info no topo (ex.: nome e preço do prato), quebra de linha e margem lateral
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        f = ImageFont.truetype(str(LEGENDA_FONTE), int(h * (0.026 if h > w else 0.046)))
        linhas, atual = [], ""
        for palavra in tx["texto"].split():
            teste = (atual + " " + palavra).strip()
            if d.textbbox((0, 0), teste, font=f, stroke_width=2)[2] <= int(w * 0.70):
                atual = teste
            else:
                linhas.append(atual)
                atual = palavra
        linhas.append(atual)
        lh = int(h * 0.034 if h > w else h * 0.05)
        for i, linha in enumerate(linhas):
            bx = d.textbbox((0, 0), linha, font=f, stroke_width=2)
            d.text(((w - (bx[2] - bx[0])) // 2, int(h * 0.12) + i * lh), linha, font=f, fill="#F6CC0A",
                   stroke_width=2, stroke_fill="#5C4800")
    else:  # legenda de apoio: amarelo com contorno, rodapé, bloco com margem lateral
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        f = ImageFont.truetype(str(LEGENDA_FONTE), int(h * (0.026 if h > w else 0.046)))
        limite = int(w * 0.70)
        linhas, atual = [], ""
        for palavra in tx["texto"].split():
            teste = (atual + " " + palavra).strip()
            if d.textbbox((0, 0), teste, font=f, stroke_width=2)[2] <= limite:
                atual = teste
            else:
                linhas.append(atual)
                atual = palavra
        linhas.append(atual)
        lh = int(h * 0.034 if h > w else h * 0.05)
        y0 = int(h * 0.84) - lh * (len(linhas) - 1)
        for i, linha in enumerate(linhas):
            bx = d.textbbox((0, 0), linha, font=f, stroke_width=2)
            d.text(((w - (bx[2] - bx[0])) // 2, y0 + i * lh), linha, font=f, fill="#F6CC0A",
                   stroke_width=2, stroke_fill="#5C4800")
    img.save(saida)


ORDEM = {"titulo": 2, "legenda": 3}  # quem fica por cima


def compor_textos(itens, w, h, t_ini, t_fim, tmp, saida):
    """Um PNG por intervalo entre trocas (todas as camadas ativas compostas) -> MOV com alfa (concat)."""
    cache = {}
    for i, tx in enumerate(itens):
        p = tmp / f"tx_{i:04d}.png"
        png_texto(tx, w, h, p)
        cache[i] = Image.open(p).convert("RGBA")
    cortes = sorted({t_ini, t_fim} | {min(t_fim, max(t_ini, c["t"])) for c in itens}
                    | {min(t_fim, max(t_ini, c["t"] + c["dur"])) for c in itens})
    vazio = tmp / "vazio.png"
    Image.new("RGBA", (w, h), (0, 0, 0, 0)).save(vazio)
    linhas = []
    for k, (a, b) in enumerate(zip(cortes, cortes[1:])):
        if b - a < 1e-3:
            continue
        meio = (a + b) / 2
        ativos = sorted((i for i, c in enumerate(itens) if c["t"] <= meio < c["t"] + c["dur"]),
                        key=lambda i: ORDEM.get(itens[i].get("estilo", "legenda"), 3))
        if ativos:
            quadro = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            for i in ativos:
                quadro.alpha_composite(cache[i])
            p = tmp / f"q_{k:05d}.png"
            quadro.save(p)
        else:
            p = vazio
        linhas += [f"file '{p}'", f"duration {b - a:.4f}"]
    linhas.append(f"file '{vazio}'")  # o concat ignora a duração do último
    (tmp / "textos.txt").write_text("\n".join(linhas))
    ff("-f", "concat", "-safe", "0", "-i", tmp / "textos.txt", "-vf", f"fps={FPS},format=rgba",
       "-c:v", "qtrle", saida)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("timeline")
    ap.add_argument("--bloco", default=None)
    ap.add_argument("--sem-legenda", action="store_true")
    args = ap.parse_args()
    inicio = time.time()

    tl = json.loads(Path(args.timeline).read_text())
    configurar(tl)
    w, h = FORMATOS[tl.get("formato", "16:9")]
    t_ini, t_fim = 0.0, tl["duracao"]
    if args.bloco:
        b = next(b for b in tl["blocos"] if b["nome"] == args.bloco)
        t_ini, t_fim = b["t"], b["t"] + b["dur"]
    dentro = lambda t0, t1: t1 > t_ini + 1e-3 and t0 < t_fim - 1e-3  # noqa: E731

    tmp = Path(tempfile.mkdtemp(prefix="preview_"))
    # 1) V1: cada corte vira um arquivo, e concatena
    lista = []
    for i, c in enumerate(x for x in tl["v1"] if dentro(x["t"], x["t"] + x["out"] - x["in"])):
        p = tmp / f"v1_{i:04d}.mp4"
        trecho(c, w, h, p)
        lista.append(f"file '{p}'")
    (tmp / "lista.txt").write_text("\n".join(lista))
    base = tmp / "base.mp4"
    ff("-f", "concat", "-safe", "0", "-i", tmp / "lista.txt", "-c", "copy", base)

    # 2) sobreposições: V2 (B-roll), música, sfx, grafismos e legendas
    entradas, filtros, rotulo, audios, n = ["-i", base], [], "[0:v]", ["[0:a]"], 1

    def audio_extra(arquivo, ss, dur, t0, volume, fade_out=0.0):
        nonlocal n
        entradas.extend(["-ss", f"{ss:.3f}", "-t", f"{dur:.3f}", "-i", str(arquivo)])
        ms = int(max(0.0, t0) * 1000)
        fade = f",afade=t=out:st={max(0, dur - fade_out):.3f}:d={fade_out}" if fade_out else ""
        filtros.append(f"[{n}:a]aresample=48000,aformat=channel_layouts=stereo,volume={volume}{fade},"
                       f"adelay={ms}|{ms}[a{n}]")
        audios.append(f"[a{n}]")
        n += 1

    for i, c in enumerate(x for x in tl["v2"] if dentro(x["t"], x["t"] + x["out"] - x["in"])):
        p = tmp / f"v2_{i:03d}.mp4"
        som = c.get("som", 0.0)
        trecho(c, w, h, p, com_audio=som > 0)
        t0 = c["t"] - t_ini
        entradas += ["-itsoffset", f"{t0:.3f}", "-i", p]
        filtros.append(f"{rotulo}[{n}:v]overlay=eof_action=pass:enable='between(t,{t0:.3f},"
                       f"{t0 + c['out'] - c['in']:.3f})'[o{n}]")
        rotulo, n = f"[o{n}]", n + 1
        if som > 0:  # som ambiente por baixo da fala
            audio_extra(p, 0.0, c["out"] - c["in"], t0, som)
    for m in tl.get("musica", []):
        if dentro(m["t"], m["t"] + m["dur"]):
            corte = max(0.0, t_ini - m["t"])  # preview de bloco que começa no meio da música
            audio_extra(arquivo_audio(m["arquivo"]), m["in"] + corte, m["dur"] - corte, m["t"] - t_ini,
                        m["volume"], m.get("fade_out", 0.0))
    for s in tl.get("sfx", []):
        if dentro(s["t"], s["t"] + 0.5):
            audio_extra(arquivo_audio(s["arquivo"]), 0.0, 3.0, s["t"] - t_ini, s.get("volume", 0.6))

    camadas = [dict(tx) for tx in tl["textos"]]
    if not args.sem_legenda:
        camadas += [{"estilo": "legenda", "texto": s["texto"], "t": s["t0"], "dur": s["t1"] - s["t0"]}
                    for s in tl["legendas"]]
    visiveis = [c for c in camadas if dentro(c["t"], c["t"] + c["dur"])]
    # textos estáticos (legendas, títulos): compostos numa ÚNICA camada com alfa,
    # um quadro por intervalo -- 400 overlays separados estouram o ffmpeg num vídeo inteiro
    estaticos = [c for c in visiveis if c.get("estilo") != "arroba"]
    if estaticos:
        camada = tmp / "textos.mov"
        compor_textos(estaticos, w, h, t_ini, t_fim, tmp, camada)
        entradas += ["-i", camada]
        filtros.append(f"{rotulo}[{n}:v]overlay=eof_action=pass[o{n}]")
        rotulo, n = f"[o{n}]", n + 1
    for i, tx in enumerate(c for c in visiveis if c.get("estilo") == "arroba"):  # motion: vídeo com alfa
        t0, t1 = tx["t"] - t_ini, tx["t"] + tx["dur"] - t_ini
        p = tmp / f"arroba_{i:02d}.mov"
        grafismos.render_arroba(tx["texto"], w, h, p, dur=tx["dur"])
        entradas += ["-itsoffset", f"{t0:.3f}", "-i", p]
        filtros.append(f"{rotulo}[{n}:v]overlay=eof_action=pass:enable='between(t,{t0:.3f},{t1:.3f})'[o{n}]")
        rotulo, n = f"[o{n}]", n + 1

    destino = RAIZ / "previews"
    destino.mkdir(exist_ok=True)
    nome = Path(args.timeline).stem.replace("timeline_", "") + (f"_{args.bloco}" if args.bloco else "")
    saida = destino / f"{nome}_{time.strftime('%H%M%S')}.mp4"
    if filtros:
        mapa_audio = ["-map", "0:a", "-c:a", "copy"]
        if len(audios) > 1:
            filtros.append(f"{''.join(audios)}amix=inputs={len(audios)}:normalize=0:duration=first[amix]")
            mapa_audio = ["-map", "[amix]", "-c:a", "aac", "-b:a", "160k"]
        ff(*entradas, "-filter_complex", ";".join(filtros), "-map", "0:v" if rotulo == "[0:v]" else rotulo,
           *mapa_audio, "-c:v", "h264_videotoolbox", "-b:v", "2500k", saida)
    else:
        shutil.copy(base, saida)
    shutil.rmtree(tmp)
    print(f"{saida}  ({t_fim - t_ini:.1f}s de vídeo, render em {time.time() - inicio:.1f}s)")


if __name__ == "__main__":
    main()
