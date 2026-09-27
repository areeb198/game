# -*- coding: utf-8 -*-
"""
SKY STRIKERS - a complete, polished 2D aircraft shooter written in Pygame.

Runs on desktop (keyboard + mouse) and packages to Android as a real APK
via Buildozer / python-for-android.

Controls
--------
  Mobile   : on-screen virtual buttons - LEFT, RIGHT, FIRE (bottom corners),
             PAUSE (top right), QUIT (pause screen), RESTART (game over screen).
  Desktop  : LEFT / RIGHT or A / D  ...  SPACE / UP (fire)  ...  P (pause)
             ENTER (start)  ...  R (restart)  ...  ESC (quit).
             Mouse can also press the on-screen buttons.

Gameplay
--------
  Four enemy types (Scout, Fighter, Drone, Bomber), combo scoring, three
  power-ups (spread gun / hull repair / shield), shield, 3 lives, a hull bar,
  and difficulty that ramps every 12 kills.  The best score and best wave are
  saved to `skystrikers.save` in the working directory, which on Android is the
  app's own private folder - so no storage permission is needed.

Design notes
------------
  * Every sprite, particle, sound and font glyph is generated at runtime.
    There are ZERO external asset files, which makes the APK tiny and the
    build 100% reproducible.
  * Rendering happens on a fixed 480x800 "virtual canvas" that is scaled
    to whatever the device screen is, so the game looks identical on a
    cheap 720p phone and a 1440p flagship (letterboxed if aspect differs).
  * All movement is delta-time based, so the game feels identical at any
    refresh rate.
  * No Surface is ever allocated inside the draw loop: overlays, the control
    pad, the menu jets' bank angles and the game-over title zoom are all
    pre-rendered once at startup.
  * Only `pygame`, `sys` and `random` are imported (plus built-ins).
"""

import sys
import random

import pygame


# ---------------------------------------------------------------------------
#  CONFIGURATION
# ---------------------------------------------------------------------------

GAME_TITLE = "SKY STRIKERS"

VW, VH = 480, 800              # virtual (design) resolution - portrait phone
FPS = 60
FULLSCREEN = True              # True = go fullscreen (needed on Android)
SOUND_ENABLED = True
SHOW_FPS = False

# Let SDL2 stretch the 480x800 canvas to the real window, which moves the
# upscale off the CPU and into the GPU/driver.  On a 1080x1920 screen the
# software version of that upscale alone costs ~8 ms per frame, which is half
# the 60 fps budget.  The game falls back to software scaling automatically if
# the driver refuses, so this is safe to leave on.
# Set to False only if a device shows a black screen with it enabled.
SCALED_DISPLAY = True

# Layout constants (virtual pixels)
HUD_H = 56
PLAY_TOP = HUD_H
PLAY_BOT = VH - 132            # top of the virtual control pad

# Gameplay tuning
PLAYER_SPEED = 335.0
PLAYER_FIRE_COOLDOWN = 0.15
PLAYER_BULLET_SPEED = 760.0
START_LIVES = 3
MAX_HP = 100
SPAWN_BASE = 0.95              # seconds between spawns at level 1
SPAWN_MIN = 0.26               # seconds between spawns at max level
KILLS_PER_LEVEL = 12
DROP_CHANCE = 0.22             # chance a kill drops a pickup at all
MAX_PARTICLES = 420            # keeps 60 fps alive on low-end phones
MAX_ENEMIES = 16

# Saved to disk next to the script.  On Android the working directory is the
# app's private folder, so this needs no permission and no extra import.
SAVE_FILE = "skystrikers.save"

# Palette (retro arcade)
C_SKY_TOP = (10, 12, 34)
C_SKY_BOT = (46, 20, 70)
C_ACCENT = (255, 214, 92)
C_CYAN = (108, 232, 255)
C_RED = (255, 84, 96)
C_GREEN = (120, 255, 170)
C_VIOLET = (188, 130, 255)
C_WHITE = (238, 246, 255)
C_DIM = (126, 146, 182)
C_PANEL = (16, 20, 46)

# Unit-circle lookup table (2 degree steps) so we never need the math module.
_CIRCLE = [pygame.math.Vector2(1, 0).rotate(i * 2) for i in range(360)]


def unit(angle_deg):
    """Return a unit Vector2 for the given angle in degrees."""
    return _CIRCLE[int(angle_deg * 0.5) % 360]


def clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value


def shade(color, factor):
    """Brighten (factor > 1) or darken (factor < 1) a colour."""
    return (clamp(int(color[0] * factor), 0, 255),
            clamp(int(color[1] * factor), 0, 255),
            clamp(int(color[2] * factor), 0, 255))


def alpha_color(color, alpha):
    """Add an alpha channel to an RGB tuple."""
    return (color[0], color[1], color[2], int(clamp(alpha, 0, 255)))


# ---------------------------------------------------------------------------
#  PERSISTENT BEST SCORE
# ---------------------------------------------------------------------------
#  Uses only the `open` builtin, so the "pygame / sys / random only" rule still
#  holds.  Every access is wrapped: on Android the storage location is not
#  guaranteed to be writable, and a missing score file is never fatal.

def load_best():
    """Return (best_score, best_wave) from disk, or (0, 1) on any problem."""
    try:
        with open(SAVE_FILE, "r") as fh:
            lines = fh.read().split()
        score = max(0, int(lines[0]))
        wave = max(1, int(lines[1]))
        return score, wave
    except Exception:
        return 0, 1


def save_best(score, wave):
    """Write the best score/wave, ignoring any failure (read-only storage)."""
    try:
        with open(SAVE_FILE, "w") as fh:
            fh.write("%d %d\n" % (int(score), int(wave)))
    except Exception:
        pass


# ---------------------------------------------------------------------------
#  PROCEDURAL AUDIO  (square / triangle blips synthesised with pure Python)
# ---------------------------------------------------------------------------
#  pygame.mixer only accepts raw PCM that matches the mixer's *current* format.
#  A driver is free to refuse the format you ask for - on this machine it
#  silently stays at 44100 Hz stereo even after asking for 22050 mono - so the
#  tone is always synthesised in whatever format the mixer actually reports.
#  Otherwise every sound would play at the wrong speed and pitch.

def synth_tone(freq, ms, volume=0.22, decay=2.4, noise=0.0, square=True,
               sweep=0.0, seed=7, rate=22050, channels=1):
    """Build a 16-bit PCM sound buffer and hand it to pygame.mixer.

    freq   : starting frequency in Hz
    ms     : duration in milliseconds
    decay  : how fast the envelope falls off (higher = snappier)
    noise  : 0.0 = pure tone ... 1.0 = pure white noise
    sweep  : extra Hz added across the whole note (for "pew" style risers)
    rate   : the mixer's actual sample rate
    channels: the mixer's actual channel count (samples are duplicated)
    """

    count = int(rate * ms / 1000.0)
    if count < 1:
        count = 1
    rng = random.Random(seed)
    buf = bytearray()
    append = buf.extend
    phase = 0.0
    for i in range(count):
        t = i / float(count)
        env = volume * (1.0 - t) ** decay
        f = freq + sweep * t
        phase += f / rate
        phase -= int(phase)
        # square wave
        s = 1.0 if phase < 0.5 else -1.0
        if not square:
            s = 2.0 * phase - 1.0 if phase < 0.5 else 3.0 - 2.0 * phase
        if noise > 0.0:
            s = s * (1.0 - noise) + rng.uniform(-1.0, 1.0) * noise
        v = int(clamp(env * s * 32000, -32000, 32000))
        packed = v.to_bytes(2, "little", signed=True)
        if channels == 1:
            append(packed)
        else:
            # duplicate the sample across every channel
            append(packed * channels)
    return pygame.mixer.Sound(buffer=bytes(buf))


def build_sounds():
    """Create the whole sound bank. Returns {} if audio is unavailable."""
    if not SOUND_ENABLED:
        return {}
    try:
        try:
            pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
        except pygame.error:
            pygame.mixer.init()          # let SDL pick whatever it can do
        fmt = pygame.mixer.get_init()
        if not fmt:
            return {}
        rate, _bits, channels = fmt
        if rate <= 0 or channels <= 0:
            return {}
        pygame.mixer.set_num_channels(12)

        def tone(freq, ms, volume=0.22, **kw):
            return synth_tone(freq, ms, volume, rate=rate,
                              channels=channels, **kw)

        s = {
            "shoot":   tone(880, 55, 0.16, decay=2.0, sweep=-560, seed=1),
            "shoot2":  tone(1180, 45, 0.10, decay=2.6, sweep=-700, seed=2),
            "hit":     tone(320, 70, 0.22, decay=2.2, noise=0.65, seed=3),
            "boom":    tone(140, 420, 0.34, decay=2.0, noise=0.92, seed=4),
            "bigboom": tone(90, 620, 0.40, decay=1.6, noise=0.95, seed=5),
            "hurt":    tone(420, 260, 0.30, decay=1.8, noise=0.45,
                            sweep=-260, seed=6),
            "power":   tone(660, 90, 0.22, decay=1.6, sweep=520, seed=8),
            "shield":  tone(520, 180, 0.22, decay=1.2, sweep=760, seed=9),
            "over":    tone(500, 900, 0.28, decay=1.1, sweep=-390, seed=10),
            "click":   tone(1500, 40, 0.18, decay=3.0, seed=11),
        }
    except Exception:
        return {}
    return s

