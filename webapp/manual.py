"""Direct vector input for drawings created in the workspace; no image recognition."""
from PIL import Image, ImageDraw

UNITS_PER_METER = 32


def drawing_plan(width_m, depth_m, walls, doors):
    return {'width': round(width_m * UNITS_PER_METER, 6),
            'height': round(depth_m * UNITS_PER_METER, 6),
            'walls': walls, 'doors': doors, 'blocks': [], 'footprint': None,
            'source': 'manual', 'method': 'manual',
            'note': '模型由现场绘制的墙线和门洞直接生成。可继续修改平面、布置家具和精装修。'}


def drawing_image(plan):
    # This is a viewable source drawing, not an input to a recognition model.
    image = Image.new('RGB', (round(plan['width']), round(plan['height'])), 'white')
    draw = ImageDraw.Draw(image)
    for line in plan['walls']:
        draw.line([tuple(p) for p in line], fill='#247ca6', width=3)
    for line in plan['doors']:
        draw.line([tuple(p) for p in line], fill='#d09423', width=5)
    return image
