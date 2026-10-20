"""Exercise the real PLA launcher with an instant preview worker and no hardware."""
import importlib.util
from pathlib import Path
import sys

import pytest


@pytest.mark.parametrize("start_ok", [True, False])
def test_first_offer_waits_for_radio_start_and_is_not_sent_after_start_failure(monkeypatch, start_ok):
    path = Path(__file__).resolve().parents[1] / "bin/pla_host.py"
    spec = importlib.util.spec_from_file_location("pla_screen_startup_host", path)
    host = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(host)
    events, offers = [], []

    class Transport:
        ssid = bytes(range(16))
        our_ip = "169.254.1.1"
        join_events = 0

        def __init__(self, **kwargs):
            pass

        def start(self):
            events.append("start")
            if not start_ok:
                raise RuntimeError("scripted initialization failure")
            events.append("ready")

        def stop(self):
            events.append("stop")

    def instant_offer(game, record):
        # A cached image can finish immediately: no download delays hide an
        # attempt to send before USB initialization and its HELLO complete.
        assert "ready" in events, "preview was sent before radio initialization"
        offers.append((game, record))
        events.append("preview")

    monkeypatch.setattr(host, "IpHostTransport", Transport)
    monkeypatch.setattr(host.pokemon_service, "validate", lambda game, record: record)
    monkeypatch.setattr(host.screen, "offer", instant_offer)
    monkeypatch.setattr(sys, "argv", ["pla_host.py", "--ip-host", "--trade-box", "--seconds", "0"])
    assert host.main() == (0 if start_ok else 2)
    if start_ok:
        assert events == ["start", "ready", "preview", "stop"]
        assert len(offers) == 1 and offers[0][0] == "pla" and offers[0][1]
    else:
        assert events == ["start"] and not offers
