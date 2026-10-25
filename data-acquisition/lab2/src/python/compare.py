"""raw vs opamp comparison of one pump pulse: spectra, plateau noise/SNR, Pa per ADC step.

Reads Lab 2 logger CSVs and Lab 1 CSVs (t_ms,adc,...). kPa uses the Atom-page
linear constants; without --*-cal they come from the MPX5700AP datasheet chain
in mpx5700.py with the arguments given here. Results are only as good as those
constants: say in the report which ones were used.
"""
import argparse
import bisect
import csv
import json
import math
from pathlib import Path
import statistics

import mpx5700
from analyze import spectrum

CLIP_LOW, CLIP_HIGH = 50, 4045   # same defaults as logger.py


def load_csv(path, run=None):
    """One run from a Lab 1 or Lab 2 CSV: seconds from first sample, ADC codes, metadata."""
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not {"t_ms", "adc"} <= set(reader.fieldnames):
            raise ValueError(f"{path}: CSV needs t_ms and adc columns")
        rows = [r for r in reader if r.get("adc") not in (None, "")]
    if "run_id" in (reader.fieldnames or []):
        runs = list(dict.fromkeys(r["run_id"] for r in rows))
        if run is None and len(runs) > 1:
            raise ValueError(f"{path}: several runs {runs}; choose one with --raw-run/--opamp-run")
        run = run or (runs[0] if runs else None)
        rows = [r for r in rows if r["run_id"] == run]
    if len(rows) < 8:
        raise ValueError(f"{path}: needs at least eight samples")
    first, last, t = int(rows[0]["t_ms"]), int(rows[0]["t_ms"]), [0.0]
    elapsed = 0
    for r in rows[1:]:
        now = int(r["t_ms"])
        dt = (now - last) & 0xffffffff   # millis() rollover
        if not 1 <= dt <= 500:
            raise ValueError(f"{path}: nonmonotonic time or gap of {dt} ms")
        elapsed += dt; last = now
        t.append(elapsed / 1000)
    meta = {k: rows[0][k] for k in ("config", "condition", "trial", "run_id") if k in rows[0]}
    return dict(source=str(path), t=t, adc=[int(r["adc"]) for r in rows], t0_ms=first, meta=meta)


def window(t, bounds):
    """Indices of samples in [start, end) seconds; t is sorted."""
    ix = range(bisect.bisect_left(t, bounds[0]), bisect.bisect_left(t, bounds[1]))
    if len(ix) < 2:
        raise ValueError(f"window {list(bounds)} s needs at least two samples")
    return ix


def auto_plateau(t, p, baseline, length):
    """Steadiest window among those at >= 80 % of the largest deviation from baseline."""
    base = statistics.mean(p[i] for i in window(t, baseline))
    step, candidates = 0.1, []
    start = baseline[1]
    while start + length <= t[-1]:
        values = p[bisect.bisect_left(t, start):bisect.bisect_left(t, start + length)]
        if len(values) >= 2:
            candidates.append((start, abs(statistics.mean(values) - base), statistics.stdev(values)))
        start = round(start + step, 6)
    if not candidates:
        raise ValueError("run too short for an automatic plateau; give --*-plateau")
    peak = max(c[1] for c in candidates)
    best = min((c for c in candidates if c[1] >= 0.8 * peak), key=lambda c: c[2])
    return [best[0], round(best[0] + length, 6)]


def snr(t, adc, p, baseline, plateau, clip):
    if max(baseline[0], plateau[0]) < min(baseline[1], plateau[1]):
        raise ValueError("baseline/plateau windows overlap")
    base, top = window(t, baseline), window(t, plateau)
    signal = statistics.mean(p[i] for i in top) - statistics.mean(p[i] for i in base)
    noise = statistics.stdev(p[i] for i in top)
    saturated = sum(adc[i] <= clip[0] or adc[i] >= clip[1] for i in top)
    return dict(baseline_s=baseline, plateau_s=plateau, signal_kpa=signal,
                plateau_noise_std_kpa=noise, plateau_noise_std_pa=noise * 1000,
                plateau_noise_std_codes=statistics.stdev(adc[i] for i in top),
                snr_db=20 * math.log10(abs(signal) / noise) if signal and noise else None,
                plateau_saturated_samples=saturated,
                note=("plateau touches the ADC floor/ceiling: noise is underestimated, SNR invalid"
                      if saturated else ""))


