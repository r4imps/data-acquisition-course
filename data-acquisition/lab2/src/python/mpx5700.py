"""MPX5700AP datasheet transfer function and Atom-page linear constants.

Datasheet (same constants as lab1/src/firmware/include/sensor.h):
    Vin = Vs * (SLOPE * P_abs_kPa + OFFSET)
Op-amp stage (non-inverting, offset by buffered Vref, then G5 divider d):
    Vout = A * Vin - (A - 1) * Vref,   V_G5 = d * Vout
Smart Solutions Atom page (smart-solutions/lab2/docs/atom_page.md):
    voltage_v    = raw_adc * volts_per_count + voltage_offset_v
    pressure_kpa = voltage_v * kpa_per_volt + pressure_offset_kpa
Pressure is relative to p_atm_kpa. Defaults are datasheet/nominal values,
not this team's calibration; pass measured values when they exist.
"""
import math

SLOPE = 0.0012858          # 1/kPa, MPX5700AP datasheet
OFFSET = 0.04              # fraction of Vs at 0 kPa absolute
VS_NOMINAL = 5.0           # V, nominal sensor supply
P_ATM_NOMINAL = 101.325    # kPa, standard atmosphere
LAB1_VOLTS_PER_COUNT = 3.70 / 4095   # Lab 1 empirical ADC factor (sensor_choice.md)
ATOM_FIELDS = ("volts_per_count", "voltage_offset_v", "kpa_per_volt", "pressure_offset_kpa")


def finite(*values):
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
        raise ValueError("calibration values must be finite numbers")


def atom_constants(volts_per_count=LAB1_VOLTS_PER_COUNT, voltage_offset_v=0.0,
                   vs=VS_NOMINAL, gain=1.0, vref=0.0, divider=1.0, p_atm_kpa=P_ATM_NOMINAL):
    """Datasheet chain -> the four Atom-page constants. gain=1, divider=1 is the raw sensor."""
    finite(volts_per_count, voltage_offset_v, vs, gain, vref, divider, p_atm_kpa)
    if volts_per_count <= 0 or vs <= 0 or gain <= 0 or divider <= 0:
        raise ValueError("volts_per_count, vs, gain and divider must be positive")
    # P = (V_G5/(d*A) + (A-1)*Vref/A) / (Vs*SLOPE) - OFFSET/SLOPE - p_atm
    kpa_per_volt = 1 / (divider * gain * vs * SLOPE)
    pressure_offset_kpa = ((gain - 1) * vref / gain / vs - OFFSET) / SLOPE - p_atm_kpa
    return dict(volts_per_count=volts_per_count, voltage_offset_v=voltage_offset_v,
                kpa_per_volt=kpa_per_volt, pressure_offset_kpa=pressure_offset_kpa)


def check(constants):
    if set(constants) < set(ATOM_FIELDS):
        raise ValueError(f"calibration needs {', '.join(ATOM_FIELDS)}")
    values = [constants[k] for k in ATOM_FIELDS]
    finite(*values)
    if values[0] == 0 or values[2] == 0:
        raise ValueError("zero scale factor")
    return constants


def to_kpa(adc, constants):
    """ADC codes -> relative kPa with the Atom-page formula."""
    c = check(constants)
    return [(a * c["volts_per_count"] + c["voltage_offset_v"]) * c["kpa_per_volt"]
            + c["pressure_offset_kpa"] for a in adc]


def pa_per_step(constants):
    c = check(constants)
    return abs(c["volts_per_count"] * c["kpa_per_volt"]) * 1000
