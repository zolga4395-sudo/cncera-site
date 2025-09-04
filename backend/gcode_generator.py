import math
from typing import Optional, Tuple, List, Dict

# ---- CAM geometry preparation ----
def prepare_bins(tris, step_xy: float, xmin: float, xmax: float, ymin: float, ymax: float):
    nx = max(16, min(96, int((xmax - xmin) / max(1e-6, step_xy * 2))))
    ny = max(16, min(96, int((ymax - ymin) / max(1e-6, step_xy * 2))))
    sx = (xmax - xmin) / nx if nx > 0 else 1.0
    sy = (ymax - ymin) / ny if ny > 0 else 1.0
    bins = [[[] for _ in range(ny)] for _ in range(nx)]
    coeffs_list = []

    def tri_coeff(tri):
        (x1, y1, z1), (x2, y2, z2), (x3, y3, z3) = tri
        ux, uy, uz = x2 - x1, y2 - y1, z2 - z1
        vx, vy, vz = x3 - x1, y3 - y1, z3 - z1
        A = uy * vz - uz * vy
        B = uz * vx - ux * vz
        C = ux * vy - uy * vx
        if abs(C) < 1e-12:
            return None
        D = -(A * x1 + B * y1 + C * z1)
        minx, maxx = min(x1, x2, x3), max(x1, x2, x3)
        miny, maxy = min(y1, y2, y3), max(y1, y2, y3)
        return (A, B, C, D, minx, maxx, miny, maxy, (x1, y1, z1), (x2, y2, z2), (x3, y3, z3))

    for tri in tris:
        c = tri_coeff(tri)
        if c is None:
            continue
        idx = len(coeffs_list)
        coeffs_list.append(c)
        minx, maxx, miny, maxy = c[4:8]
        i0 = int(max(0, min(nx - 1, math.floor((minx - xmin) / sx))))
        i1 = int(max(0, min(nx - 1, math.floor((maxx - xmin) / sx))))
        j0 = int(max(0, min(ny - 1, math.floor((miny - ymin) / sy))))
        j1 = int(max(0, min(ny - 1, math.floor((maxy - ymin) / sy))))
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                bins[i][j].append(idx)
    return bins, coeffs_list, nx, ny, sx, sy

def point_in_tri_xy(px: float, py: float, a: Tuple, b: Tuple, c: Tuple) -> bool:
    ax, ay, _ = a
    bx, by, _ = b
    cx, cy, _ = c
    v0x, v0y = cx - ax, cy - ay
    v1x, v1y = bx - ax, by - ay
    v2x, v2y = px - ax, py - ay
    d00 = v0x * v0x + v0y * v0y
    d01 = v0x * v1x + v0y * v1y
    d11 = v1x * v1x + v1y * v1y
    d20 = v2x * v0x + v2y * v0y
    d21 = v2x * v1x + v2y * v1y
    denom = d00 * d11 - d01 * d01
    if abs(denom) < 1e-12:
        return False
    v = (d11 * d20 - d01 * d21) / denom
    w = (d00 * d21 - d01 * d20) / denom
    u = 1.0 - v - w
    return u >= -1e-9 and v >= -1e-9 and w >= -1e-9

def z_for(px: float, py: float, coeffs: Tuple) -> Optional[float]:
    A, B, C, D, minx, maxx, miny, maxy, a, b, c = coeffs
    if not (minx - 1e-9 <= px <= maxx + 1e-9 and miny - 1e-9 <= py <= maxy + 1e-9):
        return None
    if not point_in_tri_xy(px, py, a, b, c):
        return None
    return -(A * px + B * py + D) / C