def events_path(csv_path):
    path = Path(csv_path)
    return path.with_name(path.stem + ".events.csv")


def half_grip(run, p, events, threshold, hold_ms):
    """Time from each marked half_grip onset until p crosses threshold and stays for hold_ms."""
    if events is None or not events.is_file():
        return dict(status="not marked: no events file", expected=str(events))
    with events.open(newline="", encoding="utf-8") as handle:
        onsets = [int(r["atom_t_ms"]) for r in csv.DictReader(handle)
                  if r.get("phase") == "half_grip" and r.get("atom_t_ms")]
    if not onsets:
        return dict(status="not marked: no half_grip rows with atom_t_ms", events=str(events))
    if threshold is None:
        return dict(status="marked, but criterion missing: give --half-grip-kpa",
                    onsets=len(onsets), events=str(events))
    t, results = run["t"], []
    for onset_ms in onsets:
        start = ((onset_ms - run["t0_ms"]) & 0xffffffff) / 1000
        first = bisect.bisect_left(t, start)
        if start > t[-1]:
            results.append(dict(onset_s=start, time_s=None, note="onset outside run")); continue
        below = p[first] > threshold   # direction: cross away from the onset side
        crossed = lambda i: (p[i] <= threshold) == below
        found = None
        for i in range(first, len(t)):
            end = bisect.bisect_right(t, t[i] + hold_ms / 1000)
            if t[i] + hold_ms / 1000 > t[-1]:
                break   # not enough run left to confirm the hold
            if crossed(i) and all(crossed(j) for j in range(i, end)):
                found = t[i] - start; break
        results.append(dict(onset_s=start, time_s=found,
                            note="" if found is not None else "threshold not crossed"))
    times = [r["time_s"] for r in results if r["time_s"] is not None]
    return dict(status="measured" if times else "no crossing", threshold_kpa=threshold,
                hold_ms=hold_ms, events=str(events), onsets=results,
                mean_s=statistics.mean(times) if times else None,
                stdev_s=statistics.stdev(times) if len(times) > 1 else None)


def analyse(run, constants, args, prefix):
    adc, t = run["adc"], run["t"]
    p = mpx5700.to_kpa(adc, constants)
    gaps = [round((b - a) * 1000) for a, b in zip(t, t[1:])]
    fs = 1000 / statistics.median(gaps)
    clip = (args.clip_low, args.clip_high)
    baseline = getattr(args, prefix + "_baseline") or [0.0, 1.0]
    plateau = getattr(args, prefix + "_plateau")
    chosen = "manual" if plateau else "auto"
    plateau = plateau or auto_plateau(t, p, baseline, args.plateau_len)
    lo, hi = min(adc), max(adc)
    return p, fs, dict(
        source=run["source"], meta=run["meta"], rows=len(adc), duration_s=t[-1],
        rate_hz=fs, dt_min_ms=min(gaps), dt_max_ms=max(gaps), calibration=constants,
        pa_per_adc_step=mpx5700.pa_per_step(constants),
        adc_min=lo, adc_max=hi, adc_range_used_percent=(hi - lo) / 4095 * 100,
        floor_samples=sum(a <= clip[0] for a in adc), ceiling_samples=sum(a >= clip[1] for a in adc),
        clip_thresholds=list(clip), plateau_choice=chosen,
        snr=snr(t, adc, p, baseline, plateau, clip),
        half_grip=half_grip(run, p, getattr(args, prefix + "_events") or events_path(run["source"]),
                            args.half_grip_kpa, args.half_grip_hold_ms))


