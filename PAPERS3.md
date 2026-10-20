# PaperS3 radio and electronic-paper variants

Base: official PokeLDN v0.32.0, radio firmware 1.6.2, ESP-IDF v6.1.
Branch: `papers3-epaper-v0.32.0`. This fork keeps the host protocol unchanged.

![PaperS3 screen simulations for Pikachu, Eevee, Charizard, Gengar, Lucario and Arceus](docs/assets/papers3/gallery-simulation.png)

**Firmware-rendered simulations, not device photographs or Mac App screenshots.**
The screen area is 960x540; gallery captions are outside that area. The renderer
uses the unchanged firmware drawing functions, M5GFX fonts and the same DISPLAY
payload parser. Panel waveforms, ghosting and ambient lighting are not simulated.

Enable with `POKELDN_PAPERS3=1` and defaults
`sdkconfig.defaults;sdkconfig.defaults.esp32s3;sdkconfig.defaults.papers3`.

Changes:

- Initialize GPIO44 (`PWROFF_PULSE`) low, as the PaperS3 branch of M5GFX does.
- Keep GPIO45 (`EPD_PWR`) and GPIO21 (buzzer) low.
- Skip `led_start`: upstream S3 LED PWM would drive the PaperS3 buzzer on GPIO21;
  upstream BOOT monitoring would read the PaperS3 LED/strap on GPIO0.
- Skip `display_start`: upstream OLED probing drives the electronic-paper data
  pins GPIO8/9. No display initialization or framebuffer is added.
- Set the physical flash size to 16 MB, retaining upstream's DIO/80 MHz mode,
  partition layout, Wi-Fi driver, USB Serial/JTAG, protocol and USB watchdog.
- Keep numeric `version=1.6.2` for the host's semantic-version comparisons;
  append `board=PaperS3 variant=1` to INFO so this local build is identifiable.

There is no periodic PMS150G keepalive in the inspected M5 sources. GPIO44 is
not to be treated as a conventional active-high power hold. M5Unified's
shutdown uses five cycles of 50 ms low / 50 ms high. This patch does not
generate those pulses or change PMS150G firmware, eFuses or security settings.

With no LED task, LED commands remain accepted but have no physical effect;
DISPLAY reports no display and BOOT marker events are unavailable.
PSRAM is left disabled because this radio-only build does not use it. M5's
Octal PSRAM requirement applies when driving its electronic-paper display.

Evidence (pinned source checkouts in the parent research directory):

- M5GFX `src/M5GFX.cpp`: PaperS3 detection, `PWROFF_PULSE_PIN`, GPIO44 low.
- M5Unified `src/utility/Power_Class.inl`: `powerOff`, repeated pulses.
- Official PaperS3 schematic: GPIO19/20 USB, GPIO21 buzzer, GPIO44 power-off,
  GPIO45 electronic-paper power, GPIO8/9 electronic-paper data.

Build success does not establish successful boot, stable power, USB protocol
compatibility, wireless connection or a completed trade. Each needs hardware
testing after a verified backup and explicit flashing approval.

## Variant 2: optional electronic-paper dashboard

The changes above describe variant 1. Variant 2 replaces the generic OLED
driver with an explicit PaperS3 ET047TC1 `Bus_EPD` / `Panel_EPD` configuration
from M5GFX, pinned at `347a23274081a105cb9fc0fc3bbf0e15c78e79c3` (0.2.33).
It enables 80 MHz Octal PSRAM for display buffers. Ordinary radio allocations
stay in internal RAM (`SPIRAM_USE_CAPS_ALLOC`, Wi-Fi PSRAM allocation disabled).
M5GFX's broad board autodetection, touch initialization and NVS settings are not
used. GPIO45 is managed by the display driver instead of being kept off.

The 960x540 landscape screen shows radio readiness, joining/hosting/linked
states, station count, sampled RX/TX counters, and the game / Pokemon title,
name and one-bit sprite supplied through the existing DISPLAY protocol.
Without a sprite it draws a Poke Ball. INFO identifies
`board=PaperS3 variant=2 display=epaper`, while the numeric radio version remains
1.6.2. No host App changes are required.

There is **no link code field in DISPLAY**, so codes and controls stay in the
Mac App. Text is capped at the protocol's 21 ASCII characters. No touchscreen
menu, SD access, game save access or key handling is added.

Validated commands are copied into a bounded eight-entry queue without waiting
for the panel. A low-priority worker on core 0 draws snapshots with at least
two seconds between completed refreshes. Counter-only changes are sampled at
15 seconds while active; idle screens do not refresh repeatedly. The first
and every twelfth update use the quality waveform; other updates use fast mode.
E-paper retains its last image after power-off: check the App for live status.

This is a snapshot UI, not the OLED animation scheduler. Timed SHOWs stay until
another command or the session returns to idle. `traded` says "Incoming Pokemon"
until an explicit `arrived` command (some games do not send it). Screen labels
are not independent proof that the game saved. HELLO discards older session
commands even if the queue was full; early offers can queue during panel init.

STATUS adds `epd=starting|ready|no_psram|init_failed|no_task` and `epd_updates=N`.
Missing PSRAM or detected initialization failures disable this display path
without intentionally resetting the radio. Driver/hardware faults can still
affect the radio; the fallback is not isolation against every electrical failure.

## Build variant 2 without flashing

Activate **ESP-IDF v6.1**, then from the repository root:

```sh
bash scripts/build_papers3_epaper.sh
```

