#!/bin/zsh
# novo_projeto.sh -- cria um projeto (EP ou reel) apontando para os scripts daqui por symlink.
# Uso: ./novo_projeto.sh <nome_do_projeto> <pasta_dos_brutos>
# Variáveis: PROJETOS_DIR (onde criar o projeto; padrão: ../projects) e VENV (pasta do virtualenv com
# openai-whisper, numpy e pillow; padrão: ../.venv).
set -e
ESTEIRA="${0:A:h}"
PROJETOS="${PROJETOS_DIR:-${ESTEIRA:h}/projects}"
VENV="${VENV:-${ESTEIRA:h}/.venv}"
[ $# -eq 2 ] || { echo "uso: $0 <nome_do_projeto> <pasta_dos_brutos>"; exit 1; }
PROJ="$PROJETOS/$1"
BRUTOS="${2:A}"
[ -e "$PROJ" ] && { echo "já existe: $PROJ (nada foi alterado)"; exit 1; }
[ -d "$BRUTOS" ] || { echo "pasta de brutos não existe: $BRUTOS"; exit 1; }
[ -x "$VENV/bin/python" ] || { echo "venv não encontrado: $VENV (defina VENV=...)"; exit 1; }
mkdir -p "$PROJ/edicao" "$PROJ/cache/palavras" "$PROJ/previews" "$PROJ/entrega"
for f in montar preview conferir xml_premiere palavras grafismos projeto; do
  ln -s "$ESTEIRA/$f.py" "$PROJ/edicao/$f.py"
done
ln -s "$VENV" "$PROJ/.venv"
ln -s "$BRUTOS" "$PROJ/brutos"
echo "ok: $PROJ"
echo "próximo passo: escrever edicao/plano_<nome>.json (ver README.md)"