def constants_for(args, prefix):
    cal = getattr(args, prefix + "_cal")
    if cal:
        return mpx5700.check(dict(zip(mpx5700.ATOM_FIELDS, cal)))
    if prefix == "raw":
        return mpx5700.atom_constants(args.volts_per_count, args.voltage_offset, args.vs,
                                      p_atm_kpa=args.p_atm_kpa)
    if args.opamp_gain is None or args.opamp_vref is None:
        raise ValueError("opamp needs --opamp-gain and --opamp-vref, or --opamp-cal")
    return mpx5700.atom_constants(args.volts_per_count, args.voltage_offset, args.vs,
                                  args.opamp_gain, args.opamp_vref, args.opamp_divider, args.p_atm_kpa)


def plot(out, runs, fs, pressure, summary):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    for name in ("raw", "opamp"):
        ax.plot(runs[name]["t"], pressure[name], label=name)
        for key, colour in (("baseline_s", "grey"), ("plateau_s", "green")):
            ax.axvspan(*summary[name]["snr"][key], color=colour, alpha=.1)
    ax.set(xlabel="Time from run start (s)", ylabel="Relative pressure (kPa)")
    ax.legend(); fig.tight_layout(); fig.savefig(out/"pressure_time.png"); plt.close(fig)
    fig, axes = plt.subplots(2, 1, sharex=True, sharey=True)
    for name in ("raw", "opamp"):
        t, p = runs[name]["t"], pressure[name]
        axes[0].semilogy(*spectrum([v * 1000 for v in p], fs[name]), label=name)
        top = window(t, summary[name]["snr"]["plateau_s"])
        axes[1].semilogy(*spectrum([p[i] * 1000 for i in top], fs[name]), label=name)
    axes[0].set(title="Whole run", ylabel="PSD (kPa²/Hz)")
    axes[1].set(title="Plateau window", xlabel="Frequency (Hz)", ylabel="PSD (kPa²/Hz)")
    for ax in axes: ax.legend()
    fig.tight_layout(); fig.savefig(out/"spectra.png"); plt.close(fig)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    pair = lambda s: [float(x) for x in s.split(",")]
    p.add_argument("raw", type=Path); p.add_argument("opamp", type=Path)
    p.add_argument("--out", type=Path, required=True, help="new output directory (never overwritten)")
    p.add_argument("--raw-run"); p.add_argument("--opamp-run")
    p.add_argument("--volts-per-count", type=float, default=mpx5700.LAB1_VOLTS_PER_COUNT,
                   help="ADC V/code at G5 (default Lab 1 empirical 3.70/4095)")
    p.add_argument("--voltage-offset", type=float, default=0.0, help="V at code 0")
    p.add_argument("--vs", type=float, default=mpx5700.VS_NOMINAL, help="measured sensor supply, V (default nominal 5.0)")
    p.add_argument("--p-atm-kpa", type=float, default=mpx5700.P_ATM_NOMINAL, help="relative-pressure zero, kPa abs")
    p.add_argument("--opamp-gain", type=float, help="A = 1 + Rf/Rref of the measured stage")
    p.add_argument("--opamp-vref", type=float, help="buffered Vref (J27) during the run, V")
    p.add_argument("--opamp-divider", type=float, default=1.0, help="V_G5/Vout; 0.5 for the 25.10 10k/10k divider")
    for name in ("raw", "opamp"):
        p.add_argument(f"--{name}-cal", type=float, nargs=4, metavar=("VPC", "VOFF", "KPV", "POFF"),
                       help="Atom-page constants volts_per_count voltage_offset_v kpa_per_volt pressure_offset_kpa")
        p.add_argument(f"--{name}-baseline", type=pair, metavar="START,END", help="seconds, default 0,1")
        p.add_argument(f"--{name}-plateau", type=pair, metavar="START,END", help="seconds, default automatic")
        p.add_argument(f"--{name}-events", type=Path, help="default <csv stem>.events.csv")
    p.add_argument("--plateau-len", type=float, default=1.0, help="automatic plateau length, s")
    p.add_argument("--clip-low", type=int, default=CLIP_LOW); p.add_argument("--clip-high", type=int, default=CLIP_HIGH)
    p.add_argument("--half-grip-kpa", type=float, help="team's discrimination threshold, kPa relative")
    p.add_argument("--half-grip-hold-ms", type=float, default=100)
    args = p.parse_args(argv)
    for key in ("raw_baseline", "raw_plateau", "opamp_baseline", "opamp_plateau"):
        value = getattr(args, key)
        if value is not None and (len(value) != 2 or not value[0] < value[1]):
            p.error(f"--{key.replace('_', '-')} needs START,END with START < END")
    if not 0 <= args.clip_low < args.clip_high <= 4095:
        p.error("need 0 <= --clip-low < --clip-high <= 4095")
    return args