This selects S3, a separate build directory and sdkconfig, and opt-in switches
`POKELDN_PAPERS3=1` / `POKELDN_PAPERS3_EPAPER=1`. ESP-IDF's component manager
fetches the pinned M5GFX dependency. The output is
`firmware/esp32/build-papers3-epaper/pokeldn-radio-s3-papers3-1.6.2-v2.bin`.
The script does not open a serial port, reset, erase or flash any device.
The optional component is outside automatic component discovery, so ordinary
builds do not acquire its dependency. Do not reuse its sdkconfig for variant 1.

The Flash configuration and partition table are unchanged: DIO/80 MHz/16 MB,
NVS 0x9000, PHY 0xf000, factory app 0x10000 with 1 MiB capacity, merged offset 0x0.

## Verification status (2026-10-20)

- Variant 1: written and independently read back on ESP32-S3 rev 0.2 PaperS3.
  INFO/STATUS, channel controls, a 300-second USB soak, two 2 MB BENCH transfers
  and 10 reopen checks passed. Official macOS arm64 App v0.32.0 identified it
  and started a Legends Z-A AP, then stopped with exit code 0.
- Variant 2: built with ESP-IDF v6.1, written after explicit approval, and
  independently read back with matching SHA-256. Boot/app hashes and partition
  MD5 passed. The owner confirmed the physical screen's orientation and text,
  and subsequently the Pikachu sprite's appearance.
- During a 180-second USB/display test, 60 STATUS samples, 12 changing text
  screens plus return to AUTO, channels 1/6/11/6 and four 2 MB BENCH transfers
  passed. Transfer rates were 956-962 kB/s with no missing/rejected frames,
  additional framing errors, resyncs, observed resets or disconnects during the
  measured interval. Initial USB negotiation had a baseline of two bad frames.
- Six display-only sprite tests (Pikachu 41x49, Eevee 39x40, Charizard 64x62,
  Gengar 51x45, Lucario 46x63, Arceus 59x64) each advanced `epd_updates` with
  `epd=ready`, unchanged free heap and no additional protocol errors. This is
  runtime evidence of completed driver refreshes; it does not establish the
  physical appearance of every sprite.
- Official macOS arm64 App v0.32.0 recognized variant 2. Its bundled Z-A CLI
  reached AP-up/hosting on channel 6 for 15 seconds and stopped with exit 0.
  No Switch joined, and no trade was attempted.
- Six native parser tests plus nineteen upstream display tests pass (25 total).
  Tests execute the real C parser against the official Python host encoders:
  odd-width and maximum sprites, all slots, malformed/truncated payloads,
  bounded text, reset/arrival handling and 10,000 deterministic random inputs.
- The radio-only variant still compiles after the opt-in display changes.
- No Switch was available. Association, LDN authentication, trades, battery-only
  operation, cold-plug startup and sustained RF load remain unverified.

Run the parser tests with Python, pyserial and a host C compiler:

```sh
python -m unittest discover -s tests -p test_papers3_display_model.py -v
```

With development dependencies installed, also run the upstream screen tests:

```sh
python -m pytest tests/test_papers3_display_model.py tests/test_esp32_screen.py -q
```

The tested merged image was 701,248 bytes, with SHA-256:

```text
aa8289eed41e191103b22f2a015408b0ca62aebbbb418b19002ba6c216915bcb
```

This identifies the locally tested build, not a guarantee that another checkout
or toolchain produces identical bytes. Generated firmware and private hardware
logs/backups are not committed.

## Reproduce the screen simulations

Use a host C/C++ compiler, SDL2 development files, Pillow, pyserial, and the
pinned M5GFX source above. Place public PNG sprites named `25.png`, `133.png`,
`6.png`, `94.png`, `448.png`, `493.png` in a local input directory, then run:

```sh
python tools/ldn/papers3_preview.py --m5gfx /path/to/M5GFX \
  --sprites /path/to/sprites --output /tmp/papers3-preview
```

The default SDL2 prefix is `/opt/homebrew`; override it with `--sdl-prefix`.
This compiles the firmware's actual drawing functions and C DISPLAY parser on
an M5GFX RAM canvas without opening a window, serial port or physical device.
The checked-in gallery, six individual simulations and provenance manifest are
in [docs/assets/papers3](docs/assets/papers3). Public artwork comes from
[PokeAPI/sprites](https://github.com/PokeAPI/sprites): FireRed/LeafGreen front
sprites through species 386, default front sprites for Lucario and Arceus,
converted by the existing host `to_bits` routine. Artwork and Pokemon characters
remain the property of their respective owners. These are display fixtures,
not a statement that all six Pokemon are legal offers in the selected game.

## Reuse on this PaperS3

1. Connect USB and start the desktop App with the previously configured keys.
2. Confirm Wireless 1.6.2 / PaperS3 is detected. Do not replace the custom image
   with the generic S3 firmware through the App's installer.
3. Enable sprite downloads or supply the App's cached sprites if artwork is
   desired; otherwise the panel uses a Poke Ball fallback.
4. Select the game and local session in the App. Codes and controls remain on
   the computer; the panel displays snapshots of App/radio state.
5. Stop the session in the App when finished. A retained e-paper image is not
   proof that the radio is still powered or connected.

## Recovery and privacy

Back up the entire physical Flash before the first write and keep verified
copies private, outside Git. With USB connected, hold the side power button
until the rear red light flashes to enter ROM download mode. A readback-verified
variant 1 merged image at 0x0 restores radio-only operation; the original full
backup restores the exact pre-PokeLDN contents. Either write needs authorization.

Sources: [M5 PaperS3](https://docs.m5stack.com/en/core/PaperS3),
[pinned M5GFX setup](https://github.com/m5stack/M5GFX/blob/347a23274081a105cb9fc0fc3bbf0e15c78e79c3/src/M5GFX.cpp#L2414),
[PokeLDN DISPLAY protocol](docs/hardware_esp32.md#the-screen).
