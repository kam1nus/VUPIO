# MIMIC v0.2 — components, model licenses and source references

MIMIC's own source is MIT licensed (LICENSE). This does not relicense bundled third-party components, model weights, or imported audio. The synthesized samples/MIMIC-check.wav is CC0-1.0.

The standalone Mac application embeds its Python runtime, qrcode, NumPy, certifi, FFmpeg/ffprobe, llama.cpp, whisper.cpp and their shared libraries. Users do not need to install Python, Ollama or development tools. ThirdPartyLicenses/ inside Contents/Resources includes collected notices, component versions, installed source-build recipes and source references. Tools/dependencies.json records the build inputs. This is an ad-hoc signed private development build, not an Apple-notarized public distribution.

- CPython 3.14: Python Software Foundation license — https://docs.python.org/3/license.html
- qrcode 8.2: BSD license — https://github.com/lincolnloop/python-qrcode
- NumPy 2.5.4: BSD-3-Clause plus dependency notices — https://numpy.org/doc/stable/license.html
- certifi 2026.10.23: MPL-2.0 certificate bundle — https://github.com/certifi/python-certifi
- PyInstaller 6.22.3: GPL with the bootloader distribution exception — https://pyinstaller.org/en/stable/license.html
- llama.cpp 0.7.0 / ggml 0.27.0: MIT — https://github.com/ggml-org/llama.cpp and https://github.com/ggml-org/ggml
- whisper.cpp 1.9.5: MIT — https://github.com/ggml-org/whisper.cpp
- FFmpeg 9.0.2_1 and this Homebrew build's codec dependencies: LGPL/GPL as configured. This build enables GPL components. Exact recipes and component notices are included; upstream corresponding sources: https://ffmpeg.org/releases/ and the source URLs in the included formulas. Public redistribution must preserve the relevant notices and satisfy source-availability requirements of those licenses; MIMIC's MIT license alone does not cover these binaries.
- BlackHole 2ch: GPL-3.0, installed separately and not bundled — https://github.com/ExistentialAudio/BlackHole
- Apple SoundAnalysis, AVFoundation, SwiftUI and system Swift runtime: macOS system components. Apple's classifier is used through the system API; the app does not redistribute that model.

Weights are NOT included in the app/source ZIPs. The app downloads fixed, SHA-256-verified files into the user's local Application Support/MIMIC/models directory:

- Qwen 2.5 0.5B Instruct Q4, 397807936 bytes, Apache-2.0. Original model: https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct ; public GGUF distribution: https://ollama.com/library/qwen2.5:0.5b . We use the registry only as a weight download source, not the Ollama API/runtime.
- EmbeddingGemma 300M BF16, 621867104 bytes, Gemma Terms of Use — https://ai.google.dev/gemma/terms . Original model: https://huggingface.co/google/embeddinggemma-300m ; public distribution: https://ollama.com/library/embeddinggemma . Before llama.cpp inference, GGUF architecture/tensor-name metadata is adapted following the mappings in https://github.com/ollama/ollama/blob/main/llama/compat/llama-ollama-compat.cpp (MIT). Tensor data is unchanged; both original and adapted file hashes are recorded locally.
- Whisper Base multilingual Q5_1, 59707625 bytes, MIT — https://huggingface.co/ggerganov/whisper.cpp and https://github.com/openai/whisper/blob/main/LICENSE . Download and inference are through whisper.cpp, with no OpenAI service/API/key.
- The tested optional imported Qwen3 8B Q4 local profile uses weights already present on this Mac, independently opened by llama.cpp. Qwen3-8B is Apache-2.0: https://huggingface.co/Qwen/Qwen3-8B . Arbitrary user-imported GGUF models retain their own licenses, which the user must verify.

Wikimedia search uses the official MediaWiki API and allows automatic imports only for explicitly recognized CC0, Public Domain, CC BY and CC BY-SA metadata without listed restrictions, in supported audio formats and within size limits. Full author/source/license/attribution metadata is retained with the clip and derived copies. The app does not independently establish that an uploader owned every right; use the source page for verification. No TikTok, Instagram or YouTube downloaders, restriction bypasses or proprietary meme/music packs are included.


## MIMIC Alpha v0.3 virtual audio driver

`driver/MIMICAudio.c` is derived from Apple's official **Creating an Audio Server Driver Plug-in** (NullAudio, copyright Apple 2024, MIT). Full notice: `driver/APPLE_SAMPLE_LICENSE.txt`. Source: https://developer.apple.com/documentation/coreaudio/creating-an-audio-server-driver-plug-in ; archive: https://docs-assets.developer.apple.com/published/430ad6501f6f/CreatingAnAudioServerDriverPlugIn.zip .

MIMIC changes replace silent/discarded IO with the timestamped stereo loopback in `driver/Loopback.h`, use a distinct bundle ID/UID/factory and device name, initialize at 48 kHz, honor volume/mute, report input delay, and correct delayed clock catch-up. COM/property plumbing remains Apple's sample code. No BlackHole source or binary is included or required by this driver. BlackHole remains an optional preinstalled fallback.

The new mixer (`native/MixerDSP.c`), decoder/capture integration, diagnostics, settings and installer scripts are part of the MIMIC source under the project's LICENSE. This local Alpha has ad-hoc signatures; Developer ID signing/notarization has not been performed.

## VUPIO preview installers

The full VUPIO builds add verified Qwen2.5 Instruct and Whisper Base model files from the pinned sources above, plus Qwen3 Embedding 0.6B Q4 (Apache-2.0), quantized by OpenMycel from Qwen's original model. See `Models/components.json` and the model-specific license files in the installer. The full builds do not bundle EmbeddingGemma v1. MIMIC development builds retain support for a separately downloaded EmbeddingGemma model.

- Qwen3 Embedding base weights — https://huggingface.co/Qwen/Qwen3-Embedding-0.6B
- Qwen3 Embedding GGUF and provenance — https://huggingface.co/openmycel/Qwen3-Embedding-0.6B-GGUF
- Windows FFmpeg 8.0.1 — https://github.com/GyanD/codexffmpeg/releases/tag/8.0.1 ; https://ffmpeg.org/releases/ffmpeg-8.0.1.tar.xz ; see the archive notice for codec dependencies and build options.
- macOS llama.cpp b10917 uses the official Apple Silicon archive; macOS Whisper v1.8.3 is built from the same source tag as the Windows runtime, with static CPU libraries. The exact source archives and SHA-256 values are recorded in `Tools/ai-dependencies.json`.
- Windows llama.cpp CPU build — https://github.com/ggml-org/llama.cpp/tree/b10917
- Windows whisper.cpp CPU build — https://github.com/ggml-org/whisper.cpp/tree/v1.8.3
- Windows audio — https://github.com/spatialaudio/python-sounddevice and https://github.com/PortAudio/portaudio (license notices accompany the Python package). VB-CABLE is separately installed from the vendor and has its own [license and distribution terms](https://vb-audio.com/Services/licensing.htm).
- The Windows installer downloads a signed Microsoft Visual C++ Runtime from Microsoft if it is missing. It does not host the Microsoft installer.

In particular, before public binary distribution, check FFmpeg corresponding source for all enabled GPL/LGPL dependencies and the exact Homebrew or Windows build configuration. Neither the project's MIT license nor a binary archive substitutes for the applicable third-party notices and source obligations.
