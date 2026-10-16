#!/usr/bin/env python3
"""xml_premiere.py -- timeline resolvida -> pacote de entrega pro Premiere (acabamento).

Gera em entrega/<ep>/:
  <ep>.xml            sequência 4K 23.976 (Final Cut Pro XML, File > Import no Premiere)
                        V1 falas (originais 4K; proxy 1080 só onde o 4K se perdeu, em escala 200%)
                        V2 B-roll        V3 grafismos (PNG/MOV com alfa em 4K)
                        VB1/VB2 fundo desfocado sob V1/V2 (só com config enquadramento = encaixar_com_fundo)
                        A1 fala          A2 som ambiente do B-roll (volume já ajustado)
                        A3 música        A4 SFX
                      flip horizontal nos clipes listados em "espelhar" (filtro "Flop")
  <ep>_legendas.srt   legendas (importar como trilha de legenda e aplicar o estilo "Legenda apoio")
  grafismos/          os PNG/MOV em 4K usados na V3

Enquadramento (config do plano):
  "preencher"           clipe cobre o quadro e corta no centro (padrão; reels verticais, longform 16:9)
  "encaixar_com_fundo"  clipe cabe inteiro (scale = 100 * min(W/w, H/h)), girado se a sequência é vertical e
                        o arquivo é horizontal; onde sobra barra, o fundo é o próprio clipe ampliado e desfocado
Tamanho da sequência: config "sequencia" [W, H]; sem ela, 3840x2160, ou 1080x1920 se o formato é 9:16.

Uso:
  python edicao/xml_premiere.py edicao/timeline_ep03.json
"""
import json
import math
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grafismos  # noqa: E402

from projeto import CFG, RAIZ, configurar  # noqa: E402

W, H = 3840, 2160
TB = 24  # timebase NTSC (23.976)
_dims_cache = {}


def fr(seg):
    return int(round(seg * 24000 / 1001))


def dimensoes(p):
    """Largura e altura reais do arquivo (o celular grava vertical: 1728x3072, 2160x3840)."""
    p = Path(p)
    if p not in _dims_cache:
        out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                       "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x",
                                       str(p)]).decode().strip().splitlines()[0]
        _dims_cache[p] = tuple(int(x) for x in out.split("x")[:2])
    return _dims_cache[p]


def original(clipe):
    """(arquivo, escala) -- final usa 4K; proxy 1080 entra a 200% pra cobrir o quadro.
    Sequência vertical (9:16): escala que preenche o quadro pelo tamanho REAL do arquivo (corte central)."""
    for pasta, escala in (("brutos_corrigidos", 100), ("brutos", 100), ("brutos_proxy", 200)):
        for ext in CFG["extensoes"]:
            p = RAIZ / pasta / f"{clipe}{ext}"
            if not p.exists():
                continue
            if H > W:
                vw, vh = dimensoes(p)
                escala = round(100 * max(H / vh, W / vw), 2)
            return p.resolve(), escala
    sys.exit(f"clipe não encontrado: {clipe} (extensões {', '.join(CFG['extensoes'])})")


def rotacao(p):
    """Sequência vertical + arquivo horizontal: gira -90° (anti-horário) para ficar em pé."""
    w, h = dimensoes(p)
    return -90 if (W < H and w > h) else 0


def escalas(p):
    """(encaixe, preenchimento) em % para a sequência, já considerando a rotação."""
    w, h = dimensoes(p)
    if rotacao(p):
        w, h = h, w
    return 100 * min(W / w, H / h), 100 * max(W / w, H / h)


def audio_path(caminho):
    p = Path(caminho).expanduser()
    return p if p.is_absolute() else (RAIZ / p).resolve()


def duracao(p):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", str(p)]).decode())


def url(p):
    return "file://localhost" + quote(str(p))


