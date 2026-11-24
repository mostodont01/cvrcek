#!/usr/bin/env python3
import argparse
import math
import shutil
import signal
import sys
import time

CHARS = ".,-~:;=!*#$@"
SPECULAR_CHARS = ".,-~:;=!*#$@%"

THEMES = {
    "rgb": None,
    "classic": "\033[38;2;215;215;215m",
    "matrix": "\033[38;2;0;255;75m",
    "gold": "\033[38;2;255;200;40m",
    "cyber": "\033[38;2;255;45;185m",
    "ocean": "\033[38;2;40;190;255m",
}

DANCE_STYLES = ["groove", "headbang", "breakdance", "jitterbug"]


def _rot_x(pt, ang):
  x, y, z = pt
  ca, sa = math.cos(ang), math.sin(ang)
  return (x, y * ca - z * sa, y * sa + z * ca)


def _rot_y(pt, ang):
  x, y, z = pt
  ca, sa = math.cos(ang), math.sin(ang)
  return (x * ca + z * sa, y, -x * sa + z * ca)


def _rot_z(pt, ang):
  x, y, z = pt
  ca, sa = math.cos(ang), math.sin(ang)
  return (x * ca - y * sa, x * sa + y * ca, z)


def _add_vec(a, b):
  return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def build_articulated_roach(step, dance_style, with_sombrero=False):
  """Builds a 3D point cloud with normals and articulated joints."""
  points = []

  t = step * 0.25
  beat = math.sin(t * 2.0)
  offbeat = math.cos(t * 2.0)
  wave = math.sin(t)

  if dance_style == "headbang":
    head_nod = beat * 0.45
    arm_pump = abs(beat) * 0.65
    leg_bounce = beat * 0.15
  elif dance_style == "breakdance":
    head_nod = offbeat * 0.25
    arm_pump = wave * 0.75
    leg_bounce = abs(beat) * 0.35
  elif dance_style == "jitterbug":
    head_nod = math.sin(t * 4.0) * 0.22
    arm_pump = math.cos(t * 4.0) * 0.55
    leg_bounce = math.sin(t * 4.0) * 0.22
  else:  # "groove"
    head_nod = offbeat * 0.20
    arm_pump = wave * 0.45
    leg_bounce = beat * 0.18

  def add_ellipsoid(
      cx, cy, cz, rx, ry, rz, u_steps=30, v_steps=18, ao_bias=0.0
  ):
    for i in range(u_steps):
      theta = (i / u_steps) * 2 * math.pi
      ct, st = math.cos(theta), math.sin(theta)
      for j in range(v_steps):
        phi = (j / (v_steps - 1) - 0.5) * math.pi
        cp, sp = math.cos(phi), math.sin(phi)

        x = cx + rx * cp * ct
        y = cy + ry * sp
        z = cz + rz * cp * st

        nx, ny, nz = (cp * ct) / rx, sp / ry, (cp * st) / rz
        norm = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        points.append((x, y, z, nx / norm, ny / norm, nz / norm, ao_bias))

  def add_limb(p1, p2, radius, steps=11, radial_steps=10):
    x1, y1, z1 = p1
    x2, y2, z2 = p2
    dx, dy, dz = x2 - x1, y2 - y1, z2 - z1
    length = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
    ux, uy, uz = dx / length, dy / length, dz / length

    if abs(ux) < 0.9:
      vx, vy, vz = 0.0, -uz, uy
    else:
      vx, vy, vz = -uz, 0.0, ux
    v_len = math.sqrt(vx * vx + vy * vy + vz * vz) or 1.0
    vx, vy, vz = vx / v_len, vy / v_len, vz / v_len
    wx, wy, wz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx

    for i in range(steps):
      frac = i / max(1, steps - 1)
      r_cur = radius * (1.0 - 0.25 * frac)
      bx, by, bz = x1 + dx * frac, y1 + dy * frac, z1 + dz * frac
      for a in range(radial_steps):
        ang = (a / radial_steps) * 2 * math.pi
        ca, sa = math.cos(ang), math.sin(ang)
        nx = vx * ca + wx * sa
        ny = vy * ca + wy * sa
        nz = vz * ca + wz * sa
        points.append((
            bx + r_cur * nx,
            by + r_cur * ny,
            bz + r_cur * nz,
            nx,
            ny,
            nz,
            0.05,
        ))

  def add_sombrero(hx, hy, hz):
    tilt_x = -0.22 + head_nod * 0.5
    tilt_z = wave * 0.14

    def place_hat(lx_p, ly_p, lz_p, lnx, lny, lnz, bias=0.0):
      p = _rot_x((lx_p, ly_p, lz_p), tilt_x)
      p = _rot_z(p, tilt_z)
      n = _rot_x((lnx, lny, lnz), tilt_x)
      n = _rot_z(n, tilt_z)
      n_len = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) or 1.0
      points.append((
          hx + p[0],
          hy + p[1],
          hz + p[2],
          n[0] / n_len,
          n[1] / n_len,
          n[2] / n_len,
          bias,
      ))

    radial_steps = 14
    angle_steps = 48
    for r_i in range(1, radial_steps + 1):
      frac = r_i / radial_steps
      radius = 0.28 + frac * 0.96
      y_local = 0.04 * (1.0 - frac) + (0.20 * (frac**3) if frac > 0.65 else 0.0)
      slope = -0.04 + (0.58 * (frac**2) if frac > 0.65 else 0.05)

      for a_i in range(angle_steps):
        ang = (a_i / angle_steps) * 2 * math.pi
        ca, sa = math.cos(ang), math.sin(ang)
        px, pz = radius * ca, radius * sa
        nx, ny, nz = slope * ca, 1.0, slope * sa
        edge_bias = 0.14 if r_i == radial_steps else 0.0
        place_hat(px, y_local, pz, nx, ny, nz, edge_bias)
        place_hat(px, y_local - 0.025, pz, -nx, -ny, -nz, -0.05)

    band_r = 0.355
    for a_i in range(40):
      ang = (a_i / 40) * 2 * math.pi
      ca, sa = math.cos(ang), math.sin(ang)
      for h_i in range(3):
        by = 0.20 + h_i * 0.025
        place_hat(band_r * ca, by, band_r * sa, ca, 0.15, sa, 0.15)

    crown_rx, crown_ry, crown_rz = 0.34, 0.34, 0.34
    crown_cy = 0.22
    for i in range(30):
      theta = (i / 30) * 2 * math.pi
      ct, st = math.cos(theta), math.sin(theta)
      for j in range(14):
        phi = (j / 13) * (math.pi * 0.5)
        cp, sp = math.cos(phi), math.sin(phi)
        px = crown_rx * cp * ct
        py = crown_cy + crown_ry * sp
        pz = crown_rz * cp * st
        nx = (cp * ct) / crown_rx
        ny = sp / crown_ry
        nz = (cp * st) / crown_rz
        place_hat(px, py, pz, nx, ny, nz, 0.08)

  # 1. Abdomen & Thorax
  thorax_shift = beat * 0.04
  add_ellipsoid(0.0, -0.35, 0.0, 0.65, 1.05, 0.42, 36, 20, ao_bias=0.05)
  add_ellipsoid(
      0.0, 0.70 + thorax_shift, 0.05, 0.55, 0.55, 0.38, 28, 16, ao_bias=0.08
  )

  # 2. Head & Eyes
  head_pivot = (0.0, 1.15, 0.15)
  head_offset = _rot_x((0.0, 0.12, 0.08), head_nod)
  hx, hy, hz = _add_vec(head_pivot, head_offset)
  add_ellipsoid(hx, hy, hz, 0.34, 0.30, 0.30, 20, 14, ao_bias=0.10)

  for side in (-1, 1):
    eye_local = _rot_x((side * 0.22, 0.07, 0.20), head_nod)
    ex, ey, ez = _add_vec((hx, hy, hz), eye_local)
    add_ellipsoid(ex, ey, ez, 0.12, 0.14, 0.12, 14, 10, ao_bias=0.20)

  # 3. Sombrero
  if with_sombrero:
    add_sombrero(hx, hy + 0.31, hz)

  # 4. Antennae
  for side in (-1, 1):
    ant_phase = t * 1.6 + (0.0 if side < 0 else math.pi * 0.5)
    base_pt = (side * 0.15, hy + 0.20, hz + 0.12)
    mid_pt = _add_vec(
        base_pt,
        (
            side * 0.32 + math.cos(ant_phase) * 0.14,
            0.58 + math.sin(ant_phase) * 0.12,
            0.28 + math.sin(ant_phase) * 0.10,
        ),
    )
    tip_pt = _add_vec(
        mid_pt,
        (
            side * 0.38 + math.sin(ant_phase * 1.3) * 0.20,
            0.38 + math.cos(ant_phase * 1.3) * 0.16,
            -0.25 + math.cos(ant_phase) * 0.18,
        ),
    )
    add_limb(base_pt, mid_pt, 0.035, steps=9, radial_steps=8)
    add_limb(mid_pt, tip_pt, 0.025, steps=9, radial_steps=8)

  # 5. Six Articulated Dancing Legs
  for side in (-1, 1):
    s_phase = arm_pump if side < 0 else -arm_pump

    sh_pt = (side * 0.45, 0.75 + thorax_shift, 0.15)
    el_pt = (
        side * (1.12 + s_phase * 0.18),
        1.05 + s_phase * 0.42,
        0.42 + s_phase * 0.15,
    )
    wr_pt = (
        side * (1.42 + s_phase * 0.25),
        1.52 + s_phase * 0.65,
        0.62 + s_phase * 0.20,
    )
    add_limb(sh_pt, el_pt, 0.06, steps=9)
    add_limb(el_pt, wr_pt, 0.045, steps=9)

    m_sh = (side * 0.55, 0.25, 0.10)
    m_el = (side * (1.28 - s_phase * 0.15), 0.22 - s_phase * 0.25, 0.38)
    m_wr = (
        side * (1.52 - s_phase * 0.20),
        -0.24 - s_phase * 0.35,
        0.52 - s_phase * 0.15,
    )
    add_limb(m_sh, m_el, 0.06, steps=9)
    add_limb(m_el, m_wr, 0.045, steps=9)

    h_phase = beat if side < 0 else -beat
    h_hip = (side * 0.40, -1.10 + leg_bounce * 0.4, 0.0)
    h_knee = (side * 0.85, -1.65 + h_phase * 0.16, 0.25 + h_phase * 0.08)
    h_foot = (side * 0.65, -2.25 + h_phase * 0.22, 0.35)
    add_limb(h_hip, h_knee, 0.07, steps=9)
    add_limb(h_knee, h_foot, 0.055, steps=9)

  return points


