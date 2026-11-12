"""Host-only tests for the call-audio daemon's open/close decisions and cleanup."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1] / "config/audio/voice"


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


daemon = load("negroni-call-audio")
voice = load("negroni-voice-test")
ROUTES = (("first", "1"), ("second", "1"))


class FakeMixer:
    def __init__(self):
        self.values = dict([("numid=1", "7,9"), ("numid=2", "0")])
        self.fail_restore = False

    def get(self, selector):
        selector = dict([("name=first", "numid=1"), ("name=second", "numid=2")]).get(selector, selector)
        return selector, self.values[selector]

    def set(self, selector, value):
        if self.fail_restore and (selector, value) == ("numid=2", "0"):
            raise OSError("restore failed")
        self.values[selector] = value


class FakeAlsa:
    def __init__(self):
        self.operations = []
        self.fail_start = False

    def open(self, name, capture):
        self.operations.append(("open", name))
        return "tx" if capture else "rx"

    def start(self, pcm, capture):
        self.operations.append(("start", pcm))
        if self.fail_start:
            raise OSError("DSP rejected graph")

    def close(self, pcm):
        self.operations.append(("close", pcm))


class DaemonTest(unittest.TestCase):
    def setUp(self):
        self.mixer, self.alsa = FakeMixer(), FakeAlsa()
        self.original = dict(self.mixer.values)
        self.states = []
        self.sessions = 0
        self.daemon = daemon.Daemon(lambda: self.states, self.factory, lambda _: None)

    def factory(self):
        self.sessions += 1
        return daemon.Session(voice, self.alsa, self.mixer, 0, 4, 5, routes=ROUTES)

    def test_call_states_parsing(self):
        listing = "    /org/freedesktop/ModemManager1/Call/0 incoming (active)\n" \
                  "    /org/freedesktop/ModemManager1/Call/1 outgoing (terminated)\n"
        detail = dict([("/org/freedesktop/ModemManager1/Call/0", "call.properties.state        : active\n"),
         ("/org/freedesktop/ModemManager1/Call/1", "call.properties.state        : terminated\n")])

        def run(*args):
            return listing if args[0] == "-m" else detail[args[1]]

        self.assertEqual(daemon.call_states(run), ["active", "terminated"])
        self.assertEqual(daemon.call_states(lambda *args: ""), [])

    def test_which_states_want_voice(self):
        self.assertTrue(daemon.wants_voice(["terminated", "active"]))
        self.assertTrue(daemon.wants_voice(["ringing-out"]))
        for state in ("ringing-in", "dialing", "held", "waiting", "terminated", "unknown"):
            self.assertFalse(daemon.wants_voice([state]), state)
        self.assertFalse(daemon.wants_voice([]))

    def test_opens_once_and_closes_when_call_ends(self):
        self.assertIsNone(self.daemon.step())
        self.assertFalse(self.alsa.operations)
        self.states = ["ringing-in"]
        self.assertIsNone(self.daemon.step())
        self.assertFalse(self.alsa.operations)
        self.states = ["active"]
        self.assertEqual(self.daemon.step(), 1.0)
        self.assertEqual(self.daemon.step(), 1.0)
        self.assertEqual(self.sessions, 1)
        self.assertEqual(self.alsa.operations, [("open", "hw:0,5"), ("open", "hw:0,4"),
           ("start", "rx"), ("start", "tx")])
        self.assertNotEqual(self.mixer.values, self.original)
        self.states = ["terminated"]
        self.assertIsNone(self.daemon.step())
        self.assertEqual(self.alsa.operations[-2:], [("close", "tx"), ("close", "rx")])
        self.assertEqual(self.mixer.values, self.original)
        self.assertIsNone(self.daemon.step())
        self.assertEqual(len(self.alsa.operations), 6)

    def test_failed_open_is_cleaned_up_and_retried(self):
        self.alsa.fail_start = True
        self.states = ["active"]
        self.assertEqual(self.daemon.step(), 2.0)
        self.assertIsNone(self.daemon.session)
        self.assertEqual(self.alsa.operations[-2:], [("close", "tx"), ("close", "rx")])
        self.assertEqual(self.mixer.values, self.original)
        self.alsa.fail_start = False
        self.assertEqual(self.daemon.step(), 1.0)
        self.assertEqual(self.sessions, 2)

    def test_shutdown_closes_open_session(self):
        self.states = ["active"]
        self.daemon.step()
        self.daemon.close()
        self.assertEqual(self.mixer.values, self.original)
        self.assertEqual(self.alsa.operations[-2:], [("close", "tx"), ("close", "rx")])

    def test_restore_failure_is_reported_not_raised(self):
        self.states = ["active"]
        self.daemon.step()
        self.mixer.fail_restore = True
        self.states = []
        self.assertIsNone(self.daemon.step())
        self.assertIsNone(self.daemon.session)
        self.assertEqual(self.mixer.values["numid=1"], self.original["numid=1"])

    def test_busy_card_is_waited_for_then_opened(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory)
            status = proc / "card0/pcm1p/sub0/status"
            status.parent.mkdir(parents=True)
            status.write_text("state: RUNNING\n")
            self.assertEqual(len(daemon.card_busy(0, proc)), 1)
            status.write_text("closed\n")
            self.assertEqual(daemon.card_busy(0, proc), [])


CARDS = """Card #43
\tName: alsa_card.platform-sound
\tProperties:
\t\talsa.card = "0"
\tProfiles:
\t\toff: Off (sinks: 0, sources: 0, priority: 0, available: yes)
\tActive Profile: HiFi (Headphones, Mic1, Speaker)
Card #50
\tName: bluez_card.AA
\tProperties:
\t\tdevice.api = "bluez5"
\tActive Profile: a2dp-sink
"""


class DesktopTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.fail = False
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state = Path(self.directory.name) / "state.json"
        self.desktop = daemon.Desktop(0, self.run_pactl, lambda: [1000], self.state)

    def run_pactl(self, uid, *args):
        self.calls.append((uid,) + args)
        if self.fail and args[0] == "set-card-profile":
            raise RuntimeError("no such card")
        return CARDS

    def test_parse_cards_selects_only_the_alsa_card(self):
        self.assertEqual(daemon.parse_cards(CARDS, 0),
            [("alsa_card.platform-sound", "HiFi (Headphones, Mic1, Speaker)")])
        self.assertEqual(daemon.parse_cards(CARDS, 1), [])
        self.assertEqual(daemon.parse_cards("", 0), [])

    def test_release_then_restore_exact_profile(self):
        self.desktop.release()
        self.desktop.release()
        self.assertEqual(self.calls, [(1000, "list", "cards"),
            (1000, "set-card-profile", "alsa_card.platform-sound", "off")])
        self.assertTrue(self.state.exists())
        self.desktop.restore()
        self.assertEqual(self.calls[-1], (1000, "set-card-profile", "alsa_card.platform-sound",
            "HiFi (Headphones, Mic1, Speaker)"))
        self.assertFalse(self.state.exists())
        self.desktop.restore()
        self.assertEqual(len(self.calls), 3)

    def test_failure_to_release_does_not_raise_or_restore(self):
        self.fail = True
        self.desktop.release()
        self.fail = False
        self.desktop.restore()
        self.assertEqual(len(self.calls), 2)

    def test_recover_restores_profile_left_by_a_dead_instance(self):
        self.desktop.release()
        fresh = daemon.Desktop(0, self.run_pactl, lambda: [1000], self.state)
        fresh.recover()
        self.assertEqual(self.calls[-1], (1000, "set-card-profile", "alsa_card.platform-sound",
            "HiFi (Headphones, Mic1, Speaker)"))
        self.assertFalse(self.state.exists())
        fresh.recover()
        self.assertEqual(len(self.calls), 3)

    def test_daemon_releases_before_open_and_restores_after_close(self):
        order = []
        alsa, mixer = FakeAlsa(), FakeMixer()

        class Recorder:
            def release(self):
                order.append("release")

            def restore(self):
                order.append("restore")

        def factory():
            order.append("session")
            return daemon.Session(voice, alsa, mixer, 0, 4, 5, routes=ROUTES)

        states = ["active"]
        subject = daemon.Daemon(lambda: states, factory, lambda _: None, desktop=Recorder())
        subject.step()
        states[:] = []
        subject.step()
        self.assertEqual(order, ["release", "session", "restore"])
        self.assertEqual(alsa.operations[-2:], [("close", "tx"), ("close", "rx")])


if __name__ == "__main__":
    unittest.main()
