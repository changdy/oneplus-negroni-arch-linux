"""Host-only fault injection for the experimental voice helper's rollback."""
import importlib.util
from pathlib import Path
import signal
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "config/audio/voice/negroni-voice-test.py"
spec = importlib.util.spec_from_file_location("voice_test", SCRIPT)
voice = importlib.util.module_from_spec(spec)
spec.loader.exec_module(voice)


class FakeMixer:
    def __init__(self):
        self.values = {"numid=1": "7,9", "numid=2": "0"}
        self.writes = []
        self.fail_apply = False
        self.fail_restore = False

    def get(self, selector):
        selector = {"name=first": "numid=1", "name=second": "numid=2"}.get(selector, selector)
        return selector, self.values[selector]

    def set(self, selector, value):
        self.writes.append((selector, value))
        if self.fail_restore and (selector, value) == ("numid=2", "0"):
            raise OSError("restore failed")
        self.values[selector] = value
        if self.fail_apply and (selector, value) == ("numid=2", "1"):
            raise OSError("partial mixer failure")


class FakeAlsa:
    def __init__(self):
        self.operations = []
        self.fail_start = False
        self.fail_close = False

    def open(self, name, capture):
        self.operations.append(("open", capture))
        return "tx" if capture else "rx"

    def start(self, pcm, capture):
        self.operations.append(("start", pcm))
        if self.fail_start:
            raise OSError("DSP rejected graph")

    def close(self, pcm):
        self.operations.append(("close", pcm))
        if self.fail_close and pcm == "tx":
            raise OSError("close failed")


class VoiceTest(unittest.TestCase):
    def setUp(self):
        self.mixer, self.alsa = FakeMixer(), FakeAlsa()
        self.original = dict(self.mixer.values)

    def run_voice(self, wait=lambda _: None):
        voice.run_test(self.alsa, self.mixer, 0, 4, 5, 1, wait=wait,
                       routes=(("first", "1"), ("second", "1")))

    def test_sequence_and_exact_vector_restore(self):
        self.run_voice()
        self.assertEqual(self.alsa.operations, [("open", True), ("open", False),
                         ("start", "rx"), ("start", "tx"), ("close", "tx"), ("close", "rx")])
        self.assertEqual(self.mixer.values, self.original)

    def test_partially_failed_mixer_write_is_rolled_back(self):
        self.mixer.fail_apply = True
        with self.assertRaisesRegex(OSError, "partial mixer"):
            self.run_voice()
        self.assertEqual(self.mixer.values, self.original)
        self.assertFalse(self.alsa.operations)

    def test_start_failure_closes_both_and_restores(self):
        self.alsa.fail_start = True
        with self.assertRaisesRegex(OSError, "DSP rejected"):
            self.run_voice()
        self.assertEqual(self.alsa.operations[-2:], [("close", "tx"), ("close", "rx")])
        self.assertEqual(self.mixer.values, self.original)

    def test_signal_restores_and_propagates(self):
        def interrupt(_):
            raise voice.StopRequested(signal.SIGTERM)
        with self.assertRaises(voice.StopRequested):
            self.run_voice(interrupt)
        self.assertEqual(self.mixer.values, self.original)
        self.assertEqual(self.alsa.operations[-2:], [("close", "tx"), ("close", "rx")])

    def test_cleanup_failure_does_not_skip_other_cleanup(self):
        self.mixer.fail_restore = self.alsa.fail_close = True
        with self.assertRaisesRegex(RuntimeError, "cleanup incomplete.*close PCM.*restore second"):
            self.run_voice()
        self.assertIn(("close", "rx"), self.alsa.operations)
        self.assertEqual(self.mixer.values["numid=1"], self.original["numid=1"])

    def test_active_pcm_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory)
            status = proc / "card0/pcm0p/sub0/status"
            status.parent.mkdir(parents=True)
            status.write_text("state: RUNNING\nowner_pid: 123\n")
            with self.assertRaisesRegex(RuntimeError, "audio clients"):
                voice.check_idle(0, proc)


if __name__ == "__main__":
    unittest.main()
