"""Create the small upload fixtures the browser walkthrough needs (img.png, notes.pdf, clip.mp4)."""
import os, struct, zlib
D = os.path.dirname(os.path.abspath(__file__))
def png(w=64, h=48):
    raw = b"".join(b"\x00" + bytes([(x * 4) % 256, (y * 5) % 256, 120] * 1)[:3] * 1 for y in range(h) for x in range(1))
    rows = b"".join(b"\x00" + b"".join(bytes([(x * 4) % 256, (y * 5) % 256, 120]) for x in range(w)) for y in range(h))
    c = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + c(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + c(b"IDAT", zlib.compress(rows)) + c(b"IEND", b"")
open(os.path.join(D, "img.png"), "wb").write(png())
open(os.path.join(D, "notes.pdf"), "wb").write(b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n")
# 9,407,603 bytes: the walkthrough checks the exact byte count that reaches (fake) Bunny. Header is a minimal ftyp box.
ftyp = struct.pack(">I", 24) + b"ftypisom" + struct.pack(">I", 0x200) + b"isomavc1"
open(os.path.join(D, "clip.mp4"), "wb").write(ftyp + os.urandom(9407603 - len(ftyp)))
print("fixtures written to", D)
