#!/bin/zsh -f
set -eu
cd "${0:A:h:h}"
MIMIC_DRIVER_BUILD="${MIMIC_DRIVER_BUILD:-$PWD/build/audio}"
mkdir -p "$MIMIC_DRIVER_BUILD/MIMICMicrophone.driver/Contents/MacOS" "$MIMIC_DRIVER_BUILD/MIMICMicrophone.driver/Contents/Resources"
clang -std=c11 -fblocks -O2 -arch arm64 -mmacosx-version-min=13.0 -bundle driver/MIMICAudio.c -framework CoreAudio -framework CoreFoundation -o "$MIMIC_DRIVER_BUILD/MIMICMicrophone.driver/Contents/MacOS/MIMICAudio"
cp driver/Info.plist "$MIMIC_DRIVER_BUILD/MIMICMicrophone.driver/Contents/Info.plist"
cp driver/APPLE_SAMPLE_LICENSE.txt "$MIMIC_DRIVER_BUILD/MIMICMicrophone.driver/Contents/Resources/"
cp LICENSE "$MIMIC_DRIVER_BUILD/MIMICMicrophone.driver/Contents/Resources/MIMIC_LICENSE.txt"
xattr -cr "$MIMIC_DRIVER_BUILD/MIMICMicrophone.driver"
if [[ -n "${MIMIC_APP_SIGN_IDENTITY:-}" ]]; then
 codesign --force --options runtime --timestamp --sign "$MIMIC_APP_SIGN_IDENTITY" "$MIMIC_DRIVER_BUILD/MIMICMicrophone.driver"
else
 codesign --force --sign - "$MIMIC_DRIVER_BUILD/MIMICMicrophone.driver"
fi
codesign --verify --strict "$MIMIC_DRIVER_BUILD/MIMICMicrophone.driver"
echo "$MIMIC_DRIVER_BUILD/MIMICMicrophone.driver"
