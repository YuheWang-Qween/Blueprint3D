"""Embed an existing mesh and render into the literal preview template."""

import argparse
import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--sample', default='optimized-sample')
parser.add_argument('--template', type=Path, default=ROOT / 'scripts' / 'preview-fragment.html')
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
out = ROOT / 'outputs' / args.sample
fragment = args.template.read_text()
fragment = fragment.replace('__MESH_DATA__', (out / 'preview-mesh.json').read_text())
image = base64.b64encode((out / 'preview.png').read_bytes()).decode('ascii')
fragment = fragment.replace('__PREVIEW_IMAGE__', 'data:image/png;base64,' + image)
if len(fragment.encode()) >= 1_000_000:
    raise ValueError('Inline preview exceeds the 1 MB limit')
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(fragment)
print(args.output)
