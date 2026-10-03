import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model import TAGS, validate, example, scan, stopped, wire_rungs, parse_branch, branch_around, dol_example, blink_example

class ModelTests(unittest.TestCase):
    def test_ton_elapsed_time_reset_and_wrap(self):
        p = {"version": 3, "rungs": [{"kind": "TON", "coil": "T0", "preset_ms": 1000,
                                       "branches": [parse_branch("I0")]}]}
        validate(p); b = dict.fromkeys(TAGS, False); timers = {}; b["I0"] = True
        scan(p, b, 0, timers); self.assertFalse(b["T0"])
        scan(p, b, 999, timers); self.assertFalse(b["T0"])
        scan(p, b, 1000, timers); self.assertTrue(b["T0"])
        b["I0"] = False; scan(p, b, 1001, timers)
        self.assertFalse(b["T0"]); self.assertEqual(timers["T0"]["elapsed"], 0)
        b["I0"] = True; scan(p, b, 1500, timers); self.assertFalse(b["T0"])
        stopped(b, timers); self.assertEqual(timers, {}); self.assertFalse(b["T0"])
        p["rungs"][0]["preset_ms"] = 32
        scan(p, b, 0xfffffff0, timers); scan(p, b, 0x10, timers)
        self.assertTrue(b["T0"])

    def test_blink_has_sustained_on_and_off_phases(self):
        p = validate(blink_example()); b = dict.fromkeys(TAGS, False); timers = {}
        changes = []; previous = False
        for now in range(0, 5001, 10):
            scan(p, b, now, timers)
            if b["Q0"] != previous:
                changes.append((now, b["Q0"])); previous = b["Q0"]
        self.assertEqual(changes, [(1000, True), (2000, False), (3020, True), (4020, False)])
        self.assertEqual(wire_rungs(p), ["T T0 1000 !T1", "T T1 1000 T0", "R Q0 T0,!T1"])
        stopped(b, timers); self.assertFalse(b["Q0"]); self.assertFalse(b["T0"])
        for invalid in (0, -1, 3600001, "1000", True):
            bad = copy.deepcopy(p); bad["rungs"][0]["preset_ms"] = invalid
            with self.assertRaises(ValueError): validate(bad)

    def test_seal_in_stop_and_restart(self):
        p = validate(example()); b = dict.fromkeys(TAGS, False)
        scan(p, b); self.assertFalse(b["Q0"])
        b["I0"] = True; scan(p, b); self.assertTrue(b["Q0"])
        b["I0"] = False; scan(p, b); self.assertTrue(b["Q0"])
        b["I2"] = True; scan(p, b); self.assertTrue(b["Q1"])
        b["I1"] = True; scan(p, b)
        self.assertFalse(b["Q0"]); self.assertFalse(b["Q1"])
        b["I1"] = False; scan(p, b); self.assertFalse(b["Q0"])

    def test_top_to_bottom_memory(self):
        p = {"version": 1, "rungs": [
            {"coil": "M0", "branches": [parse_branch("I0")]},
            {"coil": "Q0", "branches": [parse_branch("M0")]}]}
        validate(p); b = dict.fromkeys(TAGS, False); b["I0"] = True
        scan(p, b); self.assertTrue(b["Q0"])
        stopped(b); self.assertFalse(b["Q0"]); self.assertFalse(b["M0"])

    def test_wire_format(self):
        self.assertEqual(wire_rungs(example()), ["R Q0 I0,!I1;Q0,!I1", "R Q1 Q0,I2"])

    def test_duplicate_coil_and_malformed_projects(self):
        p = example(); p["rungs"][1]["coil"] = "Q0"
        with self.assertRaises(ValueError): validate(p)

    def test_local_branch_does_not_bypass_neighbour_contacts(self):
        original = {"version": 1, "rungs": [{"coil": "Q0", "branches": [parse_branch("!I2,!I1,I0")]}]}
        p = branch_around(original, 0, 2, {"tag": "Q0", "nc": False})
        self.assertEqual(p["version"], 2)
        self.assertEqual(wire_rungs(p), ["R Q0 !I2,!I1,I0;!I2,!I1,Q0"])
        self.assertEqual(len(original["rungs"][0]["branches"]), 1)  # no in-place mutation
        # Exhaust every input and previous coil state, including a held START.
        for mask in range(16):
            b = dict.fromkeys(TAGS, False)
            for i, tag in enumerate(("I0", "I1", "I2", "Q0")): b[tag] = bool(mask & (1 << i))
            expected = (b["I0"] or b["Q0"]) and not b["I1"] and not b["I2"]
            scan(p, b); self.assertEqual(b["Q0"], expected)

    def test_shared_suffix_and_two_screenshot_layouts(self):
        p = {"version": 1, "rungs": [{"coil": "Q0", "branches": [parse_branch("I0,!I1")]}]}
        p = branch_around(p, 0, 0, {"tag": "Q0", "nc": False})
        self.assertEqual(p["rungs"][0]["suffix"], parse_branch("!I1"))
        self.assertEqual(wire_rungs(p), ["R Q0 I0,!I1;Q0,!I1"])
        validate(dol_example())
        with self.assertRaises(ValueError): branch_around(p, 0, 0, {"tag": "M0", "nc": False})
        bad = copy.deepcopy(p); bad["version"] = 1
        with self.assertRaises(ValueError): validate(bad)
        bad = copy.deepcopy(p); bad["rungs"][0]["prefix"] = parse_branch("I0,I0,I0,I0,I0,I0,I0")
        with self.assertRaises(ValueError): validate(bad)
        for bad in (None, {}, {"version": 1, "rungs": []}):
            with self.assertRaises(ValueError): validate(bad)
        for bad in ("I4", "Q4", "M8", "I0,", "", "!!I0"):
            with self.assertRaises(ValueError): parse_branch(bad)
        p = example(); p["rungs"][0]["branches"][0][0]["nc"] = "false"
        with self.assertRaises(ValueError): validate(p)

if __name__ == "__main__": unittest.main()
