#!/usr/bin/env python3
"""Stackup, 50 ohm geometry, via-fence pitch and current-width maths for the
bay-station board.  Pure standard library; run it to print the tables that
docs/routing-plan.md quotes.

Stackup (DW3000 Datasheet v1.1 s7.3.2 Fig 35, as set in bay-station.kicad_pcb):
  F.Cu 35um / prepreg 254um / In1.Cu 35um / core 400um / In2.Cu 35um /
  prepreg 254um / B.Cu 35um = 1.048 mm finished.  er = 4.5 is KiCad's FR4
  default, NOT a datasheet or fab value (see docs/routing-plan.md).

Formulas and where they come from:
  microstrip  Hammerstad & Jensen, "Accurate Models for Microstrip
              Computer-Aided Design", IEEE MTT-S Digest 1980, with their
              thickness correction (du1, dur); as reproduced in Pozar,
              Microwave Engineering 4th ed. s3.8 and Wadell, Transmission
              Line Design Handbook (1991). Quoted accuracy ~1 % for
              0.01 < w/h < 100, er < 128.
  dispersion  Getsinger/Edwards-Owens: er_eff(f) = er - (er-ee0)/(1+G(f/fp)^2),
              fp = Z0/(2 mu0 h), G = 0.6 + 0.009 Z0 (Edwards & Owens 1976;
              Gupta, Garg, Bahl, Microstrip Lines and Slotlines 2e s2.2).
  CPWG        conductor-backed coplanar waveguide by conformal mapping,
              Simons, Coplanar Waveguide Circuits, Components and Systems
              (2001) s2.2 / Ghione & Naldi 1987; thickness through the
              Gupta-Garg effective-width correction.
  current     IPC-2221A s6.2 (I = k dT^0.44 A^0.725, k = 0.048 external).
              IPC-2152 is less conservative; 2221 is used as the safe side.
All of these are closed-form approximations; none replaces a field solve or
the fab's own impedance report.
"""
import math

C0 = 299792458.0
ETA0 = 376.730313668
MU0 = 4e-7 * math.pi

# ---- stackup (mm) ----------------------------------------------------------
T_CU = 0.035
H_F_IN1 = 0.254                       # F.Cu -> In1 dielectric
H_IN1_IN2 = 0.400
H_F_IN2 = H_F_IN1 + T_CU + H_IN1_IN2  # F.Cu -> In2 (valid where In1 is cleared)
ER_FILE = 4.5                         # value in the .kicad_pcb (placeholder)
TAND_FILE = 0.02
F_CH5 = 6489.6e6


def _agm(a, b):
    for _ in range(40):
        a, b = 0.5 * (a + b), math.sqrt(a * b)
    return a


def ellipk(k):
    """Complete elliptic integral of the first kind K(k) (modulus k)."""
    return math.pi / (2.0 * _agm(1.0, math.sqrt(1.0 - k * k)))


def _F(u):
    return 6 + (2 * math.pi - 6) * math.exp(-((30.666 / u) ** 0.7528))


def _eeff_hj(u, er):
    a = 1 + math.log((u**4 + (u / 52) ** 2) / (u**4 + 0.432)) / 49 \
        + math.log(1 + (u / 18.1) ** 3) / 18.7
    b = 0.564 * ((er - 0.9) / (er + 3)) ** 0.053
    return (er + 1) / 2 + (er - 1) / 2 * (1 + 10 / u) ** (-a * b)


def microstrip(w, h, er, t=T_CU, f=None):
    """(Z0 ohm, er_eff) for microstrip of width w over height h (mm).
    With f (Hz) the Getsinger dispersion is applied."""
    u = w / h
    coth2 = (1 / math.tanh(math.sqrt(6.517 * u))) ** 2
    du1 = t / (math.pi * h) * math.log(1 + 4 * math.e / ((t / h) * coth2))
    dur = 0.5 * (1 + 1 / math.cosh(math.sqrt(er - 1))) * du1
    ur = u + dur
    z01 = ETA0 / (2 * math.pi) * math.log(_F(ur) / ur + math.sqrt(1 + (2 / ur) ** 2))
    ee = _eeff_hj(ur, er)
    z0 = z01 / math.sqrt(ee)
    if f:
        fp = z0 / (2 * MU0 * h * 1e-3)
        g = 0.6 + 0.009 * z0
        ee_f = er - (er - ee) / (1 + g * (f / fp) ** 2)
        return z0 * math.sqrt(ee / ee_f), ee_f
    return z0, ee


def cpwg(w, s, h, er, t=T_CU):
    """Grounded CPW: strip w, gap s each side, ground plane at depth h.
    Returns (Z0, er_eff)."""
    d = 1.25 * t / math.pi * (1 + math.log(4 * math.pi * w / t))
    we, se = w + d, s - d
    a, b = we / 2, we / 2 + se
    k = a / b
    k1 = math.tanh(math.pi * a / (2 * h)) / math.tanh(math.pi * b / (2 * h))
    kp, k1p = math.sqrt(1 - k * k), math.sqrt(1 - k1 * k1)
    q = ellipk(kp) * ellipk(k1) / (ellipk(k) * ellipk(k1p))
    ee = (1 + er * q) / (1 + q)
    z0 = 60 * math.pi / math.sqrt(ee) / (ellipk(k) / ellipk(kp) + ellipk(k1) / ellipk(k1p))
    return z0, ee


