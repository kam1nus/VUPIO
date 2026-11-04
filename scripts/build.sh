#!/bin/zsh
set -eu
cd "${0:A:h:h}"
mkdir -p build/MIMIC.app/Contents/{MacOS,Resources} build/swift-cache
cp native/MIMIC.swift build/main.swift
clang -std=c11 -O2 -c native/MixerDSP.c -o build/MixerDSP.o
swiftc build/main.swift native/SoundAnalysis.swift native/AudioMixer.swift native/AudioProbe.swift native/CoreInput.swift build/MixerDSP.o -import-objc-header native/MixerDSP.h -O -module-cache-path build/swift-cache -o build/MIMIC.app/Contents/MacOS/MIMIC -framework Cocoa -framework WebKit -framework SoundAnalysis -framework AVFoundation -framework CoreAudio -framework AudioToolbox
swiftc scripts/icon.swift -module-cache-path build/swift-cache -o build/mimic-icon
build/mimic-icon web/icon.svg build/MIMIC.iconset
python3 scripts/icon_container.py build/MIMIC.iconset build/MIMIC.app/Contents/Resources/MIMIC.icns
cat > build/MIMIC.app/Contents/Info.plist <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>MIMIC</string>
<key>CFBundleIdentifier</key><string>local.mimic.soundboard</string>
<key>CFBundleName</key><string>VUPIO</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>0.4.3</string>
<key>CFBundleVersion</key><string>4039</string>
<key>CFBundleIconFile</key><string>MIMIC.icns</string>
<key>LSMinimumSystemVersion</key><string>26.0</string>
<key>NSMicrophoneUsageDescription</key><string>MIMIC mixes your microphone with soundboard audio for Discord, only when you enable it.</string>
<key>NSLocalNetworkUsageDescription</key><string>MIMIC connects to your iPhone remote on your private Wi-Fi.</string>
<key>NSDocumentsFolderUsageDescription</key><string>MIMIC reads its local project files and audio you choose from Documents.</string>
<key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/><key>NSAllowsArbitraryLoadsInWebContent</key><true/></dict>
</dict></plist>
PLIST
for attempt in 1 2 3; do
  xattr -cr build/MIMIC.app
  if codesign --force --sign - build/MIMIC.app; then break; fi
  if [[ "$attempt" == 3 ]]; then exit 1; fi
done
echo "Готово: $PWD/build/MIMIC.app"
