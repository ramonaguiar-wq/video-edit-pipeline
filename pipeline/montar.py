#!/usr/bin/env python3
"""montar.py -- plano de edição (o que a gente decide) -> timeline resolvida (o que renderiza).

O plano é a fonte única da edição. Dele saem o preview rápido (preview.py) e,
depois, o XML do Premiere. Aqui só se resolve tempo:

  - cada fala {clipe, in, out} vira um ou mais cortes na V1, tirando os
    silêncios entre palavras (palavras.py) maiores que `silencio.gap`;
  - coberturas (B-roll, só vídeo) e textos são posicionados em segundos
    relativos ao início do bloco JÁ cortado (`em`), ou ancorados numa palavra
    (`na_palavra`: primeira ocorrência dentro do bloco);
  - legendas saem das palavras mantidas, em grupos curtos.

Uso:
  python edicao/montar.py edicao/plano_ep03.json            # -> edicao/timeline_ep03.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from palavras import palavras  # noqa: E402
from projeto import configurar  # noqa: E402

# longform (YouTube) deixa a fala respirar: só tira pausa longa. shorts corta seco e rápido.
PERFIS = {
    "longform": {"gap": 0.70, "pad_ini": 0.15, "pad_fim": 0.35},
    "shorts": {"gap": 0.30, "pad_ini": 0.06, "pad_fim": 0.12},
}


def cortes_sem_silencio(fala, cfg):
    """[(in, out, [palavras])] -- trechos contínuos de fala dentro de [in, out]."""
    ws = [w for w in palavras(fala["clipe"], fala["in"], fala["out"], fala.get("idioma", "pt"))
          if w["end"] > fala["in"] and w["start"] < fala["out"]]
    if not ws:
        return [(fala["in"], fala["out"], [])]
    grupos, atual = [], [ws[0]]
    for w in ws[1:]:
        if w["start"] - atual[-1]["end"] > cfg["gap"]:
            grupos.append(atual)
            atual = []
        atual.append(w)
    grupos.append(atual)
    out = []
    for g in grupos:
        a = max(fala["in"], g[0]["start"] - cfg["pad_ini"])
        b = min(fala["out"], g[-1]["end"] + cfg["pad_fim"])
        out.append((a, b, g))
    return out


def legendas(palavras_tl, max_chars=32, max_dur=2.4):
    """Agrupa palavras (com tempo de timeline) em legendas curtas."""
    subs, atual = [], []
    for w in palavras_tl:
        texto = " ".join(x["w"] for x in atual + [w])
        if atual and (len(texto) > max_chars or w["t1"] - atual[0]["t0"] > max_dur
                      or w["t0"] - atual[-1]["t1"] > 0.5):
            subs.append(atual)
            atual = []
        atual.append(w)
    if atual:
        subs.append(atual)
    return [{"t0": s[0]["t0"], "t1": s[-1]["t1"], "texto": " ".join(x["w"] for x in s)} for s in subs]


SFX = {}  # apelidos de efeitos sonoros: {"tecla": "caminho/efeito.wav"}; sem apelido, o plano passa o caminho


def montar(plano):
    cfg = {**PERFIS[plano.get("perfil", "longform")], **plano.get("silencio", {})}
    tl = {"formato": plano.get("formato", "16:9"), "config": dict(configurar(plano)), "v1": [], "v2": [], "textos": [], "legendas": [],
          "blocos": []}
    tl["musica"], tl["sfx"] = [], []
    t = 0.0
    for bloco in plano["blocos"]:
        ini_bloco, pals_bloco = t, []
        for fala in bloco["falas"]:
            if fala.get("ambiente"):  # respiro: imagem + som natural, sem fala nem legenda
                trechos = [(fala["in"], fala["out"], [])]
            elif fala.get("sem_corte"):
                trechos = [(fala["in"], fala["out"], palavras(fala["clipe"], fala["in"], fala["out"],
                                                             fala.get("idioma", "pt")))]
            else:
                trechos = cortes_sem_silencio(fala, cfg)
            if fala.get("sem_legenda"):  # fala ininteligível/irrelevante: imagem e som ficam, legenda não
                trechos = [(a, b, []) for a, b, _ in trechos]
            for a, b, ws in trechos:
                tl["v1"].append({"clipe": fala["clipe"], "in": round(a, 3), "out": round(b, 3),
                                 "t": round(t, 3), "bloco": bloco["nome"]})
                if "som" in fala:  # B-roll na V1 (reel de voiceover): som ambiente baixo
                    tl["v1"][-1]["volume"] = fala["som"]
                for w in ws:
                    if a <= w["start"] and w["end"] <= b + 0.01:
                        pals_bloco.append({"w": w["w"], "t0": round(t + w["start"] - a, 3),
                                           "t1": round(t + w["end"] - a, 3)})
                t += b - a
            if "legenda" in fala:  # fala em outro idioma: legenda traduzida inteira
                pals_bloco.append({"w": fala["legenda"], "t0": tl["v1"][-len(trechos)]["t"], "t1": t,
                                   "fixa": True})
        dur_bloco = t - ini_bloco

        def ancora(item):
            if "na_palavra" in item:
                alvo = item["na_palavra"].lower()
                for w in pals_bloco:
                    if alvo in w["w"].lower():
                        return w["t0"]
                print(f"  ⚠ [{bloco['nome']}] palavra '{item['na_palavra']}' não encontrada -- item pulado")
                return None
            return ini_bloco + item.get("em", 0)

        for cob in bloco.get("cobertura", []):
            t0 = ancora(cob)
            if t0 is None:
                continue
            dur = cob.get("dur", ini_bloco + dur_bloco - t0)
            tl["v2"].append({"clipe": cob["clipe"], "in": cob["in"], "out": round(cob["in"] + dur, 3),
                             "t": round(t0, 3), "bloco": bloco["nome"],
                             "som": cob.get("som", 0.0)})  # volume do som ambiente por baixo da fala
        for tx in bloco.get("textos", []):
            t0 = ancora(tx)
            if t0 is None:
                continue
            tl["textos"].append({**{k: v for k, v in tx.items() if k not in ("em", "na_palavra", "sfx")},
                                 "t": round(t0, 3), "dur": tx.get("dur", 3.0)})
            if tx.get("sfx"):  # título "estoura" com som de tecla
                tl["sfx"].append({"arquivo": SFX.get(tx["sfx"], tx["sfx"]), "t": round(t0, 3),
                                  "volume": tx.get("volume_sfx", 0.6)})
        fixas = [w for w in pals_bloco if w.get("fixa")]
        normais = [w for w in pals_bloco if not w.get("fixa")]
        if bloco.get("legenda", True):
            for f in fixas:  # tira as palavras do idioma original que caem sob a legenda traduzida
                normais = [w for w in normais if not (f["t0"] <= w["t0"] < f["t1"])]
            tl["legendas"] += legendas(normais) + [{"t0": f["t0"], "t1": f["t1"], "texto": f["w"]}
                                                    for f in fixas]
        tl["blocos"].append({"nome": bloco["nome"], "t": round(ini_bloco, 3), "dur": round(dur_bloco, 3)})
    # erros do Whisper que a gente pega no preview ("mesmas" -> "mesas"): troca por palavra inteira
    correcoes = plano.get("correcoes_legenda", {})
    for s in tl["legendas"]:
        s["texto"] = " ".join(correcoes.get(p, p) for p in s["texto"].split(" "))
        for errado, certo in correcoes.items():  # chave com espaço = correção de trecho
            if " " in errado:
                s["texto"] = s["texto"].replace(errado, certo)
    tl["legendas"].sort(key=lambda s: s["t0"])
    # clipes listados em "espelhar" saem com o quadro espelhado (flip horizontal)
    espelhar = set(plano.get("espelhar", []))
    for item in tl["v1"] + tl["v2"]:
        if item["clipe"] in espelhar:
            item["espelhar"] = True
    # zoom (punch-in) em janelas da fonte: corta o item nas bordas da janela e marca só o trecho de dentro
    for z in plano.get("zooms", []):
        novo = []
        for item in tl["v1"]:
            if item["clipe"] != z["clipe"] or item["out"] <= z["in"] or item["in"] >= z["out"]:
                novo.append(item)
                continue
            # partes: antes da janela, dentro (com zoom), depois da janela
            a, b, t0 = item["in"], item["out"], item["t"]
            ini, fim = max(a, z["in"]), min(b, z["out"])
            for x0, x1, com in ((a, ini, False), (ini, fim, True), (fim, b, False)):
                if x1 - x0 < 0.02:
                    continue
                parte = {**item, "in": round(x0, 3), "out": round(x1, 3), "t": round(t0 + (x0 - a), 3)}
                if com:
                    parte["zoom"] = {"fator": z.get("fator", 1.6), "cx": z.get("cx", 0.5), "cy": z.get("cy", 0.5)}
                novo.append(parte)
        tl["v1"] = novo
    tl["duracao"] = round(t, 3)
    if plano.get("narracao"):  # voiceover gravado à parte: entra por cima de tudo, do início
        n = plano["narracao"]
        tl["musica"].append({"arquivo": n["arquivo"], "in": n.get("in", 0.0), "t": n.get("t", 0.0),
                             "dur": round(t - n.get("t", 0.0), 3), "volume": n.get("volume", 1.0)})
    return tl


if __name__ == "__main__":
    caminho = Path(sys.argv[1])
    plano = json.loads(caminho.read_text())
    tl = montar(plano)
    saida = caminho.with_name(caminho.name.replace("plano_", "timeline_"))
    saida.write_text(json.dumps(tl, ensure_ascii=False, indent=1))
    print(f"{saida.name}: {tl['duracao']:.1f}s, {len(tl['v1'])} cortes na V1, "
          f"{len(tl['v2'])} coberturas, {len(tl['legendas'])} legendas")
    for b in tl["blocos"]:
        print(f"  {b['t']:6.1f}s  {b['nome']} ({b['dur']:.1f}s)")
