# 本地渲染与几何优化

已克隆 `https://github.com/ashnomad/Blueprint3D`，代码版本 `bb4a4fd`。

`examples/historical-sample/` 中的 `input.jpeg`、`sema.csv`、`split.csv` 原样恢复自项目提交 `5df980e2b845285d0e72199a7a7e01ef3b3fb572`。当前本地分支为 `codex/improve-floorplan-geometry`。

此前的几何优化没有运行神经网络推理。原仓库未提供权重；现已从 [LibuLux 的 ModelWeights 发布页](https://github.com/Nouni2/LibuLux/releases/tag/ModelWeights) 下载两份候选权重，并通过发布方 SHA-256 校验：

- `SplitFloor/checkpoints/splitfloor_best_miou.pth`：224,980,379 字节。
- `SemaFloor/checkpoints/best_semafloor_model.pth`：746,521,982 字节。

下载来源、完整校验值与路径记录在 `outputs/weights/download-manifest.json`，权重已排除在 Git 跟踪之外。现已通过严格参数加载和两张图片的 CPU 推理、3D 导出测试；这不代表广泛的识别精度验证。来源的[许可证](https://github.com/Nouni2/LibuLux/blob/main/LICENSE.md)允许个人及教学评估，限制商用、对外部署和集成到其他产品。

## 优化结果

- `outputs/optimized-sample/preview.png`：优化后渲染图。
- `outputs/optimized-sample/floorplan_3d.obj`：优化后的完整模型。
- `outputs/optimized-sample/preview.html`：可旋转预览；模型数据内嵌，Three.js 首次加载需要联网。
- `outputs/optimized-sample/result.json`：参数、来源、网格统计和原版对比。
- `outputs/historical-sample/`：此前保存的原版模型与渲染结果，保留用于比较。

本次通过规则化二维轮廓、合并共用墙体、实体布尔切割门窗来重新生成模型，没有对旧模型进行大比例删面。优化预览使用新模型的完整三角网格。材质仅用于展示。

| 项目 | 原版 | 优化后 |
| --- | ---: | ---: |
| 三角面数（统一三角化后统计） | 1,249,352 | 1,442 |
| OBJ 文件字节数 | 32,558,714 | 35,200 |
| 墙体开放边 | 未作为质量指标验证 | 0 |

以上数据仅针对这个示例，具体尺寸和门窗准确度仍取决于输入分割数据。

## 复现

使用 Python 3.13 的独立虚拟环境，依赖锁定于 `requirements-preview-lock.txt`。

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements-preview-lock.txt
.venv/bin/python scripts/optimize_sample.py
.venv/bin/python -m unittest discover -s tests -v
```

启动已有预览：

```bash
python3 -m http.server 8766 --bind 127.0.0.1 --directory outputs
```

打开 `http://127.0.0.1:8766/optimized-sample/preview.html`。

`ForgeFloor/extruder.py` 的默认模式已改为 `vector`，图形界面也使用新引擎。需要旧算法时传入 `--geometry_mode legacy`；命令行使用 `--no-show_interactive` 可直接离屏导出。`wall_height` 控制实际墙高，`door_height` 默认等于墙高的 80%。图形界面提供了门高参数。

`scripts/render_sample.py` 明确选择 `legacy`，仍可重现旧版输出；`scripts/present_sample.py` 是旧版展示脚本。

## 验证

11 项回归测试全部通过：7 项几何测试覆盖门洞贯通与门楣保留、窗台及窗楣、共用墙无夹缝、网格闭合、庭院保留、细线误识别和非法参数；4 项自动推理入口测试覆盖权重文件检查、相对路径、中文/空格/单引号路径和输出缺失。依赖一致性检查通过。

### 下载权重的实际推理测试

使用 `torch.load(weights_only=True)` 安全加载，两模型均按 `strict=True` 匹配原项目模型结构，没有缺失或额外参数。SplitFloor 有 56,152,900 个参数，SemaFloor 有 62,164,340 个参数。本次使用 CPU；没有测试 MPS/GPU 和桌面 GUI。

修复了原自动入口的重复路径 `SplitFloor/SplitFloor/deploy.py`、SemaFloor 缺少正式命令行入口及漏检 `sema.csv` 等问题。推理现在使用独立输出目录，并直接加载本地完整权重，不再额外下载 ImageNet 预训练参数。

| 实际输入 | 识别后房间区域 | 三角面数 | OBJ 字节数 | 墙体开放边 |
| --- | ---: | ---: | ---: | ---: |
| 原办公平面图 | 8 | 1,720 | 40,914 | 0 |
| 历史 `valid_000000.png` 住宅图 | 7 | 784 | 18,515 | 0 |

测试记录：`outputs/inference-test/test-report.json`。办公图的渲染和模型在 `outputs/inference-test/historical-office/`；住宅图在 `outputs/inference-test/户型 B's output/`，同时验证了特殊字符输出路径。输入和标注恢复自提交 `5df980e2b845285d0e72199a7a7e01ef3b3fb572` 的 `SplitFloor/dataset/valid/`，存于 `outputs/inference-test/fixtures/`。

住宅这一个样本与历史结构标注的 IoU：门 0.874、墙 0.843、窗 0.594。样本与权重训练数据是否重合未知，不能当作独立泛化评估，也不是整体识别准确率。办公图的历史 CSV 本身是模型输出，仅能用于一致性检查。

复现办公图的自动流程（先确认上述权重文件已存在）：

```bash
.venv/bin/python -m pip install -r requirements-inference-lock.txt
.venv/bin/python scripts/verify_weights.py
OMP_NUM_THREADS=6 .venv/bin/python ForgeFloor/extruder.py \
  --input examples/historical-sample/input.jpeg --auto \
  --output_dir outputs/inference-test/historical-office \
  --no-show_interactive --no-flip_x --rotation 0 --no-show_segmentation
.venv/bin/python -m unittest discover -s tests -v
```

## 当前效果边界

- 历史示例数据处理后得到 11 个连通房间区域。
- 平面尺度沿用图像像素；墙高 200、门高 160、窗台高 50、窗高 100，未换算为真实米制尺寸。
- 新算法减少像素锯齿，并合并近邻房间之间的墙体；它不会补出分割数据中缺失的真实结构。
- 门窗从原始结构分割掩膜提取，带少量穿墙余量；相连的识别区域不等于独立门窗数量，不能据此声称识别率。
- 两张图已通过自动建模。办公图中 OFFICE 2、OFFICE 3 与走廊仍被合成一个房间区域；住宅图有窗户过度识别，部分门口轮廓不完整或不规则。后续需要更多独立标注样本评估，并针对这些误识别改进分割和结构重建。

本分支修改涉及 `ForgeFloor/morpho.py`、`ForgeFloor/extruder.py`，新增了 `ForgeFloor/vector_geometry.py`、测试和复现脚本。

## 上传户型图的校正模型

`examples/user-floorplan-2026-11-06/` 保存输入图、核对后的墙线和门位置；`model/` 中包含 GLB、OBJ、材质、渲染图和模型说明，可在仓库中直接下载。这个样例因背景方格造成自动分割误判，使用按原图核对的几何建模，并非自动识别精度的展示。

安装 `requirements-model-lock.txt` 后运行 `scripts/build_traced_plan.py` 可复现，输出默认写入忽略 Git 跟踪的 `outputs/user-floorplan-2026-11-06/reviewed/`。模型采用估算比例，墙高 2.8 米；详情见示例说明。
