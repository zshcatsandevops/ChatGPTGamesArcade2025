import sys
import math
import random
from array import array

import pygame

# ---------------------------------------------------------------------------
# Init (mixer first for low-latency & correct format)
# ---------------------------------------------------------------------------
pygame.mixer.pre_init(22050, -16, 2, 512)
pygame.init()

# ---------------------------------------------------------------------------
# Constants / Config
# ---------------------------------------------------------------------------
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
FPS = 60

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED   = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE  = (0, 0, 255)
GRAY  = (120, 120, 120)
DARK  = (40, 40, 40)

PLAYER_SPEED = 5
PLAYER_FIRE_COOLDOWN_MS = 280
BULLET_SPEED = 7
INVADER_STEP_PIXELS = 1
INVADER_STEP_FRAMES = 6
INVADER_DROP_PIXELS = 12
ENEMY_SHOT_CHANCE = 200
MAX_LIVES = 3

# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------
class SilentSound:
    def play(self, *_, **__):
        pass

def mixer_ready() -> bool:
    try:
        return pygame.mixer.get_init() is not None
    except Exception:
        return False

def generate_beep(frequency=440.0, duration=0.1, volume=0.5, sample_rate=22050):
    if not mixer_ready():
        return SilentSound()
    n_samples = int(duration * sample_rate)
    amp = int(32767 * max(0.0, min(1.0, volume)))
    frames = array('h')
    phase = 0.0
    phase_inc = float(frequency) / float(sample_rate) if frequency > 0 else 0.0
    for _ in range(n_samples):
        sample = amp if phase < 0.5 else -amp
        frames.append(sample)
        frames.append(sample)
        phase += phase_inc
        if phase >= 1.0:
            phase -= 1.0
    try:
        return pygame.mixer.Sound(buffer=frames.tobytes())
    except Exception:
        return SilentSound()

SHOOT_SOUND = generate_beep(800, 0.05, 0.5)
HIT_SOUND = generate_beep(200, 0.12, 0.6)
INVADER_MOVE_SOUND = generate_beep(300, 0.03, 0.4)

# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------
class Bullet(pygame.sprite.Sprite):
    def __init__(self, x, y, direction=-1):
        super().__init__()
        self.image = pygame.Surface((5, 10), pygame.SRCALPHA).convert_alpha()
        self.image.fill(GREEN if direction > 0 else BLUE)
        self.rect = self.image.get_rect(center=(x, y))
        self.speed = BULLET_SPEED * direction

    def update(self):
        self.rect.y += self.speed
        if self.rect.bottom < 0 or self.rect.top > SCREEN_HEIGHT:
            self.kill()


class Invader(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.image = pygame.Surface((40, 30), pygame.SRCALPHA).convert_alpha()
        self.image.fill(RED)
        pygame.draw.rect(self.image, WHITE, (5, 5, 30, 20))
        self.rect = self.image.get_rect(topleft=(x, y))
        self.direction = 1
        self.move_count = 0

    def update(self):
        self.move_count += 1
        if self.move_count >= INVADER_STEP_FRAMES:
            self.rect.x += INVADER_STEP_PIXELS * self.direction
            self.move_count = 0
            if random.randint(1, 100) <= 3:
                INVADER_MOVE_SOUND.play()


class Player(pygame.sprite.Sprite):
    def __init__(self):
        super().__init__()
        self.image = pygame.Surface((50, 30), pygame.SRCALPHA).convert_alpha()
        self.image.fill(GREEN)
        pygame.draw.polygon(self.image, WHITE, [(25, 0), (0, 30), (50, 30)])
        self.rect = self.image.get_rect()
        self.rect.centerx = SCREEN_WIDTH // 2
        self.rect.bottom = SCREEN_HEIGHT - 10
        self.speed = PLAYER_SPEED
        self.last_shot_ms = 0

    def update(self):
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT] and self.rect.left > 0:
            self.rect.x -= self.speed
        if keys[pygame.K_RIGHT] and self.rect.right < SCREEN_WIDTH:
            self.rect.x += self.speed

    def shoot(self, now_ms, all_sprites, player_bullets):
        if now_ms - self.last_shot_ms >= PLAYER_FIRE_COOLDOWN_MS:
            bullet = Bullet(self.rect.centerx, self.rect.top, -1)
            all_sprites.add(bullet)
            player_bullets.add(bullet)
            SHOOT_SOUND.play()
            self.last_shot_ms = now_ms


