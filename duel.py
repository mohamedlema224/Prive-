#!/usr/bin/env python3
"""Duel a l'epee : animation de 60 s, 2 combattants, rendu MP4 avec son."""
import math, random, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from multiprocessing import Pool

W, H = 1280, 720
SS = 2                      # supersampling
FPS = 30
DUR = 60.0
NF = int(DUR * FPS)
GROUND = 590
OUT = sys.argv[1] if len(sys.argv) > 1 else "duel.mp4"
PREVIEW = [float(x) for x in sys.argv[2:]]  # times -> png previews only

random.seed(7)

# ---------------------------------------------------------------- poses
# angles en degres, 0 = vers l'avant (droite pour A), 90 = vers le bas, -90 = haut
P = dict(
    stand=dict(lean=-90, ua=95, fa=88, sw=70, bua=92, bfa=95, ft=86, fs=92, bt=96, bs=92),
    salute=dict(lean=-90, ua=75, fa=-115, sw=-90, bua=95, bfa=92, ft=86, fs=92, bt=96, bs=92),
    guard=dict(lean=-80, ua=55, fa=-5, sw=-38, bua=150, bfa=-150, ft=58, fs=98, bt=122, bs=96),
    guard2=dict(lean=-84, ua=60, fa=-15, sw=-48, bua=145, bfa=-140, ft=62, fs=96, bt=118, bs=94),
    wind_high=dict(lean=-98, ua=-120, fa=-150, sw=-175, bua=125, bfa=165, ft=64, fs=100, bt=118, bs=94),
    hit_high=dict(lean=-72, ua=-25, fa=-30, sw=-40, bua=160, bfa=175, ft=45, fs=98, bt=135, bs=110),
    fol_high=dict(lean=-62, ua=25, fa=40, sw=55, bua=165, bfa=175, ft=40, fs=96, bt=140, bs=118),
    blk_high=dict(lean=-98, ua=-55, fa=-95, sw=-8, bua=130, bfa=160, ft=70, fs=102, bt=118, bs=96),
    wind_mid=dict(lean=-100, ua=165, fa=-175, sw=-170, bua=60, bfa=20, ft=62, fs=98, bt=120, bs=96),
    hit_mid=dict(lean=-74, ua=10, fa=-8, sw=-12, bua=165, bfa=175, ft=42, fs=98, bt=136, bs=112),
    fol_mid=dict(lean=-70, ua=-20, fa=-60, sw=-120, bua=165, bfa=175, ft=45, fs=98, bt=134, bs=110),
    blk_mid=dict(lean=-92, ua=50, fa=-35, sw=-82, bua=140, bfa=170, ft=70, fs=100, bt=120, bs=96),
    wind_low=dict(lean=-96, ua=-100, fa=-150, sw=-155, bua=130, bfa=170, ft=62, fs=98, bt=120, bs=96),
    hit_low=dict(lean=-58, ua=55, fa=45, sw=30, bua=170, bfa=-170, ft=35, fs=100, bt=140, bs=120),
    fol_low=dict(lean=-55, ua=80, fa=95, sw=120, bua=170, bfa=-170, ft=35, fs=100, bt=140, bs=120),
    blk_low=dict(lean=-72, ua=65, fa=30, sw=62, bua=150, bfa=-160, ft=50, fs=100, bt=128, bs=105),
    wind_thr=dict(lean=-95, ua=150, fa=-178, sw=-4, bua=60, bfa=-60, ft=70, fs=100, bt=115, bs=95),
    hit_thr=dict(lean=-66, ua=-6, fa=-6, sw=-10, bua=175, bfa=-175, ft=25, fs=92, bt=150, bs=140),
    blk_thr=dict(lean=-94, ua=62, fa=-8, sw=-78, bua=145, bfa=-160, ft=74, fs=102, bt=116, bs=94),
    stagger=dict(lean=-112, ua=-60, fa=-30, sw=-30, bua=-130, bfa=-110, ft=70, fs=104, bt=112, bs=95),
    kneel=dict(lean=-80, ua=-40, fa=-70, sw=-30, bua=110, bfa=95, ft=2, fs=88, bt=96, bs=175),
    point=dict(lean=-80, ua=8, fa=2, sw=6, bua=150, bfa=-150, ft=45, fs=96, bt=128, bs=100),
    victory=dict(lean=-90, ua=-80, fa=-95, sw=-92, bua=95, bfa=92, ft=80, fs=92, bt=100, bs=92),
)
KEYS = list(P["stand"].keys())

L = dict(torso=78, neck=12, head=15, ua=44, fa=40, th=58, sh=58, sword=118, hilt=18)


