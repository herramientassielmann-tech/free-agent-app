#!/usr/bin/env bash
#
# Instala el aviso diario de tareas vencidas del CRM.
#
# Se puede volver a lanzar las veces que haga falta: no duplica nada y no
# pisa la clave si ya está puesta.
#
# Uso:  bash deploy/instalar_avisos.sh
#
set -euo pipefail

RAIZ=/var/www/freeagent
cd "$RAIZ"

echo "── 1/4 · Clave de Resend ──"
if grep -q '^RESEND_API_KEY=.\+' .env 2>/dev/null; then
  echo "   Ya estaba configurada. No la toco."
else
  # -s para que no se vea al pegarla ni quede en el historial del shell.
  read -rsp "   Pega la clave de Resend (empieza por re_): " CLAVE
  echo
  if [ -z "$CLAVE" ]; then
    echo "   Sin clave no puedo seguir." >&2; exit 1
  fi
  sed -i '/^RESEND_API_KEY=/d' .env
  printf '\nRESEND_API_KEY=%s\n' "$CLAVE" >> .env
  unset CLAVE
  echo "   Guardada en .env"
fi

if ! grep -q '^EMAIL_REPLY_TO=.\+' .env 2>/dev/null; then
  sed -i '/^EMAIL_REPLY_TO=/d' .env
  echo 'EMAIL_REPLY_TO=herramientassielmann@gmail.com' >> .env
  echo "   Las respuestas de los realtors irán a herramientassielmann@gmail.com"
fi
chmod 600 .env

echo "── 2/4 · Temporizador ──"
cp deploy/freeagent-avisos.service /etc/systemd/system/
cp deploy/freeagent-avisos.timer   /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now freeagent-avisos.timer
echo "   Instalado y activado."

echo "── 3/4 · Comprobación en seco (no envía nada) ──"
.venv/bin/python3 scripts/avisar_tareas.py --ensayo

echo "── 4/4 · Próximo envío programado ──"
systemctl list-timers freeagent-avisos.timer --no-pager | head -3

echo
echo "Listo. Para mandarte un correo de prueba ahora mismo:"
echo "  cd $RAIZ && .venv/bin/python3 scripts/avisar_tareas.py --prueba TU@CORREO.com"