def solve_width(fn, target=50.0, lo=0.05, hi=5.0):
    """Bisection on width (Z0 falls as w grows)."""
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if fn(mid) > target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def ms_width(h, er, z=50.0, f=None):
    return solve_width(lambda w: microstrip(w, h, er, f=f)[0], z)


def cpwg_width(s, h, er, z=50.0):
    return solve_width(lambda w: cpwg(w, s, h, er)[0], z)


def lam_g_mm(f, ee):
    return C0 / f / math.sqrt(ee) * 1e3


def delay_ps_per_mm(ee):
    return math.sqrt(ee) / C0 * 1e9      # s/m -> ps/mm: sqrt(ee)/c * 1e12 * 1e-3


def ipc2221_width_mm(i_a, d_t=10.0, t_mm=T_CU, external=True):
    k = 0.048 if external else 0.024
    area_mil2 = (i_a / (k * d_t**0.44)) ** (1 / 0.725)
    w_mil = area_mil2 / (t_mm / 0.0254)
    return w_mil * 0.0254


def fence_pitch_mm(er=ER_FILE, h=H_F_IN1, w=None, f=F_CH5, divisor=10):
    """(lambda_g, lambda_g/divisor) in mm for a 50 ohm line at f, using the
    dispersed er_eff."""
    w = w or ms_width(h, er)
    _, ee = microstrip(w, h, er, f=f)
    lg = lam_g_mm(f, ee)
    return lg, lg / divisor


def table():
    o = []
    o.append("stackup: h(F->In1)=%.3f  h(F->In2)=%.3f mm, t=%.3f, er=%.2f (file)" %
             (H_F_IN1, H_F_IN2, T_CU, ER_FILE))
    o.append("")
    o.append("50 ohm microstrip width (mm) vs er; reference In1 (h=0.254) / In2 (h=0.689):")
    for er in (3.9, 4.0, 4.2, 4.5, 4.6):
        w1 = ms_width(H_F_IN1, er)
        w2 = ms_width(H_F_IN2, er)
        _, ee6 = microstrip(w1, H_F_IN1, er, f=F_CH5)
        o.append("  er=%.2f  In1: w=%.3f (er_eff0=%.2f)   In2: w=%.3f   | er_eff@6.49GHz=%.2f" %
                 (er, w1, microstrip(w1, H_F_IN1, er)[1], w2, ee6))
    w = ms_width(H_F_IN1, ER_FILE)
    o.append("")
    o.append("with w=%.3f fixed: " % w + ", ".join(
        "er=%.1f -> %.1f ohm" % (er, microstrip(w, H_F_IN1, er)[0]) for er in (3.9, 4.2, 4.5, 4.8)))
    o.append("width tol -/+0.03 mm -> " + ", ".join(
        "%.1f ohm" % microstrip(w + d, H_F_IN1, ER_FILE)[0] for d in (-0.03, 0.03)))
    o.append("Z0 at 6.49 GHz with w=%.3f: %.1f ohm" % (w, microstrip(w, H_F_IN1, ER_FILE, f=F_CH5)[0]))
    o.append("")
    o.append("CPWG, reference In1, er=4.5:")
    for s in (0.2, 0.25, 0.3, 0.4, 0.5):
        wc = cpwg_width(s, H_F_IN1, ER_FILE)
        o.append("  gap %.2f -> w=%.3f mm, er_eff=%.2f" % (s, wc, cpwg(wc, s, H_F_IN1, ER_FILE)[1]))
    for wr in (0.45,):
        o.append("  w=%.2f with a top GND pour at gap 0.3/0.5/0.75/inf: %s ohm" % (wr, " / ".join(
            "%.1f" % cpwg(wr, g, H_F_IN1, ER_FILE)[0] for g in (0.3, 0.5, 0.75)) + " / %.1f" %
            microstrip(wr, H_F_IN1, ER_FILE)[0]))
    o.append("")
    for div in (10, 20):
        lg, p = fence_pitch_mm(divisor=div)
        o.append("lambda_g(6489.6 MHz)=%.2f mm -> lambda/%d = %.2f mm" % (lg, div, p))
    _, ee = microstrip(w, H_F_IN1, ER_FILE, f=F_CH5)
    o.append("delay: %.2f ps/mm  (1 cm = %.1f ps)" % (delay_ps_per_mm(ee), delay_ps_per_mm(ee) * 10))
    o.append("")
    o.append("IPC-2221 external 35um, dT=10C: " + ", ".join(
        "%.2fA -> %.2f mm" % (i, ipc2221_width_mm(i)) for i in (0.1, 0.5, 1.0, 1.2, 1.8, 3.4)))
    return "\n".join(o)


if __name__ == "__main__":
    print(table())
