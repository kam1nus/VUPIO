# MIMIC Microphone · Alpha 0.3

Real Core Audio AudioServerPlugIn, arm64, MIT-derived Apple sample. Bundle ID `local.mimic.audio`; device UID `MIMICAudioDevice_UID`; stereo float32 at 44.1/48 kHz, initially 48 kHz. One WriteMix producer (HAL mixes output clients), any number of independent ReadInput clients. Output-side MIMIC engine writes the already mixed/limited signal; Discord opens the input side.

`MIMICAudio.c` preserves Apple's COM/property/clock scaffolding. `Loopback.h` implements timestamp-tagged packed atomic stereo frames: 65536 frame slots, 1024 frame input delay (21.33 ms at 48 kHz), no read cursor shared by clients, silence for missing/overwritten timestamps, no replay after writer stop. IO allocates nothing, performs no network/file operations, and takes no locks. Control methods/clock retain sample mutexes; scalar volume/mute used by IO are atomic. The sample's nonfunctional data-source selector is restricted to one loopback choice. No BlackHole code or binary is used.

Factory UUID `C62576F1-99EB-4FE0-BA93-70F99C19D53D` is distinct from Apple's sample. Original MIT license is included in `APPLE_SAMPLE_LICENSE.txt`; official source is linked in THIRD_PARTY.md.

Build: `scripts/build_driver.sh`. Package: `scripts/package_audio.sh`. Install only through the standard PKG with admin authorization; runtime registration requires reboot/manual acceptance testing. Standalone host test (`tests/driver_host.c`) invokes the actual binary's factory, Initialize, properties and IO callbacks. That test does **not** prove coreaudiod acceptance or Discord compatibility.

User deferred system installation on 2026-10-28. Installed-driver, hardware hot-plug, sleep/reboot and Discord tests remain pending. Read STATUS_V03_RU.md before treating this Alpha as production ready.
