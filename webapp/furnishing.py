"""Owner-scoped furnishing documents and the same parametric parts used by the viewer.

Coordinates are meters in the original GLB frame: X right, Y up, Z toward the
bottom of the plan. A positive furniture angle turns clockwise in the 2D plan.
"""
import json
import math
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

STATIC = Path(__file__).parent / 'static'
CATALOG = {item['id']: item for item in json.loads((STATIC / 'furniture-catalog.json').read_text())}
MATERIALS = json.loads((STATIC / 'material-profiles.json').read_text())
PRIMITIVES = json.loads((STATIC / 'furniture-geometry.json').read_text())
FLOORS = {'original': None, 'oak': '#c8ad82', 'tile': '#deded3', 'stone': '#abb9c1'}
WALLS = {'original': None, 'ivory': '#eee9dc', 'white': '#f4f5ef', 'sage': '#cbd4c4'}


class Furniture(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    type: str
    x: float = Field(ge=-2000, le=2000, allow_inf_nan=False)
    z: float = Field(ge=-2000, le=2000, allow_inf_nan=False)
    width: float = Field(ge=.1, le=8, allow_inf_nan=False)
    depth: float = Field(ge=.1, le=8, allow_inf_nan=False)
    height: float = Field(ge=.05, le=4.5, allow_inf_nan=False)
    rotation: float = Field(ge=0, lt=360, allow_inf_nan=False)
    color: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')
    variant: str = 'standard'
    material: str = 'default'

    @model_validator(mode='after')
    def known_type(self):
        if self.type not in CATALOG:
            raise ValueError('未知设施类型')
        definition = CATALOG[self.type]
        if self.variant not in ['standard'] + [v['id'] for v in definition.get('variants', [])]:
            raise ValueError('该家具不支持这个款式')
        if self.material not in ['default'] + definition.get('materials', []):
            raise ValueError('该家具不支持这个材质')
        return self


class Finishes(BaseModel):
    model_config = ConfigDict(extra='forbid')
    floor: Literal['original', 'oak', 'tile', 'stone'] = 'original'
    wall: Literal['original', 'ivory', 'white', 'sage'] = 'original'


class Layout(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: Literal[1] = 1
    revision: int = Field(default=0, ge=0)
    items: list[Furniture] = Field(default_factory=list, max_length=200)
    finishes: Finishes = Field(default_factory=Finishes)

    @model_validator(mode='after')
    def unique_ids(self):
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError('设施编号重复')
        return self


def validate_bounds(layout, directory):
    """Reject off-model coordinates without pretending to validate room clearances."""
    meshes = json.loads((directory / 'mesh.json').read_text())
    points = [p for mesh in meshes for p in zip(*[iter(mesh['positions'])] * 3)]
    xmin, xmax = min(p[0] for p in points), max(p[0] for p in points)
    zmin, zmax = min(-p[1] for p in points), max(-p[1] for p in points)
    for item in layout.items:
        angle = math.radians(item.rotation)
        rx = (abs(math.cos(angle)) * item.width + abs(math.sin(angle)) * item.depth) / 2
        rz = (abs(math.sin(angle)) * item.width + abs(math.cos(angle)) * item.depth) / 2
        if (item.x - rx < xmin - .002 or item.x + rx > xmax + .002 or
                item.z - rz < zmin - .002 or item.z + rz > zmax + .002):
            raise ValueError('设施超出户型范围，请缩小尺寸或移回图内。')


def export_glb(directory, layout):
    """Export an independent furnished scene; leave the generated shell untouched."""
    import numpy as np
    import trimesh
    from PIL import Image

    scene = trimesh.load(directory / 'model.glb', force='scene')

    def material(color, profile='default', uv=None):
        rgba = [int(color[i:i + 2], 16) for i in (1, 3, 5)] + [255]
        config = MATERIALS[profile]
        texture = None
        if config['texture'] and uv is not None:
            uv = uv * config.get('repeat', 1)
            with Image.open(STATIC / 'materials' / config['texture']) as source:
                texture = source.copy()
        return trimesh.visual.TextureVisuals(uv=uv, material=trimesh.visual.material.PBRMaterial(
            baseColorFactor=rgba, baseColorTexture=texture, metallicFactor=config['metalness'],
            roughnessFactor=config['roughness'], doubleSided=True))

    for name, mesh in scene.geometry.items():
        kind = 'floor' if name.startswith('floor') else 'wall' if name.startswith('wall') else None
        color = (FLOORS if kind == 'floor' else WALLS).get(layout['finishes'].get(kind)) if kind else None
        if color:
            mesh.visual = material(color)
    for item in layout['items']:
        scale = np.array([item['width'], item['height'], item['depth']])
        # Right-handed rotation about Y is opposite the plan's clockwise angle.
        transform = trimesh.transformations.rotation_matrix(-math.radians(item['rotation']), [0, 1, 0])
        transform[:3, 3] = [item['x'], 0, item['z']]
        definition = CATALOG[item['type']]
        variant = next((v for v in definition.get('variants', []) if v['id'] == item.get('variant')), None)
        for index, part in enumerate(variant['parts'] if variant else definition['parts']):
            size = np.asarray(part['size']) * scale
            primitive = PRIMITIVES[part['shape']]
            vertices = np.asarray(primitive['positions'], dtype=float).reshape(-1, 3)
            uv = np.asarray(primitive['uvs'], dtype=float).reshape(-1, 2)
            normals = np.asarray(primitive['normals']).reshape(-1, 3) / size
            normals /= np.linalg.norm(normals, axis=1)[:, None]
            mesh = trimesh.Trimesh(vertices=vertices * size, faces=np.arange(len(vertices)).reshape(-1, 3),
                                   vertex_normals=normals, process=False)
            mesh.apply_translation(np.asarray(part['position']) * scale)
            mesh.apply_transform(transform)
            body = part['color'] == 'body'
            mesh.visual = material(item['color'] if body else part['color'],
                                   item.get('material', 'default') if body else 'default', uv)
            name = f"furniture_{item['id']}_{index}"
            scene.add_geometry(mesh, node_name=name, geom_name=name)
    return scene.export(file_type='glb')