# ---------------------------------------------------------------------------
#  PROCEDURAL SPRITES
# ---------------------------------------------------------------------------

def draw_player_jet(size=58, body=(226, 240, 255), wing=(120, 176, 255),
                    trim=(108, 232, 255)):
    """A sleek interceptor seen from above, nose pointing up (-Y)."""
    w, h = size, int(size * 1.16)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    cx = w // 2

    # engine glow / nozzle
    pygame.draw.rect(surf, shade(trim, 0.55), (cx - 6, h - 12, 12, 8),
                     border_radius=3)

    # main wings
    pygame.draw.polygon(surf, wing, [
        (cx - 2, int(h * 0.50)), (cx + 2, int(h * 0.50)),
        (cx - 1, int(h * 0.70)), (w - 1, h - 14),
        (w - 1, h - 6), (cx - 6, int(h * 0.80)),
    ])
    pygame.draw.polygon(surf, wing, [
        (cx + 2, int(h * 0.50)), (cx - 2, int(h * 0.50)),
        (cx + 6, int(h * 0.80)), (1, h - 6), (1, h - 14),
        (cx + 1, int(h * 0.70)),
    ])

    # tail fins
    pygame.draw.polygon(surf, shade(wing, 0.75), [
        (cx - 20, h - 6), (cx - 16, h - 22), (cx - 11, h - 20),
        (cx - 12, h - 5),
    ])
    pygame.draw.polygon(surf, shade(wing, 0.75), [
        (cx + 20, h - 6), (cx + 16, h - 22), (cx + 11, h - 20),
        (cx + 12, h - 5),
    ])

    # fuselage
    pygame.draw.polygon(surf, body, [
        (cx, 1), (cx + 7, 12), (cx + 8, int(h * 0.62)), (cx + 5, h - 4),
        (cx - 5, h - 4), (cx - 8, int(h * 0.62)), (cx - 7, 12),
    ])
    # shading stripe
    pygame.draw.polygon(surf, shade(body, 0.86), [
        (cx, 1), (cx + 3, 12), (cx + 3, h - 4), (cx - 1, h - 4),
        (cx - 1, 12),
    ])
    # canopy
    pygame.draw.ellipse(surf, trim, (cx - 4, 14, 8, 18))
    pygame.draw.ellipse(surf, shade(trim, 1.4), (cx - 2, 16, 4, 8))
    # nose tip
    pygame.draw.circle(surf, C_ACCENT, (cx, 4), 2)

    return surf.convert_alpha()


def draw_scout(size=46, body=(255, 96, 118), wing=(170, 40, 70)):
    """Fast little dart - sharp delta wings."""
    w, h = size, int(size * 0.95)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    cx = w // 2
    pygame.draw.polygon(surf, shade(body, 0.45), [(cx - 4, h - 8), (cx + 4, h - 8),
                                                  (cx + 3, h - 1), (cx - 3, h - 1)])
    pygame.draw.polygon(surf, wing, [
        (cx, 2), (w - 2, h - 6), (cx + 6, h - 12), (cx, h - 16),
    ])
    pygame.draw.polygon(surf, wing, [
        (cx, 2), (2, h - 6), (cx - 6, h - 12), (cx, h - 16),
    ])
    pygame.draw.polygon(surf, body, [
        (cx, 0), (cx + 5, 14), (cx + 4, h - 8), (cx - 4, h - 8), (cx - 5, 14),
    ])
    pygame.draw.ellipse(surf, C_ACCENT, (cx - 3, 10, 6, 7))
    return surf.convert_alpha()


def draw_fighter(size=54, body=(186, 108, 255), wing=(96, 44, 160),
                 trim=(255, 190, 90)):
    """Mid-size interceptor with swept wings - shoots back."""
    w, h = size, int(size * 1.12)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    cx = w // 2
    for sx in (-1, 1):
        pygame.draw.polygon(surf, shade(body, 0.5),
                            [(cx + sx * 5, h - 12), (cx + sx * 9, h - 3),
                             (cx + sx * 5, h - 3)])
    pygame.draw.polygon(surf, wing, [
        (cx - 3, int(h * 0.40)), (cx + 3, int(h * 0.40)),
        (w - 1, int(h * 0.80)), (w - 4, int(h * 0.92)), (cx + 7, int(h * 0.78)),
    ])
    pygame.draw.polygon(surf, wing, [
        (cx + 3, int(h * 0.40)), (cx - 3, int(h * 0.40)),
        (cx - 7, int(h * 0.78)), (4, int(h * 0.92)), (1, int(h * 0.80)),
    ])
    pygame.draw.polygon(surf, body, [
        (cx, 1), (cx + 8, 16), (cx + 9, int(h * 0.70)), (cx + 5, h - 12),
        (cx - 5, h - 12), (cx - 9, int(h * 0.70)), (cx - 8, 16),
    ])
    pygame.draw.polygon(surf, shade(body, 0.8), [
        (cx, 1), (cx + 3, 16), (cx + 3, h - 12), (cx - 1, h - 12), (cx - 1, 16),
    ])
    pygame.draw.ellipse(surf, trim, (cx - 4, 15, 8, 15))
    pygame.draw.circle(surf, C_RED, (cx, 6), 2)
    return surf.convert_alpha()


def draw_bomber(size=78, body=(96, 214, 176), wing=(38, 122, 104),
                trim=(255, 240, 180)):
    """Fat heavy bomber - 6 HP, fires a 3-way spread."""
    w, h = size, int(size * 0.92)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    cx = w // 2
    # wings
    pygame.draw.polygon(surf, wing, [
        (2, int(h * 0.52)), (w - 2, int(h * 0.52)),
        (w - 6, int(h * 0.74)), (6, int(h * 0.74)),
    ])
    # engine pods
    for sx in (-1, 1):
        pygame.draw.rect(surf, shade(body, 0.55),
                         (cx + sx * 26 - 5, int(h * 0.66), 10, 12),
                         border_radius=4)
    # tail
    pygame.draw.polygon(surf, wing, [
        (cx - 16, 2), (cx + 16, 2), (cx + 10, int(h * 0.30)), (cx - 10, int(h * 0.30)),
    ])
    # fuselage
    pygame.draw.polygon(surf, body, [
        (cx, 0), (cx + 11, 12), (cx + 12, int(h * 0.70)), (cx + 7, h - 3),
        (cx - 7, h - 3), (cx - 12, int(h * 0.70)), (cx - 11, 12),
    ])
    pygame.draw.polygon(surf, shade(body, 0.82), [
        (cx, 0), (cx + 4, 12), (cx + 4, h - 3), (cx - 2, h - 3), (cx - 2, 12),
    ])
    # canopy + turret
    pygame.draw.ellipse(surf, trim, (cx - 5, 10, 10, 16))
    pygame.draw.circle(surf, C_RED, (cx, int(h * 0.58)), 4)
    return surf.convert_alpha()


def draw_drone(size=50, body=(255, 208, 88), wing=(168, 118, 24),
               trim=(70, 46, 10)):
    """Zig-zag drone with a spinning rotor look."""
    w, h = size, size
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    cx = w // 2
    pygame.draw.rect(surf, shade(body, 0.4), (cx - 4, h - 9, 8, 7),
                     border_radius=3)
    pygame.draw.polygon(surf, wing, [
        (cx, 6), (w - 1, int(h * 0.52)), (cx + 8, int(h * 0.68)), (cx, h - 6),
        (cx - 8, int(h * 0.68)), (1, int(h * 0.52)),
    ])
    pygame.draw.circle(surf, body, (cx, int(h * 0.42)), 8)
    pygame.draw.circle(surf, trim, (cx, int(h * 0.42)), 4)
    pygame.draw.circle(surf, C_WHITE, (cx, int(h * 0.42)), 2)
    return surf.convert_alpha()


