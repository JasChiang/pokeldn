"""Render the unchanged PaperS3 firmware drawing functions on an M5GFX RAM sprite.

Requires a host C/C++ compiler, SDL2 development files, Pillow, pyserial, and the
pinned M5GFX source. No window, USB, keys or hardware access. Inputs are public
Pokemon PNG sprites named <species>.png in --sprites. Outputs are simulations,
not photographs or framebuffer reads from a physical PaperS3.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from PIL import Image, ImageDraw, ImageFont
from pokeldn.app.screen import to_bits
from pokeldn.ldn.esp32 import display_show_payload, display_sprite_payload

DEMO = [(25, 'Pikachu'), (133, 'Eevee'), (6, 'Charizard'), (94, 'Gengar'),
        (448, 'Lucario'), (493, 'Arceus')]

PRELUDE = r'''
#include <M5GFX.h>
#include <cstring>
#include <fstream>
#include <iostream>
#include "papers3_model.h"
#include "scene.h"
class PaperDisplay : public lgfx::LGFX_Sprite {
public:
    PaperDisplay() : LGFX_Sprite(nullptr) {
        setColorDepth(16);
        if (!createSprite(960, 540)) throw std::runtime_error("RAM canvas allocation failed");
    }
    void setEpdMode(lgfx::epd_mode_t) {}
    void display() {}
    void waitDisplay() {}
};
'''
MAIN = r'''
int main(int argc, char **argv) {
    if (argc != 3) return 2;
    paper_model_t model{};
    std::ifstream commands(argv[1], std::ios::binary);
    for (;;) {
        unsigned char length[2];
        if (!commands.read(reinterpret_cast<char *>(length), 2)) break;
        const unsigned n = length[0] | length[1] << 8;
        unsigned char payload[PAPER_COMMAND_MAX];
        if (n > sizeof(payload) || !commands.read(reinterpret_cast<char *>(payload), n)) return 3;
        if (!paper_model_command(&model, payload, n)) return 4;
    }
    PaperDisplay canvas;
    scene_radio_t radio{};
    radio.mode = SCENE_IDLE; // matches the display-only hardware demo
    draw(canvas, model, radio, true);
    std::ofstream out(argv[2], std::ios::binary);
    out << "P6\n960 540\n255\n";
    for (int y=0; y<540; ++y) for (int x=0; x<960; ++x) {
        const uint16_t p = canvas.readPixel(x, y);
        const unsigned char rgb[3] = {
            static_cast<unsigned char>(((p >> 11) & 31) * 255 / 31),
            static_cast<unsigned char>(((p >> 5) & 63) * 255 / 63),
            static_cast<unsigned char>((p & 31) * 255 / 31)};
        out.write(reinterpret_cast<const char *>(rgb), 3);
    }
    return out.good() ? 0 : 5;
}
'''


def build(gfx, temp, sdl):
    # Extract the very same renderer rather than maintaining a second layout.
    source = ROOT / 'firmware/esp32/optional_components/papers3_display/display_papers3.cpp'
    text = source.read_text()
    drawing = text[text.index('const char *radio_label('):text.index('void display_task(')]
    driver = temp / 'preview.cpp'
    driver.write_text(PRELUDE + drawing + MAIN)
    includes = ['-I', str(gfx / 'src'), '-I', str(sdl / 'include'),
                '-I', str(ROOT / 'firmware/esp32/main'),
                '-I', str(ROOT / 'firmware/esp32/optional_components/papers3_display')]
    base = gfx / 'src/lgfx'
    sources = [base / 'v1' / name for name in (
        'lgfx_v1.cpp', 'lgfx_v1_panel.cpp', 'lgfx_v1_touch.cpp',
        'lgfx_v1_platforms.cpp', 'LGFXBase.cpp', 'lgfx_fonts.cpp')]
    sources += [base / 'utility' / name for name in (
        'lgfx_miniz.c', 'lgfx_pngle.c', 'lgfx_qoi.c', 'lgfx_qrcode.c', 'lgfx_tjpgd.c')]
    sources += [ROOT / 'firmware/esp32/optional_components/papers3_display/papers3_model.c', driver]

    def compile_one(item):
        index, src = item
        obj = temp / f'{index}.o'
        cpp = src.suffix == '.cpp'
        subprocess.run([('c++' if cpp else 'cc'), '-O2', '-DLGFX_SDL',
                        *(['-std=c++17'] if cpp else ['-std=c11']), *includes,
                        '-c', str(src), '-o', str(obj)], check=True, capture_output=True)
        return obj

    with ThreadPoolExecutor(max_workers=4) as pool:
        objects = list(pool.map(compile_one, enumerate(sources)))
    binary = temp / 'papers3-preview'
    subprocess.run(['c++', *map(str, objects), '-L', str(sdl / 'lib'),
                    '-lSDL2', '-Wl,-dead_strip', '-o', str(binary)], check=True)
    return binary, hashlib.sha256(drawing.encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--m5gfx', required=True, type=Path)
    parser.add_argument('--sdl-prefix', type=Path, default=Path('/opt/homebrew'))
    parser.add_argument('--sprites', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='papers3-preview-') as folder:
        temp = Path(folder)
        binary, draw_hash = build(args.m5gfx.resolve(), temp, args.sdl_prefix)
        cards, manifest = [], []
        for species, name in DEMO:
            raw = (args.sprites / f'{species}.png').read_bytes()
            rows = to_bits(raw)
            if not rows:
                raise ValueError(f'Invalid sprite for {name}')
            packets = [display_sprite_payload('ours', rows),
                       display_show_payload('trade', 0, 'Legends ZA', name)]
            command_file = temp / f'{species}.commands'
            command_file.write_bytes(b''.join(len(p).to_bytes(2, 'little') + p for p in packets))
            ppm = temp / f'{species}.ppm'
            subprocess.run([str(binary), str(command_file), str(ppm)], check=True)
            # Panel waveform, ghosting and real lighting are deliberately not simulated.
            canvas = Image.open(ppm).convert('L')
            canvas = canvas.point(lambda v: round(v / 17) * 17)
            assert canvas.size == (960, 540)
            canvas.save(args.output / f'{species}-{name.lower()}-simulation.png')
            card = Image.new('L', (960, 584), 255)
            card.paste(canvas, (0, 44))
            d = ImageDraw.Draw(card)
            d.text((20, 12), f'{name} | FIRMWARE RENDER SIMULATION - NOT A DEVICE PHOTO', fill=0,
                   font=ImageFont.load_default(size=17))
            cards.append(card)
            manifest.append({'species': species, 'name': name,
                             'sprite_sha256': hashlib.sha256(raw).hexdigest(),
                             'one_bit_size': [len(rows[0]), len(rows)]})
        gallery = Image.new('L', (1920, 3 * 584), 220)
        for index, card in enumerate(cards):
            gallery.paste(card, ((index % 2) * 960, (index // 2) * 584))
        gallery.save(args.output / 'gallery-simulation.png')
        metadata = {'kind': 'firmware renderer simulation, not a hardware capture',
                    'drawing_source_sha256': draw_hash, 'canvas': [960, 540],
                    'renderer': 'unchanged firmware draw functions + M5GFX LGFX_Sprite and Font2/Font4',
                    'limitations': 'No panel waveforms, ghosting, ambient lighting or hardware framebuffer readback',
                    'sprites_source': 'https://github.com/PokeAPI/sprites', 'examples': manifest}
        (args.output / 'simulation-metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
        print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as error:
        if error.stderr:
            sys.stderr.write(error.stderr.decode(errors='replace'))
        raise
