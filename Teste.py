from collections import Counter

from Estrutura import GeradorMundo, NOME_OBJETO_POR_ID


LARGURA = 32
ALTURA = 16


def imprimir_grid_blocos(gerador: GeradorMundo) -> None:
    print("Grid numérica de blocos (IDs):")
    for y in range(ALTURA):
        linha = [f"{gerador.get_block(x, y):02d}" for x in range(LARGURA)]
        print(" ".join(linha))


def imprimir_grid_objetos(gerador: GeradorMundo) -> None:
    print("\nGrid numérica de objetos naturais (IDs):")
    for y in range(ALTURA):
        linha = [f"{gerador.get_object(x, y):02d}" for x in range(LARGURA)]
        print(" ".join(linha))


def imprimir_distribuicao_objetos(gerador: GeradorMundo, tamanho: int = 128) -> None:
    contagem = Counter()
    for y in range(tamanho):
        for x in range(tamanho):
            contagem[gerador.get_object(x, y)] += 1

    print(f"\nDistribuição de objetos em grade {tamanho}x{tamanho}:")
    total = tamanho * tamanho
    for object_id, quantidade in sorted(contagem.items()):
        nome = NOME_OBJETO_POR_ID.get(object_id, f"desconhecido_{object_id}")
        percentual = (quantidade / total) * 100
        print(f"{object_id:02d} - {nome:12s}: {quantidade:5d} ({percentual:5.2f}%)")


def main() -> None:
    gerador = GeradorMundo(seed=202604)
    imprimir_grid_blocos(gerador)
    imprimir_grid_objetos(gerador)
    imprimir_distribuicao_objetos(gerador)


if __name__ == "__main__":
    main()
