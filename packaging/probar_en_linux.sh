#!/bin/sh
# Solo desarrollo (DI-08): empaqueta en Linux dentro de Docker y corre la prueba de humo, para
# validar el .spec antes de gastar un build en Windows. El binario de Windows sale de GitHub Actions.
# Uso: docker compose run --rm dev sh packaging/probar_en_linux.sh
set -e
apt-get update -qq >/dev/null && apt-get install -y -qq binutils >/dev/null
rm -rf /tmp/pi && mkdir /tmp/pi
pyinstaller packaging/autoevalpsi.spec --noconfirm --distpath /tmp/pi/dist --workpath /tmp/pi/build >/tmp/pi/log.txt 2>&1 || { tail -30 /tmp/pi/log.txt; exit 1; }
du -sh /tmp/pi/dist/AutoEvalPsi
/tmp/pi/dist/AutoEvalPsi/AutoEvalPsi --prueba-humo
