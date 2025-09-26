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
