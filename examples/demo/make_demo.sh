#!/bin/zsh
# make_demo.sh -- gera material de teste sintético (sem pessoas nem arquivos pessoais) e um plano de edição.
# Precisa de macOS (`say`) e ffmpeg. Saída: examples/demo/brutos/{fala,paisagem}.mp4 e plano_demo.json
set -e
cd "${0:A:h}"; mkdir -p brutos
say -v Samantha -o fala.aiff "Welcome to the pipeline demo. [[slnc 1800]] This clip has long pauses, [[slnc 1800]] and the tool removes them for you. [[slnc 1500]] Then it adds cutaways, titles and captions from a single plan."
ffmpeg -v error -y -f lavfi -i "testsrc2=size=1280x720:rate=24" -i fala.aiff -shortest -c:v libx264 -pix_fmt yuv420p -c:a aac brutos/fala.mp4
ffmpeg -v error -y -f lavfi -i "mandelbrot=size=1280x720:rate=24" -f lavfi -i anullsrc=r=44100:cl=mono -t 8 -c:v libx264 -pix_fmt yuv420p -c:a aac brutos/paisagem.mp4
rm fala.aiff
cat > plano_demo.json <<'J'
{
  "perfil": "shorts",
  "formato": "16:9",
  "config": {"whisper_modelo": "base", "whisper_device": "cpu"},
  "blocos": [
    {
      "nome": "demo",
      "falas": [{"clipe": "fala", "in": 0.0, "out": 16.5, "idioma": "en"}],
      "cobertura": [{"clipe": "paisagem", "in": 1.0, "na_palavra": "pauses", "dur": 2.5, "som": 0.0}],
      "textos": [
        {"estilo": "titulo", "texto": "PIPELINE\nDEMO", "lado": "direita", "em": 0.3, "dur": 2.5},
        {"estilo": "arroba", "texto": "@yourhandle", "em": 4.0, "dur": 3.2}
      ]
    }
  ]
}
J
echo "ok: $(ls brutos)"; ffprobe -v error -show_entries format=duration -of csv=p=0 brutos/fala.mp4
