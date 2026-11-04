"""Pack the generated PNG renditions into a macOS ICNS container."""
from pathlib import Path
import struct
import sys

source, dest = map(Path, sys.argv[1:])
renditions = {
    b'icp4':'16x16', b'icp5':'32x32', b'icp6':'32x32@2x',
    b'ic07':'128x128', b'ic08':'256x256', b'ic09':'512x512', b'ic10':'512x512@2x',
    b'ic11':'16x16@2x', b'ic12':'32x32@2x', b'ic13':'128x128@2x', b'ic14':'256x256@2x',
}
def chunk(kind,data):
    return struct.pack('>4sI',kind,len(data)+8)+data

dest.write_bytes(chunk(b'icns',b''.join(chunk(kind,(source/f'icon_{name}.png').read_bytes()) for kind,name in renditions.items())))
