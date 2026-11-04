#!/bin/zsh
set -eu
cd "${0:A:h:h}"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi
if [[ ! -x .venv/bin/python ]]; then
  echo "Сначала запустите scripts/setup.sh" >&2
  exit 1
fi
exec .venv/bin/python -m mimic.server --audio "${MIMIC_AUDIO_EXECUTABLE:-$PWD/build/MIMIC.app/Contents/MacOS/MIMIC}"
