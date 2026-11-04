#!/bin/zsh -f
set -eu
cd "${0:A:h:h}"
MIMIC_AUDIO_STAGE=$(mktemp -d /private/tmp/mimic-audio-package.XXXXXX)
export MIMIC_DRIVER_BUILD="$MIMIC_AUDIO_STAGE/build"
./scripts/build_driver.sh
mkdir -p "$MIMIC_AUDIO_STAGE/root/Library/Audio/Plug-Ins/HAL" build/audio
 ditto --norsrc "$MIMIC_DRIVER_BUILD/MIMICMicrophone.driver" "$MIMIC_AUDIO_STAGE/root/Library/Audio/Plug-Ins/HAL/MIMICMicrophone.driver"
ditto --norsrc "$MIMIC_DRIVER_BUILD/MIMICMicrophone.driver" build/audio/MIMICMicrophone.driver
chmod +x installer/install-scripts/preinstall installer/uninstall-scripts/postinstall
pkgbuild --root "$MIMIC_AUDIO_STAGE/root" --identifier local.mimic.audio --version 0.3.0 --install-location / --ownership recommended --component-plist installer/driver-component.plist --scripts installer/install-scripts "$MIMIC_AUDIO_STAGE/driver-component.pkg"
pkgbuild --nopayload --identifier local.mimic.audio.uninstall --version 0.3.0 --scripts installer/uninstall-scripts "$MIMIC_AUDIO_STAGE/uninstall-component.pkg"
for mode in driver uninstall; do
 name=MIMIC-Audio-0.3.pkg
 [[ "$mode" == uninstall ]] && name=MIMIC-Audio-Uninstall-0.3.pkg
 cat > "$MIMIC_AUDIO_STAGE/$mode.xml" <<XML
<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2"><title>MIMIC Audio Alpha 0.3</title><options customize="never" require-scripts="false" hostArchitectures="arm64"/><domains enable_localSystem="true" enable_currentUserHome="false" enable_anywhere="false"/><choices-outline><line choice="audio"/></choices-outline><choice id="audio" visible="false"><pkg-ref id="local.mimic.$mode"/></choice><pkg-ref id="local.mimic.$mode" onConclusion="RecommendRestart">$mode-component.pkg</pkg-ref></installer-gui-script>
XML
 # productbuild package-ref identifier must match the component identifier.
 [[ "$mode" == driver ]] && sed -i '' 's/local.mimic.driver/local.mimic.audio/g' "$MIMIC_AUDIO_STAGE/$mode.xml"
 [[ "$mode" == uninstall ]] && sed -i '' 's/local.mimic.uninstall/local.mimic.audio.uninstall/g' "$MIMIC_AUDIO_STAGE/$mode.xml"
 productbuild --distribution "$MIMIC_AUDIO_STAGE/$mode.xml" --package-path "$MIMIC_AUDIO_STAGE" "build/audio/$name"
 if [[ -n "${MIMIC_INSTALLER_SIGN_IDENTITY:-}" ]]; then
  productsign --sign "$MIMIC_INSTALLER_SIGN_IDENTITY" "build/audio/$name" "$MIMIC_AUDIO_STAGE/signed.pkg"
  cp "$MIMIC_AUDIO_STAGE/signed.pkg" "build/audio/$name"
 fi
done
cp "$MIMIC_AUDIO_STAGE/driver-component.pkg" build/audio/driver-component.pkg
mkdir -p build/MIMIC.app/Contents/Resources/Audio
cp build/audio/MIMIC*.pkg build/MIMIC.app/Contents/Resources/Audio/
echo "Installer and reversible uninstaller ready; neither has been installed."
