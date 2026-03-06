import math
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# Tamanho lógico do mundo em blocos (mundo em loop/toroidal)
WORLD_WIDTH = 3200
WORLD_HEIGHT = 3200

# Estrutura de chunks
CHUNK_SIZE = 32  # blocos por chunk
BLOCK_SIZE = 32  # pixels por bloco (zoom padrão)

# Biomas centralizados (sem arquivos separados)
BIOMAS = {
    "planicie": {"id": 0, "nome": "Planicie"},
    "floresta": {"id": 1, "nome": "Floresta"},
    "deserto": {"id": 2, "nome": "Deserto"},
    "neve": {"id": 3, "nome": "Neve"},
    "vulcanico": {"id": 4, "nome": "Vulcanico"},
    "magico": {"id": 5, "nome": "Magico"},
}

BIOMA_PLANICIE = BIOMAS["planicie"]["id"]
BIOMA_FLORESTA = BIOMAS["floresta"]["id"]
BIOMA_DESERTO = BIOMAS["deserto"]["id"]
BIOMA_NEVE = BIOMAS["neve"]["id"]
BIOMA_VULCANICO = BIOMAS["vulcanico"]["id"]
BIOMA_MAGICO = BIOMAS["magico"]["id"]

# IDs de bloco
BLOCO_GRAMA = 0
BLOCO_GRAMA_ESCURA = 1
BLOCO_AGUA_OCEANO = 2
BLOCO_AGUA_RASA = 3
BLOCO_AREIA_PRAIA = 4
BLOCO_AREIA_DESERTO = 5
BLOCO_NEVE = 6
BLOCO_PEDRA_VULCANICA_MARROM = 7
BLOCO_MATO_MAGICO_ROXO = 8

# Cores base por bloco
BLOCK_COLORS = {
    BLOCO_GRAMA: (82, 158, 74),
    BLOCO_GRAMA_ESCURA: (42, 112, 54),
    BLOCO_AGUA_OCEANO: (18, 53, 98),
    BLOCO_AGUA_RASA: (64, 128, 191),
    BLOCO_AREIA_PRAIA: (204, 183, 124),
    BLOCO_AREIA_DESERTO: (223, 198, 102),
    BLOCO_NEVE: (236, 244, 255),
    BLOCO_PEDRA_VULCANICA_MARROM: (101, 64, 38),
    BLOCO_MATO_MAGICO_ROXO: (138, 88, 188),
}

# Objetos naturais com raridade, separação mínima e restrição de bioma
OBJETOS_NATURAIS = {
    "nada": {"id": 0, "raridade": 0.66, "separacao_minima": 0, "biomas": "todos"},
    "arvore": {"id": 1, "raridade": 0.08, "separacao_minima": 2, "biomas": ["planicie", "floresta", "magico"]},
    "pedra": {"id": 2, "raridade": 0.08, "separacao_minima": 1, "biomas": "todos"},
    "arbusto": {"id": 3, "raridade": 0.06, "separacao_minima": 1, "biomas": ["planicie", "floresta", "deserto", "magico"]},
    "ouro": {"id": 4, "raridade": 0.015, "separacao_minima": 3, "biomas": "todos"},
    "ametista": {"id": 5, "raridade": 0.010, "separacao_minima": 4, "biomas": ["magico"]},
    "diamante": {"id": 6, "raridade": 0.010, "separacao_minima": 4, "biomas": ["neve"]},
    "rubi": {"id": 7, "raridade": 0.010, "separacao_minima": 4, "biomas": ["vulcanico"]},
    "esmeralda": {"id": 8, "raridade": 0.010, "separacao_minima": 4, "biomas": ["deserto"]},
    "palmeira": {"id": 9, "raridade": 0.025, "separacao_minima": 3, "biomas": ["deserto"]},
    "pinheiro": {"id": 10, "raridade": 0.025, "separacao_minima": 3, "biomas": ["neve"]},
    "cobre": {"id": 11, "raridade": 0.020, "separacao_minima": 2, "biomas": "todos"},
    "poca_de_lava": {"id": 12, "raridade": 0.015, "separacao_minima": 5, "biomas": ["vulcanico"]},
}