def build_top_sampler(stl_path, step_xy: float) -> Tuple[Tuple, callable]:
    try:
        from stl import mesh as stlmesh
    except ImportError:
        raise RuntimeError("numpy-stl not installed")
    
    m = stlmesh.Mesh.from_file(str(stl_path))
    tris = m.vectors
    xs, ys, zs = m.x, m.y, m.z
    xmin, xmax = float(xs.min()), float(xs.max())
    ymin, ymax = float(ys.min()), float(ys.max())
    zmin, zmax = float(zs.min()), float(zs.max())
    bins, coeffs, nx, ny, sx, sy = prepare_bins(tris, step_xy, xmin, xmax, ymin, ymax)

    def z_func(px: float, py: float) -> Optional[float]:
        i = int(min(nx - 1, max(0, math.floor((px - xmin) / sx))))
        j = int(min(ny - 1, max(0, math.floor((py - ymin) / sy))))
        best = None
        for di in (-1, 0, 1):
            ii = i + di
            if not (0 <= ii < nx):
                continue
            for dj in (-1, 0, 1):
                jj = j + dj
                if not (0 <= jj < ny):
                    continue
                for idx in bins[ii][jj]:
                    z = z_for(px, py, coeffs[idx])
                    if z is not None and (best is None or z > best):
                        best = z
        return best

    return (xmin, xmax, ymin, ymax, zmin, zmax), z_func

# ---- Marching Squares for waterline ----
def marching_squares(Z: List[List[float]], xs: List[float], ys: List[float], level: float) -> List[List[Tuple]]:
    ny, nx = len(Z), len(Z[0]) if Z else 0
    if nx < 2 or ny < 2:
        return []
    segs = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            z00, z10 = Z[j][i], Z[j][i + 1]
            z01, z11 = Z[j + 1][i], Z[j + 1][i + 1]
            c = 0
            if z00 > level:
                c |= 1
            if z10 > level:
                c |= 2
            if z11 > level:
                c |= 4
            if z01 > level:
                c |= 8
            if c == 0 or c == 15:
                continue
            x0, x1 = xs[i], xs[i + 1]
            y0, y1 = ys[j], ys[j + 1]

            def interp(a: float, b: float, za: float, zb: float) -> float:
                t = 0.5 if (zb - za) == 0 else (level - za) / ((zb - za) or 1e-9)
                return a + t * (b - a)

            pts = []
            if (c & 1) != (c & 8):
                pts.append((x0, interp(y0, y1, z00, z01)))
            if (c & 2) != (c & 4):
                pts.append((x1, interp(y0, y1, z10, z11)))
            if (c & 1) != (c & 2):
                pts.append((interp(x0, x1, z00, z10), y0))
            if (c & 8) != (c & 4):
                pts.append((interp(x0, x1, z01, z11), y1))
            if len(pts) == 2:
                segs.append((pts[0], pts[1]))
            elif len(pts) == 4:
                segs.append((pts[0], pts[1]))
                segs.append((pts[2], pts[3]))

    loops = []
    used = [False] * len(segs)
    for sidx, (a, b) in enumerate(segs):
        if used[sidx]:
            continue
        used[sidx] = True
        loop = [a, b]
        changed = True
        while changed:
            changed = False
            for k, (p, q) in enumerate(segs):
                if used[k]:
                    continue
                if abs(loop[-1][0] - p[0]) < 1e-6 and abs(loop[-1][1] - p[1]) < 1e-6:
                    loop.append(q)
                    used[k] = True
                    changed = True
                elif abs(loop[-1][0] - q[0]) < 1e-6 and abs(loop[-1][1] - q[1]) < 1e-6:
                    loop.append(p)
                    used[k] = True
                    changed = True
        if len(loop) >= 3:
            loops.append(loop)
    return loops

# ---- Controller and operation-specific G-code functions ----
def get_controller_settings(controller: str) -> Dict:
    """Get controller-specific G-code settings"""
    settings = {
        "fanuc": {
            "header": ["G90", "G17", "G21", "G54"],
            "spindle_on": "M3 S{spindle}",
            "spindle_off": "M5",
            "coolant_on": "M8",
            "coolant_off": "M9",
            "rapid": "G0",
            "linear": "G1",
            "program_end": "M30"
        },
        "siemens": {
            "header": ["G90", "G17", "G71", "G54"],
            "spindle_on": "M3 S{spindle}",
            "spindle_off": "M5",
            "coolant_on": "M7",
            "coolant_off": "M9",
            "rapid": "G0",
            "linear": "G1",
            "program_end": "M2"
        },
        "heidenhain": {
            "header": ["* - Generated by CNCera", "BLK FORM 0.1 Z X+0 Y+0 Z-50"],
            "spindle_on": "SPINDLE ON CW SPEED {spindle}",
            "spindle_off": "SPINDLE OFF",
            "coolant_on": "COOLANT ON",
            "coolant_off": "COOLANT OFF",
            "rapid": "L",
            "linear": "L",
            "program_end": "END PGM"
        },
        "gsk": {
            "header": ["G90", "G17", "G21", "G54"],
            "spindle_on": "M3 S{spindle}",
            "spindle_off": "M5",
            "coolant_on": "M8",
            "coolant_off": "M9",
            "rapid": "G00",
            "linear": "G01",
            "program_end": "M30"
        },
        "mazak": {
            "header": ["G90", "G17", "G21", "G54"],
            "spindle_on": "M3 S{spindle}",
            "spindle_off": "M5",
            "coolant_on": "M8",
            "coolant_off": "M9",
            "rapid": "G0",
            "linear": "G1",
            "program_end": "M99"
        }
    }
    return settings.get(controller, settings["fanuc"])

