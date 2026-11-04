"""Pack generated PNGs into macOS ICNS and, optionally, Windows ICO."""
from pathlib import Path
import struct
import sys

source, dest = map(Path, sys.argv[1:3])
renditions = {
    b'icp4':'16x16', b'icp5':'32x32', b'icp6':'32x32@2x',
    b'ic07':'128x128', b'ic08':'256x256', b'ic09':'512x512', b'ic10':'512x512@2x',
    b'ic11':'16x16@2x', b'ic12':'32x32@2x', b'ic13':'128x128@2x', b'ic14':'256x256@2x',
}
def chunk(kind,data):
    return struct.pack('>4sI',kind,len(data)+8)+data

dest.write_bytes(chunk(b'icns',b''.join(chunk(kind,(source/f'icon_{name}.png').read_bytes()) for kind,name in renditions.items())))

if len(sys.argv) > 3:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [(source/f'icon_{size}x{size}.png').read_bytes() for size in sizes]
    offset = 6 + 16*len(images)
    entries = []
    for size, image in zip(sizes, images):
        edge = size % 256
        entries.append(struct.pack('<BBBBHHII', edge, edge, 0, 0, 1, 32, len(image), offset))
        offset += len(image)
    header = struct.pack('<HHH', 0, 1, len(images))
    Path(sys.argv[3]).write_bytes(header + b''.join(entries) + b''.join(images))