class Arquivos:
    """<file> completo na 1ª vez, depois só a referência pelo id."""

    def __init__(self):
        self.ids, self.n = {}, 0

    def tag(self, p, video=True, audio=True, still=False):
        p = str(p)
        if p in self.ids:
            return f'<file id="{self.ids[p]}"/>'
        self.n += 1
        fid = self.ids[p] = f"file-{self.n}"
        dur = 86400 if still else fr(duracao(p))
        media = ""
        vw, vh = (W, H) if (still or not video or CFG["enquadramento"] == "preencher") else dimensoes(p)
        if video:
            media += f"<video><samplecharacteristics><width>{vw}</width><height>{vh}</height></samplecharacteristics></video>"
        if audio:
            media += "<audio><samplecharacteristics><depth>16</depth><samplerate>48000</samplerate></samplecharacteristics><channelcount>2</channelcount></audio>"
        return (f'<file id="{fid}"><name>{escape(Path(p).name)}</name><pathurl>{url(p)}</pathurl>'
                f"<rate><timebase>{TB}</timebase><ntsc>TRUE</ntsc></rate><duration>{dur}</duration>"
                f"<media>{media}</media></file>")


def filtro_movimento(escala, girar=0):
    rot = (f"<parameter><parameterid>rotation</parameterid><name>Rotation</name><value>{girar}</value></parameter>"
           if girar else "")
    return ("<filter><effect><name>Basic Motion</name><effectid>basic</effectid><effectcategory>motion</effectcategory>"
            "<effecttype>motion</effecttype><mediatype>video</mediatype>"
            f"<parameter><parameterid>scale</parameterid><name>Scale</name><value>{escala}</value></parameter>"
            f"{rot}</effect></filter>")


def filtro_zoom(escala, zoom):
    """Punch-in no quadro vertical: escala x fator e centro deslocado pro ponto (cx, cy) da fonte.
    Mesmo limite do preview: o quadro nunca mostra fora da fonte (sem borda preta)."""
    f = zoom["fator"]
    hf = escala / 100 * (2160 if escala < 150 else 1080) / H  # altura do clipe em alturas de quadro (1.0 = cobre)
    wf = hf * (16 / 9) * (H / W)            # largura em larguras de quadro (16:9 de fonte, quadro 9:16)
    hf, wf = hf * f, wf * f
    cx = min(max(zoom["cx"], 0.5 - (0.5 - 0.5 / wf)), 0.5 + (0.5 - 0.5 / wf))
    cy = min(max(zoom["cy"], 0.5 - (0.5 - 0.5 / hf)), 0.5 + (0.5 - 0.5 / hf))
    px, py = 0.5 - (cx - 0.5) * wf, 0.5 - (cy - 0.5) * hf
    return (f"<filter><effect><name>Basic Motion</name><effectid>basic</effectid><effectcategory>motion</effectcategory>"
            f"<effecttype>motion</effecttype><mediatype>video</mediatype>"
            f"<parameter><parameterid>scale</parameterid><name>Scale</name><value>{escala * f:.2f}</value></parameter>"
            f"<parameter><parameterid>center</parameterid><name>Center</name><value>"
            f"<horiz>{px:.4f}</horiz><vert>{py:.4f}</vert></value></parameter>"
            f"</effect></filter>")


FILTRO_BLUR = ("<filter><effect><name>Gaussian Blur</name><effectid>GaussianBlur</effectid>"
               "<effectcategory>GaussianBlur</effectcategory><effecttype>filter</effecttype><mediatype>video</mediatype>"
               "<parameter><parameterid>blurriness</parameterid><name>Blurriness</name><value>60</value></parameter>"
               "</effect></filter>")

FILTRO_FLIP = ("<filter><effect><name>Flop</name><effectid>Flop</effectid><effectcategory>Perspective</effectcategory>"
               "<effecttype>filter</effecttype><mediatype>video</mediatype></effect></filter>")


def filtro_volume(linear):
    db = 20 * math.log10(max(linear, 1e-4))
    return ("<filter><effect><name>Audio Levels</name><effectid>audiolevels</effectid><effectcategory>audiolevels</effectcategory>"
            "<effecttype>audiolevels</effecttype><mediatype>audio</mediatype>"
            f"<parameter><parameterid>level</parameterid><name>Level</name><value>{db:.2f}</value></parameter>"
            "</effect></filter>")


