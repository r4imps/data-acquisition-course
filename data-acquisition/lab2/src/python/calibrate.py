"""Three multimeter points of the op-amp stage -> gain, offset and Atom-page kPa constants.

Points: atmosphere, full suction, full blowing; each Vin (C28), Vref (J27), Vout (C26)
measured together against D29. Output fields match smart-solutions lab2 atom_page.md:
volts_per_count, voltage_offset_v, kpa_per_volt, pressure_offset_kpa.
kPa sensitivity is the MPX5700AP datasheet slope at the given Vs, zeroed at the
measured atmosphere point; it is not a reference-pressure calibration.
"""
import argparse
import json
import math
import sys

import mpx5700

POINTS = ("atmosphere", "full_suction", "full_blowing")
G5_MAX_V = 3.1    # same limit as logger --dmm-v
G5_FLOOR_V = 0.05  # ~ logger clip_low 50 codes at 0.9 mV/code


def fit(xs, ys):
    """Least-squares line y = a*x + b and residuals."""
    n = len(xs)
    mx, my = sum(xs)/n, sum(ys)/n
    sxx = sum((x-mx)**2 for x in xs)
    if sxx == 0:
        raise ValueError("all x values equal: cannot fit a line")
    a = sum((x-mx)*(y-my) for x, y in zip(xs, ys))/sxx
    b = my-a*mx
    return a, b, [y-(a*x+b) for x, y in zip(xs, ys)]


def calibrate(points, vs=mpx5700.VS_NOMINAL, divider=1.0, adc=None,
              volts_per_count=mpx5700.LAB1_VOLTS_PER_COUNT, vs_measured=False):
    """points: {name: (vin, vref, vout)}; adc: optional {name: mean ADC code at G5}."""
    if set(points) != set(POINTS):
        raise ValueError(f"need points {POINTS}")
    mpx5700.finite(vs, divider, volts_per_count, *[v for p in points.values() for v in p])
    if vs <= 0 or divider <= 0:
        raise ValueError("vs and divider must be positive")
    vin = [points[k][0] for k in POINTS]; vref = [points[k][1] for k in POINTS]
    vout = [points[k][2] for k in POINTS]
    gain, offset, residual = fit(vin, vout)
    if gain <= 0:
        raise ValueError("fitted gain is not positive: check point order and wiring")
    per_point = {}
    for k in POINTS:
        i, r, o = points[k]
        per_point[k] = dict(vin=i, vref=r, vout=o, v_g5=divider*o,
                            gain_from_vref=(o-r)/(i-r) if abs(i-r) > 1e-6 else None,
                            fit_residual_mv=1000*residual[POINTS.index(k)],
                            datasheet_kpa=(i-points["atmosphere"][0])/(vs*mpx5700.SLOPE))
    warnings = []
    if not vs_measured:
        warnings.append(f"Vs={vs} V is nominal; pass the measured sensor supply with --vs")
    if max(vref)-min(vref) > 0.003:
        warnings.append(f"Vref moved {1000*(max(vref)-min(vref)):.1f} mV between points (handoff: >2-3 mV -> stronger pull-down)")
    for k, p in per_point.items():
        if p["v_g5"] > G5_MAX_V:
            warnings.append(f"{k}: G5 {p['v_g5']:.3f} V above {G5_MAX_V} V")
        if p["v_g5"] < G5_FLOOR_V:
            warnings.append(f"{k}: G5 {p['v_g5']:.3f} V at the floor: stage saturated, fit invalid")
    if adc:
        names = [k for k in POINTS if k in adc]
        if len(names) < 2:
            raise ValueError("ADC fit needs codes for at least two points")
        volts_per_count, voltage_offset_v, adc_residual = fit([adc[k] for k in names],
                                                              [per_point[k]["v_g5"] for k in names])
        adc_source = f"fit of G5 voltage vs ADC code at {len(names)} points"
        for k, r in zip(names, adc_residual):
            per_point[k].update(adc=adc[k], adc_residual_mv=1000*r)
    else:
        voltage_offset_v, adc_source = 0.0, "Lab 1 empirical 3.70 V / 4095 (not measured for Lab 2)"
    kpa_per_volt = 1/(divider*gain*vs*mpx5700.SLOPE)
    v_g5_atm = divider*(gain*points["atmosphere"][0]+offset)
    atom = dict(volts_per_count=volts_per_count, voltage_offset_v=voltage_offset_v,
                kpa_per_volt=kpa_per_volt, pressure_offset_kpa=-kpa_per_volt*v_g5_atm)
    return dict(gain=gain, offset_v=offset,
                vref_effective_v=-offset/(gain-1) if abs(gain-1) > 1e-9 else None,
                points=per_point, atom_page=atom, pa_per_adc_step=mpx5700.pa_per_step(atom),
                sources=dict(vs=("measured" if vs_measured else "nominal")+f" {vs} V", divider=divider,
                             volts_per_count=adc_source,
                             kpa="MPX5700AP datasheet slope 0.0012858*Vs, zero at measured atmosphere"),
                warnings=warnings)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k in POINTS:
        p.add_argument("--"+k.replace("_", "-"), type=float, nargs=3, required=True,
                       metavar=("VIN", "VREF", "VOUT"))
        p.add_argument("--adc-"+k.replace("_", "-"), type=float, metavar="CODE",
                       help="mean G5 ADC code logged at the same point")
    p.add_argument("--vs", type=float, help="measured MPX5700AP supply, V (default nominal 5.0)")
    p.add_argument("--divider", type=float, default=1.0, help="V_G5/Vout (series resistor only: 1.0)")
    p.add_argument("--json", action="store_true", help="print JSON only")
    a = p.parse_args(argv)
    try:
        adc = {k: getattr(a, "adc_"+k) for k in POINTS if getattr(a, "adc_"+k) is not None}
        result = calibrate({k: tuple(getattr(a, k)) for k in POINTS},
                           a.vs if a.vs is not None else mpx5700.VS_NOMINAL, a.divider, adc or None,
                           vs_measured=a.vs is not None)
    except ValueError as error:
        print(f"Kalibratsioon peatatud: {error}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    vref = result["vref_effective_v"]
    print(f"Võimendus A = {result['gain']:.4f}, nihe B = {result['offset_v']:+.4f} V "
          f"(Vout = A·Vin + B); efektiivne Vref = {'—' if vref is None else f'{vref:.4f} V'}")
    for k, pt in result["points"].items():
        g = "—" if pt["gain_from_vref"] is None else f"{pt['gain_from_vref']:.4f}"
        print(f"  {k:13} Vin {pt['vin']:.3f}  Vref {pt['vref']:.3f}  Vout {pt['vout']:.3f}  "
              f"jääk {pt['fit_residual_mv']:+.1f} mV  A(Vref) {g}  andmeleht {pt['datasheet_kpa']:+.1f} kPa")
    print("Atomi lehe väljad (Settings & tests → rõhuanduri seaded):")
    for k in mpx5700.ATOM_FIELDS:
        print(f"  {k:20} = {result['atom_page'][k]:.8g}")
    print(f"Pa / ADC samm = {result['pa_per_adc_step']:.1f}")
    for k, v in result["sources"].items():
        print(f"  allikas {k}: {v}")
    for w in result["warnings"]:
        print("HOIATUS:", w)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
