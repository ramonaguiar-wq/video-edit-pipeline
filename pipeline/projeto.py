"""projeto.py -- onde está o projeto e quais são os parâmetros dele.

Os scripts moram aqui (esteira_edicao/) e entram em cada projeto por symlink em
<projeto>/edicao/. A raiz do projeto sai do caminho pelo qual o script foi chamado
(`.venv/bin/python edicao/montar.py ...`), sem seguir o symlink. Para chamar de outro
lugar: ESTEIRA_PROJETO=/caminho/do/projeto.

O que antes era remendado script a script agora é campo do plano (chave "config");
o montar.py copia para a timeline, e preview.py / xml_premiere.py leem de lá.
"""
import os
import sys
from pathlib import Path

RAIZ = Path(os.environ.get("ESTEIRA_PROJETO") or Path(sys.argv[0]).absolute().parent.parent)
if not (RAIZ / "edicao").is_dir():
    sys.exit(f"projeto não encontrado em {RAIZ} (sem pasta edicao/). Rode de dentro do projeto, "
             "pelo symlink edicao/<script>.py, ou defina ESTEIRA_PROJETO.")

PADRAO = {
    "extensoes": [".mov", ".MP4", ".mp4"],   # ordem de busca do arquivo do clipe
    "whisper_modelo": "large-v3-turbo",
    "whisper_device": "cpu",                 # mps quebra com autocast
    "enquadramento": "preencher",            # "preencher" (corta no centro) | "encaixar_com_fundo" (fundo desfocado)
    "sequencia": None,                       # [W, H] do XML; None = 3840x2160, ou 1080x1920 se formato 9:16
}
CFG = dict(PADRAO)


def configurar(origem):
    """origem: plano ou timeline (dict). Lê a chave "config" e avisa de campo desconhecido."""
    for k, v in (origem.get("config") or {}).items():
        if k not in PADRAO:
            print(f"  ⚠ config '{k}' desconhecida -- ignorada (válidas: {', '.join(PADRAO)})")
            continue
        CFG[k] = v
    return CFG


def achar_clipe(clipe, pastas):
    """Primeiro arquivo que existir, na ordem das pastas e das extensões do projeto."""
    for pasta in pastas:
        for ext in CFG["extensoes"]:
            p = RAIZ / pasta / f"{clipe}{ext}"
            if p.exists():
                return p
    sys.exit(f"clipe não encontrado: {clipe} (pastas {', '.join(pastas)}; extensões {', '.join(CFG['extensoes'])})")