def get_color(theme, step, depth_factor=1.0):
  if theme == "rgb":
    r = int(((math.sin(step) + 1) * 0.5) * 255 * depth_factor)
    g = int(
        ((math.sin(step + 2 * math.pi / 3) + 1) * 0.5) * 255 * depth_factor
    )
    b = int(
        ((math.sin(step + 4 * math.pi / 3) + 1) * 0.5) * 255 * depth_factor
    )
    return (
        f"\033[38;2;{max(0, min(255, r))};{max(0, min(255, g))};"
        f"{max(0, min(255, b))}m"
    )

  base_rgb = {
      "classic": (215, 215, 215),
      "matrix": (0, 255, 75),
      "gold": (255, 200, 40),
      "cyber": (255, 45, 185),
      "ocean": (40, 190, 255),
  }[theme]
  r = max(15, min(255, int(base_rgb[0] * depth_factor)))
  g = max(15, min(255, int(base_rgb[1] * depth_factor)))
  b = max(15, min(255, int(base_rgb[2] * depth_factor)))
  return f"\033[38;2;{r};{g};{b}m"


def parse_args():
  parser = argparse.ArgumentParser(
      prog="roach3d",
      description="3D ASCII dancing cockroach (sl + donut.c edition)",
  )
  parser.add_argument(
      "-s",
      "--speed",
      type=float,
      default=1.0,
      help="Speed multiplier (default: 1.0)",
  )
  parser.add_argument(
      "-z", "--size", type=float, default=1.0, help="Size scale (default: 1.0)"
  )
  parser.add_argument(
      "-b",
      "--bounce",
      type=float,
      default=1.0,
      help="Jump/bounce height multiplier (default: 1.0, 0 to disable)",
  )
  parser.add_argument(
      "--depth-weight",
      type=float,
      default=0.65,
      help=(
          "How strongly Z-depth controls ASCII characters 0.0-1.0 (default:"
          " 0.65)"
      ),
  )
  parser.add_argument(
      "-c",
      "--color",
      choices=THEMES.keys(),
      default="rgb",
      help="Color theme (default: rgb)",
  )
  parser.add_argument(
      "-d",
      "--dance",
      choices=DANCE_STYLES,
      default="groove",
      help="Dance style: groove, headbang, breakdance, jitterbug (default:"
      " groove)",
  )
  parser.add_argument(
      "-S", "--sombrero", action="store_true", help="Wear a 3D sombrero"
  )
  parser.add_argument(
      "--specular",
      action="store_true",
      help="Add bright specular highlights on glossy surfaces",
  )
  parser.add_argument(
      "--rim",
      action="store_true",
      help="Add subtle 3D rim/edge lighting to separate silhouettes",
  )
  parser.add_argument(
      "--depth-fog",
      action="store_true",
      help="Fade brightness subtly by Z-depth for stronger 3D volume",
  )
  parser.add_argument(
      "--trail",
      action="store_true",
      help="Leave a faint ghost trail behind moving roaches",
  )
  parser.add_argument(
      "-F",
      "--fly",
      action="store_true",
      help="Fly diagonally across the terminal (like sl -F)",
  )
  parser.add_argument(
      "-a",
      "--accident",
      action="store_true",
      help="Show a [HELP!] sign (like sl -a)",
  )
  parser.add_argument(
      "-l",
      "--loop",
      action="store_true",
      help="Spin endlessly in place like donut.c",
  )
  parser.add_argument(
      "-n",
      "--swarm",
      type=int,
      default=1,
      help="Number of roaches in a conga line (default: 1)",
  )
  parser.add_argument(
      "--rave", action="store_true", help="Hyper-spin and neon strobe"
  )
  parser.add_argument(
      "--mercy", action="store_true", help="Allow Ctrl+C during normal runs"
  )
  parser.add_argument(
      "-f",
      "--forever",
      action="store_true",
      help="Endless conga line of roaches (Ctrl+C to stop)",
  )
  return parser.parse_args()


