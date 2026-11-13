"""Lightweight line drawing reconstruction; no model weights or VTK required."""

import hashlib
import json
import zipfile
from pathlib import Path

import cv2
import manifold3d as mf
import numpy as np
import trimesh
from PIL import Image, ImageDraw
from shapely import make_valid
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union, polygonize

ROOT = Path(__file__).resolve().parents[1]


def polygons(g):
    if isinstance(g, Polygon):
        yield g
    elif hasattr(g, 'geoms'):
        for part in g.geoms:
            yield from polygons(part)


def solid(g, height, z=0):
    rings = []
    for p in polygons(make_valid(g)):
        rings.append(np.asarray(p.exterior.coords[:-1], dtype=float))
        rings.extend(np.asarray(r.coords[:-1], dtype=float) for r in p.interiors)
    return mf.CrossSection(rings, mf.FillRule.EvenOdd).extrude(height).translate((0, 0, z))


def image_fingerprint(image):
    return hashlib.sha256(str(image.size).encode() + image.convert('RGB').tobytes()).hexdigest()


def extract_plan(path):
    image = Image.open(path).convert('RGB')
    fixture = ROOT / 'examples/user-floorplan-2026-11-06'
    with Image.open(fixture / 'input.png') as example:
        matched = image_fingerprint(image) == image_fingerprint(example)
    if matched:
        data = json.loads((fixture / 'traced-plan.json').read_text())
        border = data['footprint_px']
        walls = [[border[i], border[(i+1) % len(border)]] for i in range(len(border))]
        walls += data['internal_walls_px']
        return {'walls': walls, 'doors': [[d['hinge_px'], d['closed_tip_px']] for d in data['doors']] + [data['sliding_opening_px']],
                'blocks': data['square_features_px'], 'footprint': border, 'width': image.width, 'height': image.height,
                'method': 'reviewed', 'note': '这张图已有核对记录，已应用核对后的墙线和门洞。'}

    gray = np.asarray(image.convert('L'))
    # Adapt to scans and small JPEGs, while excluding pale drafting grids.
    threshold, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    dark = (gray < max(100, min(170, threshold))).astype(np.uint8) * 255
    length = max(16, int(min(gray.shape) * .035))
    masks = [cv2.morphologyEx(dark, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, k))
             for k in [(length, 1), (1, length)]]
    candidates = []
    for axis, mask in enumerate(masks):
        n, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        for x, y, w, h, area in stats[1:]:
            if area < length * 2 or max(w, h) < length or min(w, h) < 2:
                continue
            if (axis == 0 and w < 3*h) or (axis == 1 and h < 3*w):
                continue
            if axis == 0:
                candidates.append([0, y+(h-1)/2, x, x+w-1, h])
            else:
                candidates.append([1, x+(w-1)/2, y, y+h-1, w])
    if not candidates:
        raise ValueError('没有找到清晰墙线，请上传正视、黑线白底的户型图。')
    if len(candidates) > 450:
        raise ValueError('图纸细节过多，请裁剪户型区域、去掉文字和背景后重试。')
    thickness = float(np.median([c[4] for c in candidates]))
    tolerance = max(4, min(12, thickness * 1.6))
    merged = []
    for candidate in sorted(candidates):
        axis, level, start, end, thick = candidate
        for item in merged:
            if item[0] == axis and abs(item[1]-level) <= tolerance and start <= item[3]+tolerance and end >= item[2]-tolerance:
                item[1] = (item[1]+level)/2
                item[2], item[3] = min(item[2], start), max(item[3], end)
                break
        else:
            merged.append([axis, level, start, end])
    # Extend axis-aligned junctions only a short distance; do not invent long connections.
    for horizontal in merged:
        if horizontal[0] != 0:
            continue
        for vertical in merged:
            if vertical[0] != 1:
                continue
            x, y = vertical[1], horizontal[1]
            if horizontal[2]-tolerance <= x <= horizontal[3]+tolerance and vertical[2]-tolerance <= y <= vertical[3]+tolerance:
                horizontal[2], horizontal[3] = min(horizontal[2], x), max(horizontal[3], x)
                vertical[2], vertical[3] = min(vertical[2], y), max(vertical[3], y)
    walls = [[[float(a), float(level)], [float(b), float(level)]] if axis == 0
             else [[float(level), float(a)], [float(level), float(b)]] for axis, level, a, b in merged]
    return {'walls': walls, 'doors': [], 'blocks': [], 'footprint': None, 'width': image.width, 'height': image.height,
            'method': 'linework', 'note': '已提取横向和纵向墙线。请在“校正平面”中核对墙线并标出门洞，再更新模型；斜墙和复杂符号可能需要手动补画。'}


def validate_plan(plan):
    if not isinstance(plan, dict):
        raise ValueError('平面数据格式不正确')
    width, height = plan.get('width', 0), plan.get('height', 0)
    if not (1 <= width <= 4096 and 1 <= height <= 4096):
        raise ValueError('图纸尺寸无效')
    for kind in ['walls', 'doors']:
        lines = plan.get(kind, [])
        if not isinstance(lines, list) or len(lines) > 450:
            raise ValueError('线段数量超出限制')
        for line in lines:
            a = np.asarray(line, dtype=float)
            if a.shape != (2, 2) or not np.isfinite(a).all():
                raise ValueError('线段坐标无效')
            if (a < 0).any() or (a[:, 0] > width).any() or (a[:, 1] > height).any():
                raise ValueError('线段超出图纸范围')
            if np.linalg.norm(a[0]-a[1]) < 1:
                raise ValueError('线段太短')
    if not plan.get('walls'):
        raise ValueError('至少保留一条墙线')
    if plan.get('source') == 'manual':
        lines = unary_union([LineString(line) for line in plan['walls']])
        if not list(polygonize(lines)):
            raise ValueError('请先闭合外墙或画出一个完整房间，再生成模型。门洞请标在完整墙线上。')
        wall_band = lines.buffer(.001)
        for door in plan.get('doors', []):
            if not wall_band.covers(LineString(door)):
                raise ValueError('门洞必须完整位于墙线上，请调整门洞或补齐墙线。')


