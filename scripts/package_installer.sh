#!/bin/zsh -f
# Run after package.sh. Produces a local unsigned Alpha installer by default.
set -eu
cd "${0:A:h:h}"
MIMIC_INSTALL_STAGE=$(mktemp -d /private/tmp/mimic-installer.XXXXXX)
mkdir -p "$MIMIC_INSTALL_STAGE/root/Applications"
app_bundle="${MIMIC_APP_BUNDLE:-build/MIMIC.app}"
target="$MIMIC_INSTALL_STAGE/root/Applications/VUPIO.app"
ditto --norsrc "$app_bundle" "$target"
xattr -cr "$target"
codesign --verify --deep --strict "$target"
version=$(/usr/libexec/PlistBuddy -c 'Print CFBundleShortVersionString' "$target/Contents/Info.plist")
mkdir -p build/releases
package=build/releases/VUPIO-macOS-AppleSilicon.pkg
cat > "$MIMIC_INSTALL_STAGE/app.plist" <<'XML'
<?xml version="1.0"?><plist version="1.0"><array><dict><key>BundleIsRelocatable</key><false/><key>BundleIsVersionChecked</key><true/><key>RootRelativeBundlePath</key><string>Applications/VUPIO.app</string></dict></array></plist>
XML
pkgbuild --root "$MIMIC_INSTALL_STAGE/root" --install-location / --ownership recommended --identifier local.mimic.app --version "$version" --component-plist "$MIMIC_INSTALL_STAGE/app.plist" "$MIMIC_INSTALL_STAGE/app.pkg"
cp build/audio/driver-component.pkg "$MIMIC_INSTALL_STAGE/driver.pkg"
cat > "$MIMIC_INSTALL_STAGE/distribution.xml" <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2"><title>VUPIO · Mac Apple Silicon</title><options customize="never" hostArchitectures="arm64"/><domains enable_localSystem="true" enable_currentUserHome="false" enable_anywhere="false"/><choices-outline><line choice="app"/><line choice="audio"/></choices-outline><choice id="app" title="VUPIO" visible="false"><pkg-ref id="local.mimic.app"/></choice><choice id="audio" title="MIMIC Microphone" visible="false"><pkg-ref id="local.mimic.audio"/></choice><pkg-ref id="local.mimic.app">app.pkg</pkg-ref><pkg-ref id="local.mimic.audio" onConclusion="RecommendRestart">driver.pkg</pkg-ref></installer-gui-script>
XML
productbuild --distribution "$MIMIC_INSTALL_STAGE/distribution.xml" --package-path "$MIMIC_INSTALL_STAGE" "$package"
if [[ -n "${MIMIC_INSTALLER_SIGN_IDENTITY:-}" ]]; then
 productsign --sign "$MIMIC_INSTALLER_SIGN_IDENTITY" "$package" "$MIMIC_INSTALL_STAGE/signed.pkg"
 cp "$MIMIC_INSTALL_STAGE/signed.pkg" "$package"
fi
if [[ -n "${MIMIC_NOTARY_PROFILE:-}" ]]; then
 [[ -n "${MIMIC_INSTALLER_SIGN_IDENTITY:-}" && -n "${MIMIC_APP_SIGN_IDENTITY:-}" ]] || { echo 'Developer ID certificates are required for notarization';exit 1; }
 xcrun notarytool submit "$package" --keychain-profile "$MIMIC_NOTARY_PROFILE" --wait
 xcrun stapler staple "$package"
fi
echo "Installer created: $PWD/$package"
