#!/bin/zsh -f
set -eu
cd "${0:A:h:h}"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
./scripts/build.sh
MIMIC_PROJECT_DIR="$PWD"
MIMIC_BUILD_WORK="${MIMIC_BUILD_WORK:-$PWD/build/packaging}"
mkdir -p "$MIMIC_BUILD_WORK" build/MIMIC.app/Contents/Resources
export PYINSTALLER_CONFIG_DIR="$MIMIC_BUILD_WORK/cache"
.venv/bin/python -m PyInstaller --noconfirm --clean --onedir --name mimic-server --paths "$PWD" \
 --distpath "$MIMIC_BUILD_WORK/dist" --workpath "$MIMIC_BUILD_WORK/temp" --specpath "$MIMIC_BUILD_WORK" \
 --add-data "$PWD/web:web" --collect-all certifi --hidden-import numpy --hidden-import qrcode.image.svg \
 scripts/frozen_entry.py > "$MIMIC_BUILD_WORK/pyinstaller.log" 2>&1
rm -rf build/MIMIC.app/Contents/Resources/server
cp -R "$MIMIC_BUILD_WORK/dist/mimic-server" build/MIMIC.app/Contents/Resources/server
rm -rf build/MIMIC.app/Contents/Resources/Tools
.venv/bin/python scripts/bundle_tools.py build/MIMIC.app/Contents/Resources/Tools
# Include source and license notices needed to reproduce/review the bundled LGPL/GPL dependencies.
cp THIRD_PARTY.md LICENSE build/MIMIC.app/Contents/Resources/
.venv/bin/python scripts/collect_licenses.py build/MIMIC.app/Contents/Resources
if [[ "${MIMIC_BUNDLE_MODELS:-0}" == 1 ]]; then
 .venv/bin/python scripts/bundle_mac_ai.py build/MIMIC.app/Contents/Resources/Tools "${MIMIC_MAC_AI_CACHE:-$MIMIC_BUILD_WORK/ai}"
 args=(build/MIMIC.app/Contents/Resources/Models)
 if [[ -n "${MIMIC_MODEL_CACHE:-}" ]]; then args+=(--cache "$MIMIC_MODEL_CACHE"); fi
 .venv/bin/python scripts/bundle_models.py "${args[@]}"
fi
./scripts/package_audio.sh
MIMIC_SIGN_STAGE=$(mktemp -d /private/tmp/mimic-sign.XXXXXX)
ditto --norsrc --noextattr --noqtn --noacl build/MIMIC.app "$MIMIC_SIGN_STAGE/MIMIC.app"
xattr -cr "$MIMIC_SIGN_STAGE/MIMIC.app"
if [[ -n "${MIMIC_APP_SIGN_IDENTITY:-}" ]]; then
 .venv/bin/python scripts/sign_macho.py "$MIMIC_SIGN_STAGE/MIMIC.app"
 codesign --force --options runtime --timestamp --entitlements native/Release.entitlements --sign "$MIMIC_APP_SIGN_IDENTITY" "$MIMIC_SIGN_STAGE/MIMIC.app"
else
 codesign --force --deep --sign - "$MIMIC_SIGN_STAGE/MIMIC.app"
fi
codesign --verify --deep --strict "$MIMIC_SIGN_STAGE/MIMIC.app"
ditto --norsrc --noextattr --noqtn --noacl "$MIMIC_SIGN_STAGE/MIMIC.app" build/MIMIC.app
echo "Подпись проверена в $MIMIC_SIGN_STAGE/MIMIC.app"
echo "Готовая переносимая сборка: $MIMIC_PROJECT_DIR/build/MIMIC.app"
