"""
Offline project templates used when the MCP server is unreachable.
They follow the Builder contract: no SysFont, no absolute paths, touch/mouse
input only, project-relative assets.
"""
from __future__ import annotations

COLOR_GAME = '''"""{title} - color guessing game (touch / mouse)."""
import random
from pathlib import Path

import pygame

BASE_DIR = Path(__file__).resolve().parent
WIDTH, HEIGHT = 480, 800
FPS = 60

COLORS = {{
    "MERAH": (231, 76, 60),
    "BIRU": (52, 152, 219),
    "HIJAU": (46, 204, 113),
    "KUNING": (241, 196, 15),
    "UNGU": (155, 89, 182),
    "ORANYE": (230, 126, 34),
}}


def new_round():
    names = random.sample(list(COLORS), 4)
    answer = random.choice(names)
    return names, answer


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.SCALED)
    pygame.display.set_caption("{title}")
    clock = pygame.time.Clock()
    # pygame's built-in default font is bundled with pygame (no host fonts).
    font_big = pygame.font.Font(None, 64)
    font = pygame.font.Font(None, 40)

    score, lives = 0, 3
    names, answer = new_round()
    buttons = [pygame.Rect(40, 380 + i * 90, WIDTH - 80, 70) for i in range(4)]
    running = True

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if lives <= 0:
                    score, lives = 0, 3
                    names, answer = new_round()
                    continue
                for rect, name in zip(buttons, names):
                    if rect.collidepoint(event.pos):
                        if name == answer:
                            score += 1
                        else:
                            lives -= 1
                        names, answer = new_round()
                        break

        screen.fill((24, 26, 33))
        title = font.render("Tebak warna kotak ini:", True, (240, 240, 240))
        screen.blit(title, title.get_rect(center=(WIDTH // 2, 60)))
        pygame.draw.rect(screen, COLORS[answer], (90, 110, WIDTH - 180, 220), border_radius=24)

        for rect, name in zip(buttons, names):
            pygame.draw.rect(screen, (60, 64, 78), rect, border_radius=16)
            label = font.render(name, True, (255, 255, 255))
            screen.blit(label, label.get_rect(center=rect.center))

        hud = font.render(f"Skor {{score}}   Nyawa {{lives}}", True, (240, 240, 240))
        screen.blit(hud, (40, HEIGHT - 70))
        if lives <= 0:
            over = font_big.render("GAME OVER", True, (231, 76, 60))
            screen.blit(over, over.get_rect(center=(WIDTH // 2, HEIGHT // 2)))
            tap = font.render("Tap untuk main lagi", True, (240, 240, 240))
            screen.blit(tap, tap.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 50)))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


if __name__ == "__main__":
    main()
'''

SKELETON = '''"""{title} - Pygame skeleton (Builder compatible)."""
from pathlib import Path

import pygame

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"   # keep every asset project-relative
WIDTH, HEIGHT = 480, 800
FPS = 60


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.SCALED)
    pygame.display.set_caption("{title}")
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 48)  # bundled default font, no SysFont

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        screen.fill((24, 26, 33))
        text = font.render("{title}", True, (240, 240, 240))
        screen.blit(text, text.get_rect(center=(WIDTH // 2, HEIGHT // 2)))
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


if __name__ == "__main__":
    main()
'''


def build_template(name: str) -> dict[str, str]:
    """Return {relative_path: content} for a starter project."""
    title = (name or "Pygame Game").strip().title()
    title = title.replace('"', "").replace("\\", "")
    tpl = COLOR_GAME if "warna" in name.lower() or "color" in name.lower() else SKELETON
    return {
        "main.py": tpl.format(title=title),
        "requirements.txt": "pygame\n",
        "assets/.gitkeep": "",
    }
