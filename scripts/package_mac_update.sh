#!/bin/zsh -f
# Keep the original app signature. The updater restores the omitted Models before verification.
set -eu
root="${0:A:h:h}"
app="${1:A}"
models="$app/Contents/Resources/Models/components.json"
hash=$(/usr/bin/shasum -a 256 "$models" | cut -d ' ' -f 1)
stage=$(mktemp -d /private/tmp/vupio-app-update.XXXXXX)
trap 'rm -rf "$stage"' EXIT
mkdir -p "$root/build/releases"
/bin/cp -cRP "$app" "$stage/VUPIO.app"
rm -rf "$stage/VUPIO.app/Contents/Resources/Models"
archive="$root/build/releases/VUPIO-macOS-AppleSilicon-Update-$hash.zip"
rm -f "$archive"
/usr/bin/ditto -c -k --keepParent "$stage/VUPIO.app" "$archive"
echo "Update archive created: $archive"

# Sparkle installs a complete signed app after models have been migrated.
cp "$models" "$stage/VUPIO.app/Contents/Resources/model-components.json"
xattr -cr "$stage/VUPIO.app"
if [[ -n "${MIMIC_APP_SIGN_IDENTITY:-}" ]]; then
 "$root/.venv/bin/python" "$root/scripts/sign_macho.py" "$stage/VUPIO.app"
 codesign --force --options runtime --timestamp --entitlements "$root/native/Release.entitlements" --sign "$MIMIC_APP_SIGN_IDENTITY" "$stage/VUPIO.app"
else
 codesign --force --deep --sign - "$stage/VUPIO.app"
fi
codesign --verify --deep --strict "$stage/VUPIO.app"
sparkle_archive="$root/build/releases/VUPIO-macOS-AppleSilicon-Sparkle.zip"
/usr/bin/ditto -c -k --keepParent "$stage/VUPIO.app" "$sparkle_archive"
echo "Sparkle archive created: $sparkle_archive"