NOME_OBJETO_POR_ID = {dados["id"]: nome for nome, dados in OBJETOS_NATURAIS.items()}
NOME_BIOMA_POR_ID = {dados["id"]: nome for nome, dados in BIOMAS.items()}


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
        self._object_chunk_cache: dict[ChunkCoord, list[list[int]]] = {}
        self._cache_lock = threading.Lock()
        self._pending_block_chunks: set[ChunkCoord] = set()
        self._pending_object_chunks: set[ChunkCoord] = set()
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

    def _hash2d(self, x: int, y: int, salt: int = 0) -> int:
        n = x * 374761393 + y * 668265263 + self.seed * 1442695040888963407 + salt * 1013904223
        n = (n ^ (n >> 13)) * 1274126177
        n = n ^ (n >> 16)
        return n & 0xFFFFFFFF

    def _value_noise(self, x: float, y: float, salt: int = 0) -> float:
        x0 = math.floor(x)
        y0 = math.floor(y)
        x1 = x0 + 1
        y1 = y0 + 1

        sx = x - x0
        sy = y - y0

        def rand01(ix: int, iy: int) -> float:
            return self._hash2d(ix, iy, salt=salt) / 0xFFFFFFFF

        n00 = rand01(x0, y0)
        n10 = rand01(x1, y0)
        n01 = rand01(x0, y1)
        n11 = rand01(x1, y1)

        sx_s = sx * sx * (3.0 - 2.0 * sx)
        sy_s = sy * sy * (3.0 - 2.0 * sy)

        ix0 = n00 + (n10 - n00) * sx_s
        ix1 = n01 + (n11 - n01) * sx_s
        return ix0 + (ix1 - ix0) * sy_s

    def _fbm(self, x: float, y: float, octaves: int, lacunarity: float, gain: float, salt: int = 0) -> float:
        value = 0.0
        amplitude = 1.0
        frequency = 1.0
        norm = 0.0

        for _ in range(octaves):
            value += self._value_noise(x * frequency, y * frequency, salt=salt) * amplitude
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
        volcanic_noise = self._fbm(nx * 13.0 + 14.5, ny * 13.0 - 34.0, octaves=3, lacunarity=2.1, gain=0.48, salt=31)
        magic_noise = self._fbm(nx * 12.0 - 99.0, ny * 12.0 + 3.0, octaves=3, lacunarity=2.1, gain=0.48, salt=67)

        # biomas raros e pequenos
        if volcanic_noise > 0.83 and temperature_noise > 0.58:
            return BIOMA_VULCANICO
        if magic_noise > 0.84 and humidity_noise > 0.56:
            return BIOMA_MAGICO

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
        river_strength = max(0.0, 1.0 - (river_band / 0.052))
        river_strength = max(0.0, river_strength - 0.20)

        lake_noise = self._fbm(nx * 8.5 - 19.4, ny * 8.5 + 7.9, octaves=4, lacunarity=2.0, gain=0.5)
        lake_strength = max(0.0, (0.39 - lake_noise) / 0.07)

        land_factor = max(0.0, min(1.0, (v - 0.53) / 0.16))

        if biome == BIOMA_FLORESTA:
            river_factor, lake_factor = 0.11, 0.05
        elif biome == BIOMA_DESERTO:
            river_factor, lake_factor = 0.07, 0.03
        elif biome == BIOMA_NEVE:
            river_factor, lake_factor = 0.13, 0.06
        elif biome == BIOMA_VULCANICO:
            river_factor, lake_factor = 0.04, 0.02
        elif biome == BIOMA_MAGICO:
            river_factor, lake_factor = 0.12, 0.08
        else:
            river_factor, lake_factor = 0.18, 0.10

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
        if biome == BIOMA_VULCANICO:
            return BLOCO_PEDRA_VULCANICA_MARROM
        if biome == BIOMA_MAGICO:
            return BLOCO_MATO_MAGICO_ROXO
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

    def _biome_name(self, biome_id: int) -> str:
        return NOME_BIOMA_POR_ID.get(biome_id, "planicie")

    def _objeto_permitido_no_bioma(self, objeto_nome: str, biome_name: str) -> bool:
        biomas = OBJETOS_NATURAIS[objeto_nome]["biomas"]
        return biomas == "todos" or biome_name in biomas

    def _escolher_objeto_base(self, world_x: int, world_y: int, biome_name: str) -> tuple[str, int]:
        valor = self._hash2d(world_x, world_y, salt=911) / 0xFFFFFFFF
        cumulativo = 0.0
        candidatos = []
        for nome, dados in OBJETOS_NATURAIS.items():
            if nome == "nada":
                continue
            if self._objeto_permitido_no_bioma(nome, biome_name):
                candidatos.append((nome, dados))

        candidatos.sort(key=lambda item: item[1]["id"])

        for nome, dados in candidatos:
            cumulativo += dados["raridade"]
            if valor <= cumulativo:
                return nome, dados["id"]
        return "nada", OBJETOS_NATURAIS["nada"]["id"]

    def _respeita_separacao_objeto(self, world_x: int, world_y: int, objeto_nome: str, objeto_id: int, biome_name: str) -> bool:
        separacao = OBJETOS_NATURAIS[objeto_nome]["separacao_minima"]
        if separacao <= 0:
            return True

        for dy in range(-separacao, separacao + 1):
            for dx in range(-separacao, separacao + 1):
                if dx == 0 and dy == 0:
                    continue
                if max(abs(dx), abs(dy)) > separacao:
                    continue
                nx = self._loop_x(world_x + dx)
                ny = self._loop_y(world_y + dy)
                vizinho_bioma_nome = self._biome_name(self._biome_value(nx, ny))
                _, vizinho_id = self._escolher_objeto_base(nx, ny, vizinho_bioma_nome)
                if vizinho_id == objeto_id:
                    return False
        return True

    def _object_at(self, world_x: int, world_y: int) -> int:
        biome_name = self._biome_name(self._biome_value(world_x, world_y))
        objeto_nome, objeto_id = self._escolher_objeto_base(world_x, world_y, biome_name)
        if objeto_nome == "nada":
            return objeto_id
        if self._respeita_separacao_objeto(world_x, world_y, objeto_nome, objeto_id, biome_name):
            return objeto_id
        return OBJETOS_NATURAIS["nada"]["id"]

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

    def _build_object_chunk_data(self, cc: ChunkCoord) -> list[list[int]]:
        start_x = cc.x * CHUNK_SIZE
        start_y = cc.y * CHUNK_SIZE
        data: list[list[int]] = []
        for local_y in range(CHUNK_SIZE):
            row: list[int] = []
            for local_x in range(CHUNK_SIZE):
                row.append(self._object_at(start_x + local_x, start_y + local_y))
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

    def _generate_object_chunk_async(self, cc: ChunkCoord) -> None:
        try:
            data = self._build_object_chunk_data(cc)
            with self._cache_lock:
                self._object_chunk_cache[cc] = data
        finally:
            with self._cache_lock:
                self._pending_object_chunks.discard(cc)

    def request_block_chunk(self, chunk_x: int, chunk_y: int) -> None:
        cc = self._normalize_chunk(chunk_x, chunk_y)
        with self._cache_lock:
            if cc in self._block_chunk_cache or cc in self._pending_block_chunks:
                return
            self._pending_block_chunks.add(cc)
        self._executor.submit(self._generate_block_chunk_async, cc)

    def request_object_chunk(self, chunk_x: int, chunk_y: int) -> None:
        cc = self._normalize_chunk(chunk_x, chunk_y)
        with self._cache_lock:
            if cc in self._object_chunk_cache or cc in self._pending_object_chunks:
                return
            self._pending_object_chunks.add(cc)
        self._executor.submit(self._generate_object_chunk_async, cc)

    def try_get_block_chunk(self, chunk_x: int, chunk_y: int) -> list[list[int]] | None:
        cc = self._normalize_chunk(chunk_x, chunk_y)
        with self._cache_lock:
            chunk = self._block_chunk_cache.get(cc)

        if chunk is None:
            self.request_block_chunk(cc.x, cc.y)
        return chunk

    def try_get_object_chunk(self, chunk_x: int, chunk_y: int) -> list[list[int]] | None:
        cc = self._normalize_chunk(chunk_x, chunk_y)
        with self._cache_lock:
            chunk = self._object_chunk_cache.get(cc)

        if chunk is None:
            self.request_object_chunk(cc.x, cc.y)
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

    def get_object_chunk(self, chunk_x: int, chunk_y: int) -> list[list[int]]:
        cc = self._normalize_chunk(chunk_x, chunk_y)
        with self._cache_lock:
            if cc in self._object_chunk_cache:
                return self._object_chunk_cache[cc]

        data = self._build_object_chunk_data(cc)
        with self._cache_lock:
            self._object_chunk_cache[cc] = data
            self._pending_object_chunks.discard(cc)
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

    def get_object(self, world_x: int, world_y: int) -> int:
        lx = self._loop_x(world_x)
        ly = self._loop_y(world_y)
        chunk_x = lx // CHUNK_SIZE
        chunk_y = ly // CHUNK_SIZE
        local_x = lx % CHUNK_SIZE
        local_y = ly % CHUNK_SIZE
        return self.get_object_chunk(chunk_x, chunk_y)[local_y][local_x]


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
