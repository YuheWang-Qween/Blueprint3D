用户上传户型图的三维转换

input.png 是上传图片的原样副本。
traced-plan.json 是参照图片核对的墙中心线、门位置与建模假设。

自动模型把背景方格误识别为 62 个房间区域，保留在 outputs/user-floorplan-2026-11-06/automatic/ 供排查。
仓库中的校正模型快照位于 examples/user-floorplan-2026-11-06/model/。
本地重新生成的结果位于 outputs/user-floorplan-2026-11-06/reviewed/。

尺寸假设：原图没有尺寸标注，以图中约 68 像素的门符号暂按 0.90 米换算；墙高 2.80 米，门高 2.10 米。
这是一份按图中比例建立的示意模型，不是实测模型。
图中两处交叉方框暂按全高结构块保留；左侧两条错开的细线按推拉隔断解释，其玻璃材质仅用于示意。

模型包含 6 处平开门与 1 处推拉隔断。逐处检查了门洞贯通、上部门楣保留和网格闭合，并重新读取 GLB 验证导出。
GLB 使用 Y 轴向上、单位米；OBJ 使用 Z 轴向上、单位米。两者采用相同估算比例。

在仓库根目录复现：
.venv/bin/python -m pip install -r requirements-model-lock.txt
.venv/bin/python scripts/build_traced_plan.py

预览使用 scripts/user-floorplan-preview.html，配合 scripts/build_preview.py 的 --template 参数。
