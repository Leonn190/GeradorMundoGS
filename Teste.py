import pygame

from Estrutura import (
    BLOCK_SIZE,
    CHUNK_SIZE,
    HEIGHT_COLORS,
    WORLD_HEIGHT,
    WORLD_WIDTH,
    GeradorMundo,
)


SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
FPS = 180
MIN_BLOCK_SIZE = 8
MAX_BLOCK_SIZE = 56
ZOOM_STEP = 4


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
    block_size = float(BLOCK_SIZE)

    minimapa_ativo = False
    minimapa_surface = None
    minimapa_rect = None

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN and event.key == pygame.K_m:
                minimapa_ativo = not minimapa_ativo

            if event.type == pygame.MOUSEBUTTONDOWN and not minimapa_ativo:
                # roda do mouse controla zoom
                if event.button == 4:
                    block_size = min(MAX_BLOCK_SIZE, block_size + ZOOM_STEP)
                elif event.button == 5:
                    block_size = max(MIN_BLOCK_SIZE, block_size - ZOOM_STEP)

        keys = pygame.key.get_pressed()
        dx = 0.0
        dy = 0.0

        if not minimapa_ativo:
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

            if keys[pygame.K_q]:
                block_size = max(MIN_BLOCK_SIZE, block_size - ZOOM_STEP * dt * 12)
            if keys[pygame.K_e]:
                block_size = min(MAX_BLOCK_SIZE, block_size + ZOOM_STEP * dt * 12)
            if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
                velocidade = min(160.0, velocidade + 30.0 * dt)
            if keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL]:
                velocidade = max(1.0, velocidade - 30.0 * dt)

            cam_x += dx * velocidade * dt
            cam_y += dy * velocidade * dt

            cam_x = wrap_world(cam_x, WORLD_WIDTH)
            cam_y = wrap_world(cam_y, WORLD_HEIGHT)

        screen.fill((0, 0, 0))

        # faixa visível de blocos
        current_block_size = max(MIN_BLOCK_SIZE, min(MAX_BLOCK_SIZE, int(round(block_size))))

        if minimapa_ativo:
            if minimapa_surface is None or minimapa_rect is None:
                mini_block = max(1, min(SCREEN_WIDTH // WORLD_WIDTH, SCREEN_HEIGHT // WORLD_HEIGHT))
                map_draw_w = WORLD_WIDTH * mini_block
                map_draw_h = WORLD_HEIGHT * mini_block
                minimapa_surface = pygame.Surface((map_draw_w, map_draw_h))

                for world_y in range(WORLD_HEIGHT):
                    draw_y = world_y * mini_block
                    for world_x in range(WORLD_WIDTH):
                        draw_x = world_x * mini_block
                        h = gerador.get_height(world_x, world_y)
                        color = HEIGHT_COLORS[h]
                        pygame.draw.rect(minimapa_surface, color, (draw_x, draw_y, mini_block, mini_block))

                map_off_x = (SCREEN_WIDTH - map_draw_w) // 2
                map_off_y = (SCREEN_HEIGHT - map_draw_h) // 2
                minimapa_rect = pygame.Rect(map_off_x, map_off_y, map_draw_w, map_draw_h)

            screen.blit(minimapa_surface, minimapa_rect.topleft)
            mini_block = max(1, minimapa_rect.width // WORLD_WIDTH)
            player_x = minimapa_rect.left + int(cam_x) * mini_block
            player_y = minimapa_rect.top + int(cam_y) * mini_block
            pygame.draw.rect(screen, (255, 255, 255), (player_x, player_y, max(2, mini_block), max(2, mini_block)))
        else:
            blocks_x = SCREEN_WIDTH // current_block_size + 3
            blocks_y = SCREEN_HEIGHT // current_block_size + 3

            start_block_x = int(cam_x) - blocks_x // 2
            start_block_y = int(cam_y) - blocks_y // 2

            offset_x = -((cam_x - int(cam_x)) * current_block_size)
            offset_y = -((cam_y - int(cam_y)) * current_block_size)

            # desenha por chunks, lendo somente os chunks necessários
            for by in range(blocks_y):
                world_y = start_block_y + by
                draw_y = int(by * current_block_size + offset_y)

                for bx in range(blocks_x):
                    world_x = start_block_x + bx
                    draw_x = int(bx * current_block_size + offset_x)

                    wrapped_x = world_x % WORLD_WIDTH
                    wrapped_y = world_y % WORLD_HEIGHT

                    chunk_x = wrapped_x // CHUNK_SIZE
                    chunk_y = wrapped_y // CHUNK_SIZE
                    local_x = wrapped_x % CHUNK_SIZE
                    local_y = wrapped_y % CHUNK_SIZE

                    chunk = gerador.get_chunk(chunk_x, chunk_y)
                    h = chunk[local_y][local_x]
                    color = HEIGHT_COLORS[h]

                    pygame.draw.rect(screen, color, (draw_x, draw_y, current_block_size, current_block_size))

        fps_real = clock.get_fps()
        modo = "MINIMAPA" if minimapa_ativo else "MUNDO"
        info = (
            f"Modo: {modo} (M alterna) | Bloco: ({int(cam_x)}, {int(cam_y)}) | Vel: {velocidade:.1f} blocos/s | "
            f"Zoom: {current_block_size}px | FPS: {fps_real:5.1f}/{FPS}"
        )
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
