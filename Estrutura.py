import math
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from bioma_deserto import BIOMA_DESERTO, BLOCO_AREIA_DESERTO
from bioma_floresta import BIOMA_FLORESTA, BLOCO_GRAMA_ESCURA
from bioma_neve import BIOMA_NEVE, BLOCO_NEVE
from bioma_planicie import BIOMA_PLANICIE, BLOCO_GRAMA

# Tamanho lógico do mundo em blocos (mundo em loop/toroidal)
WORLD_WIDTH = 1600
WORLD_HEIGHT = 1600

# Estrutura de chunks
CHUNK_SIZE = 32  # blocos por chunk
BLOCK_SIZE = 32  # pixels por bloco (zoom padrão)

# IDs de bloco
BLOCO_AGUA_OCEANO = 2
BLOCO_AGUA_RASA = 3
BLOCO_AREIA_PRAIA = 4

# Cores base por bloco
BLOCK_COLORS = {
    BLOCO_GRAMA: (82, 158, 74),
    BLOCO_GRAMA_ESCURA: (42, 112, 54),
    BLOCO_AGUA_OCEANO: (18, 53, 98),
    BLOCO_AGUA_RASA: (64, 128, 191),
    BLOCO_AREIA_PRAIA: (204, 183, 124),
    BLOCO_AREIA_DESERTO: (223, 198, 102),
    BLOCO_NEVE: (236, 244, 255),
}


@dataclass(frozen=True)
class ChunkCoord:
    x: int
    y: int


