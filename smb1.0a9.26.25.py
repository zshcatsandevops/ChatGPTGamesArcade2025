import sys
import random
import pygame

# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────
SCREEN_WIDTH, SCREEN_HEIGHT = 800, 600
TILE_SIZE = 32
FPS = 60

# World feel (NES-ish; hold Shift/X to run which is > NES walk speed)
WALK_MAX_SPEED = 160.0      # px/s  (~5 tiles/s)
RUN_MAX_SPEED  = 240.0      # px/s  (~7.5 tiles/s)
ACCEL          = 3200.0     # px/s²
FRICTION       = 3600.0     # px/s²
GRAVITY        = 3000.0     # px/s²
JUMP_SPEED     = 900.0      # px/s   (initial jump velocity)
MAX_FALL_SPEED = 1400.0     # px/s
COYOTE_TIME    = 0.08       # s after leaving a ledge where jump still works
JUMP_BUFFER    = 0.12       # s before landing we can queue a jump

# Colors (NES-ish palette)
SKY         = (172, 206, 255)
GROUND      = (139, 76, 39)
FLAG_GREEN  = (34, 177, 76)
COIN_YELLOW = (255, 236, 134)
PLAYER_RED  = (206, 52, 52)
WHITE       = (255, 255, 255)
UI_SHADOW   = (16, 22, 48)
WATER_BLUE  = (80, 140, 255)
PATH_COLOR  = (245, 245, 245)
LOCKED_GRAY = (100, 100, 100)
CLEAR_GREEN = (60, 190, 60)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def sign(x: float) -> int:
    return (x > 0) - (x < 0)

# ──────────────────────────────────────────────────────────────────────────────
# Player
# ──────────────────────────────────────────────────────────────────────────────
class Player(pygame.sprite.Sprite):
    def __init__(self, frames):
        super().__init__()
        if not frames:
            raise ValueError("Frames list cannot be empty")
        self.frames = frames
        self.image = frames[0]
        self.rect = self.image.get_rect()

        # spawn set per-level
        self.spawn_x = TILE_SIZE
        self.spawn_y = SCREEN_HEIGHT - 6 * TILE_SIZE

        # Physics
        self.vx = 0.0
        self.vy = 0.0
        self.facing = 1
        self.on_ground = False

        # Timers
        self.coyote = 0.0
        self.jump_buf = 0.0

        # Meta
        self.coins = 0
        self.world = 1
        self.level = 1

        self._reset_to_spawn()

    def set_spawn(self, x, y):
        self.spawn_x = x
        self.spawn_y = y
        self._reset_to_spawn()

    def _reset_to_spawn(self):
        self.rect.x = int(self.spawn_x)
        self.rect.y = int(self.spawn_y)
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False
        self.coyote = 0.0
        self.jump_buf = 0.0

    def respawn(self):
        self._reset_to_spawn()
        self.image = self.frames[0]

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_z, pygame.K_UP):
            self.jump_buf = JUMP_BUFFER

    def update(self, keys, tiles, dt):
        # ── Input/desired speed
        left  = keys[pygame.K_LEFT] or keys[pygame.K_a]
        right = keys[pygame.K_RIGHT] or keys[pygame.K_d]
        running = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT] or keys[pygame.K_x]
        max_speed = RUN_MAX_SPEED if running else WALK_MAX_SPEED

        # ── Horizontal accel/friction
        if left ^ right:
            ax = -ACCEL if left else ACCEL
            self.vx += ax * dt
            self.facing = -1 if left else 1
        else:
            if self.vx != 0.0:
                decel = FRICTION * dt * sign(self.vx)
                if abs(decel) > abs(self.vx):
                    self.vx = 0.0
                else:
                    self.vx -= decel

        # clamp to target max
        if abs(self.vx) > max_speed:
            self.vx = max_speed * sign(self.vx)

        # ── Timers
        if self.on_ground:
            self.coyote = COYOTE_TIME
        else:
            self.coyote = max(0.0, self.coyote - dt)
        if self.jump_buf > 0.0:
            self.jump_buf = max(0.0, self.jump_buf - dt)

        # ── Jump
        if self.jump_buf > 0.0 and (self.on_ground or self.coyote > 0.0):
            self.vy = -JUMP_SPEED
            self.on_ground = False
            self.coyote = 0.0
            self.jump_buf = 0.0

        # ── Gravity
        self.vy = min(self.vy + GRAVITY * dt, MAX_FALL_SPEED)

        # ── Axis-separated movement & collision
        self.rect.x += int(round(self.vx * dt))
        for tile in tiles:
            if self.rect.colliderect(tile):
                if self.vx > 0:
                    self.rect.right = tile.left
                elif self.vx < 0:
                    self.rect.left = tile.right
                self.vx = 0.0

        self.rect.y += int(round(self.vy * dt))
        self.on_ground = False
        for tile in tiles:
            if self.rect.colliderect(tile):
                if self.vy > 0:
                    self.rect.bottom = tile.top
                    self.vy = 0.0
                    self.on_ground = True
                elif self.vy < 0:
                    self.rect.top = tile.bottom
                    self.vy = 0.0

