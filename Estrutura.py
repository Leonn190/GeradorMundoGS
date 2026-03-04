import math
from dataclasses import dataclass

# Tamanho lógico do mundo em blocos (mundo em loop/toroidal)
# +25% em relação ao tamanho anterior (2048)
WORLD_WIDTH = 2560
WORLD_HEIGHT = 2560

# Estrutura de chunks
CHUNK_SIZE = 32  # blocos por chunk
BLOCK_SIZE = 32  # pixels por bloco (zoom padrão)

# Cores base por altura
HEIGHT_COLORS = {
    0: (18, 53, 98),    # oceano (água funda escura)
    1: (64, 128, 191),  # água rasa
    2: (204, 183, 124), # areia/transição
    3: (76, 150, 72),   # solo
}


@dataclass(frozen=True)
class ChunkCoord:
    x: int
    y: int


class GeradorMundo:
    """
    Gera um mundo 2D em loop usando seed e chunks.

    O mapa base entrega apenas 4 alturas:
        0 = oceano
        1 = água rasa
        2 = areia
        3 = solo
    """

    def __init__(self, seed: int = 12345):
        self.seed = int(seed)
        self._chunk_cache: dict[ChunkCoord, list[list[int]]] = {}

    def _loop_x(self, x: int) -> int:
        return x % WORLD_WIDTH

    def _loop_y(self, y: int) -> int:
        return y % WORLD_HEIGHT

    def _hash2d(self, x: int, y: int) -> int:
        """Hash determinístico 2D rápido para geração procedural sem libs externas."""
        n = x * 374761393 + y * 668265263 + self.seed * 1442695040888963407
        n = (n ^ (n >> 13)) * 1274126177
        n = n ^ (n >> 16)
        return n & 0xFFFFFFFF

    def _value_noise(self, x: float, y: float) -> float:
        """Value noise contínuo via interpolação bilinear de hashes de grade."""
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

        # smoothstep para transição suave
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

    def _height_value(self, world_x: int, world_y: int) -> int:
        """
        Calcula altura discreta [0..3] com tendência continental + hidrologia leve.

        Objetivo visual:
        - maior parte do mapa em oceano (0) e solo (3)
        - água rasa (1) e praia (2) apenas como transições finas
        - presença de lagos e rios rasos
        """
        lx = self._loop_x(world_x)
        ly = self._loop_y(world_y)

        # coordenadas normalizadas [0,1]
        nx = lx / WORLD_WIDTH
        ny = ly / WORLD_HEIGHT

        # dobra para formato toroidal mais contínuo visualmente
        tx = 0.5 - abs(nx - 0.5)
        ty = 0.5 - abs(ny - 0.5)

        # massa continental larga
        continent = self._fbm(tx * 3.0, ty * 3.0, octaves=5, lacunarity=2.0, gain=0.55)

        # detalhe de costa, baías e recortes
        coast_detail = self._fbm(nx * 14.0, ny * 14.0, octaves=4, lacunarity=2.2, gain=0.5)

        # "correntes" suaves para gerar orlas mais orgânicas
        wave = (
            math.sin((nx * 2.0 + coast_detail * 0.8) * math.tau)
            + math.cos((ny * 1.6 - continent * 0.7) * math.tau)
        ) * 0.08

        v = 0.70 * continent + 0.23 * coast_detail + wave

        # rios: máscara baseada em "faixas" de ruído
        # abs(noise - 0.5) pequeno => no canal do rio
        river_noise = self._fbm(nx * 42.0 + 11.7, ny * 42.0 - 3.1, octaves=3, lacunarity=2.1, gain=0.52)
        river_band = abs(river_noise - 0.5)
        # faixa mais larga para rios mais grossos visualmente
        river_strength = max(0.0, 1.0 - (river_band / 0.042))

        # lagos: bacias esparsas em área continental
        lake_noise = self._fbm(nx * 8.5 - 19.4, ny * 8.5 + 7.9, octaves=4, lacunarity=2.0, gain=0.5)
        lake_strength = max(0.0, (0.42 - lake_noise) / 0.08)

        # rios e lagos atuam principalmente sobre terreno emergido
        land_factor = max(0.0, min(1.0, (v - 0.53) / 0.16))
        water_cut = 0.25 * river_strength * land_factor + 0.13 * lake_strength * land_factor

        # borda oceânica: força oceano puro nas extremidades de forma suave,
        # evitando costura aparente quando o mundo "dá a volta".
        edge_dist = min(nx, 1.0 - nx, ny, 1.0 - ny)
        coast_band = 0.12
        edge_factor = max(0.0, min(1.0, (coast_band - edge_dist) / coast_band))
        edge_factor = edge_factor * edge_factor * (3.0 - 2.0 * edge_factor)
        water_cut += 0.42 * edge_factor
        v -= water_cut

        # thresholds: transições (1 e 2) mais finas
        if v < 0.49:
            return 0
        if v < 0.515:
            return 1
        if v < 0.535:
            return 2
        return 3

    def get_chunk(self, chunk_x: int, chunk_y: int) -> list[list[int]]:
        cc = ChunkCoord(chunk_x % (WORLD_WIDTH // CHUNK_SIZE), chunk_y % (WORLD_HEIGHT // CHUNK_SIZE))
        if cc in self._chunk_cache:
            return self._chunk_cache[cc]

        start_x = cc.x * CHUNK_SIZE
        start_y = cc.y * CHUNK_SIZE

        data: list[list[int]] = []
        for local_y in range(CHUNK_SIZE):
            row: list[int] = []
            for local_x in range(CHUNK_SIZE):
                world_x = start_x + local_x
                world_y = start_y + local_y
                row.append(self._height_value(world_x, world_y))
            data.append(row)

        self._chunk_cache[cc] = data
        return data

    def get_height(self, world_x: int, world_y: int) -> int:
        lx = self._loop_x(world_x)
        ly = self._loop_y(world_y)
        chunk_x = lx // CHUNK_SIZE
        chunk_y = ly // CHUNK_SIZE
        local_x = lx % CHUNK_SIZE
        local_y = ly % CHUNK_SIZE
        return self.get_chunk(chunk_x, chunk_y)[local_y][local_x]
