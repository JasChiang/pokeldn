"""Exercise the real e-paper parser with the official host's DISPLAY encoders.

Runs on a desktop without ESP-IDF, hardware, Switch keys or a radio connection:
    python -m unittest discover -s tests -p test_papers3_display_model.py
"""
import ctypes as C
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest

from pokeldn.ldn import esp32

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "firmware/esp32/optional_components/papers3_display"


class Sprite(C.Structure):
    _fields_ = [("width", C.c_uint8), ("height", C.c_uint8), ("bits", C.c_uint8 * 512)]


class Model(C.Structure):
    _fields_ = [("show", C.c_uint8), ("arrived", C.c_bool),
                ("title", C.c_char * 22), ("line", C.c_char * 22), ("sprite", Sprite * 3)]


@unittest.skipUnless(shutil.which("cc"), "a host C compiler is required")
class PaperDisplayModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        output = Path(cls.temp.name) / "paper-model.so"
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                        "-I", str(ROOT / "firmware/esp32/main"), str(COMPONENT / "papers3_model.c"),
                        "-o", str(output)], check=True)
        cls.lib = C.CDLL(str(output))
        cls.lib.paper_model_command.argtypes = [C.POINTER(Model), C.c_void_p, C.c_size_t]
        cls.lib.paper_model_command.restype = C.c_bool
        cls.lib.paper_model_reset.argtypes = [C.POINTER(Model)]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.model = Model()

    def command(self, payload):
        return self.lib.paper_model_command(C.byref(self.model), payload, len(payload))

    def test_host_trade_and_receipt_commands(self):
        self.assertTrue(self.command(esp32.display_show_payload("trade", 0, "Legends ZA", "Pikachu")))
        self.assertEqual((self.model.show, self.model.title, self.model.line),
                         (1, b"Legends ZA", b"Pikachu"))
        self.assertTrue(self.command(esp32.display_show_payload("traded", 24, "Legends ZA", "Eevee")))
        self.assertEqual(self.model.show, 2)
        self.assertFalse(self.model.arrived)
        self.assertTrue(self.command(esp32.display_show_payload("arrived")))
        self.assertTrue(self.model.arrived)
        self.assertEqual(self.model.line, b"Eevee")

    def test_odd_width_and_maximum_sprite_keep_stride_and_bit_order(self):
        for slot_index, slot in enumerate(("ours", "theirs", "gift")):
            for width, height in ((1, 1), (13, 9), (64, 64)):
                rows = [[(x + 3 * y) % 5 < 2 for x in range(width)] for y in range(height)]
                self.assertTrue(self.command(esp32.display_sprite_payload(slot, rows)))
                sprite = self.model.sprite[slot_index]
                self.assertEqual((sprite.width, sprite.height), (width, height))
                decoded = [[bool(sprite.bits[y * ((width + 7) // 8) + x // 8] & (0x80 >> (x % 8)))
                            for x in range(width)] for y in range(height)]
                self.assertEqual(decoded, rows)

    def test_invalid_or_truncated_sprite_never_changes_model(self):
        self.command(esp32.display_show_payload("gift", 0, "Gift", "Clefairy"))
        good = esp32.display_sprite_payload("ours", [[True] * 64] * 64)
        invalid = [b"", b"\x00", bytes((0, 6, 0, 0)), bytes((1, 3, 0, 0)),
                   bytes((1, 0, 65, 1)) + bytes(9), good + b"x"]
        invalid += [good[:i] for i in range(len(good))]
        for payload in invalid:
            before = bytes(self.model)
            self.assertFalse(self.command(payload))
            self.assertEqual(bytes(self.model), before)

    def test_unterminated_and_non_ascii_text_is_bounded(self):
        self.assertTrue(self.command(bytes((0, 1, 0, 0)) + b"A" * 100 + b"\0" + b"\xff" * 100))
        self.assertEqual(self.model.title, b"A" * 21)
        self.assertEqual(self.model.line, b"?" * 21)
        self.assertEqual(self.model.sprite[0].width, 0)

    def test_arrival_does_not_replace_unrelated_view_and_reset_clears_all_slots(self):
        self.command(esp32.display_show_payload("gift", 0, "Gift", "Pikachu"))
        self.command(esp32.display_show_payload("arrived"))
        self.assertEqual(self.model.show, 3)
        self.assertFalse(self.model.arrived)
        self.command(esp32.display_sprite_payload("gift", [[True] * 8] * 8))
        self.lib.paper_model_reset(C.byref(self.model))
        self.assertEqual(bytes(self.model), bytes(Model()))

    def test_random_wire_bytes_preserve_bounds_and_invalid_atomicity(self):
        randomizer = random.Random(42026)
        for _ in range(10000):
            payload = randomizer.randbytes(randomizer.randrange(0, 600))
            before = bytes(self.model)
            accepted = self.command(payload)
            if not accepted:
                self.assertEqual(bytes(self.model), before)
            self.assertLess(self.model.show, 6)
            for sprite in self.model.sprite:
                self.assertLessEqual(sprite.width, 64)
                self.assertLessEqual(sprite.height, 64)


if __name__ == "__main__":
    unittest.main()