# ──────────────────────────────────────────────────────────────────────────────
# Level Generation
# ──────────────────────────────────────────────────────────────────────────────
def generate_level(width_tiles, height_tiles):
    """Generate a simple level with ground and some platforms"""
    level = []
    
    # Create ground tiles
    for x in range(width_tiles):
        level.append(pygame.Rect(x * TILE_SIZE, (height_tiles - 1) * TILE_SIZE, TILE_SIZE, TILE_SIZE))
        # Add some ground tiles above the bottom
        if x % 3 == 0:
            level.append(pygame.Rect(x * TILE_SIZE, (height_tiles - 2) * TILE_SIZE, TILE_SIZE, TILE_SIZE))
    
    # Add some platforms
    for x in range(5, width_tiles - 5, 8):
        level.append(pygame.Rect(x * TILE_SIZE, (height_tiles - 4) * TILE_SIZE, TILE_SIZE * 3, TILE_SIZE))
    
    return level
#!/usr/bin/env python3
"""
Samsoft DS Engine — single-file demo (Pygame 2.5+)
Window: 600x400 @ 60 FPS (internal 300x200 buffer, 2x nearest-neighbor upscale)

Controls:
  ←/→  move
  Shift / X  run
  Space / Z / ↑ / W  jump (variable height: release to short hop)
  Esc quit
"""

import math
import random
import sys
import pygame

# ──────────────────────────────────────────────────────────────────────────────
# Config (DS-ish tuning)
# ──────────────────────────────────────────────────────────────────────────────
SCREEN_W, SCREEN_H = 600, 400        # Output window
FRAME_W,  FRAME_H  = 300, 200        # Internal buffer (crisp 2x → 600x400)
SCALE_X, SCALE_Y   = SCREEN_W // FRAME_W, SCREEN_H // FRAME_H
assert SCALE_X >= 1 and SCALE_Y >= 1, "Window must be >= internal frame"

FPS        = 60
TILE_SIZE  = 16                       # DS-like tile size
# Keep similar *tile* feel as your earlier settings (converted for 16px tiles)
WALK_MAX_SPEED   = 5.0  * TILE_SIZE   # px/s  (≈80)
RUN_MAX_SPEED    = 7.5  * TILE_SIZE   # px/s  (≈120)
ACCEL            = 100.0 * TILE_SIZE  # px/s² (≈1600)
FRICTION         = 112.5 * TILE_SIZE  # px/s² (≈1800)
GRAVITY          = 93.75* TILE_SIZE   # px/s² (≈1500)
JUMP_SPEED       = 28.0 * TILE_SIZE   # px/s  (≈450)
MAX_FALL_SPEED   = 43.75* TILE_SIZE   # px/s  (≈700)
COYOTE_TIME      = 0.08               # s
JUMP_BUFFER      = 0.12               # s
JUMP_CUT_MULT    = 0.50               # variable jump: cut upward velocity on release

# Colors (NES/DS-ish palette)
SKY_TOP     = (172, 206, 255)
SKY_BOTTOM  = ( 76, 116, 208)
GRASS_LIGHT = (120, 220, 120)
GRASS_DARK  = ( 68, 168,  68)
DIRT_MAIN   = (139,  76,  39)
DIRT_DARK   = ( 92,  48,  25)
COIN_LIGHT  = (255, 236, 134)
COIN_MED    = (246, 200,  84)
COIN_DARK   = (198, 140,  38)
PLAYER_RED  = (206,  52,  52)
PLAYER_SH   = (140,  24,  24)
WHITE       = (255, 255, 255)

JUMP_KEYS = {pygame.K_SPACE, pygame.K_z, pygame.K_w, pygame.K_UP}