def ease(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def lerp_angle(a, b, u):
    d = (b - a + 180) % 360 - 180
    return a + d * u


class Track:
    """Suite de keyframes (t, pose, x)."""
    def __init__(self):
        self.k = []

    def add(self, t, pose, x):
        self.k.append((t, pose, x))

    def sample(self, t):
        k = self.k
        if t <= k[0][0]:
            return dict(P[k[0][1]]), k[0][2]
        for i in range(len(k) - 1):
            t0, p0, x0 = k[i]
            t1, p1, x1 = k[i + 1]
            if t0 <= t <= t1:
                u = ease((t - t0) / max(1e-6, t1 - t0))
                a, b = P[p0], P[p1]
                pose = {n: lerp_angle(a[n], b[n], u) for n in KEYS}
                return pose, x0 + (x1 - x0) * u
        return dict(P[k[-1][1]]), k[-1][2]


# ---------------------------------------------------------------- choregraphie
A, B = Track(), Track()
events = []  # (t, kind, data)

A.add(0, "stand", 330); B.add(0, "stand", 950)
A.add(3.2, "stand", 330); B.add(3.6, "stand", 950)
A.add(4.4, "salute", 330); B.add(4.8, "salute", 950)
A.add(5.8, "salute", 330); B.add(6.1, "salute", 950)
A.add(7.0, "guard", 340); B.add(7.2, "guard", 940)
events += [(4.1, "swish", 330), (4.5, "swish", 950), (6.6, "swish", 340), (6.9, "swish", 940)]

# approche / tournoiement
t = 7.2
ax, bx = 340, 940
for i, (dax, dbx) in enumerate([(70, -60), (40, -50), (-20, 10), (50, -40), (25, -35)]):
    t += 0.75
    ax += dax; bx += dbx
    A.add(t, "guard2" if i % 2 else "guard", ax)
    B.add(t + 0.1, "guard" if i % 2 else "guard2", bx)
    events.append((t, "step", ax)); events.append((t + 0.1, "step", bx))
t += 0.4

GAP = 255  # distance entre hanches lors d'un echange
center = (ax + bx) / 2
ax, bx = center - GAP / 2, center + GAP / 2
A.add(t, "guard", ax); B.add(t, "guard", bx)

kinds = ["high", "mid", "low", "thr"]
blocks = dict(high="blk_high", mid="blk_mid", low="blk_low", thr="blk_thr")
script = []
seq_end = 50.0
attacker = 0
prev_kind = None
while t < seq_end - 1.6:
    kind = random.choice([k for k in kinds if k != prev_kind])
    prev_kind = kind
    fast = random.random() < 0.35
    sp = 0.65 if fast else 1.0
    script.append((t, kind, attacker, sp))
    # avance / recul : la paire glisse vers le defenseur
    drift = 45 if attacker == 0 else -45
    if center + drift > 900 or center + drift < 380:
        drift = -drift * 0.5
    atk, dfn = (A, B) if attacker == 0 else (B, A)
    c0 = center
    center += drift
    nax, nbx = center - GAP / 2, center + GAP / 2
    a_x0, d_x0 = (c0 - GAP / 2, c0 + GAP / 2) if attacker == 0 else (c0 + GAP / 2, c0 - GAP / 2)
    a_x1, d_x1 = (nax, nbx) if attacker == 0 else (nbx, nax)
    sgn = 1 if attacker == 0 else -1
    tw, th_, tf, tr = t + 0.38 * sp, t + 0.62 * sp, t + 0.80 * sp, t + 1.15 * sp
    atk.add(tw, "wind_" + kind, a_x0 + sgn * 5)
    atk.add(th_, "hit_" + kind, a_x1)
    atk.add(tf, "fol_" + kind if kind != "thr" else "hit_thr", a_x1 - sgn * 8)
    atk.add(tr, "guard", a_x1 - sgn * 4)
    dfn.add(t + 0.30 * sp, "guard2", d_x0)
    dfn.add(th_ - 0.06 * sp, blocks[kind], d_x1 + sgn * 6)
    dfn.add(tf + 0.05, blocks[kind], d_x1 + sgn * 10)
    dfn.add(tr + 0.08, "guard", d_x1)
    events.append((tw + 0.05 * sp, "whoosh", a_x1))
    events.append((th_, "clash", kind))
    events.append((th_ - 0.1, "step", d_x1))
    t = tr + (0.12 if fast else random.uniform(0.3, 0.7))
    # changement d'attaquant
    if random.random() < 0.55:
        attacker = 1 - attacker
    # pause occasionnelle : les deux tournent
    if random.random() < 0.18 and t < seq_end - 4:
        t += 0.5
        A.add(t, "guard2", center - GAP / 2 - 40); B.add(t, "guard2", center + GAP / 2 + 40)
        t += 0.7
        A.add(t, "guard", center - GAP / 2); B.add(t, "guard", center + GAP / 2)
        events.append((t - 0.7, "step", center)); events.append((t, "step", center))

# final : A desarme B
ax, bx = center - GAP / 2, center + GAP / 2
t = max(t, seq_end - 1.4)
A.add(t, "guard", ax); B.add(t, "guard", bx)
t += 0.5
A.add(t, "wind_low", ax - 10); B.add(t, "guard2", bx)
T_DISARM = t + 0.3
A.add(T_DISARM, "hit_thr", ax + 40); B.add(T_DISARM - 0.05, "blk_thr", bx + 5)
events.append((T_DISARM - 0.2, "whoosh", ax)); events.append((T_DISARM, "clash", "disarm"))
B.add(T_DISARM + 0.45, "stagger", bx + 50)
A.add(T_DISARM + 0.6, "guard", ax + 60)
B.add(T_DISARM + 1.3, "kneel", bx + 45)
events.append((T_DISARM + 1.2, "thud", bx))
A.add(T_DISARM + 1.7, "guard", ax + 60)
A.add(T_DISARM + 2.3, "point", ax + 45)
A.add(T_DISARM + 5.0, "point", ax + 45)
B.add(T_DISARM + 5.5, "kneel", bx + 45)
A.add(T_DISARM + 6.0, "stand", ax + 45)
A.add(T_DISARM + 6.8, "victory", ax + 45)
A.add(DUR + 1, "victory", ax + 45)
B.add(DUR + 1, "kneel", bx + 45)
events.append((T_DISARM + 6.4, "swish", ax))
CLASH_T = sorted(e[0] for e in events if e[1] == "clash")
B_DISARMED = T_DISARM + 0.03


# ---------------------------------------------------------------- squelette
def rad(a):
    return math.radians(a)


def pt(p, ang, l, face):
    a = rad(ang)
    return (p[0] + face * l * math.cos(a), p[1] + l * math.sin(a))


def skeleton(pose, x, face):
    hip0 = (x, 0.0)
    fk = pt(hip0, pose["ft"], L["th"], face); ff = pt(fk, pose["fs"], L["sh"], face)
    bk = pt(hip0, pose["bt"], L["th"], face); bf = pt(bk, pose["bs"], L["sh"], face)
    low = max(ff[1], bf[1], fk[1] + 6, bk[1] + 6)
    dy = GROUND - low
    sh = lambda p: (p[0], p[1] + dy)
    hip = sh(hip0); fk, ff, bk, bf = map(sh, (fk, ff, bk, bf))
    nk = pt(hip, pose["lean"], L["torso"], face)
    head = pt(nk, pose["lean"], L["neck"] + L["head"], face)
    sho = pt(hip, pose["lean"], L["torso"] - 6, face)
    fe = pt(sho, pose["ua"], L["ua"], face); fh = pt(fe, pose["fa"], L["fa"], face)
    be = pt(sho, pose["bua"], L["ua"], face); bh = pt(be, pose["bfa"], L["fa"], face)
    pommel = pt(fh, pose["sw"] + 180, 14, face)
    tip = pt(fh, pose["sw"], L["sword"], face)
    guard_c = pt(fh, pose["sw"], 8, face)
    return dict(hip=hip, fk=fk, ff=ff, bk=bk, bf=bf, nk=nk, head=head, sho=sho,
                fe=fe, fh=fh, be=be, bh=bh, tip=tip, pommel=pommel, gc=guard_c,
                swang=pose["sw"], face=face)


def seg_closest(p1, p2, q1, q2):
    p1, p2, q1, q2 = map(np.array, (p1, p2, q1, q2))
    best = (1e9, None)
    for s in np.linspace(0, 1, 25):
        a = p1 + (p2 - p1) * s
        d = q2 - q1
        u = np.clip(np.dot(a - q1, d) / max(1e-9, np.dot(d, d)), 0, 1)
        b = q1 + d * u
        dist = np.linalg.norm(a - b)
        if dist < best[0]:
            best = (dist, (a + b) / 2)
    return best


# ---------------------------------------------------------------- simulation
class Scarf:
    def __init__(self, n=9, seg=9):
        self.n, self.seg = n, seg
        self.p = None

    def step(self, anchor, dt, wind):
        if self.p is None:
            self.p = [list(anchor) for _ in range(self.n)]
            self.o = [list(anchor) for _ in range(self.n)]
        self.p[0] = list(anchor)
        for i in range(1, self.n):
            x, y = self.p[i]; ox, oy = self.o[i]
            vx, vy = (x - ox) * 0.96, (y - oy) * 0.96
            self.o[i] = [x, y]
            self.p[i] = [x + vx + wind * dt * dt, y + vy + 260 * dt * dt]
        for _ in range(4):
            for i in range(1, self.n):
                ax_, ay = self.p[i - 1]; bx_, by = self.p[i]
                dx, dy = bx_ - ax_, by - ay
                d = math.hypot(dx, dy) or 1e-6
                k = (d - self.seg) / d
                if i == 1:
                    self.p[i] = [bx_ - dx * k, by - dy * k]
                else:
                    self.p[i - 1] = [ax_ + dx * k * 0.5, ay + dy * k * 0.5]
                    self.p[i] = [bx_ - dx * k * 0.5, by - dy * k * 0.5]
        return [tuple(q) for q in self.p]


def simulate():
    frames = []
    sparks = []
    scarfA, scarfB = Scarf(), Scarf()
    trailA, trailB = [], []
    clash_done = set()
    shake = 0.0
    flash = 0.0
    loose = None  # epee volante de B
    cam_x, cam_z = 640.0, 1.0
    dust = [[random.uniform(-300, 1600), random.uniform(80, 600), random.uniform(0.5, 2.2),
             random.uniform(8, 30)] for _ in range(70)]
    ground_dust = []
    rng = random.Random(3)
    dt = 1 / FPS
    for f in range(NF):
        t = f / FPS
        pa, xa = A.sample(t); pb, xb = B.sample(t)
        # petite respiration en garde
        pa["lean"] += 1.5 * math.sin(t * 3.1); pb["lean"] += 1.5 * math.sin(t * 2.7 + 1)
        sa = skeleton(pa, xa, 1); sb = skeleton(pb, xb, -1)
        # chocs
        for ct in CLASH_T:
            if ct not in clash_done and t >= ct:
                clash_done.add(ct)
                d, mid = seg_closest(sa["gc"], sa["tip"], sb["gc"], sb["tip"])
                if mid is None or d > 60:
                    mid = ((sa["tip"][0] + sb["tip"][0]) / 2, (sa["tip"][1] + sb["tip"][1]) / 2)
                big = abs(ct - T_DISARM) < 1e-6
                for _ in range(60 if big else 34):
                    a = rng.uniform(0, 2 * math.pi); v = rng.uniform(150, 650 if big else 480)
                    sparks.append([mid[0], mid[1], math.cos(a) * v, math.sin(a) * v - 120,
                                   rng.uniform(0.25, 0.7), 0.0])
                shake = 14 if big else 7
                flash = 1.0 if big else 0.55
                frames_flash_pos = mid
        # epee de B qui vole
        if t >= B_DISARMED:
            if loose is None:
                loose = dict(x=sb["fh"][0], y=sb["fh"][1], vx=330, vy=-820, a=sb["swang"],
                             va=-1150, landed=False)
            elif not loose["landed"]:
                loose["vy"] += 1500 * dt
                loose["x"] += loose["vx"] * dt; loose["y"] += loose["vy"] * dt
                loose["a"] += loose["va"] * dt
                tipy = loose["y"] + L["sword"] * math.sin(rad(180 - loose["a"]))
                if loose["vy"] > 0 and loose["y"] > GROUND - L["sword"] + 18:
                    loose["landed"] = True
                    loose["a"] = 180 - 78  # pointe plantee
                    loose["y"] = GROUND + 16 - L["sword"] * math.sin(rad(78))
                    shake = max(shake, 4)
                    for _ in range(25):
                        ground_dust.append([loose["x"] + 25, GROUND, rng.uniform(-120, 120),
                                            rng.uniform(-160, -40), rng.uniform(0.6, 1.2), 0])
        # traces des lames
        trailA = ([(sa["gc"], sa["tip"])] + trailA)[:6]
        trailB = ([(sb["gc"], sb["tip"])] + trailB)[:6] if t < B_DISARMED else []
        for s in sparks:
            s[5] += dt; s[3] += 900 * dt
            s[0] += s[2] * dt; s[1] += s[3] * dt
            s[2] *= 0.97
        sparks = [s for s in sparks if s[5] < s[4]]
        for g in ground_dust:
            g[5] += dt; g[0] += g[2] * dt; g[1] += g[3] * dt; g[3] += 120 * dt
        ground_dust = [g for g in ground_dust if g[5] < g[4]]
        wind = -900 - 300 * math.sin(t * 0.7)
        scA = scarfA.step(sa["nk"], dt, wind)
        scB = scarfB.step(sb["nk"], dt, wind)
        for d in dust:
            d[0] += -d[3] * dt * 2; d[1] += math.sin(t * d[2] + d[3]) * 0.3
            if d[0] < -320:
                d[0] = 1600
        # camera
        if t < T_DISARM + 2:
            tx = (sa["hip"][0] + sb["hip"][0]) / 2
            spread = abs(sb["hip"][0] - sa["hip"][0])
        else:
            tx = (sa["hip"][0] + sb["hip"][0]) / 2
            spread = 230
        tz = max(1.0, min(1.55, 560 / max(spread + 150, 1)))
        if t < 4:
            tz = 1.0 + 0.05 * t / 4
        if t > 54:
            tz += (t - 54) * 0.03
        cam_x += (tx - cam_x) * 0.06
        cam_z += (tz - cam_z) * 0.04
        sx = rng.uniform(-1, 1) * shake; sy = rng.uniform(-1, 1) * shake
        shake *= 0.82; flash *= 0.78
        frames.append(dict(t=t, sa=sa, sb=sb, scA=scA, scB=scB, trailA=list(trailA),
                           trailB=list(trailB), sparks=[tuple(s) for s in sparks],
                           gdust=[tuple(g) for g in ground_dust],
                           loose=dict(loose) if loose else None,
                           cam=(cam_x, cam_z, sx, sy), flash=flash,
                           dust=[tuple(d) for d in dust], B_armed=t < B_DISARMED))
    return frames


# ---------------------------------------------------------------- decor
def build_background():
    w, h = 2600 * SS, H * SS
    y = np.linspace(0, 1, h)[:, None]
    top = np.array([28, 24, 58]); mid = np.array([196, 82, 70]); low = np.array([252, 186, 104])
    a = np.clip(y / 0.55, 0, 1); b = np.clip((y - 0.55) / 0.30, 0, 1)
    col = top * (1 - a) + mid * a
    col = col * (1 - b) + low * b
    sky = np.repeat(col[:, None, :], w, axis=1).astype(np.uint8)
    img = Image.fromarray(sky.reshape(h, w, 3), "RGB")
    return img


def mountains(seed, base, amp, color, w=2600):
    r = random.Random(seed)
    pts = []
    x = 0
    yv = base
    while x <= w + 40:
        yv = base - amp * (0.5 + 0.5 * math.sin(x / r.uniform(90, 260) + seed)) - r.uniform(0, amp * 0.35)
        pts.append((x * SS, yv * SS))
        x += r.uniform(30, 90)
    pts += [(w * SS + 100, H * SS), (0, H * SS)]
    lay = Image.new("RGBA", (w * SS, H * SS), (0, 0, 0, 0))
    ImageDraw.Draw(lay).polygon(pts, fill=color)
    return lay


BG = None
LAYERS = None
FONT_BIG = FONT_SM = None


def init_worker():
    global BG, LAYERS, FONT_BIG, FONT_SM
    BG = build_background()
    sunlay = Image.new("RGBA", BG.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(sunlay)
    cx, cy = 1300 * SS, 430 * SS
    for r_, al in [(240, 18), (180, 30), (130, 50), (95, 90)]:
        d.ellipse([cx - r_ * SS, cy - r_ * SS, cx + r_ * SS, cy + r_ * SS], fill=(255, 220, 150, al))
    d.ellipse([cx - 70 * SS, cy - 70 * SS, cx + 70 * SS, cy + 70 * SS], fill=(255, 236, 190, 255))
    sunlay = sunlay.filter(ImageFilter.GaussianBlur(6 * SS))
    BG.paste(sunlay, (0, 0), sunlay)
    LAYERS = [
        (mountains(1, 470, 150, (120, 60, 90, 255)), 0.15),
        (mountains(2, 520, 110, (80, 38, 70, 255)), 0.35),
        (mountains(3, 565, 70, (48, 24, 48, 255)), 0.6),
    ]
    for lay, _ in LAYERS:
        pass
    fonts = ["/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
             "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"]
    for fp in fonts:
        try:
            FONT_BIG = ImageFont.truetype(fp, 92 * SS)
            FONT_SM = ImageFont.truetype(fp, 30 * SS)
            break
        except OSError:
            continue
    if FONT_BIG is None:
        FONT_BIG = FONT_SM = ImageFont.load_default()


def render(fr):
    t = fr["t"]
    cam_x, cam_z, sx, sy = fr["cam"]
    # repere monde -> ecran
    def S(p):
        x = (p[0] - cam_x) * cam_z + W / 2 + sx
        y = (p[1] - GROUND) * cam_z + GROUND - 40 * (cam_z - 1) + sy
        return (x * SS, y * SS)
    z = cam_z * SS

    # ciel + soleil (fixe) + montagnes en parallaxe
    off = int((cam_x - 640) * 0.05 * SS) + 650 * SS
    img = BG.crop((off, 0, off + W * SS, H * SS)).copy()
    for lay, par in LAYERS:
        o = int((cam_x - 640) * par * SS) + 650 * SS
        img.paste(lay.crop((o, 0, o + W * SS, H * SS)), (0, 0), lay.crop((o, 0, o + W * SS, H * SS)))
    d = ImageDraw.Draw(img, "RGBA")
    # sol
    gy = S((0, GROUND))[1]
    d.rectangle([0, gy, W * SS, H * SS], fill=(26, 14, 24, 255))
    d.rectangle([0, gy, W * SS, gy + 3 * SS], fill=(90, 46, 50, 255))
    # herbes
    r = random.Random(11)
    for i in range(160):
        wx = r.uniform(-400, 1700)
        hgt = r.uniform(6, 22)
        sway = math.sin(t * 2 + wx * 0.02) * 4
        p0 = S((wx, GROUND + 1)); p1 = S((wx + sway - 3, GROUND - hgt))
        d.line([p0, p1], fill=(26, 14, 24, 255), width=int(2 * z))
    # poussiere / particules dans l'air
    for (x, y, ph, sp) in fr["dust"]:
        px = (x - (cam_x - 640) * 0.8) * SS
        d.ellipse([px - 2 * SS, y * SS - 2 * SS, px + 2 * SS, y * SS + 2 * SS], fill=(255, 210, 160, 90))

    def lw(v):
        return max(1, int(v * z))

    def limb(a, b, w, col):
        a, b = S(a), S(b)
        d.line([a, b], fill=col, width=lw(w))
        rr = w * z / 2
        for p in (a, b):
            d.ellipse([p[0] - rr, p[1] - rr, p[0] + rr, p[1] + rr], fill=col)

    def sword(s, trail, armed=True, alpha=255):
        if not armed:
            return
        # traine
        for i in range(len(trail) - 1):
            (g0, t0), (g1, t1) = trail[i], trail[i + 1]
            al = int(70 * (1 - i / len(trail)))
            mid0 = ((g0[0] * 0.3 + t0[0] * 0.7), (g0[1] * 0.3 + t0[1] * 0.7))
            mid1 = ((g1[0] * 0.3 + t1[0] * 0.7), (g1[1] * 0.3 + t1[1] * 0.7))
            d.polygon([S(mid0), S(t0), S(t1), S(mid1)], fill=(255, 240, 220, al))
        draw_blade(s["fh"], s["swang"], s["face"])

    def draw_blade(hand, ang, face):
        gc = pt(hand, ang, 8, face)
        tip = pt(hand, ang, L["sword"], face)
        pom = pt(hand, ang + 180, 14, face)
        g1 = pt(gc, ang + 90, 11, face); g2 = pt(gc, ang - 90, 11, face)
        d.line([S(gc), S(tip)], fill=(225, 228, 238, 255), width=lw(4.2))
        d.line([S(gc), S(pt(gc, ang, L["sword"] - 12, face))], fill=(255, 255, 255, 200), width=lw(1.4))
        d.line([S(pom), S(gc)], fill=(60, 40, 30, 255), width=lw(5))
        d.line([S(g1), S(g2)], fill=(200, 160, 70, 255), width=lw(4))
        pp = S(pom); rr = 3.5 * z
        d.ellipse([pp[0] - rr, pp[1] - rr, pp[0] + rr, pp[1] + rr], fill=(200, 160, 70, 255))

    def fighter(s, scarf, body, back, scol, trail, armed):
        # ombre
        hp = S((s["hip"][0], GROUND + 4))
        d.ellipse([hp[0] - 55 * z, hp[1] - 6 * z, hp[0] + 55 * z, hp[1] + 6 * z], fill=(0, 0, 0, 90))
        # foulard (derriere)
        pts = [S(p) for p in scarf]
        d.line(pts, fill=scol, width=lw(7), joint="curve")
        # membres arriere
        limb(s["hip"], s["bk"], 14, back); limb(s["bk"], s["bf"], 12, back)
        foot = pt(s["bf"], 0, 12, s["face"]); limb(s["bf"], foot, 8, back)
        limb(s["sho"], s["be"], 11, back); limb(s["be"], s["bh"], 10, back)
        # torse
        limb(s["hip"], s["nk"], 22, body)
        # ceinture
        bpos = pt(s["hip"], 0, 0, 1)
        limb(s["hip"], pt(s["hip"], -90, 4, 1), 24, scol)
        # tete
        hc = S(s["head"]); rr = L["head"] * z
        d.ellipse([hc[0] - rr, hc[1] - rr, hc[0] + rr, hc[1] + rr], fill=body)
        # bandeau
        d.line([(hc[0] - rr, hc[1] - rr * 0.25), (hc[0] + rr, hc[1] - rr * 0.25)], fill=scol, width=lw(4))
        # jambes avant
        limb(s["hip"], s["fk"], 15, body); limb(s["fk"], s["ff"], 13, body)
        foot = pt(s["ff"], 0, 13, s["face"]); limb(s["ff"], foot, 9, body)
        # epee puis bras avant
        sword(s, trail, armed)
        limb(s["sho"], s["fe"], 12, body); limb(s["fe"], s["fh"], 11, body)

    fighter(fr["sb"], fr["scB"], (18, 12, 22, 255), (40, 30, 46, 255), (40, 140, 200, 255),
            fr["trailB"], fr["B_armed"])
    fighter(fr["sa"], fr["scA"], (14, 10, 16, 255), (36, 26, 34, 255), (205, 40, 40, 255),
            fr["trailA"], True)
    lo = fr["loose"]
    if lo:
        draw_blade((lo["x"], lo["y"]), 180 - lo["a"], 1)

    # etincelles
    for (x, y, vx, vy, life, age) in fr["sparks"]:
        k = 1 - age / life
        p0 = S((x, y)); p1 = S((x - vx * 0.02, y - vy * 0.02))
        d.line([p0, p1], fill=(255, int(200 + 55 * k), int(120 * k), int(255 * k)), width=lw(2.4))
    for (x, y, vx, vy, life, age) in fr["gdust"]:
        k = 1 - age / life
        p = S((x, y)); rr = (4 + 10 * (1 - k)) * z
        d.ellipse([p[0] - rr, p[1] - rr, p[0] + rr, p[1] + rr], fill=(120, 80, 70, int(120 * k)))

    # flash du choc
    if fr["flash"] > 0.03:
        ov = Image.new("RGB", img.size, (255, 235, 200))
        img = Image.blend(img, ov, min(0.35, fr["flash"] * 0.3))
        d = ImageDraw.Draw(img, "RGBA")

    # vignette + bandes cinema
    img = img.resize((W, H), Image.LANCZOS)
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle([0, 0, W, 52], fill=(0, 0, 0, 255))
    d.rectangle([0, H - 52, W, H], fill=(0, 0, 0, 255))

    def title(txt, font, y, alpha):
        if alpha <= 0:
            return
        bb = d.textbbox((0, 0), txt, font=font)
        tw = bb[2] - bb[0]
        d.text(((W - tw) / 2 + 2, y + 2), txt, font=font, fill=(0, 0, 0, int(160 * alpha)))
        d.text(((W - tw) / 2, y), txt, font=font, fill=(255, 236, 205, int(255 * alpha)))

    global FONT_BIG_1X, FONT_SM_1X
    a1 = min(1, t / 0.8) * (1 - ease((t - 2.6) / 1.0))
    title("LE DUEL", FONT_BIG_1X, 190, a1)
    title("au soleil couchant", FONT_SM_1X, 300, a1)
    # fondu au noir final
    if t > 56.5:
        k = ease((t - 56.5) / 1.6)
        img = Image.blend(img, Image.new("RGB", img.size, (0, 0, 0)), k)
        d = ImageDraw.Draw(img, "RGBA")
        title("FIN", FONT_BIG_1X, 300, ease((t - 57.8) / 0.8))
    if t < 0.6:
        img = Image.blend(Image.new("RGB", img.size, (0, 0, 0)), img, t / 0.6)
    return img.tobytes()


FONT_BIG_1X = FONT_SM_1X = None


def init_all():
    global FONT_BIG_1X, FONT_SM_1X
    init_worker()
    for fp in ["/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
               "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"]:
        try:
            FONT_BIG_1X = ImageFont.truetype(fp, 92)
            FONT_SM_1X = ImageFont.truetype(fp, 30)
            return
        except OSError:
            pass
    FONT_BIG_1X = FONT_SM_1X = ImageFont.load_default()


# ---------------------------------------------------------------- son
SR = 44100


def make_audio(path):
    n = int(SR * DUR)
    L_ = np.zeros(n); R_ = np.zeros(n)
    rng = np.random.default_rng(5)

    def add(sig, t, pan=0.5, g=1.0):
        i = int(t * SR)
        if i >= n:
            return
        sig = sig[: n - i]
        L_[i:i + len(sig)] += sig * g * math.sqrt(1 - pan)
        R_[i:i + len(sig)] += sig * g * math.sqrt(pan)

    def clash(big=False):
        dur = 1.6 if big else 1.1
        tt = np.arange(int(SR * dur)) / SR
        f0 = rng.uniform(1900, 2600) * (0.8 if big else 1)
        s = np.zeros_like(tt)
        for k, (m, dec, amp) in enumerate([(1, 3.5, 1), (2.76, 5, .6), (5.4, 7, .4), (8.93, 9, .25), (1.51, 4, .5)]):
            s += amp * np.sin(2 * np.pi * f0 * m * tt + rng.uniform(0, 6)) * np.exp(-dec * tt)
        noise = rng.normal(0, 1, len(tt)) * np.exp(-60 * tt)
        s = s * 0.5 + noise * 0.8
        return s * (1.3 if big else 1)

    def whoosh():
        dur = 0.35
        m = int(SR * dur)
        x = rng.normal(0, 1, m)
        k = np.ones(18) / 18
        x = np.convolve(x, k, "same")
        env = np.sin(np.linspace(0, np.pi, m)) ** 2
        return x * env * 1.6

    def step():
        m = int(SR * 0.12)
        x = rng.normal(0, 1, m)
        x = np.convolve(x, np.ones(60) / 60, "same")
        return x * np.exp(-np.linspace(0, 12, m)) * 3

    def drum(f=58):
        m = int(SR * 0.9)
        tt = np.arange(m) / SR
        fr = f * (1 + 1.2 * np.exp(-tt * 18))
        ph = 2 * np.pi * np.cumsum(fr) / SR
        return np.sin(ph) * np.exp(-tt * 4.5)

    # vent
    wn = rng.normal(0, 1, n)
    wn = np.convolve(wn, np.ones(400) / 400, "same")
    mod = 0.6 + 0.4 * np.sin(np.arange(n) / SR * 0.5)
    L_ += wn * mod * 2.2; R_ += np.roll(wn, 900) * mod * 2.2

    def pan(x):
        return float(np.clip(x / 1280, 0.1, 0.9))

    for (te, kind, data) in events:
        if te >= DUR:
            continue
        if kind == "clash":
            add(clash(data == "disarm"), te, 0.5, 0.55)
        elif kind == "whoosh":
            add(whoosh(), te, pan(data), 0.35)
        elif kind == "swish":
            add(whoosh(), te, pan(data), 0.25)
        elif kind == "step":
            add(step(), te, pan(data), 0.4)
        elif kind == "thud":
            add(step() * 2, te, pan(data), 0.6)
    # tambours : tension pendant le combat
    beat = 0.9
    tb = 7.0
    while tb < T_DISARM:
        add(drum(), tb, 0.5, 0.5)
        if int((tb - 7) / beat) % 4 == 3:
            add(drum(80) * 0.6, tb + beat / 2, 0.5, 0.4)
        tb += beat
    add(drum(45) * 1.5, T_DISARM, 0.5, 0.7)
    # fondu
    fade = np.ones(n)
    a = int(56.5 * SR)
    fade[a:] = np.linspace(1, 0, n - a)
    fi = int(0.5 * SR); fade[:fi] = np.linspace(0, 1, fi)
    L_ *= fade; R_ *= fade
    peak = max(np.abs(L_).max(), np.abs(R_).max())
    st = np.stack([L_, R_], 1) / peak * 0.85
    data = (st * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(data.tobytes())


def main():
    frames = simulate()
    if PREVIEW:
        init_all()
        for tp in PREVIEW:
            fr = frames[min(NF - 1, int(tp * FPS))]
            Image.frombytes("RGB", (W, H), render(fr)).save(f"prev_{tp:05.2f}.png")
        return
    make_audio("audio.wav")
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", "audio.wav",
                             "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                             "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", OUT],
                            stdin=subprocess.PIPE)
    with Pool(4, initializer=init_all) as pool:
        for i, buf in enumerate(pool.imap(render, frames, chunksize=8)):
            proc.stdin.write(buf)
            if i % 150 == 0:
                print(f"frame {i}/{NF}", flush=True)
    proc.stdin.close(); proc.wait()
    print("done", OUT)


if __name__ == "__main__":
    main()