def clipitem(cid, nome, arq_tag, t0, t1, i0, extra="", tipo="video"):
    sourcetrack = "" if tipo == "video" else "<sourcetrack><mediatype>audio</mediatype><trackindex>1</trackindex></sourcetrack>"
    return (f'<clipitem id="{cid}"><name>{escape(nome)}</name><enabled>TRUE</enabled>'
            f"<rate><timebase>{TB}</timebase><ntsc>TRUE</ntsc></rate>"
            f"<start>{t0}</start><end>{t1}</end><in>{i0}</in><out>{i0 + (t1 - t0)}</out>"
            f"{arq_tag}{sourcetrack}{extra}</clipitem>")


def clip_video(arqs, trilhas, track, bg_track, c, t0, t1, i0, n_id):
    """Põe o clipe na trilha de vídeo conforme o enquadramento do projeto."""
    p, escala = original(c["clipe"])
    flip = FILTRO_FLIP if c.get("espelhar") else ""
    if CFG["enquadramento"] == "encaixar_com_fundo":
        if c.get("zoom"):
            print(f"  ⚠ zoom em {c['clipe']} ignorado: não existe com enquadramento encaixar_com_fundo")
        encaixe, preench = escalas(p)
        girar = rotacao(p)
        mov = filtro_movimento(round(encaixe, 2), girar) if (girar or abs(encaixe - 100) > 0.5) else ""
        trilhas[track].append(clipitem(n_id(), p.name, arqs.tag(p), t0, t1, i0, mov + flip))
        if encaixe < 99.5:  # sobra barra: fundo = mesmo clipe, ampliado e desfocado
            fundo = filtro_movimento(round(preench, 2), girar) + FILTRO_BLUR
            trilhas[bg_track].append(clipitem(n_id(), p.name, arqs.tag(p, audio=False), t0, t1, i0, fundo))
        return p
    if c.get("zoom"):
        mov = filtro_zoom(escala, c["zoom"])
    else:
        mov = filtro_movimento(escala) if escala != 100 else ""
    trilhas[track].append(clipitem(n_id(), p.name, arqs.tag(p), t0, t1, i0, mov + flip))
    return p


