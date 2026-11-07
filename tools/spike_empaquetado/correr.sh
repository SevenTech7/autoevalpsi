#!/bin/sh
# Dentro del contenedor dev (Linux). Uso: docker compose run --rm dev sh tools/spike_empaquetado/correr.sh [extra args de pyinstaller]
set -e
apt-get update -qq >/dev/null && apt-get install -y -qq binutils >/dev/null
rm -rf /tmp/pi && mkdir /tmp/pi && cd /tmp/pi
pyinstaller --noconfirm --onedir --name hola --distpath /tmp/pi/dist --workpath /tmp/pi/build \
  --specpath /tmp/pi "$@" /app/tools/spike_empaquetado/hola.py >/tmp/pi/log.txt 2>&1 || { tail -20 /tmp/pi/log.txt; exit 1; }
echo "tamaño:"; du -sh dist/hola
echo "arranque en frío (3 corridas):"
for i in 1 2 3; do
  s=$(date +%s.%N); ./dist/hola/hola --sin-ventana; e=$(date +%s.%N)
  echo "total $(echo "$e - $s" | bc 2>/dev/null || python -c "print(round($e-$s,2))")"
done
echo "mayores:"; du -sk dist/hola/_internal/* | sort -rn | head -8
echo "avisos de PyInstaller sobre módulos no hallados:"; grep -ciE "not found|hidden" /tmp/pi/log.txt || true
