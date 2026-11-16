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
