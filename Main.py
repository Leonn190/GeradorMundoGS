from Estrutura import GeradorMundo


LARGURA = 32
ALTURA = 16


def main() -> None:
    gerador = GeradorMundo(seed=202604)

    print("Grid numérica de blocos (IDs):")
    for y in range(ALTURA):
        linha = [f"{gerador.get_block(x, y):02d}" for x in range(LARGURA)]
        print(" ".join(linha))

    print("\nGrid numérica de objetos naturais (IDs):")
    for y in range(ALTURA):
        linha = [f"{gerador.get_object(x, y):02d}" for x in range(LARGURA)]
        print(" ".join(linha))


if __name__ == "__main__":
    main()