# Tiles:
# '.' empty sky, 'P' grass/dirt ground (solid), '#' block (solid),
# '=' platform top (one-way), 'C' coin, 'F' flagpole, 'S' spawn
SOLID_TILES   = {'P', '#'}
ONE_WAY_TILES = {'='}

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def sign(x: float) -> int:
    return (x > 0) - (x < 0)

def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v

# ──────────────────────────────────────────────────────────────────────────────
# Coin sprite (little bob + shine)
# ──────────────────────────────────────────────────────────────────────────────
class Coin(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.base = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
        self._draw_coin(self.base)
        self.image = self.base.copy()
        self.rect  = self.image.get_rect(topleft=(x, y))
        self.t     = random.random() * 100.0

    def _draw_coin(self, surf):
        r = TILE_SIZE // 2
        cx, cy = r, r
        # simple layered coin
        pygame.draw.circle(surf, COIN_DARK, (cx, cy), r)
        pygame.draw.circle(surf, COIN_MED,  (cx, cy), r-2)
        pygame.draw.circle(surf, COIN_LIGHT,(cx-2, cy-2), r-4)

    def update(self, dt):
        self.t += dt
        bob = math.sin(self.t * 6.0) * 1.5
        self.rect.y = int(self.rect.y - bob)  # cheap visual bob (no world gravity)
        # Keep image same size; visual only

# ──────────────────────────────────────────────────────────────────────────────
# TileMap with grid collisions and drawing
# ──────────────────────────────────────────────────────────────────────────────
class TileMap:
    def __init__(self, grid):
        self.grid = [list(row) for row in grid]
        self.h = len(self.grid)
        self.w = len(self.grid[0]) if self.h else 0
        self.pixel_w = self.w * TILE_SIZE
        self.pixel_h = self.h * TILE_SIZE

        self.coins = pygame.sprite.Group()
        self.flag_rect = None
        self.spawn = (TILE_SIZE, TILE_SIZE)

        for ty, row in enumerate(self.grid):
            for tx, ch in enumerate(row):
                x, y = tx*TILE_SIZE, ty*TILE_SIZE
                if ch == 'C':
                    self.coins.add(Coin(x, y - 2))  # slight lift
                    self.grid[ty][tx] = '.'        # not solid
                elif ch == 'F':
                    self.flag_rect = pygame.Rect(x, y - 3*TILE_SIZE, TILE_SIZE, 3*TILE_SIZE)
                elif ch == 'S':
                    self.spawn = (x, y - TILE_SIZE)

    def get(self, tx, ty):
        if 0 <= tx < self.w and 0 <= ty < self.h:
            return self.grid[ty][tx]
        return '.'  # out of bounds is air

    def rects_around(self, rect):
        """Return solid/oneway rects near AABB."""
        results = []
        tx0 = (rect.left  // TILE_SIZE) - 1
        tx1 = (rect.right // TILE_SIZE) + 1
        ty0 = (rect.top   // TILE_SIZE) - 1
        ty1 = (rect.bottom// TILE_SIZE) + 1
        for ty in range(ty0, ty1+1):
            for tx in range(tx0, tx1+1):
                ch = self.get(tx, ty)
                if ch in SOLID_TILES or ch in ONE_WAY_TILES:
                    results.append((ch, pygame.Rect(tx*TILE_SIZE, ty*TILE_SIZE, TILE_SIZE, TILE_SIZE)))
        return results

    def draw(self, surf, camx, camy):
        # Parallax sky (cheap two-band gradient + mountains)
        surf.fill(SKY_BOTTOM)
        top = pygame.Surface((1, 2))
        top.fill(SKY_BOTTOM)
        top.set_at((0, 0), SKY_TOP)
        grad = pygame.transform.smoothscale(top, (FRAME_W, FRAME_H))
        surf.blit(grad, (0, 0))

        # Mountains (slow parallax)
        off = int(camx * 0.25) % (FRAME_W + 120)
        for i in (-1, 0, 1, 2):
            base_x = i*(FRAME_W+120) - off
            pygame.draw.polygon(
                surf, (120, 150, 200),
                [(base_x+20, FRAME_H-60), (base_x+120, FRAME_H-110), (base_x+220, FRAME_H-60)]
            )

        # Draw tiles
        vx0 = camx // TILE_SIZE
        vy0 = camy // TILE_SIZE
        tiles_x = FRAME_W // TILE_SIZE + 3
        tiles_y = FRAME_H // TILE_SIZE + 3

        for ty in range(vy0, vy0 + tiles_y):
            for tx in range(vx0, vx0 + tiles_x):
                ch = self.get(tx, ty)
                if ch == 'P':
                    # grass top + dirt body
                    x = tx*TILE_SIZE - camx
                    y = ty*TILE_SIZE - camy
                    pygame.draw.rect(surf, DIRT_MAIN, (x, y, TILE_SIZE, TILE_SIZE))
                    pygame.draw.rect(surf, DIRT_DARK, (x, y+TILE_SIZE-3, TILE_SIZE, 3))
                    pygame.draw.rect(surf, GRASS_DARK,(x, y, TILE_SIZE, 4))
                    pygame.draw.rect(surf, GRASS_LIGHT,(x, y, TILE_SIZE, 2))
                elif ch == '#':
                    x = tx*TILE_SIZE - camx
                    y = ty*TILE_SIZE - camy
                    pygame.draw.rect(surf, (118, 96, 68), (x, y, TILE_SIZE, TILE_SIZE))
                    pygame.draw.rect(surf, (92,  72, 48), (x, y, TILE_SIZE, 3))
                    pygame.draw.rect(surf, (72,  56, 36), (x, y+TILE_SIZE-3, TILE_SIZE, 3))
                elif ch == '=':
                    # one-way platform top
                    x = tx*TILE_SIZE - camx
                    y = ty*TILE_SIZE - camy
                    pygame.draw.rect(surf, (90, 170, 90), (x, y+TILE_SIZE-4, TILE_SIZE, 4))

        # Flag (if present)
        if self.flag_rect:
            fx = self.flag_rect.x - camx
            fy = self.flag_rect.y - camy
            pygame.draw.rect(surf, (160,160,160), (fx, fy, 3, self.flag_rect.height))  # pole
            pygame.draw.polygon(surf, (34, 177, 76),
                                [(fx+3, fy+6), (fx+3+10, fy+11), (fx+3, fy+16)])    # tiny flag

        # Coins (draw after tiles)
        for coin in self.coins:
            cx = coin.rect.x - camx
            cy = coin.rect.y - camy
            surf.blit(coin.image, (cx, cy))

# ──────────────────────────────────────────────────────────────────────────────
# Player
# ──────────────────────────────────────────────────────────────────────────────
class Player(pygame.sprite.Sprite):
    def __init__(self, spawn_xy):
        super().__init__()
        self.frames = self._make_frames()
        self.image  = self.frames['idle']
        self.rect   = self.image.get_rect(topleft=spawn_xy)

        # physics
        self.vx = 0.0
        self.vy = 0.0
        self.facing = 1
        self.on_ground = False
        self.coyote = 0.0
        self.jump_buf = 0.0
        self.jump_held = False

        # meta
        self.coins = 0

    def _make_frames(self):
        w, h = 12, 16
        # idle
        idle = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(idle, PLAYER_SH, (0, 1, w, h-1))
        pygame.draw.rect(idle, PLAYER_RED, (0, 0, w, h-2))
        # run
        run = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(run,  PLAYER_SH, (0, 1, w, h-1))
        pygame.draw.rect(run,  PLAYER_RED, (0, 0, w, h-2))
        pygame.draw.rect(run,  WHITE,     (2, h-3, 3, 2))
        # jump
        jump = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(jump, PLAYER_SH, (0, 1, w, h-1))
        pygame.draw.rect(jump, PLAYER_RED,(0, 0, w, h-2))
        pygame.draw.rect(jump, WHITE,     (w-5, 2, 3, 2))
        return {'idle': idle, 'run': run, 'jump': jump}

    def handle_event(self, e):
        if e.type == pygame.KEYDOWN and e.key in JUMP_KEYS:
            self.jump_buf = JUMP_BUFFER
            self.jump_held = True
        elif e.type == pygame.KEYUP and e.key in JUMP_KEYS:
            self.jump_held = False
            if self.vy < 0.0:
                self.vy *= JUMP_CUT_MULT  # variable jump height

    def update(self, keys, tilemap: TileMap, dt):
        # desired max speed
        running = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT] or keys[pygame.K_x]
        max_speed = RUN_MAX_SPEED if running else WALK_MAX_SPEED

        # horizontal input
        left  = keys[pygame.K_LEFT] or keys[pygame.K_a]
        right = keys[pygame.K_RIGHT] or keys[pygame.K_d]

        if left ^ right:
            ax = -ACCEL if left else ACCEL
            self.vx += ax * dt
            self.facing = -1 if left else 1
        else:
            # friction
            if self.vx != 0.0:
                decel = FRICTION * dt * sign(self.vx)
                if abs(decel) > abs(self.vx):
                    self.vx = 0.0
                else:
                    self.vx -= decel

        # clamp horizontal
        if abs(self.vx) > max_speed:
            self.vx = max_speed * sign(self.vx)

        # timers (coyote + jump buffer)
        self.coyote = COYOTE_TIME if self.on_ground else max(0.0, self.coyote - dt)
        if self.jump_buf > 0.0:
            self.jump_buf = max(0.0, self.jump_buf - dt)

        # jump consume
        if self.jump_buf > 0.0 and (self.on_ground or self.coyote > 0.0):
            self.vy = -JUMP_SPEED
            self.on_ground = False
            self.coyote = 0.0
            self.jump_buf = 0.0

        # gravity
        self.vy = min(self.vy + GRAVITY * dt, MAX_FALL_SPEED)

        # ── axis-separated collisions
        # X axis
        self.rect.x += int(round(self.vx * dt))
        for ch, tile in tilemap.rects_around(self.rect):
            if ch in SOLID_TILES and self.rect.colliderect(tile):
                if self.vx > 0:  self.rect.right = tile.left
                elif self.vx < 0:self.rect.left  = tile.right
                self.vx = 0.0

        # Y axis
        self.on_ground = False
        self.rect.y += int(round(self.vy * dt))
        for ch, tile in tilemap.rects_around(self.rect):
            if ch in SOLID_TILES and self.rect.colliderect(tile):
                if self.vy > 0:
                    self.rect.bottom = tile.top
                    self.vy = 0.0
                    self.on_ground = True
                elif self.vy < 0:
                    self.rect.top = tile.bottom
                    self.vy = 0.0
            elif ch in ONE_WAY_TILES and self.rect.colliderect(tile):
                # one-way: only stop when falling and above platform
                if self.vy > 0 and (self.rect.bottom - tile.top) <= 8 and (self.rect.centery <= tile.top):
                    self.rect.bottom = tile.top
                    self.vy = 0.0
                    self.on_ground = True

        # sprite pose
        if not self.on_ground:
            self.image = self.frames['jump']
        elif abs(self.vx) > 8.0:
            self.image = self.frames['run']
        else:
            self.image = self.frames['idle']

    def draw(self, surf, camx, camy):
        img = self.image
        if self.facing < 0:
            img = pygame.transform.flip(img, True, False)
        surf.blit(img, (self.rect.x - camx, self.rect.y - camy))

# ──────────────────────────────────────────────────────────────────────────────
# Sample level (simple generator → DS-ish 1-1)
# ──────────────────────────────────────────────────────────────────────────────
def make_level_w1_1():
    H = 14  # rows
    W = 160 # cols (≈ 2560 px)
    rows = [['.' for _ in range(W)] for _ in range(H)]

    # baseline ground
    ground_y = H - 2
    for x in range(W):
        rows[ground_y][x] = 'P'
        rows[ground_y+1][x] = 'P'

    # spawn & early platforms
    rows[ground_y-1][2] = 'S'
    for x in range(10, 20):
        rows[ground_y-4][x] = '='
    for x in range(26, 30):
        rows[ground_y-6][x] = '='

    # small pits
    for x in range(40, 43):  rows[ground_y][x] = '.'
    for x in range(41, 43):  rows[ground_y+1][x] = '.'

    # blocks section
    for x in range(55, 60):
        rows[ground_y-5][x] = '#'
    for x in range(62, 67):
        rows[ground_y-3][x] = '#'

    # coin lines
    for x in range(14, 20):
        rows[ground_y-6][x] = 'C'
    for x in range(70, 76):
        rows[ground_y-7][x] = 'C'

    # step-up platforms
    for i, x0 in enumerate([84, 88, 92]):
        for x in range(x0, x0+3):
            rows[ground_y-2-i][x] = '='

    # final run and flag
    rows[ground_y-5][W-20] = 'C'
    rows[ground_y-6][W-18] = 'C'
    rows[ground_y-7][W-16] = 'C'
    rows[ground_y-1][W-6]  = 'F'

    return ["".join(r) for r in rows]

# ──────────────────────────────────────────────────────────────────────────────
# Game
# ──────────────────────────────────────────────────────────────────────────────
class Game:
    def __init__(self):
        pygame.init()
        flags = 0
        try:
            self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), flags, vsync=1)
        except TypeError:
            # Older SDL/Pygame without vsync kwarg
            self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), flags)
        pygame.display.set_caption("Samsoft DS Engine — 600x400 @ 60")

        self.clock = pygame.time.Clock()
        self.frame = pygame.Surface((FRAME_W, FRAME_H)).convert()  # offscreen buffer

        # World
        self.level = TileMap(make_level_w1_1())
        self.player = Player(self.level.spawn)

        # Camera
        self.camx = 0
        self.camy = 0

        # UI
        self.font = pygame.font.Font(None, 12*2)  # scaled later

        # State
        self.level_complete = False
        self.fade = 0.0

    def handle_events(self):
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return False
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                return False
            self.player.handle_event(e)
        return True

    def update(self, dt):
        keys = pygame.key.get_pressed()
        self.player.update(keys, self.level, dt)

        # coins
        got = pygame.sprite.spritecollide(self.player, self.level.coins, dokill=True)
        if got:
            self.player.coins += len(got)

        # flag reach
        if self.level.flag_rect and self.player.rect.colliderect(self.level.flag_rect):
            self.level_complete = True

        # parallax objects
        self.level.coins.update(dt)

        # camera follow (x only for comfort)
        target = self.player.rect.centerx - FRAME_W//2
        self.camx = clamp(target, 0, max(0, self.level.pixel_w - FRAME_W))
        self.camy = 0  # keep simple

    def draw_ui(self):
        txt = f"COINS {self.player.coins:02d}"
        fps = f"{self.clock.get_fps():.0f} FPS"
        t1 = self.font.render(txt, True, WHITE)
        t2 = self.font.render(fps, True, WHITE)
        self.frame.blit(t1, (6, 6))
        self.frame.blit(t2, (FRAME_W - t2.get_width() - 6, 6))

    def render(self):
        # draw everything to internal frame
        self.level.draw(self.frame, self.camx, self.camy)
        self.player.draw(self.frame, self.camx, self.camy)
        self.draw_ui()

        # simple fade when level complete
        if self.level_complete:
            self.fade = clamp(self.fade + 0.8, 0, 255)
            shade = pygame.Surface((FRAME_W, FRAME_H))
            shade.set_alpha(int(self.fade))
            shade.fill((0, 0, 0))
            self.frame.blit(shade, (0, 0))

        # scale to window (crisp)
        scaled = pygame.transform.scale(self.frame, (SCREEN_W, SCREEN_H))
        self.screen.blit(scaled, (0, 0))
        pygame.display.flip()
        # clear frame for next draw
        self.frame.fill((0, 0, 0))

    def run(self):
        # Warm-up to stabilize timers
        self.clock.tick(FPS)
        running = True
        while running:
            running = self.handle_events()
            dt = self.clock.tick(FPS) / 1000.0
            dt = min(dt, 1/30)  # clamp for stable physics on hiccups
            self.update(dt)
            self.render()
        pygame.quit()