def make_flame(width, height, frames=5):
    """Animated engine exhaust: a list of surfaces to cycle through."""
    out = []
    for i in range(frames):
        t = i / float(frames)
        h = max(3, int(height * (0.45 + 0.55 * t)))
        s = pygame.Surface((width, h + 6), pygame.SRCALPHA)
        cx = width // 2
        pygame.draw.polygon(s, (255, 240, 170, 220),
                            [(cx - width // 2 + 1, 0), (cx + width // 2 - 1, 0),
                             (cx, h + 5)])
        pygame.draw.polygon(s, (255, 150, 60, 200),
                            [(cx - width // 4, 0), (cx + width // 4, 0),
                             (cx, int(h * 0.75) + 4)])
        out.append(s.convert_alpha())
    return out


def make_background(w, h):
    """Vertical gradient sky with a few nebula blobs, pre-rendered once."""
    bg = pygame.Surface((w, h)).convert()
    for y in range(h):
        t = y / float(h - 1)
        bg.fill((int(C_SKY_TOP[0] + (C_SKY_BOT[0] - C_SKY_TOP[0]) * t),
                 int(C_SKY_TOP[1] + (C_SKY_BOT[1] - C_SKY_TOP[1]) * t),
                 int(C_SKY_TOP[2] + (C_SKY_BOT[2] - C_SKY_TOP[2]) * t)),
                (0, y, w, 1))
    glow = pygame.Surface((w, h), pygame.SRCALPHA)
    for _ in range(7):
        r = random.randint(90, 220)
        c = random.choice([(120, 60, 160, 26), (40, 90, 170, 24), (160, 40, 120, 20)])
        pygame.draw.circle(glow, c, (random.randint(0, w), random.randint(0, h)), r)
    glow = pygame.transform.smoothscale(glow, (w // 3, h // 3))
    glow = pygame.transform.smoothscale(glow, (w, h))
    bg.blit(glow, (0, 0))
    return bg


def make_stars(w, h, count=90):
    """3 parallax layers of stars: (x, y, radius, layer)."""
    stars = []
    for _ in range(count):
        layer = random.choice((0, 1, 2))
        stars.append([random.uniform(0, w), random.uniform(0, h),
                      random.choice((1, 1, 1, 2)),
                      layer,
                      random.randint(140, 255)])
    return stars


def build_assets():
    """Pre-render every sprite once. Called after the display is initialised."""
    base = draw_player_jet()
    frames = []
    for deg in (-14, 0, 14):                     # banking animation
        f = pygame.transform.rotate(base, deg)
        frames.append(f)
    return {
        "player": frames,
        "scout": draw_scout(),
        "fighter": draw_fighter(),
        "bomber": draw_bomber(),
        "drone": draw_drone(),
        "flame_player": make_flame(16, 26),
        "flame_enemy": make_flame(11, 18),
        "bullet": None,
        "bg": make_background(VW, VH),
        "stars": make_stars(VW, VH),
    }


# ---------------------------------------------------------------------------
#  ENTITIES
# ---------------------------------------------------------------------------

class Particle(object):
    """A single explosion / debris spark. Plain object = fastest possible."""

    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size", "color",
                 "glow")

    def __init__(self, x, y, vx, vy, life, size, color, glow=False):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.life = life
        self.max_life = life
        self.size = size
        self.color = color
        self.glow = glow

    def update(self, dt):
        self.life -= dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vx *= 0.965
        self.vy *= 0.965

    def draw(self, surf):
        if self.life <= 0:
            return
        t = self.life / self.max_life
        r = max(1, int(self.size * (0.35 + 0.65 * t)))
        if self.glow:
            c = alpha_color(self.color, 90 + 150 * t)
            pygame.draw.circle(surf, c, (int(self.x), int(self.y)), r + 2)
        pygame.draw.circle(surf, self.color, (int(self.x), int(self.y)), r)


class Shockwave(object):
    __slots__ = ("x", "y", "life", "max_life", "radius", "color")

    def __init__(self, x, y, radius, color, life=0.42):
        self.x = x
        self.y = y
        self.life = life
        self.max_life = life
        self.radius = radius
        self.color = color

    def update(self, dt):
        self.life -= dt

    def draw(self, surf):
        if self.life <= 0:
            return
        t = 1.0 - self.life / self.max_life
        r = int(self.radius * (0.25 + 0.75 * t))
        alpha = int(190 * (1.0 - t))
        pygame.draw.circle(surf, alpha_color(self.color, alpha),
                           (int(self.x), int(self.y)), r, 2)


class FloatText(object):
    """Score pop-ups that drift upward and fade out."""
    __slots__ = ("x", "y", "life", "text", "color", "vy")

    def __init__(self, x, y, text, color, life=0.85):
        self.x = x
        self.y = y
        self.text = text
        self.color = color
        self.life = life
        self.vy = -58.0

    def update(self, dt):
        self.life -= dt
        self.y += self.vy * dt

    def draw(self, surf, font):
        if self.life <= 0:
            return
        img = font.render(self.text, True, self.color)
        img.set_alpha(int(255 * clamp(self.life / 0.5, 0, 1)))
        surf.blit(img, img.get_rect(midbottom=(int(self.x), int(self.y))))


class Bullet(pygame.sprite.Sprite):
    """Player bullet. Straight, fast, glowy."""

    def __init__(self, x, y, vx, vy, damage, color, friendly=True):
        pygame.sprite.Sprite.__init__(self)
        self.image = Bullet.make_image(color)
        self.rect = self.image.get_rect(midbottom=(x, y))
        self.x = float(x)
        self.y = float(y)
        self.vx = vx
        self.vy = vy
        self.damage = damage
        self.friendly = friendly

    _cache = {}

    @classmethod
    def make_image(cls, color):
        if color not in cls._cache:
            w, h = 5, 18
            s = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.rect(s, alpha_color(color, 90), (0, 1, w, h - 2),
                             border_radius=3)
            pygame.draw.rect(s, (255, 255, 255), (1, 2, w - 2, h - 5),
                             border_radius=2)
            cls._cache[color] = s.convert_alpha()
        return cls._cache[color]

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.rect.x = int(self.x)
        self.rect.y = int(self.y)
        if (self.y < PLAY_TOP - 30 or self.y > VH + 30 or
                self.x < -30 or self.x > VW + 30):
            self.kill()


class Enemy(pygame.sprite.Sprite):
    """Base enemy. Subclasses only tweak stats + a few behaviour flags."""

    sprite_key = "scout"
    hp = 1
    speed = 120.0
    points = 100
    radius = 16              # collision radius
    fire_rate = 0.0          # 0 = never shoots
    fire_spread = 0.0
    drift = 0.0              # horizontal sine amplitude
    drift_rate = 0.0
    bullet_speed = 300.0
    color = (200, 60, 80)
    w = 1.0                  # speed multiplier applied by the difficulty ramp
    shoot_flame = True

    def __init__(self, game, x, y, hp_bonus=0, speed_mul=1.0):
        pygame.sprite.Sprite.__init__(self)
        self.game = game
        self.image = game.assets[self.sprite_key]
        self.rect = self.image.get_rect(midbottom=(x, y))
        self.x = float(x)
        self.y = float(y)
        self.home_x = float(x)
        self.max_hp = self.hp + hp_bonus
        self.hp = self.max_hp
        self.speed = self.speed * speed_mul
        self.age = 0.0
        self.fire_timer = random.uniform(0.6, 1.8)
        self.flame_t = random.random() * 5.0
        self.dead = False

    def kill(self):
        """Mark the sprite as spent (pygame's Sprite.alive is a method, and
        we want a plain flag we can safely read in the cull pass)."""
        self.dead = True
        pygame.sprite.Sprite.kill(self)

    # -- helpers ----------------------------------------------------------
    def collides(self, x, y):
        """Fast circle hit test against this enemy's core (no Rect churn)."""
        dx = x - self.x
        dy = y - self.y
        r = self.radius
        return dx * dx + dy * dy <= r * r

    def damage(self, amount):
        self.hp -= amount
        return self.hp <= 0

    # -- behaviour --------------------------------------------------------
    def update(self, dt):
        self.age += dt
        self.y += self.speed * dt
        if self.drift:
            self.x = self.home_x + self.drift * self.game.wobble(self.age * self.drift_rate)

        if self.fire_rate > 0.0:
            self.fire_timer -= dt
            if self.fire_timer <= 0.0 and self.age > 0.7:
                self.fire_timer = self.fire_rate * random.uniform(0.75, 1.25)
                self.shoot()

        if self.y > VH + 80:
            self.kill()
            return

        self.rect.x = int(self.x - self.rect.width / 2)
        self.rect.y = int(self.y - self.rect.height / 2)

    def shoot(self):
        g = self.game
        if g.state != PLAY:
            return
        if self.fire_spread:
            angles = (90.0 - self.fire_spread, 90.0, 90.0 + self.fire_spread)
        elif g.player is not None and g.player.rect.y > self.y - 8:
            # aim at the player.  In pygame's convention 90 deg == straight
            # down, which is exactly what unit() returns for a downwards shot.
            v = pygame.math.Vector2(g.player.rect.centerx - self.x,
                                   g.player.rect.centery - self.y)
            if v.length() < 1:
                v = pygame.math.Vector2(0, 1)
            angles = (unit(0).angle_to(v.normalize()),)
        else:
            angles = (90.0,)
        for a in angles:
            d = unit(a)
            b = Bullet(self.x, self.y + self.rect.height * 0.4,
                       d.x * self.bullet_speed, d.y * self.bullet_speed,
                       10, self.color, friendly=False)
            g.enemy_bullets.add(b)
        g.play("shoot2", 0.05)


class Scout(Enemy):
    sprite_key = "scout"
    hp = 1
    speed = 165.0
    points = 100
    radius = 15
    drift = 46.0
    drift_rate = 2.6
    color = (255, 120, 140)


class Fighter(Enemy):
    sprite_key = "fighter"
    hp = 2
    speed = 108.0
    points = 220
    radius = 18
    fire_rate = 1.9
    drift = 28.0
    drift_rate = 1.5
    bullet_speed = 280.0
    color = (208, 130, 255)


class Drone(Enemy):
    sprite_key = "drone"
    hp = 2
    speed = 92.0
    points = 180
    radius = 16
    fire_rate = 2.6
    fire_spread = 16.0
    drift = 120.0
    drift_rate = 1.9
    bullet_speed = 250.0
    color = (255, 214, 92)


class Bomber(Enemy):
    sprite_key = "bomber"
    hp = 6
    speed = 62.0
    points = 600
    radius = 30
    fire_rate = 1.5
    fire_spread = 26.0
    bullet_speed = 235.0
    color = (120, 240, 200)
    drift = 18.0
    drift_rate = 0.7


ENEMY_TYPES = (Scout, Fighter, Drone, Bomber)


class PowerUp(pygame.sprite.Sprite):
    """Falling pickup: 'P' spread gun, 'H' repair, 'S' shield."""

    KINDS = {
        "P": (C_ACCENT, "SPREAD"),
        "H": (C_GREEN, "REPAIR"),
        "S": (C_CYAN, "SHIELD"),
    }

    def __init__(self, game, x, y, kind=None):
        pygame.sprite.Sprite.__init__(self)
        self.game = game
        self.kind = kind or random.choice(("P", "H", "S"))
        self.color = self.KINDS[self.kind][0]
        self.size = 22
        self.image = self.make_image(self.kind, self.size, self.color)
        self.rect = self.image.get_rect(midbottom=(x, y))
        self.x = float(x)
        self.y = float(y)
        self.age = 0.0
        self.vy = 92.0

    @classmethod
    def make_image(cls, kind, size, color):
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(s, alpha_color(color, 70), (size // 2, size // 2),
                           size // 2)
        pygame.draw.circle(s, color, (size // 2, size // 2), size // 2 - 3, 2)
        font = pygame.font.Font(None, int(size * 0.85))
        img = font.render(kind, True, (12, 14, 30))
        s.blit(img, img.get_rect(center=(size // 2, size // 2 + 1)))
        return s.convert_alpha()

    def update(self, dt):
        self.age += dt
        self.y += self.vy * dt
        self.x += 26.0 * self.game.wobble(self.age * 2.2) * dt
        self.rect.x = int(self.x - self.rect.width / 2)
        self.rect.y = int(self.y - self.rect.height / 2)
        if self.y > VH + 40:
            self.kill()


class Player(pygame.sprite.Sprite):
    """The player's fighter. Movement, banking, auto-fire, damage handling."""

    def __init__(self, game):
        pygame.sprite.Sprite.__init__(self)
        self.game = game
        self.frames = game.assets["player"]
        self.image = self.frames[1]
        self.rect = self.image.get_rect(midbottom=(VW // 2, VH - 118))
        self.lives = START_LIVES
        self.cooldown = 0.0
        self.invuln = 1.2             # spawn protection
        self.shield = 0.0
        self.spread = 0.0
        self.tilt = 0
        self.recoil = 0.0
        self.destroyed = False
        self.fire_hold = False
        self.muzzle = 0.0
        self.reset()

    def reset(self):
        self.hp = MAX_HP
        self.rect.midbottom = (VW // 2, VH - 118)
        self.cooldown = 0.0
        self.shield = 0.0
        self.spread = 0.0
        self.invuln = 1.6
        self.tilt = 0
        self.recoil = 0.0
        self.destroyed = False

    def hurtbox(self):
        """Shrunken rect so grazing an enemy does not feel unfair."""
        return self.rect.inflate(-int(self.rect.width * 0.42),
                                 -int(self.rect.height * 0.22))

    def update(self, dt, move_x, firing):
        # ---- timers -------------------------------------------------
        self.cooldown = max(0.0, self.cooldown - dt)
        self.invuln = max(0.0, self.invuln - dt)
        self.shield = max(0.0, self.shield - dt)
        self.spread = max(0.0, self.spread - dt)
        self.recoil = max(0.0, self.recoil - dt * 5.0)
        self.muzzle = max(0.0, self.muzzle - dt * 12.0)

        # ---- horizontal movement -------------------------------------
        self.rect.x += int(move_x * PLAYER_SPEED * dt)
        self.rect.x = clamp(self.rect.x, 6, VW - self.rect.width - 6)

        # ---- banking animation --------------------------------------
        target_tilt = 1 if move_x > 0.05 else (-1 if move_x < -0.05 else 0)
        self.tilt += (target_tilt - self.tilt) * clamp(dt * 11.0, 0, 1)
        idx = 0 if self.tilt < -0.4 else (2 if self.tilt > 0.4 else 1)
        self.image = self.frames[idx]

        # ---- firing --------------------------------------------------
        self.fire_hold = firing
        if firing and self.cooldown <= 0.0 and not self.destroyed:
            self.shoot()

    def shoot(self):
        g = self.game
        self.cooldown = PLAYER_FIRE_COOLDOWN
        self.muzzle = 1.0
        self.recoil = 1.0
        nose = self.rect.top + 4 + self.recoil * 3
        cx = self.rect.centerx
        if self.spread > 0.0:
            for dx, dy in ((0, 0), (-17, 16), (17, 16)):
                d = unit(270.0)
                b = Bullet(cx + dx, nose,
                           d.x * PLAYER_BULLET_SPEED + dx * 4.6,
                           d.y * PLAYER_BULLET_SPEED,
                           1, C_ACCENT)
                g.bullets.add(b)
        else:
            d = unit(270.0)
            b = Bullet(cx, nose, d.x * PLAYER_BULLET_SPEED,
                       d.y * PLAYER_BULLET_SPEED, 1, C_CYAN)
            g.bullets.add(b)
        g.play("shoot", 0.07)

    def draw(self, surf, time_value):
        # engine flame
        if not self.destroyed:
            frames = self.game.assets["flame_player"]
            f = frames[int(time_value * 22) % len(frames)]
            surf.blit(f, f.get_rect(midtop=(self.rect.centerx, self.rect.bottom - 6)))
        # blink while invulnerable
        if self.invuln > 0.0 and int(self.invuln * 14) % 2 == 0:
            return
        surf.blit(self.image, self.rect)
        # muzzle flash
        if self.muzzle > 0.0:
            c = alpha_color(C_CYAN, 200 * self.muzzle)
            pygame.draw.circle(surf, c, (self.rect.centerx, self.rect.top + 3),
                               int(4 + 7 * self.muzzle))
        # shield bubble
        if self.shield > 0.0:
            t = 0.5 + 0.5 * self.game.wobble(time_value * 4.0)
            a = int(70 + 60 * t)
            pygame.draw.circle(surf, alpha_color(C_CYAN, a),
                               self.rect.center, int(self.rect.width * 0.62), 2)
            pygame.draw.circle(surf, alpha_color(C_CYAN, a // 3),
                               self.rect.center, int(self.rect.width * 0.62))


# ---------------------------------------------------------------------------
#  ON-SCREEN TOUCH BUTTONS
# ---------------------------------------------------------------------------

class Button(object):
    """A virtual button drawn straight onto the canvas.

    Multi-touch aware: every button keeps the set of finger ids currently
    resting on it, so two thumbs work at the same time.
    """

    def __init__(self, name, rect, kind="round"):
        self.name = name
        self.rect = pygame.Rect(rect)
        self.kind = kind
        self.fingers = set()
        self.pressed = False
        self.pulse = 0.0

    def hit(self, vx, vy):
        return self.rect.collidepoint(vx, vy)

    def update(self, dt):
        self.pressed = bool(self.fingers)
        self.pulse = min(1.0, self.pulse + dt * 6.0) if self.pressed else max(
            0.0, self.pulse - dt * 5.0)

    def draw(self, surf, color, glyph, font, alpha=90):
        r = self.rect
        glow = 1.0 + 0.18 * self.pulse
        rect = r.inflate(int((r.width * (glow - 1.0)) / 2) * 2,
                         int((r.height * (glow - 1.0)) / 2) * 2)
        fill = alpha_color(color, 70 + 130 * self.pulse)
        pygame.draw.rect(surf, fill, rect, border_radius=r.width // 2)
        pygame.draw.rect(surf, alpha_color(color, 150 + 90 * self.pulse), rect,
                         width=2, border_radius=r.width // 2)
        self._glyph(surf, color, glyph, font)

    # -- glyphs -----------------------------------------------------------
    def _glyph(self, surf, color, glyph, font):
        r = self.rect
        c = r.center
        g = alpha_color(C_WHITE, 210 + 45 * self.pulse)
        if glyph == "left" or glyph == "right":
            s = 1 if glyph == "right" else -1
            w = r.width * 0.22
            h = r.height * 0.30
            pygame.draw.polygon(surf, g, [
                (c[0] - s * w, c[1] - h), (c[0] - s * w, c[1] + h), (c[0] + s * w, c[1]),
            ])
        elif glyph == "fire":
            rr = r.width * 0.26
            pygame.draw.circle(surf, alpha_color(C_ACCENT, 190), c, int(rr), 3)
            pygame.draw.circle(surf, alpha_color(C_ACCENT, 120), c, int(rr * 0.45))
            for a in (0, 90, 180, 270):
                d = unit(a)
                pygame.draw.line(surf, alpha_color(C_ACCENT, 190),
                                 (c[0] + d.x * rr * 1.25, c[1] + d.y * rr * 1.25),
                                 (c[0] + d.x * rr * 1.75, c[1] + d.y * rr * 1.75), 3)
        elif glyph == "pause":
            w = max(3, int(r.width * 0.11))
            h = r.height * 0.30
            pygame.draw.rect(surf, g, (c[0] - w * 2, c[1] - h // 2, w, h))
            pygame.draw.rect(surf, g, (c[0] + w, c[1] - h // 2, w, h))
        elif glyph == "play":
            w = r.width * 0.20
            h = r.height * 0.30
            pygame.draw.polygon(surf, g, [(c[0] - w, c[1] - h), (c[0] - w, c[1] + h),
                                          (c[0] + w, c[1])])
        elif glyph == "restart":
            label = font.render("RESTART", True, g)
            surf.blit(label, label.get_rect(center=c))
        else:
            label = font.render(glyph, True, g)
            surf.blit(label, label.get_rect(center=c))


# ---------------------------------------------------------------------------
#  GAME
# ---------------------------------------------------------------------------

MENU, PLAY, PAUSE, OVER = 0, 1, 2, 3


class Game(object):
    def __init__(self):
        pygame.init()
        self.sounds = build_sounds()

        flags = pygame.FULLSCREEN if FULLSCREEN else pygame.RESIZABLE
        # Try the driver-scaled window first: SDL2 then does the 480x800 ->
        # device upscale itself, so the game never pays for it on the CPU.
        self.hw_scaled = False
        if SCALED_DISPLAY:
            try:
                self.screen = pygame.display.set_mode((VW, VH),
                                                     flags | pygame.SCALED)
                self.hw_scaled = True
            except pygame.error:
                self.hw_scaled = False
        if not self.hw_scaled:
            try:
                self.screen = pygame.display.set_mode((VW, VH), flags)
            except pygame.error:
                self.screen = pygame.display.set_mode((VW, VH),
                                                      pygame.RESIZABLE)
        pygame.display.set_caption(GAME_TITLE)
        pygame.mouse.set_visible(False)

        self.canvas = pygame.Surface((VW, VH)).convert()
        self.scaled = None              # cached upscale target (see layout)
        self.scale_size = (VW, VH)
        self.clock = pygame.time.Clock()
        self.assets = build_assets()
        self.sound_time = {}

        # ---- fonts (bundled default font works on every platform) ------
        def font(size):
            try:
                return pygame.font.SysFont("consolas,arial,dejavusansmono", size,
                                           bold=True)
            except Exception:
                return pygame.font.Font(None, int(size * 1.25))

        self.f = {
            "hud": font(26), "hud_s": font(18), "pop": font(20),
            "title": font(64), "sub": font(24), "btn": font(26),
            "big": font(40), "tiny": font(16),
        }

        # ---- sprite groups ---------------------------------------------
        self.bullets = pygame.sprite.Group()
        self.enemy_bullets = pygame.sprite.Group()
        self.enemies = pygame.sprite.Group()
        self.powerups = pygame.sprite.Group()
        self.player = None

        # ---- particles / fx --------------------------------------------
        self.particles = []
        self.shocks = []
        self.pops = []
        self.shake = 0.0
        self.flash = 0.0
        self.time_value = 0.0

        # ---- virtual buttons -------------------------------------------
        self.btn_left = Button("left", (14, VH - 118, 96, 96))
        self.btn_right = Button("right", (118, VH - 118, 96, 96))
        self.btn_fire = Button("fire", (VW - 136, VH - 122, 122, 122))
        self.btn_pause = Button("pause", (VW - 54, 8, 46, 46))
        self.btn_restart = Button("restart", (VW // 2 - 116, 566, 232, 70))
        self.btn_quit = Button("quit", (VW // 2 - 78, 452, 156, 56))
        self.all_buttons = [self.btn_left, self.btn_right, self.btn_fire,
                            self.btn_pause, self.btn_restart, self.btn_quit]

        # ---- pre-rendered static layers ---------------------------------
        # A full-screen SRCALPHA surface is 384 KB; building a few of those
        # every frame is the fastest way to turn a 60 fps game into a 30 fps
        # one on a cheap phone.  All of these are constant, so build them once.
        self.overlay_menu = self._fill_overlay((6, 8, 24, 150))
        self.overlay_pause = self._fill_overlay((4, 6, 20, 190))
        self.overlay_over = self._fill_overlay((10, 4, 14, 200))
        self.pad = self._build_pad()
        # menu jets: pre-rotate 9 frames instead of rotate() x3 every frame
        self.menu_jets = [pygame.transform.rotate(self.assets["fighter"], a)
                          for a in (-16, -12, -8, -4, 0, 4, 8, 12, 16)]
        # game-over title: pre-scale 9 steps instead of smoothscale() per frame
        over_title = self.f["title"].render("GAME OVER", True, C_RED)
        self.over_title = []
        for i in range(9):
            k = 0.92 + 0.08 * (i / 8.0)
            self.over_title.append(pygame.transform.smoothscale(
                over_title, (int(over_title.get_width() * k),
                             int(over_title.get_height() * k))))

        # ---- state -------------------------------------------------------
        self.state = MENU
        self.high_score, self.best_wave = load_best()
        self.new_record = False
        self.keys = pygame.key.get_pressed()
        self.mouse_pos = (VW // 2, VH // 2)
        self.tap_flash = 0.0
        self.reset()
        # Derive the scale/offset immediately so the object is renderable the
        # instant it is constructed (run() re-runs this after any resize).
        self.layout()

    # -- cached static layers ------------------------------------------------
    def _fill_overlay(self, rgba):
        s = pygame.Surface((VW, VH), pygame.SRCALPHA)
        s.fill(rgba)
        return s.convert_alpha()

    def _build_pad(self):
        pad = pygame.Surface((VW, VH - PLAY_BOT), pygame.SRCALPHA)
        for i in range(0, VW, 3):
            pad.fill(alpha_color(C_CYAN, 6), (i, 0, 1, VH - PLAY_BOT))
        return pad.convert_alpha()

    # -- state -------------------------------------------------------------
    def reset(self):
        self.score = 0
        self.level = 1
        self.kills = 0
        self.combo = 0
        self.combo_timer = 0.0
        self.spawn_timer = 0.7
        self.banner_timer = 1.6
        self.game_over_timer = 0.0
        self.bullets.empty()
        self.enemy_bullets.empty()
        self.enemies.empty()
        self.powerups.empty()
        del self.particles[:]
        del self.shocks[:]
        del self.pops[:]
        self.player = Player(self)
        self.shake = 0.0
        self.flash = 0.0
        # NOTE: the old high score is deliberately NOT touched here.  self.score
        # was just zeroed, so the comparison could never be true.  Records are
        # settled once, in game_over().
        self.new_record = False

    def start(self):
        self.reset()
        self.state = PLAY
        self.play("click")

    # -- helpers -----------------------------------------------------------
    def wobble(self, t):
        """Cheap sine replacement (no math module needed)."""
        phase = (t % 1.0) * 2.0
        if phase < 0.5:
            return 4.0 * phase - 1.0
        return 3.0 - 4.0 * phase

    def play(self, name, min_gap=0.0):
        """Fire-and-forget SFX with an optional per-sound re-trigger gap."""
        if name not in self.sounds:
            return
        t = self.time_value
        last = self.sound_time.get(name, -9.0)
        if t - last < min_gap:
            return
        self.sound_time[name] = t
        try:
            self.sounds[name].play()
        except Exception:
            pass

    def add_shake(self, amount):
        self.shake = min(22.0, self.shake + amount)

    def add_flash(self, amount):
        self.flash = min(1.0, self.flash + amount)

    def explosion(self, x, y, size, color):
        count = int(14 + size * 1.6)
        for _ in range(count):
            a = random.uniform(0, 360)
            sp = random.uniform(40, 240) * (0.6 + size / 40.0)
            d = unit(a)
            life = random.uniform(0.28, 0.75)
            if random.random() < 0.55:
                c = random.choice((color, (255, 214, 92), (255, 246, 220)))
                glow = True
            else:
                c = (72, 68, 84)
                glow = False
            self.particles.append(
                Particle(x, y, d.x * sp, d.y * sp, life,
                         random.choice((2, 3, 4, 5)), c, glow))
        # hard cap: cheap phones cannot afford thousands of live particles
        if len(self.particles) > MAX_PARTICLES:
            del self.particles[:len(self.particles) - MAX_PARTICLES]
        self.shocks.append(Shockwave(x, y, int(size * 1.5),
                                     (255, 220, 160), 0.40))
        self.add_shake(min(14.0, size * 0.32))

    # -- input -------------------------------------------------------------
    def layout(self):
        w, h = self.screen.get_size()
        if self.hw_scaled:
            # SDL2 owns the stretch, so the logical canvas maps 1:1 and we
            # must not scale it again ourselves.
            self.scale = 1.0
            self.off_x = 0.0
            self.off_y = 0.0
            self.scale_size = (VW, VH)
            self.scaled = None
            return
        self.scale = min(w / float(VW), h / float(VH))
        self.off_x = (w - VW * self.scale) / 2.0
        self.off_y = (h - VH * self.scale) / 2.0
        # Reuse one destination surface for the upscale. transform.scale()
        # otherwise allocates a multi-megabyte surface every single frame,
        # which is the most expensive thing this game can do.
        size = (max(1, int(VW * self.scale)), max(1, int(VH * self.scale)))
        self.scale_size = size
        if self.scale == 1.0:
            self.scaled = None
        elif self.scaled is None or self.scaled.get_size() != size:
            self.scaled = pygame.Surface(size).convert()

    def to_virtual(self, pos):
        return ((pos[0] - self.off_x) / self.scale,
                (pos[1] - self.off_y) / self.scale)

    def handle_events(self):
        self.keys = pygame.key.get_pressed()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.VIDEORESIZE:
                if self.hw_scaled:
                    # SDL2 owns the window size; the logical surface stays
                    # VW x VH, so there is nothing to re-create here.
                    continue
                if not FULLSCREEN:
                    self.screen = pygame.display.set_mode(
                        (max(320, event.w), max(240, event.h)),
                        pygame.RESIZABLE)
                self.layout()
                continue

            # ---------- pointer input (touch + mouse) ----------
            if event.type == pygame.FINGERDOWN:
                if not self._pointer_down(event.x, event.y, event.finger_id):
                    return False
            elif event.type == pygame.FINGERUP:
                self._pointer_up(event.finger_id)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if not self._pointer_down(event.pos[0], event.pos[1], -1):
                    return False
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self._pointer_up(-1)
            elif event.type == pygame.MOUSEMOTION:
                self.mouse_pos = self.to_virtual(event.pos)

            # ---------- keyboard ----------
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    if self.state == MENU:
                        self.start()
                    elif self.state == OVER:
                        self.start()
                elif event.key in (pygame.K_p, pygame.K_P):
                    if self.state == PLAY:
                        self.state = PAUSE
                    elif self.state == PAUSE:
                        self.state = PLAY
                elif event.key in (pygame.K_r, pygame.K_R):
                    if self.state in (OVER, PAUSE):
                        self.start()
        return True

    def _pointer_down(self, sx, sy, fid):
        """Handle a touch/mouse press. Returns False to quit the game."""
        vx, vy = self.to_virtual((sx, sy))
        self.mouse_pos = (vx, vy)
        if self.state == MENU:
            self.start()
            return True
        if self.state == OVER:
            if self.btn_restart.hit(vx, vy) and self.game_over_timer > 0.6:
                self.play("click")
                self.start()
            return True
        if self.state == PAUSE:
            if self.btn_pause.hit(vx, vy):
                self.play("click")
                self.state = PLAY
            elif self.btn_quit.hit(vx, vy):
                self.play("click")
                return False
            return True
        # in-game: register the finger on whichever control it landed on
        for b in self.all_buttons:
            if b.name in ("restart", "pause", "quit"):
                continue
            if b.hit(vx, vy):
                b.fingers.add(fid)
                return True
        # pause button is a tap, not a hold
        if self.btn_pause.hit(vx, vy):
            self.state = PAUSE
            self.play("click")
        return True

    def _pointer_up(self, fid):
        for b in self.all_buttons:
            b.fingers.discard(fid)

    def read_controls(self):
        """Merge keyboard + on-screen buttons into a movement/fire state."""
        k = self.keys
        move = 0.0
        if k[pygame.K_LEFT] or k[pygame.K_a]:
            move -= 1.0
        if k[pygame.K_RIGHT] or k[pygame.K_d]:
            move += 1.0
        if self.btn_left.pressed:
            move -= 1.0
        if self.btn_right.pressed:
            move += 1.0
        move = clamp(move, -1.0, 1.0)
        fire = bool(k[pygame.K_SPACE] or k[pygame.K_UP] or k[pygame.K_w] or
                    self.btn_fire.pressed)
        return move, fire

    # -- spawning ----------------------------------------------------------
    def spawn_enemy(self):
        if len(self.enemies) >= MAX_ENEMIES:
            return
        level = self.level
        margin = 34
        x = random.randint(margin, VW - margin)
        hp_bonus = 1 if level > 6 and random.random() < 0.25 * (level - 5) / 5.0 else 0
        speed_mul = 1.0 + 0.055 * (level - 1)

        # weighted random: tougher enemies become more common as you level up
        table = [
            (Scout, max(20, 100 - 9 * level)),
            (Fighter, 8 + 9 * level),
            (Drone, 6 + 8 * level),
            (Bomber, 4 + 7 * level),
        ]
        total = sum(w for _, w in table) or 1
        r = random.uniform(0, total)
        cls = Scout
        for c, w in table:
            r -= w
            if r <= 0:
                cls = c
                break
        e = cls(self, x, -60 - random.randint(0, 70), hp_bonus, speed_mul)
        self.enemies.add(e)

    def maybe_drop(self, enemy):
        if random.random() > DROP_CHANCE:
            return
        kind = "H" if self.player.hp < MAX_HP * 0.6 else None
        self.powerups.add(PowerUp(self, enemy.x, enemy.y, kind))

    # -- update ------------------------------------------------------------
    def update(self, dt):
        self.time_value += dt
        self.flash = max(0.0, self.flash - dt * 3.2)
        self.tap_flash = max(0.0, self.tap_flash - dt * 3.0)
        for b in self.all_buttons:
            b.update(dt)

        move, fire = self.read_controls()

        if self.state == PLAY:
            self.update_play(dt, move, fire)
        elif self.state == OVER:
            self.game_over_timer += dt
            self.update_particles(dt)
            self.bullets.update(dt)
            self.enemies.update(dt)

        self.update_stars(dt)
        self.shake = max(0.0, self.shake - dt * 38.0)

    def update_play(self, dt, move, fire):
        p = self.player
        p.update(dt, move, fire)

        # --- spawning ------------------------------------------------
        self.spawn_timer -= dt
        if self.spawn_timer <= 0.0:
            self.spawn_timer = max(SPAWN_MIN, SPAWN_BASE * (0.93 ** (self.level - 1)))
            self.spawn_timer *= random.uniform(0.72, 1.24)
            self.spawn_enemy()
            # occasional tight formation of two scouts
            if self.level > 3 and random.random() < 0.18:
                self.spawn_enemy()

        # --- bullets & entities -------------------------------------
        self.bullets.update(dt)
        self.enemy_bullets.update(dt)
        self.enemies.update(dt)
        self.powerups.update(dt)

        # --- collisions ----------------------------------------------
        # NOTE: iterate over snapshots - kill() mutates the sprite groups.
        # player bullets -> enemies
        for bullet in list(self.bullets):
            hit = None
            for enemy in self.enemies:
                if enemy.collides(bullet.x, bullet.y):
                    hit = enemy
                    break
            if hit is not None:
                bullet.kill()
                self.on_enemy_hit(hit, bullet)

        # enemy bullets -> player
        if not p.destroyed and p.invuln <= 0.0:
            hbox = p.hurtbox()
            for bullet in list(self.enemy_bullets):
                if hbox.collidepoint(bullet.x, bullet.y):
                    bullet.kill()
                    self.on_player_hit(10, "hit")
                    break

        # enemies -> player
        if not p.destroyed and p.invuln <= 0.0:
            hbox = p.hurtbox()
            for enemy in list(self.enemies):
                if hbox.collidepoint(enemy.x, enemy.y):
                    self.on_player_hit(34, "crash")
                    self.explosion(enemy.x, enemy.y, 34, (255, 150, 90))
                    enemy.kill()
                    break

        # powerups -> player
        if not p.destroyed:
            hbox = p.hurtbox()
            for pu in list(self.powerups):
                if hbox.colliderect(pu.rect):
                    pu.kill()
                    self.on_powerup(pu)

        # cull dead / off-screen
        for e in list(self.enemies):
            if e.dead:
                e.kill()
        for b in list(self.bullets):
            if b.rect.bottom < PLAY_TOP or b.rect.top > VH or \
               b.rect.right < 0 or b.rect.left > VW:
                b.kill()
        for b in list(self.enemy_bullets):
            if b.rect.top > VH + 20 or b.rect.bottom < PLAY_TOP - 20:
                b.kill()

        # --- combo ---------------------------------------------------
        if self.combo > 1:
            self.combo_timer -= dt
            if self.combo_timer <= 0.0:
                self.combo = 0
                self.combo_timer = 0.0
        self.banner_timer = max(0.0, self.banner_timer - dt)

        self.update_particles(dt)

    def update_particles(self, dt):
        for p in self.particles:
            p.update(dt)
        keep = [p for p in self.particles if p.life > 0]
        self.particles = keep
        for s in self.shocks:
            s.update(dt)
        self.shocks = [s for s in self.shocks if s.life > 0]
        for f in self.pops:
            f.update(dt)
        self.pops = [f for f in self.pops if f.life > 0]

    def update_stars(self, dt):
        speeds = (26.0, 52.0, 96.0)
        for s in self.assets["stars"]:
            s[1] += speeds[s[3]] * dt
            if s[1] > VH:
                s[1] = -2
                s[0] = random.uniform(0, VW)

    # -- combat events -----------------------------------------------------
    def on_enemy_hit(self, enemy, bullet):
        dead = enemy.damage(bullet.damage)
        self.play("hit", 0.03)
        # small spark burst
        for _ in range(5):
            a = random.uniform(0, 360)
            d = unit(a)
            self.particles.append(Particle(
                bullet.x, bullet.y, d.x * 120, d.y * 120, 0.22, 3,
                random.choice((C_WHITE, C_ACCENT, C_CYAN)), glow=True))
        if not dead:
            return

        enemy.kill()
        self.kills += 1
        self.combo += 1
        self.combo_timer = 2.2
        bonus = min(self.combo - 1, 8) * 25
        gained = enemy.points + bonus
        self.score += gained
        self.pops.append(FloatText(enemy.x, enemy.y - 10, "+%d" % gained,
                                   C_ACCENT))
        if bonus:
            self.pops.append(FloatText(enemy.x, enemy.y - 34,
                                       "x%d" % self.combo, C_CYAN))
        self.explosion(enemy.x, enemy.y, enemy.radius * 2, enemy.color)
        if enemy.radius >= 26:
            self.play("bigboom")
            self.add_flash(0.45)
        else:
            self.play("boom")
        self.maybe_drop(enemy)

        # level up
        if self.kills % KILLS_PER_LEVEL == 0:
            self.level += 1
            self.banner_timer = 1.8
            self.play("power")

    def on_player_hit(self, damage, kind):
        p = self.player
        if p.invuln > 0.0 or p.destroyed or self.state != PLAY:
            return
        if p.shield > 0.0:
            self.play("shield", 0.2)
            p.shield = 0.0
            p.invuln = 0.8
            self.explosion(p.rect.centerx, p.rect.centery, 26, C_CYAN)
            self.pops.append(FloatText(p.rect.centerx, p.rect.top, "SHIELD",
                                       C_CYAN))
            return

        p.hp -= damage
        p.invuln = 0.85
        self.add_shake(10 if kind == "crash" else 5)
        self.add_flash(0.35)
        self.play("hurt", 0.15)
        self.combo = 0
        for _ in range(10):
            a = random.uniform(0, 360)
            d = unit(a)
            self.particles.append(Particle(
                p.rect.centerx, p.rect.centery, d.x * 150, d.y * 150, 0.35, 3,
                C_RED, glow=True))
        if p.hp <= 0:
            self.kill_player()

    def kill_player(self):
        p = self.player
        p.destroyed = True
        p.lives -= 1
        self.explosion(p.rect.centerx, p.rect.centery, 46, C_CYAN)
        self.play("bigboom")
        self.add_flash(0.8)
        self.add_shake(20)
        if p.lives <= 0:
            self.game_over()
        else:
            p.reset()

    def game_over(self):
        self.state = OVER
        self.game_over_timer = 0.0
        self.btn_restart.rect.center = (VW // 2, 640)
        self.play("over")
        # settle the record exactly once, before anything is drawn
        self.new_record = self.score > self.high_score
        if self.new_record:
            self.high_score = self.score
        if self.level > self.best_wave:
            self.best_wave = self.level
        save_best(self.high_score, self.best_wave)

    def on_powerup(self, pu):
        p = self.player
        if pu.kind == "P":
            p.spread = 12.0
            msg, col = "SPREAD GUN", C_ACCENT
        elif pu.kind == "H":
            p.hp = min(MAX_HP, p.hp + 35)
            msg, col = "+35 HULL", C_GREEN
        else:
            p.shield = 7.0
            msg, col = "SHIELD", C_CYAN
        self.pops.append(FloatText(p.rect.centerx, p.rect.top - 4, msg, col))
        self.play("power", 0.1)
        for _ in range(16):
            a = random.uniform(0, 360)
            d = unit(a)
            self.particles.append(Particle(pu.x, pu.y, d.x * 130, d.y * 130,
                                           0.4, 3, pu.color, glow=True))

    # ======================================================================
    #  RENDERING
    # ======================================================================
    def draw(self):
        canvas = self.canvas
        sh = int(self.shake)
        ox = random.randint(-sh, sh) if sh else 0
        oy = random.randint(-sh, sh) if sh else 0

        canvas.blit(self.assets["bg"], (0, 0))
        self.draw_stars(canvas)

        if self.state == MENU:
            self.draw_menu(canvas)
        else:
            self.draw_world(canvas, ox, oy)
            self.draw_hud(canvas)
            self.draw_controls(canvas)
            if self.state == PAUSE:
                self.draw_pause(canvas)
            elif self.state == OVER:
                self.draw_over(canvas)

        # white damage / explosion flash
        if self.flash > 0.0:
            canvas.fill(alpha_color((255, 120, 120), 70 * self.flash), special_flags=pygame.BLEND_RGBA_ADD)

        self.present()

    def present(self):
        if self.scaled is None:
            self.screen.blit(self.canvas, (int(self.off_x), int(self.off_y)))
        else:
            # blit straight into the cached surface - no per-frame allocation
            pygame.transform.scale(self.canvas, self.scale_size, self.scaled)
            self.screen.blit(self.scaled, (int(self.off_x), int(self.off_y)))
        pygame.display.flip()
        if SHOW_FPS:
            img = self.f["tiny"].render("%d FPS" % self.clock.get_fps(), True,
                                        C_GREEN)
            self.screen.blit(img, (8, self.screen.get_height() - 20))

    def draw_stars(self, surf):
        for x, y, r, _layer, b in self.assets["stars"]:
            if r == 1:
                surf.fill((b, b, b), (int(x), int(y), 1, 1))
            else:
                # brighter "beacon" stars get a tiny cross glow
                pygame.draw.circle(surf, (255, 255, 255), (int(x), int(y)), 1)
                glow = (b // 3, b // 3, b // 3)
                surf.fill(glow, (int(x) - 2, int(y), 1, 1))
                surf.fill(glow, (int(x) + 2, int(y), 1, 1))
                surf.fill(glow, (int(x), int(y) - 2, 1, 1))
                surf.fill(glow, (int(x), int(y) + 2, 1, 1))

    def draw_world(self, surf, ox, oy):
        for s in self.shocks:
            s.draw(surf)
        for pu in self.powerups:
            pulse = 0.5 + 0.5 * self.wobble(self.time_value * 3.0 + pu.age)
            img = pu.image.copy()
            img.set_alpha(200 + 55 * int(pulse))
            surf.blit(img, (pu.rect.x + ox, pu.rect.y + oy))
        for b in self.bullets:
            surf.blit(b.image, (b.rect.x + ox, b.rect.y + oy))
        for b in self.enemy_bullets:
            img = b.image
            surf.blit(img, (b.rect.x + ox, b.rect.y + oy))
        for p in self.particles:
            p.draw(surf)

        # enemy engine flames
        frames = self.assets["flame_enemy"]
        for e in self.enemies:
            f = frames[int((self.time_value + e.flame_t) * 20) % len(frames)]
            surf.blit(f, f.get_rect(midtop=(e.rect.centerx + ox,
                                            e.rect.bottom - 3 + oy)))

        for e in self.enemies:
            if e.hp < e.max_hp:
                self.draw_enemy_hp(surf, e, ox, oy)
            surf.blit(e.image, (e.rect.x + ox, e.rect.y + oy))

        if self.player is not None and not self.player.destroyed:
            # move the player sprite by the shake offset without fighting the
            # Sprite machinery: temporarily offset, draw, restore.
            keep = self.player.rect.copy()
            self.player.rect.x += ox
            self.player.rect.y += oy
            self.player.draw(surf, self.time_value)
            self.player.rect = keep

        for f in self.pops:
            f.draw(surf, self.f["pop"])

    def draw_enemy_hp(self, surf, enemy, ox, oy):
        w = enemy.radius * 2
        x = int(enemy.x - w / 2 + ox)
        y = int(enemy.y - enemy.rect.height / 2 - 9 + oy)
        pygame.draw.rect(surf, (14, 16, 30), (x - 1, y - 1, w + 2, 5))
        frac = clamp(enemy.hp / float(enemy.max_hp), 0, 1)
        pygame.draw.rect(surf, C_RED, (x, y, int(w * frac), 3))

    # -- HUD ---------------------------------------------------------------
    def draw_hud(self, surf):
        panel = pygame.Surface((VW, HUD_H), pygame.SRCALPHA)
        panel.fill(alpha_color(C_PANEL, 225))
        surf.blit(panel, (0, 0))
        pygame.draw.line(surf, alpha_color(C_CYAN, 90), (0, HUD_H - 1), (VW, HUD_H - 1))

        # score (left)
        s_img = self.f["hud_s"].render("SCORE", True, C_DIM)
        surf.blit(s_img, (12, 6))
        v_img = self.f["hud"].render("%06d" % self.score, True, C_WHITE)
        surf.blit(v_img, (12, 22))

        # level + combo (centre)
        lv = self.f["hud_s"].render("WAVE %d" % self.level, True, C_ACCENT)
        surf.blit(lv, lv.get_rect(center=(VW // 2, 18)))
        if self.combo > 1:
            cb = self.f["hud_s"].render("COMBO x%d" % self.combo, True, C_CYAN)
            surf.blit(cb, cb.get_rect(center=(VW // 2, 38)))

        # hull bar + lives (right)
        bar_w = 96
        bx, by = VW - bar_w - 66, 20
        pygame.draw.rect(surf, (10, 12, 26), (bx, by, bar_w, 12), border_radius=6)
        frac = clamp(self.player.hp / float(MAX_HP), 0, 1)
        col = C_GREEN if frac > 0.55 else (C_ACCENT if frac > 0.25 else C_RED)
        if frac > 0:
            pygame.draw.rect(surf, col, (bx + 2, by + 2, int((bar_w - 4) * frac), 8),
                             border_radius=4)
        pygame.draw.rect(surf, alpha_color(C_DIM, 150), (bx, by, bar_w, 12), 1,
                         border_radius=6)
        lbl = self.f["tiny"].render("HULL", True, C_DIM)
        surf.blit(lbl, (bx - 2, 4))

        for i in range(self.player.lives):
            jet = pygame.transform.scale(self.assets["player"][1], (15, 17))
            surf.blit(jet, (VW - 58 + i * 18, 8))

        # active power-up timers
        py = HUD_H + 4
        if self.player.spread > 0.0:
            self._chip(surf, "SPREAD", C_ACCENT, self.player.spread / 12.0, py)
            py += 20
        if self.player.shield > 0.0:
            self._chip(surf, "SHIELD", C_CYAN, self.player.shield / 7.0, py)
            py += 20
        if self.player.invuln > 0.0 and self.state == PLAY:
            self._chip(surf, "SHIELDS UP", C_VIOLET,
                       1.0 - self.player.invuln / 1.6, py)

        # wave banner
        if self.banner_timer > 0.0 and self.state == PLAY:
            t = self.banner_timer
            a = 255 if t > 1.2 else int(255 * (t / 1.2))
            img = self.f["big"].render("WAVE %d" % self.level, True, C_ACCENT)
            img.set_alpha(a)
            surf.blit(img, img.get_rect(center=(VW // 2, VH * 0.34)))
            sub = self.f["sub"].render("INCOMING", True, C_RED)
            sub.set_alpha(a)
            surf.blit(sub, sub.get_rect(center=(VW // 2, VH * 0.34 + 34)))

    def _chip(self, surf, text, color, frac, y):
        img = self.f["tiny"].render(text, True, color)
        w = img.get_width() + 10
        pygame.draw.rect(surf, alpha_color(color, 40), (10, y, w, 15),
                         border_radius=7)
        pygame.draw.rect(surf, color, (10, y, int(w * clamp(frac, 0, 1)), 15),
                         border_radius=7)
        surf.blit(img, (15, y + 1))

    # -- virtual controls ---------------------------------------------------
    def draw_controls(self, surf):
        surf.blit(self.pad, (0, PLAY_BOT))
        pygame.draw.line(surf, alpha_color(C_CYAN, 45), (0, PLAY_BOT),
                         (VW, PLAY_BOT))

        font = self.f["btn"]
        self.btn_left.draw(surf, C_CYAN, "left", font)
        self.btn_right.draw(surf, C_CYAN, "right", font)
        self.btn_fire.draw(surf, C_RED, "fire", font)
        if self.state == PLAY:
            self.btn_pause.draw(surf, C_ACCENT, "pause", font, alpha=60)

    # -- screens -------------------------------------------------------------
    def draw_menu(self, surf):
        surf.blit(self.overlay_menu, (0, 0))

        t = self.time_value
        y = VH * 0.30
        title = self.f["title"].render(GAME_TITLE, True, C_ACCENT)
        glow = title.copy()
        glow.fill(alpha_color(C_CYAN, 60), special_flags=pygame.BLEND_RGBA_ADD)
        for i in range(3):
            surf.blit(glow, title.get_rect(center=(VW // 2, y)).move(
                i - 1, int(self.wobble(t * 1.2) * 2)))
        surf.blit(title, title.get_rect(center=(VW // 2, y)))

        sub = self.f["sub"].render("RETRO ARCADE SHOOTER", True, C_CYAN)
        surf.blit(sub, sub.get_rect(center=(VW // 2, y + 44)))
        pygame.draw.line(surf, alpha_color(C_ACCENT, 120), (90, y + 62),
                         (VW - 90, y + 62))

        # demo jets flying down - bank angle comes from the pre-rotated frames
        for i in range(3):
            dx = VW * 0.5 + self.wobble(t * 0.8 + i * 0.33) * VW * 0.36
            dy = (t * 90 + i * 260) % (VH + 160) - 80
            frame = int(self.wobble(t * 1.5 + i) * 4) + 4      # -1..1 -> 0..8
            img = self.menu_jets[clamp(frame, 0, 8)]
            surf.blit(img, img.get_rect(center=(int(dx), int(dy))))

        # start button
        bw, bh = 236, 74
        r = pygame.Rect(0, 0, bw, bh)
        r.center = (VW // 2, int(VH * 0.70))
        pulse = 0.5 + 0.5 * self.wobble(t * 1.6)
        pygame.draw.rect(surf, alpha_color(C_CYAN, 40 + 30 * pulse), r,
                         border_radius=r.height // 2)
        pygame.draw.rect(surf, alpha_color(C_CYAN, 200), r, 3,
                         border_radius=r.height // 2)
        label = self.f["btn"].render("TAP TO START", True, C_WHITE)
        surf.blit(label, label.get_rect(center=r.center))

        hi = self.f["hud_s"].render("HIGH SCORE  %06d" % self.high_score, True,
                                    C_ACCENT)
        surf.blit(hi, hi.get_rect(center=(VW // 2, int(VH * 0.70) + 62)))
        wave = self.f["tiny"].render("BEST WAVE  %d" % self.best_wave, True,
                                     C_VIOLET)
        surf.blit(wave, wave.get_rect(center=(VW // 2, int(VH * 0.70) + 86)))

        keys = self.f["tiny"].render(
            "KEYBOARD:  ARROWS / WASD MOVE    SPACE FIRE    P PAUSE", True, C_DIM)
        surf.blit(keys, keys.get_rect(center=(VW // 2, VH - 26)))
        keys2 = self.f["tiny"].render("TOUCH:  HOLD  < >  TO MOVE, HOLD FIRE TO SHOOT",
                                      True, C_DIM)
        surf.blit(keys2, keys2.get_rect(center=(VW // 2, VH - 10)))

    def draw_pause(self, surf):
        surf.blit(self.overlay_pause, (0, 0))
        title = self.f["big"].render("PAUSED", True, C_CYAN)
        surf.blit(title, title.get_rect(center=(VW // 2, VH // 2 - 60)))
        label = self.f["sub"].render("TAP  ||  OR PRESS  P  TO RESUME", True,
                                     C_WHITE)
        surf.blit(label, label.get_rect(center=(VW // 2, VH // 2 - 18)))
        quit_lbl = self.f["tiny"].render("OR QUIT", True, C_DIM)
        surf.blit(quit_lbl, quit_lbl.get_rect(center=(VW // 2, VH // 2 + 8)))
        # still show the pause button so tapping it resumes
        self.btn_pause.draw(surf, C_ACCENT, "play", self.f["btn"], alpha=60)
        # ... and a real QUIT button, because ESC does not exist on a phone
        self.btn_quit.draw(surf, C_RED, "QUIT", self.f["sub"], alpha=60)

    def draw_over(self, surf):
        surf.blit(self.overlay_over, (0, 0))

        t = clamp(self.game_over_timer / 0.5, 0, 1)
        idx = int(t * (len(self.over_title) - 1) + 0.5)
        img = self.over_title[clamp(idx, 0, len(self.over_title) - 1)].copy()
        img.set_alpha(int(255 * t))
        surf.blit(img, img.get_rect(center=(VW // 2, 200)))

        cy = 300
        if self.new_record:
            nw = self.f["hud_s"].render("NEW RECORD!", True, C_ACCENT)
            nw.set_alpha(int(160 + 95 * (0.5 + 0.5 * self.wobble(
                self.time_value * 3))))
            surf.blit(nw, nw.get_rect(center=(VW // 2, cy)))
        else:
            hs = self.f["hud_s"].render("BEST  %06d" % self.high_score, True,
                                        C_DIM)
            surf.blit(hs, hs.get_rect(center=(VW // 2, cy)))

        rows = [("SCORE", "%06d" % self.score, C_WHITE),
                ("WAVE", "%d" % self.level, C_CYAN),
                ("KILLS", "%d" % self.kills, C_WHITE),
                ("BEST", "%06d" % self.high_score, C_ACCENT),
                ("BEST WAVE", "%d" % self.best_wave, C_VIOLET)]
        y = cy + 40
        for label, value, col in rows:
            l = self.f["sub"].render(label, True, C_DIM)
            v = self.f["hud"].render(value, True, col)
            surf.blit(l, (VW // 2 - 20 - l.get_width(), y))
            surf.blit(v, (VW // 2 + 20, y - 4))
            y += 34

        # restart button
        btn = self.btn_restart
        pulse = 0.5 + 0.5 * self.wobble(self.time_value * 2.0)
        btn.rect.center = (VW // 2, 640)
        pygame.draw.rect(surf, alpha_color(C_GREEN, 40 + 40 * pulse), btn.rect,
                         border_radius=btn.rect.height // 2)
        pygame.draw.rect(surf, alpha_color(C_GREEN, 220), btn.rect, 3,
                         border_radius=btn.rect.height // 2)
        btn._glyph(surf, C_GREEN, "restart", self.f["btn"])

        hint = self.f["tiny"].render("OR PRESS  R  /  ENTER", True, C_DIM)
        surf.blit(hint, hint.get_rect(center=(VW // 2, 692)))

    # -- main loop ----------------------------------------------------------
    def run(self):
        self.layout()
        self.keys = pygame.key.get_pressed()
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            dt = clamp(dt, 0.0, 1.0 / 20.0)      # never simulate a huge jump
            if not self.handle_events():
                break
            self.update(dt)
            self.draw()
        pygame.quit()
        sys.exit(0)


def main():
    Game().run()


if __name__ == "__main__":
    main()
