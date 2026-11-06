"""Safely load downloaded checkpoints and strictly match local architectures."""

import gc
import importlib.util
import json
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]


def verify(folder, module_name, class_name, filename, options):
    spec = importlib.util.spec_from_file_location(module_name, ROOT / folder / 'net.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    checkpoint = torch.load(ROOT / folder / 'checkpoints' / filename,
                            map_location='cpu', weights_only=True, mmap=True)
    state = checkpoint.get('model_state_dict', checkpoint)
    with torch.device('meta'):
        model = getattr(module, class_name)(pretrained=False, **options)
    loaded = model.load_state_dict(state, strict=True, assign=True)
    result = {
        'model': folder, 'file': filename, 'keys': len(state),
        'parameters': sum(p.numel() for p in model.parameters()),
        'missing_keys': loaded.missing_keys,
        'unexpected_keys': loaded.unexpected_keys,
        'strict_load_passed': True,
    }
    if 'epoch' in checkpoint:
        result['checkpoint_epoch'] = checkpoint['epoch']
    print(json.dumps(result), flush=True)
    del model, state, checkpoint
    gc.collect()
    return result


def main():
    results = [
        verify('SplitFloor', 'splitfloor_net', 'SplitFloor',
               'splitfloor_best_miou.pth', {'num_classes': 4}),
        verify('SemaFloor', 'semafloor_net', 'SemafloorNet',
               'best_semafloor_model.pth', {'deep_supervision': True}),
    ]
    report = {
        'torch_version': torch.__version__,
        'mps_available': torch.backends.mps.is_available(),
        'models': results,
    }
    out = ROOT / 'outputs' / 'inference-test'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'weight-verification.json').write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
