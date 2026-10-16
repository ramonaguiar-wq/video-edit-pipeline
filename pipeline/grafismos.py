#!/usr/bin/env python3
"""grafismos.py -- gráficos de texto como código: título de episódio e lower third animado.

Tudo é desenhado em pixels de um quadro 4K (3840x2160) e escala proporcionalmente para o preview.

  titulo   tema do episódio em caixa alta, linhas coladas, cor de destaque. `lado` (esquerda |
           direita | centro) deixa o rosto livre. Estilo "titulo" no plano.
  arroba   lower third animado (ícone + @handle revelado da esquerda pra direita, fade na saída),
           renderizado como .mov com alfa: entra igual no preview e no Premiere. Estilo "arroba".

Fontes: as do sistema (Helvetica / Arial Bold). Troque com as variáveis de ambiente
ESTEIRA_FONTE_TEXTO e ESTEIRA_FONTE_TITULO (caminho de um .ttf/.otf).
"""
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTES = {
    "texto": Path(os.environ.get("ESTEIRA_FONTE_TEXTO", "/System/Library/Fonts/Helvetica.ttc")),
    "titulo": Path(os.environ.get("ESTEIRA_FONTE_TITULO", "/System/Library/Fonts/Supplemental/Arial Bold.ttf")),
}
DESTAQUE = (255, 111, 0, 255)   # cor do título
BRANCO = (255, 255, 255, 255)
W4K, H4K = 3840, 2160


def _fonte(nome, tam):
    return ImageFont.truetype(str(FONTES[nome]), max(1, int(tam)))


def _tela(w, h, fundo=None):
    return Image.new("RGBA", (w, h), fundo or (0, 0, 0, 0))


def titulo(texto, w, h, lado="direita"):
    """Linhas coladas, caixa alta. lado: esquerda | direita | centro."""
    k = w / W4K
    img = _tela(w, h)
    d = ImageDraw.Draw(img)
    linhas = texto.upper().split("\n")
    f = _fonte("titulo", 1045 * k)
    maior = max(_largura_apertada(d, l, f, k) for l in linhas)
    caixa = 0.86 * w           # o título nunca passa de 86% da largura (fontes largas encolhem)
    fator = min(1.0, caixa / maior) if maior else 1.0
    f = _fonte("titulo", 1045 * k * fator)
    passo = 745 * k * fator    # distância entre linhas de base (~ altura da maiúscula)
    topo = 0.17 * h            # topo da 1ª maiúscula
    cap = d.textbbox((0, 0), "H", font=f, anchor="ls")
    base = topo - cap[1]       # cap[1] é negativo (acima da base)
    margem_esq, margem_dir = 0.08 * w, 0.975 * w
    for i, linha in enumerate(linhas):
        largura = _largura_apertada(d, linha, f, k)
        if lado == "esquerda":
            x = margem_esq
        elif lado == "centro":
            x = (w - largura) / 2
        else:
            x = margem_dir - largura
        _texto_apertado(d, (x, base + i * passo), linha, f, DESTAQUE, k)
    return img


TRACKING = -60  # px em 4K: letras encostando, 


def _largura_apertada(d, texto, f, k):
    return sum(d.textlength(c, font=f) + TRACKING * k for c in texto) - TRACKING * k


def _texto_apertado(d, xy, texto, f, cor, k):
    x, y = xy
    for c in texto:
        d.text((x, y), c, font=f, fill=cor, anchor="ls")
        x += d.textlength(c, font=f) + TRACKING * k


def _ease_out(x):
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def _icone_instagram(d, x, y, lado, k):
    """Glifo minimalista: quadrado arredondado + círculo + ponto, traço fino branco."""
    tr = max(1, int(7 * k))
    d.rounded_rectangle((x, y, x + lado, y + lado), radius=lado * 0.28, outline=BRANCO, width=tr)
    r, cx, cy, p = lado * 0.22, x + lado / 2, y + lado / 2, lado * 0.06
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=BRANCO, width=tr)
    d.ellipse((x + lado * 0.74 - p, y + lado * 0.26 - p, x + lado * 0.74 + p, y + lado * 0.26 + p), fill=BRANCO)


def arroba(handle, w, h, t, dur=3.2):
    """Lower third do @ no instante t (s), alinhado à margem esquerda (x=208 em 4K), acima da legenda.
    Entra: ícone cresce e o @ é revelado da esquerda pra direita (ease-out, 0,5 s). Sai: fade 0,35 s."""
    from PIL import ImageFilter
    k = w / W4K
    entrada = _ease_out(t / 0.5)
    alfa = 1.0 - _ease_out((t - (dur - 0.35)) / 0.35)
    img = _tela(w, h)
    if alfa <= 0:
        return img
    x0, base, nominal = 208 * k, 0.775 * h, 96 * k
    icone = _tela(w, h)
    lado = nominal * (0.6 + 0.4 * entrada)
    _icone_instagram(ImageDraw.Draw(icone), x0 + (nominal - lado) / 2, base - 88 * k + (nominal - lado) / 2, lado, k)
    texto = _tela(w, h)
    dt = ImageDraw.Draw(texto)
    f, xt = _fonte("texto", 104 * k), x0 + 132 * k
    dt.text((xt, base), handle, font=f, fill=BRANCO, anchor="ls")
    largura = dt.textbbox((xt, base), handle, font=f, anchor="ls")[2] - xt
    mascara = Image.new("L", (w, h), 0)  # revela o texto da esquerda pra direita
    ImageDraw.Draw(mascara).rectangle((0, 0, int(xt + largura * entrada + 4 * k), h), fill=255)
    texto.putalpha(Image.composite(texto.getchannel("A"), mascara, mascara))
    camada = _tela(w, h)
    camada.alpha_composite(icone)
    camada.alpha_composite(texto)
    camada.putalpha(camada.getchannel("A").point(lambda v: int(v * alfa)))
    sombra = Image.new("RGBA", (w, h), (0, 0, 0, 0))  # sombra suave pra ler sobre qualquer imagem
    sombra.putalpha(camada.getchannel("A").filter(ImageFilter.GaussianBlur(10 * k)).point(lambda v: int(v * 0.55)))
    img.alpha_composite(sombra)
    img.alpha_composite(camada)
    return img


def render_arroba(handle, w, h, saida, fps=24, dur=3.2):
    """.mov com alfa (PNG em MOV): entra igual no preview e no Premiere (V3)."""
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(int(dur * fps)):
            arroba(handle, w, h, i / fps, dur).save(f"{tmp}/f_{i:04d}.png")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(fps), "-i", f"{tmp}/f_%04d.png",
                        "-c:v", "png", "-pix_fmt", "rgba", str(saida)], check=True)
    return saida


GERADORES = {}  # estilos de quadro fixo sem texto próprio: {"nome": funcao(w, h) -> Image}; some projeto pode registrar os seus
