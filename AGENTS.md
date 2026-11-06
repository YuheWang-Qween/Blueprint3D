## 项目概述
将 2D 户型图（floor plan）转换为交互式 3D 模型的深度学习管线。包含语义分割（房间 / 结构件）与形态学处理、3D 挤压生成。

## 技术栈
- 语言：Python 3.8+（本机 3.12）
- 主要依赖：PyTorch、numpy、OpenCV、Pillow、matplotlib、pyvista、scikit-image、albumentations、scipy、scikit-learn 等
- 无 package.json / requirements.txt / pyproject.toml（依赖按 README 手动安装）
- 包管理器：无（原生 Python），遵循 `uv` 约定用项目级虚拟环境

## 目录结构
- `ForgeFloor/` — 核心管线与 3D 生成引擎：`extruder.py`（主入口）、`Shape.py`（2D 几何/形态学清洗）、`morpho.py`（3D 挤压，pyvista）
- `SemaFloor/` — 语义房间分割网络（ResNet-50 + ASPP）：`train.py` / `deploy.py` / `net.py` / `data.py`
- `SplitFloor/` — 结构件分割网络（墙/门/窗 4 类）：`train.py` / `deploy.py` / `net.py` / `data.py`
- `images/` — 管线各阶段可视化示例图
- `.codegraph/` — 代码索引（忽略 git）

## 关键入口 / 核心模块
- 主入口：`python ForgeFloor/extruder.py --gui`（Tkinter 桌面 GUI）；`python ForgeFloor/extruder.py --input <img> --auto --output_dir <dir>`（CLI 自动处理）
- 子模块推理：`SemaFloor/deploy.py`、`SplitFloor/deploy.py`
- 训练：`python SemaFloor/train.py`、`python SplitFloor/train.py`

## 运行与预览
- 非预览型项目（`project_type = ""`），`.coze` 中 `[preview].preview_enable = "disabled"`，无 `[dev]`、无 `.preview`。
- 无法通过常驻预览进程做可视验证；验证以 CLI/单测/构建 / 类型检查等脚本方式兜底。
- 运行环境：`uv` + 项目级虚拟环境管理依赖；首次运行前先同步依赖。

## 用户偏好与长期约束
- （暂无明确记录；后续跨任务长期有效的偏好在此沉淀）

## 常见问题和预防
- 管线强依赖 torch + CUDA，CPU 环境推理较慢；训练建议有 GPU。
- 三个模块间通过相对项目根的路径引用，运行 `ForgeFloor` 时应保证 `SplitFloor`/`SemaFloor` 目录相对项目根可访问。