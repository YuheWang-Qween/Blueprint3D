## 项目概述
将 2D 户型图转换为交互式 3D 模型。提供 FastAPI 浏览器工作台和原有深度学习/桌面管线；Web 默认采用无需权重的线稿建模，增强识别按配置启用。桌面与 Web 账号独立。

## 技术栈
- 语言：Python 3.12+（Web）；JavaScript / Three.js 浏览器查看器
- 主要依赖：PyTorch、numpy、OpenCV、Pillow、matplotlib、pyvista、scikit-image、albumentations、scipy、scikit-learn 等
- Web 依赖：`requirements.txt` → `requirements-web.txt`；原神经网络依赖按 README / lock 文件安装。
- 前端：`webapp/package.json` / `package-lock.json`；修改 viewer.js 后用 npm 重建并提交 static/viewer.bundle.js，保留 Three.js 许可证。
- 家具布置：`static/furniture-catalog.json` 同时用于 2D、Three.js 和服务端 GLB；坐标为原始 GLB 的 X/Z 米制坐标，不可存储查看器居中后的坐标。`layouts` 表按模型隔离并做 revision 冲突检查；接口先验证任务归属。
- 精装修：款式与材质为每件家具的 `variant` / `material`，缺省兼容 `standard` / `default`；更换外观不能更改粗布置的坐标与尺寸。共享几何由 `scripts/build_furniture_geometry.mjs` 生成；材质和本地纹理同时用于查看器及 GLB 导出。
- 墙地面：`surfaces.py` 从不可变 `mesh.json` 派生区域与稳定 ID，`/surfaces` 接口先验证归属。`finishes.floorStyle` / `wallStyle` 是全屋设置，`finishes.surfaces` 是区域覆盖；旧 `floor` / `wall` 配色兼容。显示和导出共用区域三角面、UV、材质；只增加薄饰面，不修改原始结构文件。保存时拒绝其他模型的区域 ID。
- Python 使用项目级 `.venv`，扣子构建支持 `PIP_TARGET`。

## 目录结构
- `ForgeFloor/` — 核心管线与 3D 生成引擎：`extruder.py`（主入口）、`Shape.py`（2D 几何/形态学清洗）、`morpho.py`（3D 挤压，pyvista）、`auth.py`（本地认证 + 蓝图风格登录窗口）
- `SemaFloor/` — 语义房间分割网络（ResNet-50 + ASPP）：`train.py` / `deploy.py` / `net.py` / `data.py`
- `SplitFloor/` — 结构件分割网络（墙/门/窗 4 类）：`train.py` / `deploy.py` / `net.py` / `data.py`
- `images/` — 管线各阶段可视化示例图
- `.codegraph/` — 代码索引（忽略 git）
- `DESIGN.md` — GUI 视觉基调（蓝图风格），新增界面时遵循
- `webapp/` — FastAPI、SQLite 认证/任务、轻量几何、Three.js 工作台
- `scripts/setup_web.sh` / `scripts/start_web.sh` — 本地和扣子安装/启动入口
- `WEB_DEPLOY.md` — 部署、持久磁盘、单进程限制与权重许可说明

## 关键入口 / 核心模块
- 主入口：`python ForgeFloor/extruder.py --gui`（Tkinter 桌面 GUI，先登录后进主界面）；`python ForgeFloor/extruder.py --input <img> --auto --output_dir <dir>`（CLI 自动处理，无需登录）
- 登录：`ForgeFloor/auth.py` — `register()`/`verify()`（PBKDF2-HMAC-SHA256，200k 迭代）+ `LoginWindow`（登录/注册切换）；账号存 `ForgeFloor/users.json`（已 gitignore，勿提交）；`create_gui()` 中 `on_login_success` 销毁登录组件后构建主窗口
- 子模块推理：`SemaFloor/deploy.py`、`SplitFloor/deploy.py`
- 训练：`python SemaFloor/train.py`、`python SplitFloor/train.py`

## 运行与预览
- `.coze` 为 `project_type = "web"`，预览已启用；开发和部署运行单个 FastAPI 进程，默认端口 5000。
- `bash scripts/setup_web.sh` 安装，`bash scripts/start_web.sh` 启动；必须实际在浏览器检查登录、上传、三维显示和下载。
- Web 测试：安装 httpx 后 `.venv/bin/python -m unittest discover -s tests -p 'test_web.py' -v`；完整测试另需原几何/推理依赖。
- 布置与室内视角前端测试：`node --test webapp/*.test.js`；实际检查平面拖放、所有家具的款式与材质、墙地面局部/全屋修改、室内移动、刷新恢复、JSON 导入导出和带材质 GLB。
- 账户、任务与模型写入 `BLUEPRINT_DATA_DIR`（默认 var/web），禁止提交运行数据或权重。生产需要持久磁盘，不能默认容器目录会跨部署保留。
- 不增加 Uvicorn worker 或多副本；当前任务队列是单服务进程。增强识别仅在依赖、权重与使用授权齐全时启用。
- GUI 无头验证方法（本沙箱已验证可行）：`xvfb-run -a python3 <脚本>` 跑 Tkinter；`auth.py`/登录窗口仅依赖标准库 + tkinter，可直接测；要测 `create_gui` 完整接线但不想装重型依赖时，用桩模块替身（`Shape.py`/`morpho.py` 提供 `ShapeProcessor()`/`MorphoExtruder()` 空类，`sys.modules` 注入 PIL 替身）复制 extruder.py/auth.py 到临时目录后驱动。
- 运行环境：`uv` + 项目级虚拟环境管理依赖；首次运行前先同步依赖。沙箱注意：系统 Python 需 `apt install python3-tk` 才有 tkinter；`python3 -m venv` 需 `apt install python3.12-venv`（未装时 venv 创建会失败）。

## 用户偏好与长期约束
- （暂无明确记录；后续跨任务长期有效的偏好在此沉淀）

## 常见问题和预防
- 管线强依赖 torch + CUDA，CPU 环境推理较慢；训练建议有 GPU。
- 三个模块间通过相对项目根的路径引用，运行 `ForgeFloor` 时应保证 `SplitFloor`/`SemaFloor` 目录相对项目根可访问。
- `auth.py` 中 tkinter 是在 `LoginWindow.__init__` 内延迟导入的，方法体里不要引用 `tk.X` 之类的模块常量（用字符串 `'x'`/`'both'` 代替），否则 NameError。
- `ForgeFloor/users.json` 是本地账号库（含 PBKDF2 哈希），已 gitignore；删除该文件等于清空所有账号。
- 扣子 FaaS 部署环境把项目根（`/opt/bytefaas`）挂载为只读：`webapp/app.py` 的默认数据目录不可写时会自动降级到 `tempfile.gettempdir()/blueprint-web` 并在 stderr 打警告（数据不跨重启保留）；显式设置 `BLUEPRINT_DATA_DIR` 时不会降级，配置错误会直接报错暴露。生产仍需持久磁盘。
