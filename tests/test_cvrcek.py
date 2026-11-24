"""Tests for cvrcek. Run with: python3 -m unittest discover tests"""
import math
import os
import random
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import cvrcek  # noqa: E402
from cvrcek import CHARS, SPECULAR_CHARS, _rot_x, _rot_y, _rot_z  # noqa: E402,F401

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "cvrcek.py")


# The original (slow) renderer, kept as the reference the fast one must match.
def reference_render_sprite(
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
  zbuffer = [-999.0] * (box_w * box_h)
  depth_map = [0.5] * (box_w * box_h)
  output = [" "] * (box_w * box_h)

  scale_y = box_h * 0.185
  scale_x = scale_y * 2.0

  vx, vy, vz = 0.0, 0.0, 1.0
  hx_dir, hy_dir, hz_dir = lx + vx, ly + vy, lz + vz
  h_len = math.sqrt(hx_dir**2 + hy_dir**2 + hz_dir**2) or 1.0
  hx_dir, hy_dir, hz_dir = hx_dir / h_len, hy_dir / h_len, hz_dir / h_len

  dw = max(0.0, min(1.0, depth_weight))
  lw = 1.0 - dw

  for x, y, z, nx, ny, nz, bias in mesh:
    p = _rot_y((x, y + bob_y, z), angle_y)
    p = _rot_z(p, angle_z)
    x3, y3, z3 = _rot_x(p, angle_x)

    n = _rot_y((nx, ny, nz), angle_y)
    n = _rot_z(n, angle_z)
    nx3, ny3, nz3 = _rot_x(n, angle_x)

    denom = z3 + 5.8
    if denom <= 0.4:
      continue
    inv_z = 1.0 / denom
    px = int(box_w / 2 + x3 * scale_x * inv_z * 5.0)
    py = int(box_h / 2 - y3 * scale_y * inv_z * 5.0)

    if 0 <= px < box_w and 0 <= py < box_h:
      idx = py * box_w + px
      if inv_z > zbuffer[idx]:
        zbuffer[idx] = inv_z

        near_factor = max(0.0, min(1.0, (1.6 - z3) / 3.2))

        if depth_fog:
          depth_map[idx] = max(0.45, min(1.25, 0.55 + near_factor * 0.65))

        raw_lum = nx3 * lx + ny3 * ly + nz3 * lz + bias
        lit_factor = max(0.0, min(1.0, (raw_lum + 0.65) / 1.65))

        spec = 0.0
        if specular:
          ndoth = max(0.0, nx3 * hx_dir + ny3 * hy_dir + nz3 * hz_dir)
          spec = (ndoth**14) * 0.35

        rim_boost = 0.0
        if rim:
          grazing = max(0.0, 1.0 - abs(nz3))
          rim_boost = (grazing**2.2) * 0.20

        combined = max(
            0.0, min(1.0, dw * near_factor + lw * lit_factor + spec + rim_boost)
        )
        ramp = SPECULAR_CHARS if specular else CHARS
        char_idx = int(combined * (len(ramp) - 1 + 0.999))
        char_idx = max(0, min(len(ramp) - 1, char_idx))
        output[idx] = ramp[char_idx]

  rows_out = [
      "".join(output[r * box_w : (r + 1) * box_w]) for r in range(box_h)
  ]
  avg_depths = [
      sum(depth_map[r * box_w : (r + 1) * box_w]) / max(1, box_w)
      for r in range(box_h)
  ]
  return rows_out, avg_depths



class RenderTest(unittest.TestCase):

  def test_fast_render_matches_reference(self):
    rng = random.Random(1)
    for _ in range(30):
      mesh = cvrcek.build_articulated_roach(
          rng.uniform(0, 50),
          rng.choice(cvrcek.DANCE_STYLES),
          with_sombrero=rng.random() < 0.5,
      )
      angles = (
          rng.uniform(-3, 3),
          rng.uniform(-0.4, 0.4),
          rng.uniform(-0.2, 0.2),
          rng.uniform(0, 0.6),
      )
      opts = dict(
          specular=rng.random() < 0.5,
          rim=rng.random() < 0.5,
          depth_fog=rng.random() < 0.5,
      )
      w, h = rng.choice([(48, 28), (16, 10), (96, 40)])
      fast_rows, fast_depths = cvrcek.render_sprite(
          mesh, w, h, *angles, 0.45, 0.55, 0.70, **opts
      )
      ref_rows, ref_depths = reference_render_sprite(
          mesh, w, h, *angles, 0.45, 0.55, 0.70, **opts
      )
      self.assertEqual(fast_rows, ref_rows)
      for a, b in zip(fast_depths, ref_depths):
        self.assertAlmostEqual(a, b, places=9)


class VisibleRoachesTest(unittest.TestCase):

  def brute(self, pos, spacing, box_w, cols, count):
    return [
        s
        for s in range(count)
        if -box_w < pos + s * spacing < cols
    ]

  def test_matches_brute_force(self):
    for pos in range(-3000, 300, 7):
      for count in (1, 3, 50):
        self.assertEqual(
            list(cvrcek.visible_roaches(pos, 40, 48, 220, count)),
            self.brute(pos, 40, 48, 220, count),
        )

  def test_forever_always_has_roaches(self):
    for pos in (-10**6, -12345, 0):
      self.assertTrue(cvrcek.visible_roaches(pos, 40, 48, 220, None))


class CenteringTest(unittest.TestCase):

  def screen_extent(self, rows, cols, bounce, sombrero, size=1.0):
    """Highest and lowest screen row the roach reaches over a hop cycle,
    placed exactly the way run() places it."""
    box_w = max(16, min(cols, int(48 * size)))
    box_h = max(10, min(rows - 2, int(28 * size)))
    top_row = cvrcek.centered_top_row(
        rows, box_h, bounce, cvrcek.figure_middle(box_w, box_h, sombrero)
    )
    highest, lowest = rows, 0
    for k in range(60):
      hop_wave = abs(math.sin(k * math.pi / 60))
      mesh = cvrcek.build_articulated_roach(k * 0.1, "groove", sombrero)
      sprite, _ = cvrcek.render_sprite(
          mesh, box_w, box_h, k * 0.22, 0.0, 0.0,
          hop_wave * 0.55 * bounce, 0.45, 0.55, 0.70,
      )
      base = max(1, top_row - int(round(hop_wave * 2.2 * bounce)))
      drawn = [base + r for r, line in enumerate(sprite) if line.strip()]
      highest, lowest = min(highest, drawn[0]), max(lowest, drawn[-1])
    return highest, lowest

  def test_hop_is_centered_vertically(self):
    for rows, bounce, sombrero, size in [
        (40, 1.0, False, 1.0), (60, 1.0, True, 1.0), (50, 0.0, False, 1.0),
        (80, 1.0, False, 2.0), (35, 1.0, False, 1.0),
    ]:  # not -b 2: there the head hops out of the sprite box and is clipped
      highest, lowest = self.screen_extent(rows, 200, bounce, sombrero, size)
      space_above = highest - 1
      space_below = rows - lowest
      self.assertLessEqual(
          abs(space_above - space_below), 2,
          f"rows={rows} bounce={bounce}: {space_above} above, "
          f"{space_below} below",
      )


class CliTest(unittest.TestCase):

  def test_forever_flag(self):
    ns = self._parse(["-f"])
    self.assertTrue(ns.forever)
    self.assertFalse(self._parse([]).forever)

  def _parse(self, argv):
    old = sys.argv
    sys.argv = ["cvrcek"] + argv
    try:
      return cvrcek.parse_args()
    finally:
      sys.argv = old

  def test_short_run_finishes(self):
    env = dict(os.environ, COLUMNS="40", LINES="20")
    out = subprocess.run(
        [sys.executable, SCRIPT, "-s", "20", "-n", "2", "-S", "--trail", "-a"],
        env=env, capture_output=True, timeout=60,
    )
    self.assertEqual(out.returncode, 0, out.stderr)
    self.assertIn(b"\033[?25h", out.stdout)  # cursor restored


if __name__ == "__main__":
  unittest.main()
