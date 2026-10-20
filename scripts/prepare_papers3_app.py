"""Make a separate macOS v0.32.0 App copy with this fork's PLA preview fix.

No firmware, keys, settings or game records are read or written. The official
App is preserved. Its bundled, runpy-loaded PLA launcher is replaced in the copy,
then the copy is ad-hoc signed, as the upstream macOS packer does.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_PLA_SHA256 = "ac42a31ba045026ce60341a72ed8b5cfdb01e246b386d715160e8c1ab2f66b6d"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    if sys.platform != "darwin":
        parser.error("this helper is only for macOS")
    if output.exists() or source == output or source in output.parents:
        parser.error("output must be a new location outside the original App")
    if source.suffix != ".app" or output.suffix != ".app":
        parser.error("source and output must be .app bundles")
    relative = Path("Contents/Resources/bin/pla_host.py")
    original = (source / relative).read_bytes()
    if hashlib.sha256(original).hexdigest() != OFFICIAL_PLA_SHA256:
        parser.error("unexpected bundled PLA launcher; only official v0.32.0 is supported")
    patched = (ROOT / "bin/pla_host.py").read_bytes()
    if patched == original:
        parser.error("the source checkout has no PLA launcher fix")
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ditto", str(source), str(output)], check=True)
    (output / relative).write_bytes(patched)
    # Only a data script changed. Leave the nested executable signatures intact.
    subprocess.run(["codesign", "--force", "--sign", "-", str(output)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(output)], check=True)
    manifest = {"base": "official PokeLDN v0.32.0 macOS App",
                "patched_file": str(relative), "original_sha256": OFFICIAL_PLA_SHA256,
                "patched_sha256": hashlib.sha256(patched).hexdigest(),
                "change": "PLA initial preview follows successful transport.start()",
                "signature": "local ad-hoc, not Developer ID or notarization",
                "firmware_changed": False, "official_app_preserved": True}
    (output.parent / (output.stem + "-patch.json")).write_text(json.dumps(manifest, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    main()
