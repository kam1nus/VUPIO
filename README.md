# VUPIO

A local soundboard, audio editor and wireless phone remote for macOS and Windows.

## Download VUPIO Alpha 4046

**[↓ Windows 11 x64](https://github.com/kam1nus/VUPIO/releases/download/alpha-4046/VUPIO-Windows-x64-Setup.exe)** · **[↓ Apple Silicon Mac, macOS 26+](https://github.com/kam1nus/VUPIO/releases/download/alpha-4046/VUPIO-macOS-AppleSilicon.pkg)**

Download and run the installer for your computer. [Release notes](https://github.com/kam1nus/VUPIO/releases/tag/alpha-4046) · [SHA-256 checksums](https://github.com/kam1nus/VUPIO/releases/download/alpha-4046/SHA256SUMS.txt)

## Updates

Open **Updates → Check for updates** in VUPIO to find the latest installer for your platform. Published previews are also available in [GitHub Releases](https://github.com/kam1nus/VUPIO/releases).

The English interface includes Soundboard, Discover, Studio, Trend Radar, Remote, Updates and Settings. Search queries, meme names and imported metadata can use their original languages. Search quality depends on the model and available sources.

## Features

- Soundboard library with search, categories, favorites, card-triggered playback, volume, STOP and PANIC.
- Discover searches the web and your local library with natural-language queries. Original queries and names are preserved, with optional English keyword expansion from the local AI model.
- Studio shows the actual audio waveform and supports trim, silence removal, normalization, fades, speech transcription, AI commands and preview before saving.
- Trend Radar provides regional meme charts and music charts. Meme sounds are checked and preloaded before appearing, unavailable files are skipped, and Add saves the same audio you previewed.
- Remote pairs an iPhone or another browser with a QR code and one-time code on your local network.
- Settings includes audio routing, microphone diagnostics, models, tasks and optional search API configuration.
- Local clip listening is on by default. It follows the system output or remembers your headphones/speakers, without playing your microphone back to you.

Full installers include FFmpeg, llama.cpp, whisper.cpp, Qwen2.5 Instruct, Qwen3 Embedding and multilingual Whisper Base. Local AI features work without Python, Ollama or API keys. Web search uses Tavily with service limits. Add an optional Tavily key in **Settings → Advanced** if needed.

These are Alpha preview installers. The Mac app is ad-hoc signed without Apple notarization. The Windows installer has no Authenticode signature.

## Mac setup

1. Close VUPIO, open the PKG and follow the installer.
2. Restart your Mac after the first driver installation, then open VUPIO in Applications.
3. In Discord **Voice & Video**, select **MIMIC Microphone** as input and your headphones as output.
4. In VUPIO, select your physical microphone and enable it to mix your voice with clips. Grant microphone access when macOS asks. Local clip listening is enabled by default; select your headphones or **System output (automatic)** in Settings. Your microphone is not sent to local listening.
5. Start Discord Mic Test and trigger a sound in Soundboard. Stop Mic Test afterward to end voice playback.

MIMIC Microphone keeps its existing device name for compatibility with saved Discord settings. Your library and preferences are stored in `~/Library/Application Support/MIMIC`.

## Windows setup

1. Run `VUPIO-Windows-x64-Setup.exe`. Keep the small VUPIO launcher window open while using the browser interface.
2. For Discord routing, select **Download VB-CABLE** during setup. The installer downloads it from VB-Audio, checks the archive hash and vendor signature, then opens the vendor installer. Confirm installation there and restart Windows.
3. In VUPIO **Settings → Audio devices**, select **CABLE Input** as output and your physical microphone as input.
4. In Discord, select **CABLE Output** as input and your headphones as output.
5. Clip listening is enabled by default. In **Settings → Audio devices**, use **System output (automatic)** or choose headphones/speakers. Keep Windows **Listen to this device** disabled to avoid doubled audio.

Windows uses WASAPI. Speech transcription, waveform editing, energy-based highlights and semantic search are available on both platforms. Core Audio and Apple SoundAnalysis diagnostics run on Mac. Windows data is stored in `%LOCALAPPDATA%\MIMIC`.

## Phone remote

Connect your computer and phone to the same trusted local network. Open **Remote**, create a pairing code and scan the QR with the phone camera. Open the link in Safari and enter the code. Use **Share → Add to Home Screen** for quick access.

On Windows, allow VUPIO through the firewall on private networks. Keep router port forwarding disabled.

## Build from source

Use **Actions → VUPIO preview installers → Run workflow** on GitHub. Enable **Publish** to create a prerelease after both platform builds succeed.

For Mac, install FFmpeg and CMake, create a Python environment, then build:

```sh
brew install ffmpeg cmake
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt pyinstaller==6.22.3
MIMIC_BUNDLE_MODELS=1 ./scripts/package.sh
./scripts/package_installer.sh
```

For Windows, install Python 3.14 and Inno Setup 6, then run:

```powershell
python -m pip install -r requirements-windows.txt
pwsh -File scripts/package_windows.ps1
```

Installers are written to `build/releases`. For Mac release signing, configure `MIMIC_APP_SIGN_IDENTITY`, `MIMIC_INSTALLER_SIGN_IDENTITY` and `MIMIC_NOTARY_PROFILE`.

Mac developer builds can use a signed local update folder through `MIMIC_LOCAL_UPDATE_CHANNEL` and `MIMIC_LOCAL_UPDATE_KEY`. Each release needs a higher `MIMIC_BUILD_NUMBER`. Keep the private key outside the repository.

The project uses the MIT license. Bundled dependencies and imported media have their own terms. Component notices, source references and recipes ship in Tools, Models and ThirdPartyLicenses. See [THIRD_PARTY.md](THIRD_PARTY.md) for dependency details.
