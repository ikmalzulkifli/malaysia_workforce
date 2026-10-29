"""Derive PWA sizes from approved artwork; no logo redrawing or vendor source edits."""

import hashlib
import json
import re
from pathlib import Path

from PIL import Image


def build_assets(hrms_frontend: Path) -> None:
	public = Path(__file__).parent / "public"
	artwork = public / "images" / "ocean6"
	output = artwork / "pwa"
	output.mkdir(exist_ok=True)
	icon = Image.open(artwork / "icon.png").convert("RGBA")
	logo = Image.open(artwork / "wordmark.png").convert("RGBA")
	files = []
	for size in (192, 512):
		path = output / f"icon-{size}.png"
		icon.resize((size, size), Image.Resampling.LANCZOS).save(path, optimize=True)
		files.append(path)
	# Preserve every native splash media query and its exact pixel dimensions.
	source = (hrms_frontend.parent / "hrms" / "www" / "hrms.html").read_text()
	sizes = set(re.findall(r"apple-splash-(\d+)-(\d+)\.jpg", source))
	if not sizes:
		raise RuntimeError("Unsupported HRMS splash template")
	for raw_width, raw_height in sorted(sizes):
		width, height = int(raw_width), int(raw_height)
		canvas = Image.new("RGB", (width, height), "#f2f0ea")
		mark = logo.copy()
		mark.thumbnail((int(width * 0.58), int(height * 0.22)), Image.Resampling.LANCZOS)
		canvas.paste(mark, ((width - mark.width) // 2, (height - mark.height) // 2), mark)
		path = output / f"splash-{width}x{height}.png"
		canvas.save(path, optimize=True)
		files.append(path)
	rows = [{"path": p.name, "size": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]
	(output / "asset-list.json").write_text(json.dumps(rows, indent=2) + "\n")
