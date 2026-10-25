"""compare.py, mpx5700.py and calibrate.py. Synthetic inputs in TemporaryDirectory;
RealFileSmokeTests only read repo CSVs and write to a temporary directory."""
import contextlib
import csv
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB/"src/python"))
import calibrate
import compare
import mpx5700
from logger import FIELDS

RUN, OTHER = "0123456789abcdef", "fedcba9876543210"


def adc_for(kpa, constants):
    """Inverse of the Atom-page formula, for synthetic data."""
    c = constants
    return round(((kpa - c["pressure_offset_kpa"]) / c["kpa_per_volt"] - c["voltage_offset_v"]) / c["volts_per_count"])


def pulse(t):
    """Synthetic pump pulse: 0 kPa, -50 kPa plateau from 2 s to 6 s."""
    return -50.0 if 2 <= t < 6 else 0.0


def write_lab2(path, codes, run=RUN, config="raw", t0=0, condition="pulse", trial=1):
    with path.open("a" if path.exists() else "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if handle.tell() == 0:
            writer.writeheader()
        for i, code in enumerate(codes):
            writer.writerow(dict(zip(FIELDS, [(t0 + 10*i) & 0xffffffff, code, "", "", config, run, i, 0,
                                              "", "", "", condition, trial, 0])))


def write_lab1(path, codes):
    with path.open("w", newline="") as handle:
        handle.write("t_ms,adc,p_kpa,pump\n")
        for i, code in enumerate(codes):
            handle.write(f"{1000+10*i},{code},,0\n")


RAW = mpx5700.atom_constants()
OPAMP = mpx5700.atom_constants(gain=2.18, vref=0.48)


def codes(constants, noise=(0, 1, 0, -1)):
    return [adc_for(pulse(i/100), constants) + noise[i % len(noise)] for i in range(1000)]


class Mpx5700Tests(unittest.TestCase):
    def test_lab1_raw_baseline_141_pa_per_code(self):
        self.assertAlmostEqual(mpx5700.pa_per_step(RAW), 140.5, delta=0.1)

    def test_opamp_chain_roundtrip(self):
        # P -> Vin (datasheet) -> Vout (stage) -> G5 (divider) -> code -> P
        vs, gain, vref, d = 4.9, 2.18, 0.48, 0.5
        c = mpx5700.atom_constants(0.0009, 0.0, vs, gain, vref, d, p_atm_kpa=100)
        for kpa in (-70, 0, 110):
            vin = vs * (mpx5700.SLOPE * (kpa + 100) + mpx5700.OFFSET)
            code = d * (gain * vin - (gain - 1) * vref) / 0.0009
            self.assertAlmostEqual(mpx5700.to_kpa([code], c)[0], kpa, places=6)
        self.assertAlmostEqual(mpx5700.pa_per_step(c), 0.9 / (d * gain * vs * mpx5700.SLOPE), places=6)

    def test_invalid_constants(self):
        for bad in (dict(RAW, kpa_per_volt=0), dict(RAW, volts_per_count=math.nan), {"kpa_per_volt": 1}):
            with self.subTest(bad=bad), self.assertRaises(ValueError): mpx5700.check(bad)
        with self.assertRaises(ValueError): mpx5700.atom_constants(gain=0)


class CompareTests(unittest.TestCase):
    def run_compare(self, tmp, raw, opamp, *extra):
        out = Path(tmp)/"out"
        with contextlib.redirect_stdout(io.StringIO()) as text:
            code = compare.main([str(raw), str(opamp), "--out", str(out),
                                 "--opamp-gain", "2.18", "--opamp-vref", "0.48", *extra])
        return code, out, text.getvalue()

    def test_lab1_vs_lab2_pulse(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, opamp = Path(tmp)/"lab1.csv", Path(tmp)/"opamp.csv"
            write_lab1(raw, codes(RAW)); write_lab2(opamp, codes(OPAMP), config="opamp")
            code, out, text = self.run_compare(tmp, raw, opamp)
            self.assertEqual(code, 0, text)
            self.assertTrue((out/"spectra.png").is_file() and (out/"pressure_time.png").is_file())
            runs = json.loads((out/"summary.json").read_text())["runs"]
            for name in ("raw", "opamp"):
                snr = runs[name]["snr"]
                self.assertAlmostEqual(snr["signal_kpa"], -50, delta=0.5)
                self.assertGreaterEqual(snr["plateau_s"][0], 2); self.assertLessEqual(snr["plateau_s"][1], 6)
                self.assertAlmostEqual(runs[name]["rate_hz"], 100)
            # same code noise, finer step -> lower Pa noise and higher SNR after the stage
            self.assertLess(runs["opamp"]["pa_per_adc_step"], runs["raw"]["pa_per_adc_step"])
            self.assertGreater(runs["opamp"]["snr"]["snr_db"], runs["raw"]["snr"]["snr_db"])
            self.assertGreater(runs["opamp"]["adc_range_used_percent"], runs["raw"]["adc_range_used_percent"])

    def test_output_dir_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, opamp = Path(tmp)/"raw.csv", Path(tmp)/"opamp.csv"
            write_lab1(raw, codes(RAW)); write_lab1(opamp, codes(OPAMP))
            (Path(tmp)/"out").mkdir()
            self.assertEqual(self.run_compare(tmp, raw, opamp)[0], 2)

    def test_opamp_needs_stage_parameters_or_cal(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, opamp = Path(tmp)/"raw.csv", Path(tmp)/"opamp.csv"
            write_lab1(raw, codes(RAW)); write_lab1(opamp, codes(OPAMP))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(compare.main([str(raw), str(opamp), "--out", str(Path(tmp)/"a")]), 2)
                cal = [str(OPAMP[k]) for k in mpx5700.ATOM_FIELDS]
                self.assertEqual(compare.main([str(raw), str(opamp), "--out", str(Path(tmp)/"b"),
                                               "--opamp-cal", *cal]), 0)

    def test_multi_run_csv_needs_selection_and_rollover(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"both.csv"
            write_lab2(path, [100]*20, RUN, t0=0xfffffff6); write_lab2(path, [200]*20, OTHER)
            with self.assertRaises(ValueError): compare.load_csv(path)
            run = compare.load_csv(path, RUN)
            self.assertEqual(run["t"][:3], [0, .01, .02])
            self.assertEqual(compare.load_csv(path, OTHER)["adc"][0], 200)

    def test_gap_and_schema_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"gap.csv"; path.write_text("t_ms,adc\n" + "".join(f"{t},1\n" for t in (0, 10, 20, 900, 910, 920, 930, 940)))
            with self.assertRaises(ValueError): compare.load_csv(path)
            path.write_text("time,adc\n1,2\n")
            with self.assertRaises(ValueError): compare.load_csv(path)

    def test_saturated_plateau_flagged(self):
        t = [i/100 for i in range(400)]
        adc = [20 if 2 <= x < 3 else 600 for x in t]
        p = mpx5700.to_kpa(adc, RAW)
        result = compare.snr(t, adc, p, [0, 1], [2, 3], (50, 4045))
        self.assertEqual(result["plateau_saturated_samples"], 100)
        self.assertIn("SNR invalid", result["note"])

    def test_overlapping_windows_rejected(self):
        t = [i/100 for i in range(400)]
        with self.assertRaises(ValueError): compare.snr(t, [1]*400, [0.0]*400, [0, 2], [1, 3], (50, 4045))

    def test_half_grip_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"grip.csv"; write_lab1(path, codes(RAW))
            run = compare.load_csv(path); p = mpx5700.to_kpa(run["adc"], RAW)
            events = compare.events_path(path)
            self.assertEqual(events.name, "grip.events.csv")
            self.assertTrue(compare.half_grip(run, p, events, -20, 100)["status"].startswith("not marked"))
            # onset at 1.5 s (t_ms 1000 + 1500), pulse reaches -50 kPa at 2.0 s
            events.write_text("wall_s,atom_t_ms,cycle,phase,p_kpa\n0,2500,1,half_grip,\n0,,2,suction,\n")
            self.assertIn("criterion missing", compare.half_grip(run, p, events, None, 100)["status"])
            result = compare.half_grip(run, p, events, -20, 100)
            self.assertAlmostEqual(result["mean_s"], 0.5, places=6)
            self.assertIsNone(compare.half_grip(run, p, events, -80, 100)["mean_s"])


class CalibrateTests(unittest.TestCase):
    POINTS = dict(atmosphere=(0.85, 0.48, 2.18*0.85-1.18*0.48),
                  full_suction=(0.40, 0.48, 2.18*0.40-1.18*0.48),
                  full_blowing=(1.56, 0.48, 2.18*1.56-1.18*0.48))

    def test_gain_offset_and_atom_constants(self):
        r = calibrate.calibrate(self.POINTS, vs=5.0, vs_measured=True)
        self.assertAlmostEqual(r["gain"], 2.18); self.assertAlmostEqual(r["vref_effective_v"], 0.48)
        c = r["atom_page"]
        self.assertEqual(set(c), set(mpx5700.ATOM_FIELDS))
        # atmosphere -> 0 kPa, suction/blowing -> datasheet kPa
        for name, (vin, _, vout) in self.POINTS.items():
            code = vout / c["volts_per_count"]
            expected = (vin - 0.85) / (5.0 * mpx5700.SLOPE)
            self.assertAlmostEqual(mpx5700.to_kpa([code], c)[0], expected, places=6)
        self.assertEqual(r["warnings"], [])

    def test_adc_fit_and_warnings(self):
        points = dict(self.POINTS, full_blowing=(1.56, 0.49, 3.4))
        adc = dict(atmosphere=1400, full_suction=340)
        r = calibrate.calibrate(points, adc=adc)
        self.assertIn("fit of G5", r["sources"]["volts_per_count"])
        text = " ".join(r["warnings"])
        for needle in ("nominal", "Vref moved", "above 3.1"):
            self.assertIn(needle, text)
        with self.assertRaises(ValueError): calibrate.calibrate(self.POINTS, adc=dict(atmosphere=1))

    def test_floor_and_bad_input(self):
        floor = dict(self.POINTS, full_suction=(0.40, 0.48, 0.02))
        self.assertIn("floor", " ".join(calibrate.calibrate(floor)["warnings"]))
        with self.assertRaises(ValueError): calibrate.calibrate({"atmosphere": (1, 1, 1)})
        flat = {k: (0.5, 0.4, 1.0) for k in calibrate.POINTS}
        with self.assertRaises(ValueError): calibrate.calibrate(flat)

    def test_cli_prints_atom_fields(self):
        argv = []
        for name, values in self.POINTS.items():
            argv += ["--"+name.replace("_", "-"), *map(str, values)]
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(calibrate.main(argv + ["--json", "--vs", "5.0"]), 0)
        self.assertEqual(set(json.loads(out.getvalue())["atom_page"]), set(mpx5700.ATOM_FIELDS))


class RealFileSmokeTests(unittest.TestCase):
    """25.10 opamp CSVs against Lab 1 raw. Parameters are test values, not results."""
    LAB1 = LAB.parent/"lab1/data/lab1_ownbox_hold_air_02.10.26.csv"

    def test_25_10_opamp_csvs_against_lab1_raw(self):
        names = ("opamp_pump_off_test.csv", "opamp_vacum_test.csv", "opamp_pressure_test.csv")
        if not self.LAB1.is_file() or not all((LAB/"data"/n).is_file() for n in names):
            self.skipTest("repo data not present")
        for name in names:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp, \
                    contextlib.redirect_stdout(io.StringIO()) as text:
                code = compare.main([str(self.LAB1), str(LAB/"data"/name), "--out", str(Path(tmp)/"out"),
                                     "--opamp-gain", "2.542", "--opamp-vref", "0.5", "--opamp-divider", "0.5"])
                self.assertEqual(code, 0, text.getvalue())
                summary = json.loads((Path(tmp)/"out/summary.json").read_text())
                self.assertEqual(summary["runs"]["opamp"]["meta"]["config"], "opamp")
                if name == "opamp_vacum_test.csv":
                    self.assertGreater(summary["runs"]["opamp"]["floor_samples"], 0)


if __name__ == "__main__":
    unittest.main()