def _rotation_matrix(angle_y, angle_z, angle_x):
  """Rows of Rx(angle_x) @ Rz(angle_z) @ Ry(angle_y) (same order as _rot_*)."""
  cy, sy = math.cos(angle_y), math.sin(angle_y)
  cz, sz = math.cos(angle_z), math.sin(angle_z)
  cx, sx = math.cos(angle_x), math.sin(angle_x)
  # Rz @ Ry
  a = ((cz * cy, -sz, cz * sy), (sz * cy, cz, sz * sy), (-sy, 0.0, cy))
  # Rx @ (Rz @ Ry)
  return (
      a[0],
      tuple(cx * a[1][i] - sx * a[2][i] for i in range(3)),
      tuple(sx * a[1][i] + cx * a[2][i] for i in range(3)),
  )


def render_sprite(
    mesh,
    box_w,
    box_h,
    angle_y,
    angle_z,
    angle_x,
    bob_y,
    lx,
    ly,
    lz,
    depth_weight=0.65,
    specular=False,
    rim=False,
    depth_fog=False,
):
  """Renders one roach into box_h rows of box_w characters.

  Two passes for speed: first every point is only projected and z-tested
  (keeping the index of the nearest point per cell), then lighting runs once
  per visible cell instead of once per point. Normals are never rotated:
  the light and half vectors are rotated into mesh space instead
  (dot(R n, l) == dot(n, R^T l)).
  """
  size = box_w * box_h
  zbuffer = [-999.0] * size
  winner = [-1] * size

  scale_y = box_h * 0.185
  sx5 = scale_y * 2.0 * 5.0
  sy5 = scale_y * 5.0
  half_w = box_w / 2
  half_h = box_h / 2

  (r00, r01, r02), (r10, r11, r12), (r20, r21, r22) = _rotation_matrix(
      angle_y, angle_z, angle_x
  )
  # bob_y is added to y before rotating: fold it into a constant offset.
  ox, oy, oz = r01 * bob_y, r11 * bob_y, r21 * bob_y

  for i, (x, y, z, _nx, _ny, _nz, _b) in enumerate(mesh):
    denom = r20 * x + r21 * y + r22 * z + oz + 5.8
    if denom <= 0.4:
      continue
    inv_z = 1.0 / denom
    px = int(half_w + (r00 * x + r01 * y + r02 * z + ox) * sx5 * inv_z)
    if px < 0 or px >= box_w:
      continue
    py = int(half_h - (r10 * x + r11 * y + r12 * z + oy) * sy5 * inv_z)
    if py < 0 or py >= box_h:
      continue
    idx = py * box_w + px
    if inv_z > zbuffer[idx]:
      zbuffer[idx] = inv_z
      winner[idx] = i

  vx, vy, vz = 0.0, 0.0, 1.0
  hx_dir, hy_dir, hz_dir = lx + vx, ly + vy, lz + vz
  h_len = math.sqrt(hx_dir**2 + hy_dir**2 + hz_dir**2) or 1.0
  hx_dir, hy_dir, hz_dir = hx_dir / h_len, hy_dir / h_len, hz_dir / h_len

  # Light / half vector in mesh space (R^T v).
  mlx = r00 * lx + r10 * ly + r20 * lz
  mly = r01 * lx + r11 * ly + r21 * lz
  mlz = r02 * lx + r12 * ly + r22 * lz
  mhx = r00 * hx_dir + r10 * hy_dir + r20 * hz_dir
  mhy = r01 * hx_dir + r11 * hy_dir + r21 * hz_dir
  mhz = r02 * hx_dir + r12 * hy_dir + r22 * hz_dir

  dw = max(0.0, min(1.0, depth_weight))
  lw = 1.0 - dw
  ramp = SPECULAR_CHARS if specular else CHARS
  ramp_top = len(ramp) - 1
  ramp_scale = ramp_top + 0.999

  output = [" "] * size
  depth_map = [0.5] * size

  for idx in range(size):
    i = winner[idx]
    if i < 0:
      continue
    x, y, z, nx, ny, nz, bias = mesh[i]
    z3 = 1.0 / zbuffer[idx] - 5.8

    near_factor = (1.6 - z3) / 3.2
    near_factor = 0.0 if near_factor < 0.0 else 1.0 if near_factor > 1.0 else near_factor

    if depth_fog:
      depth_map[idx] = max(0.45, min(1.25, 0.55 + near_factor * 0.65))

    raw_lum = nx * mlx + ny * mly + nz * mlz + bias
    lit_factor = max(0.0, min(1.0, (raw_lum + 0.65) / 1.65))

    combined = dw * near_factor + lw * lit_factor
    if specular:
      ndoth = nx * mhx + ny * mhy + nz * mhz
      if ndoth > 0.0:
        combined += (ndoth**14) * 0.35
    if rim:
      grazing = 1.0 - abs(r20 * nx + r21 * ny + r22 * nz)
      if grazing > 0.0:
        combined += (grazing**2.2) * 0.20

    combined = 0.0 if combined < 0.0 else 1.0 if combined > 1.0 else combined
    char_idx = int(combined * ramp_scale)
    output[idx] = ramp[char_idx if char_idx < ramp_top else ramp_top]

  rows_out = [
      "".join(output[r * box_w : (r + 1) * box_w]) for r in range(box_h)
  ]
  avg_depths = [
      sum(depth_map[r * box_w : (r + 1) * box_w]) / max(1, box_w)
      for r in range(box_h)
  ]
  return rows_out, avg_depths