# ──────────────────────────────────────────────────────────────────────────────
# Entry
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    Game().run()

# ──────────────────────────────────────────────────────────────────────────────
# Game Class
# ──────────────────────────────────────────────────────────────────────────────
class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Super Mario Bros")
        self.clock = pygame.time.Clock()
        
        # Create player frames (simple colored rectangles for now)
        player_frames = [
            pygame.Surface((TILE_SIZE, TILE_SIZE)),
            pygame.Surface((TILE_SIZE, TILE_SIZE))
        ]
        for frame in player_frames:
            frame.fill(PLAYER_RED)
        
        self.player = Player(player_frames)
        self.tiles = generate_level(SCREEN_WIDTH // TILE_SIZE, SCREEN_HEIGHT // TILE_SIZE)
        
        self.running = True
        
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            self.player.handle_event(event)
    
    def update(self, dt):
        keys = pygame.key.get_pressed()
        self.player.update(keys, self.tiles, dt)
    
    def render(self):
        self.screen.fill(SKY)
        
        # Draw tiles
        for tile in self.tiles:
            pygame.draw.rect(self.screen, GROUND, tile)
        
        # Draw player
        self.screen.blit(self.player.image, self.player.rect)
        
        pygame.display.flip()
    
    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0  # Convert to seconds
            
            self.handle_events()
            self.update(dt)
            self.render()
        
        pygame.quit()

def main():
    Game().run()

if __name__ == "__main__":
    main()