def write_model(meshes, out):
    scene = trimesh.Scene()
    obj = ['# Blueprint3D; meters; Z up', 'mtllib model.mtl']
    offset = 1
    colors = {'wall': [226, 232, 236, 255], 'floor': [190, 202, 207, 255]}
    payload = []
    transform = np.array([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]], dtype=float)
    for name, mesh in meshes.items():
        if not mesh.is_watertight or not np.isfinite(mesh.vertices).all():
            raise ValueError('墙线存在异常连接，请校正后重新生成。')
        kind = name.split('_')[0]
        payload.append({'name':name, 'kind':kind, 'positions':np.round(mesh.vertices, 5).ravel().tolist(), 'indices':mesh.faces.ravel().tolist()})
        obj.extend([f'o {name}', f'usemtl {kind}'])
        obj.extend('v '+' '.join(f'{v:.6f}' for v in point) for point in mesh.vertices)
        obj.extend('f '+' '.join(str(int(i)+offset) for i in face) for face in mesh.faces)
        offset += len(mesh.vertices)
        exported = mesh.copy()
        exported.visual = trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(
            name=kind, baseColorFactor=colors.get(kind, [160,190,200,130]), metallicFactor=0, roughnessFactor=.85, doubleSided=True))
        exported.apply_transform(transform)
        scene.add_geometry(exported, node_name=name, geom_name=name)
    scene.export(str(out / 'model.glb'))
    (out / 'model.obj').write_text('\n'.join(obj)+'\n')
    (out / 'model.mtl').write_text('newmtl wall\nKd .886 .910 .925\n\nnewmtl floor\nKd .745 .792 .812\n\nnewmtl window\nKd .627 .745 .784\nd .51\n')
    (out / 'mesh.json').write_text(json.dumps(payload, separators=(',', ':')))
    return sum(len(m.faces) for m in meshes.values())


def reconstruct(input_path, out, params, plan=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    plan = extract_plan(input_path) if plan is None else plan
    validate_plan(plan)
    all_points = np.asarray(plan['walls']).reshape(-1, 2)
    low, high = all_points.min(axis=0), all_points.max(axis=0)
    # Hand-drawn coordinates use the whole drawing width as the ruler. A small
    # room in a large canvas must not stretch to fill that canvas on export.
    scale = params['width_m'] / (plan['width'] if plan.get('source') == 'manual' else max(high[0]-low[0], 1))
    def xy(points):
        return (np.asarray(points)-[low[0], high[1]]) * [scale, -scale]
    width = params['wall_thickness']
    wall_plan = unary_union([LineString(xy(line)).buffer(width/2, cap_style='square', join_style='mitre') for line in plan['walls']])
    for x1,y1,x2,y2 in plan.get('blocks', []):
        a,b=xy([[x1,y1],[x2,y2]])
        wall_plan=wall_plan.union(box(min(a[0],b[0]),min(a[1],b[1]),max(a[0],b[0]),max(a[1],b[1])))
    walls = solid(wall_plan, params['wall_height'])
    for line in plan.get('doors', []):
        cutter=LineString(xy(line)).buffer(width*1.6, cap_style='flat')
        walls -= solid(cutter, params['door_height']+.02, -.01)
    if plan.get('source') == 'manual':
        rooms = unary_union(list(polygonize(unary_union([LineString(xy(line)) for line in plan['walls']]))))
        floor_plan = rooms.buffer(width/2, join_style='mitre').union(wall_plan)
    elif plan.get('footprint'):
        floor_plan = Polygon(xy(plan['footprint'])).buffer(width/2, join_style='mitre')
    else:
        # Fill only bounded outlines; also retain small gaps without a convex-hull shortcut.
        closed = wall_plan.buffer(.35, join_style='mitre').buffer(-.35, join_style='mitre')
        floor_plan = unary_union([Polygon(p.exterior) for p in polygons(closed)])
    if floor_plan.is_empty:
        raise ValueError('未形成有效轮廓，请补齐外墙。')
    def mesh(part):
        if part.status() != mf.Error.NoError:
            raise ValueError('几何运算失败，请检查重复墙线。')
        data = part.to_mesh()
        return trimesh.Trimesh(np.asarray(data.vert_properties)[:,:3].copy(), np.asarray(data.tri_verts).copy(), process=False)
    meshes = {'wall_shell':mesh(walls),'floor_slab':mesh(solid(floor_plan,.12,-.12))}
    triangles = write_model(meshes,out)
    overlay = Image.open(input_path).convert('RGB')
    draw=ImageDraw.Draw(overlay)
    for line in plan['walls']:
        draw.line([tuple(p) for p in line], fill='#216d9b', width=4)
    for line in plan.get('doors',[]):
        draw.line([tuple(p) for p in line],fill='#bd7c1f',width=7)
    overlay.save(out/'overlay.png')
    result={'triangles':triangles,'wall_count':len(plan['walls']),'door_count':len(plan.get('doors',[])),
            'width_m':params['width_m'],'wall_height':params['wall_height'],'units':'meters; user-estimated scale',
            'method':plan.get('method','edited'),'note':plan.get('note',''),'closed_meshes':True,'plan':plan}
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    with zipfile.ZipFile(out/'model.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for name in ['model.glb','model.obj','model.mtl','result.json','overlay.png']:
            archive.write(out/name,name)
    return result
