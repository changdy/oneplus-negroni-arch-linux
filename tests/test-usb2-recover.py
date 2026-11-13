#!/usr/bin/env python3
"""Check that the experimental MMIO workaround refuses unrelated USB states."""

import contextlib
import importlib.util
import io
from pathlib import Path
import struct
import unittest
from unittest.mock import MagicMock, patch


spec = importlib.util.spec_from_file_location(
    "usb2_recover", Path(__file__).resolve().parents[1] / "scripts/negroni-usb2-recover.py"
)
recover = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recover)

READY = {"role": "device", "mode": "device", "data_role": "host [device]",
         "partner": True, "udc": "a600000.usb", "state": "not attached", "speed": "UNKNOWN"}


class RecoveryGuards(unittest.TestCase):
    def run_recovery(self, states, compatible=b"oplus,negroni\0", apply=True):
        mem = bytearray(4096)
        offset = recover.PHY_CFG0 % 4096
        struct.pack_into("<I", mem, offset, 0x01010101)
        mapped = MagicMock()
        mapped.__enter__.return_value = mem
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch("sys.argv", ["recover"] + (["--apply"] if apply else [])))
            stack.enter_context(patch.object(recover.os, "geteuid", return_value=0, create=True))
            stack.enter_context(patch.object(recover.os, "O_SYNC", 0, create=True))
            for name, value in (("MAP_SHARED", 1), ("PROT_READ", 1), ("PROT_WRITE", 2)):
                stack.enter_context(patch.object(recover.mmap, name, value, create=True))
            stack.enter_context(patch.object(recover.Path, "read_bytes", return_value=compatible))
            stack.enter_context(patch.object(recover, "status", side_effect=states))
            opened = stack.enter_context(patch.object(recover.os, "open", return_value=99))
            stack.enter_context(patch.object(recover.os, "close"))
            mmapped = stack.enter_context(patch.object(recover.mmap, "mmap", return_value=mapped))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            error = None
            try:
                recover.main()
            except SystemExit as exc:
                error = exc
            return error, opened, mmapped, mem

    def test_inspection_and_configured_gadget_never_open_devmem(self):
        for state, apply in ((READY, False), ({**READY, "state": "configured"}, True)):
            with self.subTest(state=state, apply=apply):
                error, opened, _, _ = self.run_recovery([state], apply=apply)
                self.assertIsNone(error)
                opened.assert_not_called()

    def test_host_missing_partner_and_unbound_gadget_refuse_writes(self):
        for change in ({"role": "host"}, {"mode": "host"}, {"data_role": "[host] device"},
                       {"partner": False}, {"udc": ""}, {"state": "default"}):
            with self.subTest(change=change):
                error, opened, _, _ = self.run_recovery([{**READY, **change}])
                self.assertIsNotNone(error)
                opened.assert_not_called()

    def test_other_board_refuses_writes(self):
        error, opened, _, _ = self.run_recovery([], compatible=b"qcom,sm8450-hdk\0")
        self.assertIsNotNone(error)
        opened.assert_not_called()

    def test_role_change_before_write_preserves_register(self):
        error, _, _, mem = self.run_recovery([READY, {**READY, "role": "host"}])
        self.assertIsNotNone(error)
        self.assertEqual(struct.unpack_from("<I", mem, recover.PHY_CFG0 % 4096)[0], 0x01010101)

    def test_recovery_maps_only_phy_and_preserves_other_bits(self):
        error, _, mmapped, mem = self.run_recovery(
            [READY, READY, {**READY, "state": "configured", "speed": "high-speed"}]
        )
        self.assertIsNone(error)
        self.assertEqual(mmapped.call_args.kwargs["offset"], recover.PHY_CFG0 // 4096 * 4096)
        self.assertEqual(struct.unpack_from("<I", mem, recover.PHY_CFG0 % 4096)[0], 0x01010100)


if __name__ == "__main__":
    unittest.main()
