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


# ---- solder mask over the line (bare vs masked) ------------------------------
# ASSUMPTIONS (not fab data): JLCPCB-class LPI mask, er 3.7 (range 3.3-4.2 quoted for
# epoxy LPI at 1-10 GHz), tan d ~0.025, 0.020 mm thick on the laminate AND on the
# copper (real mask is thinner on top of copper, 10-15 um, and thicker in the gaps;
# a uniform 20 um coat is the simple, slightly pessimistic case).
ER_MASK = 3.7
TAND_MASK = 0.025
T_MASK = 0.020


def _fd_solve(w, h, er, t, tm, erm, step=1.0, xmax=3.0, ymax=3.0):
    """2-D quasi-static finite-element solve (bilinear rectangles, graded mesh, Jacobi-CG)
    of the strip of width w and thickness t at height h over a ground plane, in a grounded
    box xmax x ymax (half domain, symmetry at x = 0).  Substrate er below y = h; a CONFORMAL
    mask layer of thickness tm (relative permittivity erm) on the laminate, the strip top and
    the strip sides when tm > 0.  Returns (C / eps0 per metre for the FULL strip).  Pure
    stdlib: slow (tens of seconds), used to calibrate and cross-check the closed-form
    mask correction, not inside loops."""
    def graded(points, lo_n, xend, growth=1.25, hmax=0.4):
        # insert refinement between the fixed lines `points` (sorted) and grow out to xend
        out = [points[0]]
        for a, b in zip(points, points[1:]):
            n = max(1, int(round((b - a) / (0.0125 / step))))
            out += [a + (b - a) * k / n for k in range(1, n + 1)]
        d = (out[-1] - out[-2])
        x = out[-1]
        while x < xend - 1e-9:
            d = min(d * growth, hmax)
            x = min(x + d, xend)
            out.append(x)
        return out
    hw = w / 2
    tmm = tm if tm > 0 else 0.0
    xs_fixed = sorted({0.0, hw - 0.0, hw + (tmm if tmm else 0.0)})
    xs = graded(xs_fixed, 0, xmax)
    ys_fixed = [0.0, h * 0.5, h]
    lines = [0.0]
    ys = [0.0]
    # fixed y lines above the substrate: h, h+tm, h+t, h+t+tm
    top = sorted({h, h + t} | ({h + tmm, h + t + tmm} if tmm else set()))
    # lower part, refined toward the strip
    n_low = 14
    for k in range(1, n_low + 1):
        f = k / n_low
        ys.append(h * (1 - (1 - f) ** 1.6))
    ys[-1] = h
    prev = h
    for yv in top[1:]:
        n = max(1, int(round((yv - prev) / (0.0125 / step))))
        ys += [prev + (yv - prev) * k / n for k in range(1, n + 1)]
        prev = yv
    d = ys[-1] - ys[-2]
    y = ys[-1]
    while y < ymax - 1e-9:
        d = min(d * 1.25, 0.4)
        y = min(y + d, ymax)
        ys.append(y)
    nx, ny = len(xs), len(ys)
    eps_cell = [[1.0] * (ny - 1) for _ in range(nx - 1)]
    cu = [[False] * ny for _ in range(nx)]
    ymid = lambda j: 0.5 * (ys[j] + ys[j + 1])
    xmid = lambda i: 0.5 * (xs[i] + xs[i + 1])
    for i in range(nx - 1):
        for j in range(ny - 1):
            x_, y_ = xmid(i), ymid(j)
            e = 1.0
            if y_ < h:
                e = er
            else:
                in_cu = x_ < hw and y_ < h + t
                if in_cu:
                    e = er          # inside the conductor (irrelevant: potential fixed)
                elif tmm:
                    a_ = y_ < h + tmm
                    b_ = x_ < hw + tmm and h + t <= y_ < h + t + tmm
                    c_ = hw <= x_ < hw + tmm and h <= y_ < h + t + tmm
                    if a_ or b_ or c_:
                        e = erm
            eps_cell[i][j] = e
    for i in range(nx):
        for j in range(ny):
            if xs[i] <= hw + 1e-9 and h - 1e-9 <= ys[j] <= h + t + 1e-9:
                cu[i][j] = True
    # stencil assembly: nodes (i, j); neighbours (di, dj) in -1..1
    idx = lambda i, j: i * ny + j
    N = nx * ny
    sten = [dict() for _ in range(N)]
    for i in range(nx - 1):
        a = xs[i + 1] - xs[i]
        for j in range(ny - 1):
            b = ys[j + 1] - ys[j]
            e = eps_cell[i][j]
            k1 = b / (6 * a)
            k2 = a / (6 * b)
            X = ((2, -2, -1, 1), (-2, 2, 1, -1), (-1, 1, 2, -2), (1, -1, -2, 2))
            Y = ((2, 1, -1, -2), (1, 2, -2, -1), (-1, -2, 2, 1), (-2, -1, 1, 2))
            nodes = (idx(i, j), idx(i + 1, j), idx(i + 1, j + 1), idx(i, j + 1))
            for p in range(4):
                for q in range(4):
                    v = e * (k1 * X[p][q] + k2 * Y[p][q])
                    sd = sten[nodes[p]]
                    sd[nodes[q]] = sd.get(nodes[q], 0.0) + v
    # symmetry plane x = 0: natural (Neumann) boundary comes for free (half-domain mesh)
    fixed = [None] * N
    for i in range(nx):
        for j in range(ny):
            n_ = idx(i, j)
            if cu[i][j]:
                fixed[n_] = 1.0
            elif j == 0 or j == ny - 1 or i == nx - 1:
                fixed[n_] = 0.0
    free = [n for n in range(N) if fixed[n] is None]
    pos = {n: k for k, n in enumerate(free)}
    rows = []
    for n in free:
        r = [(pos[m], v) for m, v in sten[n].items() if fixed[m] is None]
        rows.append(r)
    rhs = [-sum(v * fixed[m] for m, v in sten[n].items() if fixed[m] is not None) for n in free]
    diag = [sum(v for (m, v) in r if m == k) for k, r in enumerate(rows)]
    xk = [0.0] * len(free)
    # warm start: 1 near strip decaying, just zeros is fine for CG
    def matvec(v):
        return [sum(c * v[m] for m, c in r) for r in rows]
    r_ = rhs[:]
    z = [r_[k] / diag[k] for k in range(len(free))]
    p_ = z[:]
    rz = sum(a * b for a, b in zip(r_, z))
    tol = 1e-10 * math.sqrt(sum(a * a for a in rhs))
    for it in range(4000):
        Ap = matvec(p_)
        pAp = sum(a * b for a, b in zip(p_, Ap))
        al = rz / pAp
        xk = [a + al * b for a, b in zip(xk, p_)]
        r_ = [a - al * b for a, b in zip(r_, Ap)]
        if math.sqrt(sum(a * a for a in r_)) < tol:
            break
        z = [r_[k] / diag[k] for k in range(len(free))]
        rz2 = sum(a * b for a, b in zip(r_, z))
        be = rz2 / rz
        rz = rz2
        p_ = [a + be * b for a, b in zip(z, p_)]
    phi = [0.0] * N
    for n in range(N):
        phi[n] = fixed[n] if fixed[n] is not None else 0.0
    for n, k in pos.items():
        phi[n] = xk[k]
    # energy: C = sum phi_i K_ij phi_j  (V = 1), x2 for the full strip; the mesh cells
    # inside the conductor carry zero gradient (all nodes at 1)
    W = 0.0
    for n in range(N):
        pn = phi[n]
        if pn == 0.0:
            continue
        W += pn * sum(v * phi[m] for m, v in sten[n].items())
    return 2.0 * W      # C/eps0 for the full structure (V = 1, W = C/2 -> C = 2W, halved domain x2)


def fd_z0(w, h, er, t=T_CU, tm=0.0, erm=ER_MASK, **kw):
    """(Z0, er_eff) of the strip from the finite-element solve (quasi-static, lossless)."""
    c_d = _fd_solve(w, h, er, t, tm, erm, **kw) if tm > 0 else _fd_solve(w, h, er, t, 0.0, 1.0, **kw)
    c_a = _fd_solve(w, h, 1.0, t, 0.0, 1.0, **kw)
    ee = c_d / c_a
    z0 = 1.0 / (C0 * 8.8541878128e-12 * math.sqrt(c_d * c_a)) * 1.0
    return z0, ee


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
