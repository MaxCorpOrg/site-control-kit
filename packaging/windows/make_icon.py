from __future__ import annotations

import struct
from pathlib import Path


def _bmp_payload(size: int) -> bytes:
    width = height = size
    xor_stride = width * 4
    and_stride = ((width + 31) // 32) * 4
    header = struct.pack(
        "<IIIHHIIIIII",
        40,
        width,
        height * 2,
        1,
        32,
        0,
        xor_stride * height + and_stride * height,
        0,
        0,
        0,
        0,
    )
    pixels = bytearray()
    for y in range(height - 1, -1, -1):
        for x in range(width):
            cx = (x + 0.5) / width
            cy = (y + 0.5) / height
            dx = cx - 0.5
            dy = cy - 0.5
            radius = (dx * dx + dy * dy) ** 0.5
            if radius > 0.48:
                pixels.extend((0, 0, 0, 0))
                continue
            blue = int(210 - 80 * cy)
            green = int(190 + 45 * (1 - radius))
            red = int(36 + 20 * cx)
            alpha = 255
            if 0.23 < cy < 0.75 and abs(dx) < 0.12:
                red, green, blue = 255, 255, 255
            if 0.42 < cy < 0.54 and -0.29 < dx < 0.25:
                red, green, blue = 255, 255, 255
            pixels.extend((blue, green, red, alpha))
    mask = bytes(and_stride * height)
    return header + bytes(pixels) + mask


def write_icon(path: Path, sizes: tuple[int, ...] = (16, 32, 48, 256)) -> Path:
    images = [_bmp_payload(size) for size in sizes]
    header_size = 6 + 16 * len(images)
    offset = header_size
    entries = []
    for size, image in zip(sizes, images):
        entries.append(
            struct.pack(
                "<BBBBHHII",
                0 if size >= 256 else size,
                0 if size >= 256 else size,
                0,
                0,
                1,
                32,
                len(image),
                offset,
            )
        )
        offset += len(image)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack("<HHH", 0, 1, len(images)) + b"".join(entries) + b"".join(images))
    return path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate Telegram Control Center .ico without external dependencies.")
    parser.add_argument("output")
    args = parser.parse_args()
    print(write_icon(Path(args.output)))