def main(argv=None):
    args = parse_args(argv)
    try:
        if not args.raw.is_file() or not args.opamp.is_file():
            print("CSV puudub; tulemusi ei loodud.")
            return 2
        runs = dict(raw=load_csv(args.raw, args.raw_run), opamp=load_csv(args.opamp, args.opamp_run))
        summary, pressure, fs, warnings = {}, {}, {}, []
        for name in ("raw", "opamp"):
            config = runs[name]["meta"].get("config")
            if config and config != name:
                warnings.append(f"{name} argument holds a config={config} run")
            pressure[name], fs[name], summary[name] = analyse(runs[name], constants_for(args, name), args, name)
        a, b = runs["raw"]["meta"], runs["opamp"]["meta"]
        if any(k in a and k in b and a[k] != b[k] for k in ("condition", "trial")):
            warnings.append("condition/trial differ: not the same logged pulse protocol")
        if abs(fs["raw"] - fs["opamp"]) > 1:
            warnings.append("sampling rates differ by more than 1 Hz")
        args.out.mkdir(parents=True, exist_ok=False)
        plot(args.out, runs, fs, pressure, summary)
        payload = dict(runs=summary, warnings=warnings,
                       spectrum_method="Mean-subtracted Hann one-sided periodogram (analyze.spectrum), "
                                       "median sample rate, no resampling",
                       snr_method="signal = mean(plateau) - mean(baseline); noise = stdev(plateau, ddof=1)")
        (args.out/"summary.json").write_text(json.dumps(payload, indent=2, allow_nan=False)+"\n")
        print(f"{'':24}{'raw':>14}{'opamp':>14}")
        for label, get in (("Pa / ADC samm", lambda s: f"{s['pa_per_adc_step']:.1f}"),
                           ("ADC vahemik (%)", lambda s: f"{s['adc_range_used_percent']:.1f}"),
                           ("platoo müra (Pa)", lambda s: f"{s['snr']['plateau_noise_std_pa']:.1f}"),
                           ("signaal (kPa)", lambda s: f"{s['snr']['signal_kpa']:.2f}"),
                           ("SNR (dB)", lambda s: "—" if s["snr"]["snr_db"] is None else f"{s['snr']['snr_db']:.1f}"),
                           ("põrand/lagi proove", lambda s: f"{s['floor_samples']}/{s['ceiling_samples']}"),
                           ("poolik haare (s)", lambda s: "—" if s["half_grip"].get("mean_s") is None
                                                           else f"{s['half_grip']['mean_s']:.3f}")):
            print(f"{label:24}{get(summary['raw']):>14}{get(summary['opamp']):>14}")
        for warning in warnings + [f"{n}: {summary[n]['snr']['note']}" for n in summary if summary[n]["snr"]["note"]]:
            print("HOIATUS:", warning)
        print(f"Tulemused: {args.out} (summary.json, spectra.png, pressure_time.png)")
        return 0
    except (ValueError, KeyError, OSError, ImportError) as error:
        print(f"Võrdlus peatatud: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