class Barrier(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.max_hp = 6
        self.hp = self.max_hp
        self.image = pygame.Surface((60, 40), pygame.SRCALPHA).convert_alpha()
        self.rect = self.image.get_rect(topleft=(x, y))
        self._redraw()

    def _redraw(self):
        t = max(0, min(1, self.hp / float(self.max_hp)))
        shade = int(40 + 160 * t)
        self.image.fill((shade, shade, shade))
        pygame.draw.rect(self.image, DARK, (0, 30, 60, 10))
        pygame.draw.rect(self.image, DARK, (0, 0, 4, 40))
        pygame.draw.rect(self.image, DARK, (56, 0, 4, 40))

    def damage(self, n=1):
        self.hp -= n
        if self.hp <= 0:
            self.kill()
        else:
            self._redraw()


# ---------------------------------------------------------------------------
# Game helpers
# ---------------------------------------------------------------------------
def spawn_invader_grid(all_sprites, invaders, rows=5, cols=10, x0=50, y0=50, dx=60, dy=40):
    for row in range(rows):
        for col in range(cols):
            inv = Invader(x0 + col * dx, y0 + row * dy)
            all_sprites.add(inv)
            invaders.add(inv)

def spawn_barriers(all_sprites, barriers, count=4, x0=150, dx=150, y=450):
    for i in range(count):
        b = Barrier(x0 + i * dx, y)
        all_sprites.add(b)
        barriers.add(b)

def reset_wave(all_sprites, invaders, player_bullets, enemy_bullets):
    for s in invaders.sprites():
        s.kill()
    for b in player_bullets.sprites():
        b.kill()
    for b in enemy_bullets.sprites():
        b.kill()
    spawn_invader_grid(all_sprites, invaders)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main():
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SCALED | pygame.RESIZABLE)
    pygame.display.set_caption("Space Invaders — UST-POSIX Edition")
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 36)

    all_sprites = pygame.sprite.Group()
    invaders = pygame.sprite.Group()
    player_bullets = pygame.sprite.Group()
    enemy_bullets = pygame.sprite.Group()
    barriers = pygame.sprite.Group()

    player = Player()
    all_sprites.add(player)

    spawn_invader_grid(all_sprites, invaders)
    spawn_barriers(all_sprites, barriers)

    score = 0
    lives = MAX_LIVES
    invader_direction = 1
    edge_cooldown = 0
    paused = False
    game_over = False

    while True:
        dt = clock.tick(FPS)
        now = pygame.time.get_ticks()

        # --- Events ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit(0)
                if event.key == pygame.K_p:
                    paused = not paused
                if not paused and not game_over:
                    if event.key == pygame.K_SPACE:
                        player.shoot(now, all_sprites, player_bullets)
                if game_over and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    score = 0
                    lives = MAX_LIVES
                    game_over = False
                    for s in all_sprites.sprites():
                        if s is not player:
                            s.kill()
                    spawn_invader_grid(all_sprites, invaders)
                    spawn_barriers(all_sprites, barriers)
                    player.rect.centerx = SCREEN_WIDTH // 2
                    player.rect.bottom = SCREEN_HEIGHT - 10

        if edge_cooldown > 0:
            edge_cooldown -= 1

        if paused:
            screen.fill(BLACK)
            txt = font.render("Paused — press P to resume", True, WHITE)
            screen.blit(txt, (SCREEN_WIDTH//2 - txt.get_width()//2, SCREEN_HEIGHT//2 - 10))
            pygame.display.flip()
            continue

        if game_over:
            screen.fill(BLACK)
            over = font.render("Game Over — Press Enter to restart", True, WHITE)
            score_txt = font.render(f"Final Score: {score}", True, WHITE)
            screen.blit(over, (SCREEN_WIDTH//2 - over.get_width()//2, SCREEN_HEIGHT//2 - 20))
            screen.blit(score_txt, (SCREEN_WIDTH//2 - score_txt.get_width()//2, SCREEN_HEIGHT//2 + 20))
            pygame.display.flip()
            continue

        # --- Update ---
        all_sprites.update()

        move_invaders = False
        if edge_cooldown == 0:
            for inv in invaders:
                if inv.rect.right >= SCREEN_WIDTH or inv.rect.left <= 0:
                    move_invaders = True
                    break
            if move_invaders:
                invader_direction *= -1
                for inv in invaders:
                    inv.rect.y += INVADER_DROP_PIXELS
                    inv.direction = invader_direction
                    inv.rect.x += invader_direction
                    if inv.rect.left < 0:
                        inv.rect.left = 0
                    if inv.rect.right > SCREEN_WIDTH:
                        inv.rect.right = SCREEN_WIDTH
                edge_cooldown = INVADER_STEP_FRAMES
                INVADER_MOVE_SOUND.play()

        for inv in invaders:
            if inv.rect.bottom >= SCREEN_HEIGHT - 50:
                lives -= 1
                reset_wave(all_sprites, invaders, player_bullets, enemy_bullets)
                if lives <= 0:
                    game_over = True
                break

        if len(invaders) > 0 and random.randint(1, ENEMY_SHOT_CHANCE) == 1:
            shooter = random.choice(invaders.sprites())
            bullet = Bullet(shooter.rect.centerx, shooter.rect.bottom, +1)
            all_sprites.add(bullet)
            enemy_bullets.add(bullet)

        hits = pygame.sprite.groupcollide(invaders, player_bullets, True, True)
        if hits:
            destroyed = sum(len(v) for v in hits.values())
            score += 10 * destroyed
            HIT_SOUND.play()
            if len(invaders) == 0:
                reset_wave(all_sprites, invaders, player_bullets, enemy_bullets)

        if pygame.sprite.spritecollide(player, enemy_bullets, True):
            lives -= 1
            HIT_SOUND.play()
            if lives <= 0:
                game_over = True

        for b in enemy_bullets.sprites():
            struck = pygame.sprite.spritecollide(b, barriers, False)
            if struck:
                b.kill()
                for bunker in struck:
                    bunker.damage(1)

        for b in player_bullets.sprites():
            struck = pygame.sprite.spritecollide(b, barriers, False)
            if struck:
                b.kill()
                for bunker in struck:
                    bunker.damage(1)

        # --- Draw ---
        screen.fill(BLACK)
        all_sprites.draw(screen)

        score_text = font.render(f"Score: {score}", True, WHITE)
        lives_text = font.render(f"Lives: {lives}", True, WHITE)
        screen.blit(score_text, (10, 10))
        screen.blit(lives_text, (SCREEN_WIDTH - lives_text.get_width() - 10, 10))

        pygame.display.flip()


if __name__ == "__main__":
    main()