def generate_chamfer_gcode(stl_path, out_path, **params) -> Dict:
    """Generate G-code for chamfering operations"""
    controller_settings = get_controller_settings(params.get("controller", "fanuc"))

    (xmin, xmax, ymin, ymax, zmin, zmax), z_func = build_top_sampler(stl_path, 0.1)

    xmin -= params.get("allowance_x", 0)
    xmax += params.get("allowance_x", 0)
    ymin -= params.get("allowance_y", 0)
    ymax += params.get("allowance_y", 0)
    zmax += params.get("allowance_z", 0)

    with open(out_path, "w", encoding="ascii", errors="ignore") as f:
        w = f.write
        w("(Generated by CNCera - Chamfer Operation)\n")
        for cmd in controller_settings["header"]:
            w(f"{cmd}\n")
        if params.get("spindle"):
            w(f"{controller_settings['spindle_on'].format(spindle=params['spindle'])}\n")
        w(f"{controller_settings['coolant_on']}\n")

        clearance = params.get("clearance", 5.0)
        tool_diam = params.get("tool_diam", 3.0)

        w(f"(Chamfer around perimeter)\n")
        w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")

        w(f"{controller_settings['rapid']} X{xmin:.3f} Y{ymin:.3f}\n")
        w(f"{controller_settings['linear']} Z{zmax:.3f} F{params.get('plunge', 120):.1f}\n")

        chamfer_points = [
            (xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax), (xmin, ymin)
        ]
        w(f"F{params.get('feed', 300):.1f}\n")
        for x, y in chamfer_points:
            w(f"{controller_settings['linear']} X{x:.3f} Y{y:.3f}\n")

        w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")
        w(f"{controller_settings['coolant_off']}\n")
        if params.get("spindle"):
            w(f"{controller_settings['spindle_off']}\n")
        w(f"{controller_settings['program_end']}\n")

    return {
        "bbox": {"xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax, "zmin": zmin, "zmax": zmax},
        "grid": {"nx": 4, "ny": 4, "step_xy": (xmax - xmin) / 4},
        "origin": {"ox": xmin, "oy": ymin, "oz": zmin}
    }

def generate_turning_gcode(stl_path, out_path, **params) -> Dict:
    """Generate G-code for turning operations"""
    controller_settings = get_controller_settings(params.get("controller", "fanuc"))

    with open(out_path, "w", encoding="ascii", errors="ignore") as f:
        w = f.write
        w("(Generated by CNCera - Turning Operation)\n")
        for cmd in controller_settings["header"]:
            w(f"{cmd}\n")
        if params.get("spindle"):
            w(f"{controller_settings['spindle_on'].format(spindle=params['spindle'])}\n")
        w(f"{controller_settings['coolant_on']}\n")

        workpiece_dia = params.get("workpiece_diameter", 50.0)
        cut_depth = params.get("cut_depth", 1.0)
        feed_per_rev = params.get("feed_per_rev", 0.2)
        turning_type = params.get("turning_type", "roughing")
        clearance = params.get("clearance", 5.0)

        if turning_type == "facing":
            w("(Face operation)\n")
            w(f"{controller_settings['rapid']} X{workpiece_dia + clearance:.3f} Z{clearance:.3f}\n")
            w(f"{controller_settings['rapid']} Z0.5\n")
            w(f"{controller_settings['linear']} X{workpiece_dia:.3f} F{feed_per_rev:.3f}\n")
            w(f"{controller_settings['linear']} X0 Z0\n")
        else:
            w(f"(Turning - {turning_type})\n")
            current_dia = workpiece_dia
            target_dia = workpiece_dia - (cut_depth * 2)
            while current_dia > target_dia:
                w(f"{controller_settings['rapid']} X{current_dia + clearance:.3f} Z{clearance:.3f}\n")
                w(f"{controller_settings['rapid']} Z0.5\n")
                w(f"{controller_settings['linear']} X{current_dia:.3f} F{feed_per_rev:.3f}\n")
                w(f"{controller_settings['linear']} Z-50\n")
                current_dia -= cut_depth * 2

        w(f"{controller_settings['rapid']} X{workpiece_dia + clearance:.3f} Z{clearance:.3f}\n")
        w(f"{controller_settings['coolant_off']}\n")
        if params.get("spindle"):
            w(f"{controller_settings['spindle_off']}\n")
        w(f"{controller_settings['program_end']}\n")

    return {
        "bbox": {"xmin": 0, "xmax": workpiece_dia, "ymin": 0, "ymax": workpiece_dia, "zmin": -50, "zmax": 0},
        "grid": {"nx": 10, "ny": 10, "step_xy": workpiece_dia / 10},
        "origin": {"ox": 0, "oy": 0, "oz": 0}
    }

def generate_drilling_gcode(stl_path, out_path, **params) -> Dict:
    """Generate G-code for drilling operations"""
    controller_settings = get_controller_settings(params.get("controller", "fanuc"))

    (xmin, xmax, ymin, ymax, zmin, zmax), z_func = build_top_sampler(stl_path, 0.5)

    with open(out_path, "w", encoding="ascii", errors="ignore") as f:
        w = f.write
        w("(Generated by CNCera - Drilling Operation)\n")
        for cmd in controller_settings["header"]:
            w(f"{cmd}\n")
        if params.get("spindle"):
            w(f"{controller_settings['spindle_on'].format(spindle=params['spindle'])}\n")
        w(f"{controller_settings['coolant_on']}\n")

        drill_cycle = params.get("drill_cycle", "G81")
        drill_depth = params.get("drill_depth", 10.0)
        clearance = params.get("clearance", 5.0)
        peck_depth = params.get("peck_depth", 2.0)
        feed = params.get("feed", 300.0)

        center_x = (xmin + xmax) / 2
        center_y = (ymin + ymax) / 2

        w(f"(Drilling cycle: {drill_cycle})\n")
        w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")
        w(f"{controller_settings['rapid']} X{center_x:.3f} Y{center_y:.3f}\n")

        if drill_cycle == "G83":
            w(f"G83 X{center_x:.3f} Y{center_y:.3f} Z{-drill_depth:.3f} R{clearance:.3f} Q{peck_depth:.3f} F{feed:.1f}\n")
        elif drill_cycle == "G82":
            w(f"G82 X{center_x:.3f} Y{center_y:.3f} Z{-drill_depth:.3f} R{clearance:.3f} P1000 F{feed:.1f}\n")
        else:
            w(f"G81 X{center_x:.3f} Y{center_y:.3f} Z{-drill_depth:.3f} R{clearance:.3f} F{feed:.1f}\n")

        w("G80\n")
        w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")
        w(f"{controller_settings['coolant_off']}\n")
        if params.get("spindle"):
            w(f"{controller_settings['spindle_off']}\n")
        w(f"{controller_settings['program_end']}\n")

    return {
        "bbox": {"xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax, "zmin": zmin - drill_depth, "zmax": zmax},
        "grid": {"nx": 1, "ny": 1, "step_xy": 1},
        "origin": {"ox": center_x, "oy": center_y, "oz": zmax}
    }

def generate_raster_gcode(
        stl_path,
        out_path,
        tool_diam: float = 3.0,
        stepover: float = 0.4,
        feed: float = 300.0,
        plunge: float = 120.0,
        clearance: float = 5.0,
        spindle: Optional[int] = 8000,
        dir_axis: str = "X",
        origin: str = "bbox_min",
        stepdown: float = 0.0,
        feed_rough: Optional[float] = None,
        feed_finish: Optional[float] = None,
        finish_stepover: Optional[float] = None,
        waterline: bool = False,
        waterline_dz: float = 0.0,
        allowance_x: float = 0.0,
        allowance_y: float = 0.0,
        allowance_z: float = 0.0,
        controller: str = "fanuc",
        operation_type: str = "milling"
) -> Dict:
    def validate_float(value, default: float, min_val: float, max_val: float) -> float:
        try:
            val = float(value)
            return max(min_val, min(max_val, val))
        except (TypeError, ValueError):
            return default

    def validate_int(value, default: int, min_val: int, max_val: int) -> int:
        try:
            val = int(value)
            return max(min_val, min(max_val, val))
        except (TypeError, ValueError):
            return default

    tool_diam = validate_float(tool_diam, 3.0, 0.1, 50.0)
    stepover = validate_float(stepover, 0.4, 0.05, 0.95)
    feed = validate_float(feed, 300.0, 10.0, 5000.0)
    plunge = validate_float(plunge, 120.0, 10.0, 2000.0)
    clearance = validate_float(clearance, 5.0, 1.0, 50.0)
    spindle = validate_int(spindle, 8000, 1000, 24000) if spindle else None
    stepdown = validate_float(stepdown, 0.0, 0.0, 50.0)
    feed_rough = validate_float(feed_rough, feed, 10.0, 5000.0) if feed_rough else feed
    feed_finish = validate_float(feed_finish, feed, 10.0, 5000.0) if feed_finish else feed
    finish_stepover = validate_float(finish_stepover, stepover, 0.05, 0.95) if finish_stepover else stepover
    waterline_dz = validate_float(waterline_dz, 0.0, 0.0, 50.0)

    step_xy = max(0.1, tool_diam * stepover)
    (xmin, xmax, ymin, ymax, zmin, zmax), z_func = build_top_sampler(stl_path, step_xy)

    # Apply allowances to geometry bounds
    xmin -= allowance_x
    xmax += allowance_x
    ymin -= allowance_y
    ymax += allowance_y
    zmax += allowance_z

    def estimate_cost(step: float) -> int:
        nx = max(2, int(math.ceil((xmax - xmin) / step)) + 1)
        ny = max(2, int(math.ceil((ymax - ymin) / step)) + 1)
        return nx * ny

    MAX_POINTS = 40000
    points = estimate_cost(step_xy)
    while points > MAX_POINTS:
        step_xy *= 1.3
        points = estimate_cost(step_xy)

    nx = max(2, int(math.ceil((xmax - xmin) / step_xy)) + 1)
    ny = max(2, int(math.ceil((ymax - ymin) / step_xy)) + 1)

    origin = origin if origin in ("bbox_min", "bbox_center", "bbox_top_center") else "bbox_min"
    ox, oy, oz = {
        "bbox_min": (xmin, ymin, zmin),
        "bbox_center": ((xmin + xmax) / 2.0, (ymin + ymax) / 2.0, zmin),
        "bbox_top_center": ((xmin + xmax) / 2.0, (ymin + ymax) / 2.0, zmax)
    }[origin]

    controller_settings = get_controller_settings(controller)

    def zigzag_lines():
        lines = []
        dir_axis_upper = dir_axis.upper()
        if dir_axis_upper == "X":
            ys = [ymin + i * step_xy for i in range(ny)]
            for j, y in enumerate(ys):
                xs = [xmin + i * step_xy for i in range(nx)]
                if j % 2 == 1:
                    xs.reverse()
                lines.append([(x, y) for x in xs])
        else:
            xs = [xmin + i * step_xy for i in range(nx)]
            for i, x in enumerate(xs):
                ys = [ymin + j * step_xy for j in range(ny)]
                if i % 2 == 1:
                    ys.reverse()
                lines.append([(x, y) for y in ys])
        return lines

    def sample_height_grid(step: float):
        xs = [xmin + i * step for i in range(nx)]
        ys = [ymin + j * step for j in range(ny)]
        Z = [[z_func(x, y) or -1e12 for x in xs] for y in ys]
        return xs, ys, Z

    with open(out_path, "w", encoding="ascii", errors="ignore") as f:
        w = f.write
        w(f"(Generated by CNCera - {operation_type.title()} - {controller.upper()})\n")
        w(f"(Origin: {origin})\n")

        for cmd in controller_settings["header"]:
            w(f"{cmd}\n")

        if spindle:
            w(f"{controller_settings['spindle_on'].format(spindle=spindle)}\n")
        w(f"{controller_settings['coolant_on']}\n")
        w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")

        if stepdown > 0:
            zL = zmax
            while zL > zmin + 0.5 * stepdown:
                zL -= stepdown
                w(f"(Rough level Z={zL - oz:.3f})\n")
                for line in zigzag_lines():
                    x0, y0 = line[0]
                    w(f"{controller_settings['rapid']} X{(x0 - ox):.3f} Y{(y0 - oy):.3f}\n")
                    z0 = z_func(x0, y0)
                    if z0 is not None:
                        zt = min(z0, zL)
                        w(f"{controller_settings['linear']} Z{(zt - oz):.3f} F{plunge:.1f}\n")
                        w(f"F{feed_rough:.1f}\n")
                    else:
                        w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")
                    for x, y in line[1:]:
                        z = z_func(x, y)
                        if z is None:
                            w(f"{controller_settings['rapid']} Z{clearance:.3f}\n{controller_settings['rapid']} X{(x - ox):.3f} Y{(y - oy):.3f}\n")
                        else:
                            zt = min(z, zL)
                            w(f"{controller_settings['linear']} X{(x - ox):.3f} Y{(y - oy):.3f} Z{(zt - oz):.3f}\n")
                w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")

        if finish_stepover != stepover:
            step_fin_xy = max(0.05, tool_diam * finish_stepover)
            if step_fin_xy != step_xy:
                (xmin, xmax, ymin, ymax, _, _), z_func = build_top_sampler(stl_path, step_fin_xy)
                xmin -= allowance_x
                xmax += allowance_x
                ymin -= allowance_y
                ymax += allowance_y
                nx = max(2, int(math.ceil((xmax - xmin) / step_fin_xy)) + 1)
                ny = max(2, int(math.ceil((ymax - ymin) / step_fin_xy)) + 1)

        w("(Finish pass)\n")
        for line in zigzag_lines():
            x0, y0 = line[0]
            w(f"{controller_settings['rapid']} X{(x0 - ox):.3f} Y{(y0 - oy):.3f}\n")
            z0 = z_func(x0, y0)
            if z0 is not None:
                w(f"{controller_settings['linear']} Z{(z0 - oz):.3f} F{plunge:.1f}\n")
                w(f"F{feed_finish:.1f}\n")
            else:
                w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")
            for x, y in line[1:]:
                z = z_func(x, y)
                if z is None:
                    w(f"{controller_settings['rapid']} Z{clearance:.3f}\n{controller_settings['rapid']} X{(x - ox):.3f} Y{(y - oy):.3f}\n")
                else:
                    w(f"{controller_settings['linear']} X{(x - ox):.3f} Y{(y - oy):.3f} Z{(z - oz):.3f}\n")
        w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")

        if waterline and waterline_dz > 0:
            w("(Waterline)\n")
            xs, ys, Z = sample_height_grid(max(step_xy, tool_diam * 0.6))
            cur = zmax
            while cur > zmin + 0.5 * waterline_dz:
                cur -= waterline_dz
                loops = marching_squares(Z, xs, ys, cur)
                for loop in loops:
                    sx, sy = loop[0]
                    w(f"{controller_settings['rapid']} X{(sx - ox):.3f} Y{(sy - oy):.3f} Z{clearance:.3f}\n")
                    w(f"{controller_settings['linear']} Z{(cur - oz):.3f} F{plunge:.1f}\n")
                    w(f"F{feed_finish:.1f}\n")
                    for x, y in loop[1:]:
                        w(f"{controller_settings['linear']} X{(x - ox):.3f} Y{(y - oy):.3f} Z{(cur - oz):.3f}\n")
                    w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")

        w(f"{controller_settings['coolant_off']}\n")
        if spindle:
            w(f"{controller_settings['spindle_off']}\n")
        w(f"{controller_settings['program_end']}\n")

    return {
        "bbox": {"xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax, "zmin": zmin, "zmax": zmax},
        "grid": {"nx": nx, "ny": ny, "step_xy": step_xy},
        "origin": {"ox": ox, "oy": oy, "oz": oz}
    }