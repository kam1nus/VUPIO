#!/bin/zsh
set -eu
cd "${0:A:h:h}"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
./scripts/build.sh
if ! command -v ffmpeg >/dev/null; then
  echo "Для импорта установите FFmpeg: brew install ffmpeg"
fi