def srt(legendas, saida):
    def ts(s):
        ms = int(round(s * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    linhas = [f"{i}\n{ts(s['t0'])} --> {ts(s['t1'])}\n{s['texto']}\n" for i, s in enumerate(legendas, 1)]
    saida.write_text("\n".join(linhas), encoding="utf-8")


def main():
    global W, H
    caminho = Path(sys.argv[1])
    tl = json.loads(caminho.read_text())
    configurar(tl)
    if CFG["sequencia"]:
        W, H = (int(x) for x in CFG["sequencia"])
    elif tl.get("formato") == "9:16":
        W, H = 1080, 1920  # Shorts/TikTok/Reels
    ep = caminho.stem.replace("timeline_", "")
    destino = RAIZ / "entrega" / ep
    (destino / "grafismos").mkdir(parents=True, exist_ok=True)
    arqs = Arquivos()
    trilhas = {k: [] for k in ("VB1", "V1", "VB2", "V2", "V3", "A1", "A2", "A3", "A4")}
    n = 0

    def novo_id():
        nonlocal n
        n += 1
        return f"clip-{n}"

    # V1 + A1: falas (vinheta muda: só vídeo; telas pretas do encerramento ficam como vazio = preto)
    for c in tl["v1"]:
        if c["clipe"] is None:
            continue
        t0, t1, i0 = fr(c["t"]), fr(c["t"] + c["out"] - c["in"]), fr(c["in"])
        p = clip_video(arqs, trilhas, "V1", "VB1", c, t0, t1, i0, novo_id)
        if not c.get("mudo"):
            trilhas["A1"].append(clipitem(novo_id(), p.name, arqs.tag(p), t0, t1, i0,
                                           filtro_volume(c["volume"]) if "volume" in c else "", "audio"))
    # V2 + A2: B-roll e o som ambiente dele
    for c in tl["v2"]:
        t0, t1, i0 = fr(c["t"]), fr(c["t"] + c["out"] - c["in"]), fr(c["in"])
        p = clip_video(arqs, trilhas, "V2", "VB2", c, t0, t1, i0, novo_id)
        if c.get("som", 0) > 0:
            trilhas["A2"].append(clipitem(novo_id(), p.name, arqs.tag(p), t0, t1, i0, filtro_volume(c["som"]), "audio"))
    # V3: grafismos em 4K
    for i, tx in enumerate(tl["textos"]):
        estilo = tx.get("estilo")
        t0, t1 = fr(tx["t"]), fr(tx["t"] + tx["dur"])
        if estilo == "arroba":
            p = destino / "grafismos" / f"{i:02d}_arroba_{tx['texto'].strip('@')}.mov"
            if not p.exists():
                grafismos.render_arroba(tx["texto"], W, H, p, dur=tx["dur"])
            trilhas["V3"].append(clipitem(novo_id(), p.name, arqs.tag(p, audio=False), t0, t1, 0))
            continue
        if estilo == "titulo":
            img = grafismos.titulo(tx["texto"], W, H, tx.get("lado", "direita"))
            nome = f"{i:02d}_titulo_{tx['texto'].replace(chr(10), '_')}.png"
        elif estilo in grafismos.GERADORES:
            img, nome = grafismos.GERADORES[estilo](W, H), f"{i:02d}_{estilo}.png"
        elif estilo in ("gancho", "legenda"):
            import preview  # mesmo gerador de texto do preview
            nome = f"{i:02d}_{estilo}.png"
            p = destino / "grafismos" / nome
            preview.png_texto(tx, W, H, p)
            trilhas["V3"].append(clipitem(novo_id(), p.name, arqs.tag(p, audio=False, still=True), t0, t1, 0))
            continue
        else:
            continue
        p = destino / "grafismos" / nome
        img.save(p)
        trilhas["V3"].append(clipitem(novo_id(), p.name, arqs.tag(p, audio=False, still=True), t0, t1, 0))
    # A3 música, A4 SFX
    for m in tl.get("musica", []):
        p = audio_path(m["arquivo"])
        trilhas["A3"].append(clipitem(novo_id(), p.name, arqs.tag(p, video=False), fr(m["t"]), fr(m["t"] + m["dur"]),
                                      fr(m["in"]), filtro_volume(m["volume"]), "audio"))
    for s in tl.get("sfx", []):
        p = audio_path(s["arquivo"])
        dur = min(3.0, duracao(p))
        trilhas["A4"].append(clipitem(novo_id(), p.name, arqs.tag(p, video=False), fr(s["t"]), fr(s["t"] + dur), 0,
                                      filtro_volume(s.get("volume", 0.6)), "audio"))

    video = "".join(f"<track>{''.join(trilhas[k])}</track>" for k in ("VB1", "V1", "VB2", "V2", "V3") if trilhas[k] or not k.startswith("VB"))
    audio = "".join(f"<track>{''.join(trilhas[k])}</track>" for k in ("A1", "A2", "A3", "A4"))
    total = fr(tl["duracao"])
    xml = (f'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="4"><sequence id="seq-{ep}">'
           f"<name>{ep.upper()} - montagem (esteira)</name><duration>{total}</duration>"
           f"<rate><timebase>{TB}</timebase><ntsc>TRUE</ntsc></rate><media>"
           f"<video><format><samplecharacteristics><rate><timebase>{TB}</timebase><ntsc>TRUE</ntsc></rate>"
           f"<width>{W}</width><height>{H}</height><pixelaspectratio>square</pixelaspectratio></samplecharacteristics></format>{video}</video>"
           f"<audio><format><samplecharacteristics><depth>16</depth><samplerate>48000</samplerate></samplecharacteristics></format>{audio}</audio>"
           f"</media></sequence></xmeml>\n")
    (destino / f"{ep}.xml").write_text(xml, encoding="utf-8")
    srt(tl["legendas"], destino / f"{ep}_legendas.srt")
    print(f"{destino}/{ep}.xml  ({tl['duracao'] / 60:.1f} min; " +
          ", ".join(f"{k} {len(v)}" for k, v in trilhas.items()) + ")")


if __name__ == "__main__":
    main()
