import struct
from pathlib import Path

import matplotlib.pyplot as plt
from PIL import Image
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

root = Path(r"C:\Users\PC\forma-workspace\a78a885c-10fa-48b4-a0df-6927321f00e2")
assets = Path(__file__).parent
raw = (root / "cad" / "outputs" / "assembly.stl").read_bytes()
count = struct.unpack_from("<I", raw, 80)[0]
triangles = []
for index in range(count):
    offset = 84 + index * 50 + 12
    triangles.append([struct.unpack_from("<fff", raw, offset + point * 12) for point in range(3)])
points = [point for triangle in triangles for point in triangle]
xs, ys, zs = zip(*points)
frames = []
for angle in range(0, 360, 5):
    fig = plt.figure(figsize=(8, 6), dpi=120)
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor("#11151a")
    fig.patch.set_facecolor("#11151a")
    ax.add_collection3d(Poly3DCollection(triangles, facecolor="#6f7782", edgecolor="#9da4ac", linewidth=0.08))
    ax.set_xlim(min(xs) - 8, max(xs) + 8)
    ax.set_ylim(min(ys) - 8, max(ys) + 8)
    ax.set_zlim(min(zs) - 8, max(zs) + 8)
    ax.set_box_aspect((max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)))
    ax.view_init(elev=88, azim=angle)
    ax.set_axis_off()
    fig.tight_layout(pad=0)
    frame_path = assets / f".frame-{angle:03d}.png"
    fig.savefig(frame_path, facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    frames.append(Image.open(frame_path).convert("RGB"))
frames[0].save(assets / "04-step-rotation.gif", save_all=True, append_images=frames[1:], duration=55, loop=0, optimize=False)
for frame in frames:
    frame.close()
for frame_path in assets.glob(".frame-*.png"):
    frame_path.unlink()
print({"stl_triangles": count, "frames": len(frames)})
