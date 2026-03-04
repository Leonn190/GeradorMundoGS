import pygame
import threading
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from Estrutura import (
    BLOCK_SIZE,
    CHUNK_SIZE,
    BLOCK_COLORS,
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
    fallback_chunk = [[2 for _ in range(CHUNK_SIZE)] for _ in range(CHUNK_SIZE)]

    # câmera começa no bloco (0,0)
    cam_x = 0.0
    cam_y = 0.0
    velocidade = 6.0  # blocos por segundo
    block_size = float(BLOCK_SIZE)

    foto_thread = None
    foto_status = ""
    foto_lock = threading.Lock()

    def salvar_foto_mapa() -> None:
        nonlocal foto_status
        try:
            with foto_lock:
                foto_status = "Gerando foto do mapa inteiro..."

            mapa_surface = pygame.Surface((WORLD_WIDTH, WORLD_HEIGHT))
            for world_y in range(WORLD_HEIGHT):
                for world_x in range(WORLD_WIDTH):
                    bloco = gerador.get_block(world_x, world_y)
                    mapa_surface.set_at((world_x, world_y), BLOCK_COLORS[bloco])

            pasta_saida = Path("fotos_mapa")
            pasta_saida.mkdir(exist_ok=True)
            nome_arquivo = f"mapa_seed_{gerador.seed}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            caminho_saida = pasta_saida / nome_arquivo
            pygame.image.save(mapa_surface, str(caminho_saida))

            with foto_lock:
                foto_status = f"Foto salva: {caminho_saida}"
        except Exception as exc:
            with foto_lock:
                foto_status = f"Erro ao salvar foto: {exc}"

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN and event.key == pygame.K_m:
                if foto_thread is None or not foto_thread.is_alive():
                    foto_thread = threading.Thread(target=salvar_foto_mapa, daemon=True)
                    foto_thread.start()

            if event.type == pygame.MOUSEBUTTONDOWN:
                # roda do mouse controla zoom
                if event.button == 4:
                    block_size = min(MAX_BLOCK_SIZE, block_size + ZOOM_STEP)
                elif event.button == 5:
                    block_size = max(MIN_BLOCK_SIZE, block_size - ZOOM_STEP)

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

        blocks_x = SCREEN_WIDTH // current_block_size + 3
        blocks_y = SCREEN_HEIGHT // current_block_size + 3

        start_block_x = int(cam_x) - blocks_x // 2
        start_block_y = int(cam_y) - blocks_y // 2

        offset_x = -((cam_x - int(cam_x)) * current_block_size)
        offset_y = -((cam_y - int(cam_y)) * current_block_size)

        chunks_visiveis: dict[tuple[int, int], list[tuple[int, int, int, int]]] = defaultdict(list)

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

                chunks_visiveis[(chunk_x, chunk_y)].append((local_x, local_y, draw_x, draw_y))

        # pré-carrega chunks próximos em thread para reduzir travadas
        for chunk_x, chunk_y in chunks_visiveis.keys():
            gerador.request_block_chunk(chunk_x, chunk_y)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    gerador.request_block_chunk(chunk_x + dx, chunk_y + dy)

        # desenha com o que já estiver pronto sem bloquear o frame
        for (chunk_x, chunk_y), blocos in chunks_visiveis.items():
            chunk_data = gerador.try_get_block_chunk(chunk_x, chunk_y) or fallback_chunk
            for local_x, local_y, draw_x, draw_y in blocos:
                bloco = chunk_data[local_y][local_x]
                color = BLOCK_COLORS[bloco]

                pygame.draw.rect(screen, color, (draw_x, draw_y, current_block_size, current_block_size))

        fps_real = clock.get_fps()
        modo = "MUNDO"
        with foto_lock:
            status_foto = foto_status
        info = (
            f"Modo: {modo} (M salva foto do mapa) | Bloco: ({int(cam_x)}, {int(cam_y)}) | "
            f"Vel: {velocidade:.1f} blocos/s | Zoom: {current_block_size}px | FPS: {fps_real:5.1f}/{FPS} | "
            f"Chunks pendentes: {gerador.pending_chunk_count()}"
        )
        if status_foto:
            info = f"{info} | {status_foto}"
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