def visible_roaches(pos, spacing, box_w, cols, count=None):
  """Indices s of the roaches on screen (roach_x = pos + s * spacing must be
  in (-box_w, cols)). count=None means an endless line (--forever)."""
  first = max(0, (-box_w - pos) // spacing + 1)
  last = (cols - 1 - pos) // spacing
  if count is not None:
    last = min(count - 1, last)
  return range(first, last + 1)


def figure_middle(box_w, box_h, sombrero=False):
  """Vertical middle (in rows, from the top of the box) of a resting roach."""
  mesh = build_articulated_roach(0.0, "groove", with_sombrero=sombrero)
  rows_out, _ = render_sprite(mesh, box_w, box_h, 0.0, 0.0, 0.0, 0.0,
                              0.45, 0.55, 0.70)
  drawn = [i for i, row in enumerate(rows_out) if row.strip()]
  if not drawn:
    return box_h / 2
  return (drawn[0] + drawn[-1] + 1) / 2


def centered_top_row(rows, box_h, bounce, fig_mid):
  """1-based screen row for the top of the sprite box, chosen so the roach
  hops evenly around the middle of the screen (half the hop above the middle,
  half below), instead of resting on the middle and hopping only upwards."""
  # How far a full hop lifts the roach on screen: the 3D bob (bob_y, projected
  # the way render_sprite does it) plus the whole-sprite row_hop.
  bob_rows = 0.55 * bounce * box_h * 0.185 * 5.0 / 5.8
  hop_rows = 2.2 * bounce + bob_rows
  top = int(round(rows / 2 - fig_mid + hop_rows / 2)) + 1
  return max(1, min(rows - box_h + 1, top))


def run():
  args = parse_args()

  if not (args.mercy or args.loop or args.forever):
    signal.signal(signal.SIGINT, signal.SIG_IGN)

  sys.stdout.write("\033[?25l\033[2J")
  sys.stdout.flush()

  lx, ly, lz = 0.45, 0.55, 0.70
  l_len = math.sqrt(lx * lx + ly * ly + lz * lz)
  lx, ly, lz = lx / l_len, ly / l_len, lz / l_len

  try:
    cols, rows = shutil.get_terminal_size()
    box_w = max(16, min(cols, int(48 * args.size)))
    box_h = max(10, min(rows - 2, int(28 * args.size)))

    spin_rate = (0.55 if args.rave else 0.22) * max(0.2, args.speed)
    dance_step_rate = (2.2 if args.rave else 1.0) * max(0.2, args.speed)
    hop_rate = (0.85 if args.rave else 0.45) * max(0.2, args.speed)
    delay = max(0.006, 0.035 / max(0.1, args.speed))
    swarm_count = max(1, args.swarm)
    spacing = int(box_w * 0.85)
    center_top = centered_top_row(
        rows, box_h, args.bounce, figure_middle(box_w, box_h, args.sombrero)
    )

    angle_y = 0.0
    anim_step = 0.0
    hop_phase = 0.0
    frame_idx = 0

    if args.loop:
      positions = [(cols - box_w) // 2]
    elif args.forever:
      positions = None  # pos is computed per frame, never ends
    else:
      total_span = spacing * (swarm_count - 1)
      positions = list(range(cols, -box_w - total_span, -1))

    pos_idx = 0
    next_frame = time.monotonic()
    while True:
      if args.loop:
        pos = positions[0]
      elif args.forever:
        pos = cols - pos_idx
      else:
        pos = positions[pos_idx]
      mesh = build_articulated_roach(
          anim_step, args.dance, with_sombrero=args.sombrero
      )

      bg_code = (
          "\033[48;2;25;0;45m" if (args.rave and frame_idx % 4 < 2) else ""
      )
      clear_cmd = "\033[H" if args.trail else f"{bg_code}\033[2J"
      frame_buf = [clear_cmd]

      if args.trail and not args.loop:
        trail_x = pos + 3
        if -box_w < trail_x < cols:
          trail_col = max(1, trail_x + 1)
          start_c = max(0, -trail_x)
          end_c = min(box_w, cols - trail_x)
          if start_c < end_c:
            base_r = center_top
            for r in range(min(box_h, rows - base_r + 1)):
              dots = "." * (end_c - start_c)
              frame_buf.append(
                  f"\033[{base_r + r};{trail_col}H\033[38;2;70;70;85m{dots}"
              )

      count = None if args.forever else swarm_count
      for s in visible_roaches(pos, spacing, box_w, cols, count):
        roach_x = pos + s * spacing
        if roach_x >= cols or roach_x <= -box_w:
          continue

        phase = s * 0.9
        angle_z = math.sin(hop_phase * 0.5 + phase) * (
            0.35 if args.rave else 0.22
        )
        angle_x = math.cos(hop_phase * 0.5 + phase) * 0.15

        hop_wave = abs(math.sin(hop_phase + phase))
        bob_y = hop_wave * 0.55 * args.bounce
        row_hop = int(round(hop_wave * 2.2 * args.bounce))

        sprite_rows, row_depths = render_sprite(
            mesh,
            box_w,
            box_h,
            angle_y + phase,
            angle_z,
            angle_x,
            bob_y,
            lx,
            ly,
            lz,
            depth_weight=args.depth_weight,
            specular=args.specular,
            rim=args.rim,
            depth_fog=args.depth_fog,
        )

        if args.fly and not args.loop:
          progress = (cols - roach_x) / max(1, cols + box_w)
          ground_row = int(
              (rows - box_h) * (1.0 - progress)
              + math.sin(hop_phase * 0.3 + phase) * 2
          )
          ground_row = max(1, min(rows - box_h, ground_row))
        else:
          ground_row = center_top

        base_row = max(1, ground_row - row_hop)

        for r, row_str in enumerate(sprite_rows):
          draw_row = base_row + r
          if not (1 <= draw_row <= rows):
            continue

          start_c = max(0, -roach_x)
          end_c = min(box_w, cols - roach_x)
          draw_col = max(1, roach_x + 1)

          if start_c < end_c:
            visible = row_str[start_c:end_c]
            d_factor = row_depths[r] if args.depth_fog else 1.0
            color = get_color(args.color, anim_step * 0.25 + phase, d_factor)
            frame_buf.append(f"\033[{draw_row};{draw_col}H{color}{visible}")

        if args.accident:
          help_col = roach_x + box_w - 4
          help_row = base_row + 2
          if 1 <= help_row <= rows and 1 <= help_col <= cols - 7:
            frame_buf.append(
                f"\033[{help_row};{help_col}H\033[1;31m[HELP!]\033[0m{bg_code}"
            )

      sys.stdout.write("".join(frame_buf))
      sys.stdout.flush()

      angle_y += spin_rate
      anim_step += dance_step_rate * 0.1
      hop_phase += hop_rate
      frame_idx += 1
      # Sleep only for what is left of this frame's time slot.
      next_frame += delay
      wait = next_frame - time.monotonic()
      if wait > 0:
        time.sleep(wait)
      else:
        next_frame = time.monotonic()  # running behind: don't try to catch up

      if not args.loop:
        pos_idx += 1
        if not args.forever and pos_idx >= len(positions):
          break

  except KeyboardInterrupt:
    pass
  finally:
    sys.stdout.write("\033[0m\033[2J\033[H\033[?25h")
    sys.stdout.flush()


if __name__ == "__main__":
  run()