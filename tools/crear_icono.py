"""DI-R1: genera `packaging/icono.ico` (marca de verificación sobre azul). Uso manual:
`docker compose run --rm dev python -m tools.crear_icono`."""

from pathlib import Path

from PIL import Image, ImageDraw

DESTINO = Path("packaging/icono.ico")
TAMANOS = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def dibujar(lado: int = 256) -> Image.Image:
    img = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, lado - 1, lado - 1), radius=lado // 5, fill=(30, 94, 168, 255))
    p = lado / 256
    marca = [(64 * p, 136 * p), (110 * p, 182 * p), (194 * p, 82 * p)]
    d.line(marca, fill=(255, 255, 255, 255), width=max(2, round(26 * p)), joint="curve")
    return img


def main() -> None:
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    dibujar().save(DESTINO, sizes=TAMANOS)
    print(f"escrito {DESTINO}")


if __name__ == "__main__":
    main()