class GeradorMundo:
    def __init__(self, seed: int = 12345, worker_threads: int = 2):
        self.seed = int(seed)
        self._height_chunk_cache: dict[ChunkCoord, list[list[int]]] = {}
        self._biome_chunk_cache: dict[ChunkCoord, list[list[int]]] = {}
        self._block_chunk_cache: dict[ChunkCoord, list[list[int]]] = {}
        self._cache_lock = threading.Lock()
        self._pending_block_chunks: set[ChunkCoord] = set()
        self._executor = ThreadPoolExecutor(max_workers=max(1, int(worker_threads)), thread_name_prefix="chunk")

    def _normalize_chunk(self, chunk_x: int, chunk_y: int) -> ChunkCoord:
        return ChunkCoord(chunk_x % (WORLD_WIDTH // CHUNK_SIZE), chunk_y % (WORLD_HEIGHT // CHUNK_SIZE))

    def __del__(self) -> None:
        executor = getattr(self, "_executor", None)
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)

    def _loop_x(self, x: int) -> int:
        return x % WORLD_WIDTH

    def _loop_y(self, y: int) -> int:
        return y % WORLD_HEIGHT

    def _hash2d(self, x: int, y: int) -> int:
        n = x * 374761393 + y * 668265263 + self.seed * 1442695040888963407
        n = (n ^ (n >> 13)) * 1274126177
        n = n ^ (n >> 16)
        return n & 0xFFFFFFFF

    def _value_noise(self, x: float, y: float) -> float:
        x0 = math.floor(x)
        y0 = math.floor(y)
        x1 = x0 + 1
        y1 = y0 + 1

        sx = x - x0
        sy = y - y0

        def rand01(ix: int, iy: int) -> float:
            return self._hash2d(ix, iy) / 0xFFFFFFFF

        n00 = rand01(x0, y0)
        n10 = rand01(x1, y0)
        n01 = rand01(x0, y1)
        n11 = rand01(x1, y1)

        sx_s = sx * sx * (3.0 - 2.0 * sx)
        sy_s = sy * sy * (3.0 - 2.0 * sy)

        ix0 = n00 + (n10 - n00) * sx_s
        ix1 = n01 + (n11 - n01) * sx_s
        return ix0 + (ix1 - ix0) * sy_s

    def _fbm(self, x: float, y: float, octaves: int, lacunarity: float, gain: float) -> float:
        value = 0.0
        amplitude = 1.0
        frequency = 1.0
        norm = 0.0

        for _ in range(octaves):
            value += self._value_noise(x * frequency, y * frequency) * amplitude
            norm += amplitude
            amplitude *= gain
            frequency *= lacunarity

        return value / norm if norm else 0.0

    def _biome_value(self, world_x: int, world_y: int) -> int:
        lx = self._loop_x(world_x)
        ly = self._loop_y(world_y)
        nx = lx / WORLD_WIDTH
        ny = ly / WORLD_HEIGHT

        humidity_noise = self._fbm(nx * 5.0 + 73.1, ny * 5.0 - 51.7, octaves=4, lacunarity=2.0, gain=0.52)
        temperature_noise = self._fbm(nx * 4.3 - 19.0, ny * 4.3 + 88.2, octaves=4, lacunarity=2.0, gain=0.5)

        if temperature_noise < 0.36:
            return BIOMA_NEVE
        if temperature_noise > 0.66 and humidity_noise < 0.50:
            return BIOMA_DESERTO
        if humidity_noise > 0.68:
            return BIOMA_FLORESTA
        return BIOMA_PLANICIE

    def _height_value(self, world_x: int, world_y: int, biome: int) -> int:
        lx = self._loop_x(world_x)
        ly = self._loop_y(world_y)

        nx = lx / WORLD_WIDTH
        ny = ly / WORLD_HEIGHT

        tx = 0.5 - abs(nx - 0.5)
        ty = 0.5 - abs(ny - 0.5)

        continent = self._fbm(tx * 3.0, ty * 3.0, octaves=5, lacunarity=2.0, gain=0.55)
        coast_detail = self._fbm(nx * 14.0, ny * 14.0, octaves=4, lacunarity=2.2, gain=0.5)

        wave = (
            math.sin((nx * 2.0 + coast_detail * 0.8) * math.tau)
            + math.cos((ny * 1.6 - continent * 0.7) * math.tau)
        ) * 0.08

        v = 0.70 * continent + 0.23 * coast_detail + wave

        river_noise = self._fbm(nx * 24.0 + 11.7, ny * 24.0 - 3.1, octaves=3, lacunarity=2.1, gain=0.52)
        river_band = abs(river_noise - 0.5)
        # rios mais grossos, porém menos frequentes no geral
        river_strength = max(0.0, 1.0 - (river_band / 0.052))
        river_strength = max(0.0, river_strength - 0.20)

        lake_noise = self._fbm(nx * 8.5 - 19.4, ny * 8.5 + 7.9, octaves=4, lacunarity=2.0, gain=0.5)
        lake_strength = max(0.0, (0.39 - lake_noise) / 0.07)

        land_factor = max(0.0, min(1.0, (v - 0.53) / 0.16))

        if biome == BIOMA_FLORESTA:
            river_factor = 0.11
            lake_factor = 0.05
        elif biome == BIOMA_DESERTO:
            river_factor = 0.07
            lake_factor = 0.03
        elif biome == BIOMA_NEVE:
            river_factor = 0.13
            lake_factor = 0.06
        else:
            river_factor = 0.18
            lake_factor = 0.10

        water_cut = river_factor * river_strength * land_factor + lake_factor * lake_strength * land_factor

        edge_dist = min(nx, 1.0 - nx, ny, 1.0 - ny)
        coast_band = 0.12
        edge_factor = max(0.0, min(1.0, (coast_band - edge_dist) / coast_band))
        edge_factor = edge_factor * edge_factor * (3.0 - 2.0 * edge_factor)
        water_cut += 0.42 * edge_factor
        v -= water_cut

        if v < 0.49:
            return 0
        if v < 0.515:
            return 1
        if v < 0.531:
            return 2
        return 3

    def _block_from(self, height: int, biome: int) -> int:
        if height == 0:
            return BLOCO_AGUA_OCEANO
        if height == 1:
            return BLOCO_AGUA_RASA
        if height == 2:
            return BLOCO_AREIA_PRAIA
        if biome == BIOMA_DESERTO:
            return BLOCO_AREIA_DESERTO
        if biome == BIOMA_NEVE:
            return BLOCO_NEVE
        if biome == BIOMA_FLORESTA:
            return BLOCO_GRAMA_ESCURA
        return BLOCO_GRAMA

    def _raw_block_at(self, world_x: int, world_y: int) -> int:
        biome = self._biome_value(world_x, world_y)
        height = self._height_value(world_x, world_y, biome)
        return self._block_from(height, biome)

    def _cleanup_isolated_block(self, world_x: int, world_y: int, center_block: int) -> int:
        counts: dict[int, int] = {}
        same_neighbors = 0

        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                neighbor_block = self._raw_block_at(world_x + dx, world_y + dy)
                counts[neighbor_block] = counts.get(neighbor_block, 0) + 1
                if neighbor_block == center_block:
                    same_neighbors += 1

        if same_neighbors >= 2:
            return center_block

        return max(counts.items(), key=lambda pair: pair[1])[0]

    def get_biome_chunk(self, chunk_x: int, chunk_y: int) -> list[list[int]]:
        cc = self._normalize_chunk(chunk_x, chunk_y)
        with self._cache_lock:
            if cc in self._biome_chunk_cache:
                return self._biome_chunk_cache[cc]

        start_x = cc.x * CHUNK_SIZE
        start_y = cc.y * CHUNK_SIZE
        data: list[list[int]] = []
        for local_y in range(CHUNK_SIZE):
            row: list[int] = []
            for local_x in range(CHUNK_SIZE):
                row.append(self._biome_value(start_x + local_x, start_y + local_y))
            data.append(row)

        with self._cache_lock:
            self._biome_chunk_cache[cc] = data
        return data

    def get_height_chunk(self, chunk_x: int, chunk_y: int) -> list[list[int]]:
        cc = self._normalize_chunk(chunk_x, chunk_y)
        with self._cache_lock:
            if cc in self._height_chunk_cache:
                return self._height_chunk_cache[cc]

        biome_chunk = self.get_biome_chunk(cc.x, cc.y)
        start_x = cc.x * CHUNK_SIZE
        start_y = cc.y * CHUNK_SIZE

        data: list[list[int]] = []
        for local_y in range(CHUNK_SIZE):
            row: list[int] = []
            for local_x in range(CHUNK_SIZE):
                biome = biome_chunk[local_y][local_x]
                world_x = start_x + local_x
                world_y = start_y + local_y
                row.append(self._height_value(world_x, world_y, biome))
            data.append(row)

        with self._cache_lock:
            self._height_chunk_cache[cc] = data
        return data

    def _build_block_chunk_data(self, cc: ChunkCoord) -> list[list[int]]:
        biome_chunk = self.get_biome_chunk(cc.x, cc.y)
        height_chunk = self.get_height_chunk(cc.x, cc.y)
        start_x = cc.x * CHUNK_SIZE
        start_y = cc.y * CHUNK_SIZE
        data: list[list[int]] = []

        for local_y in range(CHUNK_SIZE):
            row: list[int] = []
            for local_x in range(CHUNK_SIZE):
                center_block = self._block_from(height_chunk[local_y][local_x], biome_chunk[local_y][local_x])
                world_x = start_x + local_x
                world_y = start_y + local_y
                row.append(self._cleanup_isolated_block(world_x, world_y, center_block))
            data.append(row)
        return data

    def _generate_block_chunk_async(self, cc: ChunkCoord) -> None:
        try:
            data = self._build_block_chunk_data(cc)
            with self._cache_lock:
                self._block_chunk_cache[cc] = data
        finally:
            with self._cache_lock:
                self._pending_block_chunks.discard(cc)

    def request_block_chunk(self, chunk_x: int, chunk_y: int) -> None:
        cc = self._normalize_chunk(chunk_x, chunk_y)
        with self._cache_lock:
            if cc in self._block_chunk_cache or cc in self._pending_block_chunks:
                return
            self._pending_block_chunks.add(cc)
        self._executor.submit(self._generate_block_chunk_async, cc)

    def try_get_block_chunk(self, chunk_x: int, chunk_y: int) -> list[list[int]] | None:
        cc = self._normalize_chunk(chunk_x, chunk_y)
        with self._cache_lock:
            chunk = self._block_chunk_cache.get(cc)

        if chunk is None:
            self.request_block_chunk(cc.x, cc.y)
        return chunk

    def pending_chunk_count(self) -> int:
        with self._cache_lock:
            return len(self._pending_block_chunks)

    def get_block_chunk(self, chunk_x: int, chunk_y: int) -> list[list[int]]:
        cc = self._normalize_chunk(chunk_x, chunk_y)
        with self._cache_lock:
            if cc in self._block_chunk_cache:
                return self._block_chunk_cache[cc]

        data = self._build_block_chunk_data(cc)
        with self._cache_lock:
            self._block_chunk_cache[cc] = data
            self._pending_block_chunks.discard(cc)
        return data

    def get_chunk(self, chunk_x: int, chunk_y: int) -> list[list[int]]:
        return self.get_height_chunk(chunk_x, chunk_y)

    def get_height(self, world_x: int, world_y: int) -> int:
        lx = self._loop_x(world_x)
        ly = self._loop_y(world_y)
        chunk_x = lx // CHUNK_SIZE
        chunk_y = ly // CHUNK_SIZE
        local_x = lx % CHUNK_SIZE
        local_y = ly % CHUNK_SIZE
        return self.get_height_chunk(chunk_x, chunk_y)[local_y][local_x]

    def get_biome(self, world_x: int, world_y: int) -> int:
        lx = self._loop_x(world_x)
        ly = self._loop_y(world_y)
        chunk_x = lx // CHUNK_SIZE
        chunk_y = ly // CHUNK_SIZE
        local_x = lx % CHUNK_SIZE
        local_y = ly % CHUNK_SIZE
        return self.get_biome_chunk(chunk_x, chunk_y)[local_y][local_x]

    def get_block(self, world_x: int, world_y: int) -> int:
        lx = self._loop_x(world_x)
        ly = self._loop_y(world_y)
        chunk_x = lx // CHUNK_SIZE
        chunk_y = ly // CHUNK_SIZE
        local_x = lx % CHUNK_SIZE
        local_y = ly % CHUNK_SIZE
        return self.get_block_chunk(chunk_x, chunk_y)[local_y][local_x]


def salvar_foto_mundo(seed: int = 202604) -> Path:
    gerador = GeradorMundo(seed=seed)
    pasta_saida = Path("fotos_mapa")
    pasta_saida.mkdir(exist_ok=True)
    nome_arquivo = f"mapa_seed_{seed}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ppm"
    caminho_saida = pasta_saida / nome_arquivo

    with caminho_saida.open("wb") as arquivo:
        arquivo.write(f"P6\n{WORLD_WIDTH} {WORLD_HEIGHT}\n255\n".encode("ascii"))
        for world_y in range(WORLD_HEIGHT):
            linha = bytearray()
            for world_x in range(WORLD_WIDTH):
                bloco = gerador.get_block(world_x, world_y)
                linha.extend(BLOCK_COLORS[bloco])
            arquivo.write(linha)

    return caminho_saida


if __name__ == "__main__":
    caminho = salvar_foto_mundo()
    print(f"Foto do mundo salva em: {caminho}")
