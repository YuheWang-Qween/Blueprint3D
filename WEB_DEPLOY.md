# Blueprint3D 网页版运行与部署

## 使用流程

1. 打开网站，首次点击“创建账户”，已有账户直接登录。
2. 上传 PNG、JPG 或 WebP 户型图（不超过 12 MB / 1200 万像素）。
3. 输入户型总宽、墙高、门高和墙厚；单位为米。总宽对应墙线左右边界的距离。
4. 点击“生成 3D 模型”。生成任务在后台排队，可刷新后从“我的模型”继续查看。
5. 在“校正平面”中画墙线、标门洞或擦除误识别线段，点击“更新 3D 模型”。
   修改会生成新版本；旧版本保留。未提交的墙线草稿保存在当前浏览器，按账户和模型隔离。
6. 在 3D 页拖动旋转、滚轮缩放、右键平移；可切换俯视或半墙。
7. 下载 GLB 供三维软件使用，或下载含 GLB、OBJ、MTL、校正图和参数的 ZIP。

## 本地与扣子

Python 3.12+。仓库内已包含 Three.js 构建产物，运行网站不依赖外部 CDN 或 Node.js。

```bash
bash scripts/setup_web.sh
bash scripts/start_web.sh
```

打开 http://localhost:5000。健康检查为 `/healthz`。
`PORT` 或扣子提供的 `DEPLOY_RUN_PORT` 可覆盖端口；默认是 5000。

扣子工作区需要同步包含网页版的 `main` 提交。`.coze` 已声明 `project_type = "web"`，
预览的 `dev.run` 通过 `dev_web.sh` 顺序安装依赖并启动（不能依赖 `dev.build` 自动安装）。
生产环境分别执行安装、启动脚本。安装脚本兼容扣子生产构建提供的
`PIP_TARGET`，本地则使用 `.venv`。缺少 ensurepip / venv 的精简云端环境自动安装到
项目内 `.web-deps`，启动脚本设置相应模块路径，无需 apt 或改动系统 Python。
启动后应先确认预览可见登录页并实际生成一个模型，再在部署面板发布。
GitHub 推送完成不等于扣子工作区或线上服务已经自动更新。

预览嵌在跨站 iframe 时，浏览器可能限制会话 Cookie。可以在新标签页打开预览；
或者仅在 HTTPS 环境设置 `BLUEPRINT_SECURE_COOKIES=1`、`BLUEPRINT_COOKIE_SAMESITE=none`。
正式 HTTPS 域名建议使用 Secure Cookie，通常保留 SameSite=lax 即可。

## 数据保存与运行规模

`BLUEPRINT_DATA_DIR` 存放 SQLite 账户/会话/任务数据库和每个模型文件夹，默认 `var/web`。
生产环境必须将这个目录指向持久磁盘并备份整个目录；临时容器重建会丢失未持久化数据。
示例：`BLUEPRINT_DATA_DIR=/data/blueprint3d`。扣子是否保留该路径应以所用部署环境为准，
不能把开发工作区磁盘当作生产持久卷的保证。

当前版本使用**单个服务进程和一个生成工作进程**，适合个人/小规模工作台。
不要增加 Uvicorn workers 或多副本共享同一数据库；扩容需要外部队列、数据库和对象存储。
服务重启时，未完成任务会标记失败，用户可以重新提交；账户和已完成模型只要磁盘保留即可恢复。
生成全局最多排队 8 个、每账户最多 2 个，单任务超时 12 分钟。
任务文件持续保留；部署者需按实际使用量安排磁盘容量、备份和保留期限。

Docker 提供相同轻量服务，可挂载持久卷：

```bash
docker build -t blueprint3d-web .
docker run --rm -p 5000:5000 -v blueprint-data:/data blueprint3d-web
```

## 可选神经网络识别

默认 Web 安装不包含 PyTorch、VTK 和权重，因此云端可直接运行轻量线稿建模。
要启用“增强识别”，需另行安装原推理依赖，将两个检查点放到项目约定位置，
并设置 `BLUEPRINT_ENABLE_NEURAL=1` 后重启。只有文件齐全且开关启用时前端才显示该选项。
参见 [PREVIEW.md](PREVIEW.md) 中的权重来源、完整性与许可说明。
外部权重有商业/托管服务限制，使用者需要先取得适用授权；仓库、Docker 和默认云端包均不包含权重。
增强识别结果可下载，但墙线编辑仅适用于线稿建模。

## 验证与第三方组件

`tests/test_web.py` 覆盖真实上传与生成、导出、账户隔离、会话失效、校正版本、
损坏图片、尺寸校验和上传限制。完整项目测试另需原有几何/推理依赖。
Three.js 的 MIT 许可随包保存在 `webapp/static/THREE-LICENSE.txt`；
`webapp/package-lock.json` 固定前端构建依赖。
