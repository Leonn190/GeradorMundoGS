import pygame

from Estrutura import (
    BLOCK_SIZE,
    CHUNK_SIZE,
    HEIGHT_COLORS,
    WORLD_HEIGHT,
    WORLD_WIDTH,
    GeradorMundo,
)


SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60


def wrap_world(value: float, max_value: int) -> float:
    return value % max_value


def main() -> None:
    pygame.init()
    pygame.display.set_caption("Gerador de Mundos GS - Base")
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 24)

    gerador = GeradorMundo(seed=202604)

    # câmera começa no bloco (0,0)
    cam_x = 0.0
    cam_y = 0.0
    velocidade = 6.0  # blocos por segundo

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.MOUSEBUTTONDOWN:
                # esquerdo: aumenta; direito: diminui
                if event.button == 1:
                    velocidade = min(120.0, velocidade + 1.0)
                elif event.button == 3:
                    velocidade = max(1.0, velocidade - 1.0)

        keys = pygame.key.get_pressed()
        dx = 0.0
        dy = 0.0

        if keys[pygame.K_w]:
            dy -= 1.0
        if keys[pygame.K_s]:
            dy += 1.0
        if keys[pygame.K_a]:
            dx -= 1.0
        if keys[pygame.K_d]:
            dx += 1.0

        if dx != 0.0 and dy != 0.0:
            dx *= 0.7071
            dy *= 0.7071

        cam_x += dx * velocidade * dt
        cam_y += dy * velocidade * dt

        cam_x = wrap_world(cam_x, WORLD_WIDTH)
        cam_y = wrap_world(cam_y, WORLD_HEIGHT)

        screen.fill((0, 0, 0))

        # faixa visível de blocos
        blocks_x = SCREEN_WIDTH // BLOCK_SIZE + 3
        blocks_y = SCREEN_HEIGHT // BLOCK_SIZE + 3

        start_block_x = int(cam_x) - blocks_x // 2
        start_block_y = int(cam_y) - blocks_y // 2

        offset_x = -((cam_x - int(cam_x)) * BLOCK_SIZE)
        offset_y = -((cam_y - int(cam_y)) * BLOCK_SIZE)

        # desenha por chunks, lendo somente os chunks necessários
        for by in range(blocks_y):
            world_y = start_block_y + by
            draw_y = int(by * BLOCK_SIZE + offset_y)

            for bx in range(blocks_x):
                world_x = start_block_x + bx
                draw_x = int(bx * BLOCK_SIZE + offset_x)

                wrapped_x = world_x % WORLD_WIDTH
                wrapped_y = world_y % WORLD_HEIGHT

                chunk_x = wrapped_x // CHUNK_SIZE
                chunk_y = wrapped_y // CHUNK_SIZE
                local_x = wrapped_x % CHUNK_SIZE
                local_y = wrapped_y % CHUNK_SIZE

                chunk = gerador.get_chunk(chunk_x, chunk_y)
                h = chunk[local_y][local_x]
                color = HEIGHT_COLORS[h]

                pygame.draw.rect(screen, color, (draw_x, draw_y, BLOCK_SIZE, BLOCK_SIZE))

        info = f"Bloco: ({int(cam_x)}, {int(cam_y)}) | Velocidade: {velocidade:.1f} blocos/s"
        text = font.render(info, True, (255, 255, 255))
        text_rect = text.get_rect(topright=(SCREEN_WIDTH - 16, 12))

        # fundo semitransparente da HUD
        hud = pygame.Surface((text_rect.width + 16, text_rect.height + 8), pygame.SRCALPHA)
        hud.fill((0, 0, 0, 130))
        screen.blit(hud, (text_rect.left - 8, text_rect.top - 4))
        screen.blit(text, text_rect)

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
