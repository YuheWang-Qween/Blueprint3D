"""Single-origin web workspace, REST API and queued reconstruction workers."""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field, ValidationError, model_validator

from .store import Store
from .furnishing import Layout, validate_bounds, export_glb

ROOT=Path(__file__).resolve().parents[1]
STATIC=Path(__file__).parent/'static'
COOKIE='blueprint_session'


class LimitedBody:
    """Bound chunked uploads before the multipart parser writes temporary files."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] not in ('POST', 'PUT', 'PATCH'):
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body', b'')
            size += len(chunk)
            if size > 13 * 1024 * 1024:
                return await JSONResponse({'detail': '图片不能超过 12 MB。'}, status_code=413)(scope, receive, send)
            chunks.append(chunk)
            if not message.get('more_body', False):
                break
        sent = False
        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {'type': 'http.request', 'body': b''.join(chunks), 'more_body': False}
            return await receive()
        await self.app(scope, replay, send)


class Credentials(BaseModel):
    username: str = Field(min_length=2,max_length=32)
    password: str = Field(min_length=1,max_length=128)


class Parameters(BaseModel):
    width_m: float = Field(default=10.8,ge=2,le=100,allow_inf_nan=False)
    wall_height: float = Field(default=2.8,ge=1.8,le=8,allow_inf_nan=False)
    wall_thickness: float = Field(default=.16,ge=.06,le=.6,allow_inf_nan=False)
    door_height: float = Field(default=2.1,ge=1.5,le=5,allow_inf_nan=False)
    engine: str = 'linework'

    @model_validator(mode='after')
    def dimensions(self):
        if self.door_height>=self.wall_height:
            raise ValueError('门高需要低于墙高')
        if self.engine not in ['linework','neural']:
            raise ValueError('请选择有效建模方式')
        return self


class Revision(BaseModel):
    params: Parameters
    walls: list = Field(min_length=1,max_length=450)
    doors: list = Field(default_factory=list,max_length=450)


class ManualDrawing(Revision):
    name: str = Field(default='手绘户型',min_length=1,max_length=80)
    depth_m: float = Field(default=9,ge=2,le=100,allow_inf_nan=False)


def neural_available():
    return os.getenv('BLUEPRINT_ENABLE_NEURAL')=='1' and all((ROOT/p).is_file() for p in [
        'SplitFloor/checkpoints/splitfloor_best_miou.pth','SemaFloor/checkpoints/best_semafloor_model.pth'])


def default_data_dir():
    # FaaS/containers may mount the project root read-only; only the implicit
    # default degrades so an explicit BLUEPRINT_DATA_DIR still fails loudly.
    preferred=ROOT/'var/web'
    try:
        preferred.mkdir(parents=True,exist_ok=True)
        probe=preferred/'.write-probe'
        probe.touch();probe.unlink()
        return preferred
    except OSError:
        fallback=Path(tempfile.gettempdir())/'blueprint-web'
        fallback.mkdir(parents=True,exist_ok=True)
        print(f'[blueprint] data dir {preferred} is not writable; falling back to {fallback} '
              '(ephemeral, data will not survive restarts; set BLUEPRINT_DATA_DIR to a persistent volume)',
              file=sys.stderr,flush=True)
        return fallback


def create_app(data_dir=None):
    store=Store(data_dir or os.getenv('BLUEPRINT_DATA_DIR') or default_data_dir())
    pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='blueprint-job')
    limits={}
    lock=threading.Lock()

    @asynccontextmanager
    async def lifespan(app):
        yield
        pool.shutdown(wait=True,cancel_futures=True)

    app=FastAPI(title='Blueprint3D',lifespan=lifespan,docs_url=None,redoc_url=None)
    app.state.store=store
    app.add_middleware(LimitedBody)

    @app.middleware('http')
    async def guards(request,call_next):
        if request.url.path.startswith('/api/') and request.method not in ('GET','HEAD','OPTIONS'):
            if request.headers.get('x-blueprint-request')!='1':
                return JSONResponse({'detail':'请求已过期，请刷新后再试。'},status_code=403)
            try:
                length = int(request.headers.get('content-length','0') or 0)
            except ValueError:
                return JSONResponse({'detail':'请求长度无效。'},status_code=400)
            if length>13*1024*1024:
                return JSONResponse({'detail':'图片不能超过 12 MB。'},status_code=413)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='same-origin'
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control']='no-store'
        elif request.url.path.startswith('/static/') and Path(request.url.path).suffix in {'.js','.css','.json'}:
            # These files keep stable names across releases. Revalidate them so
            # new entrypoints cannot run alongside older cached editor modules.
            response.headers['Cache-Control']='no-cache'
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid(request,error):
        return JSONResponse({'detail':'请检查输入信息、尺寸范围和文件格式。'},status_code=422)

    def current(request):
        user=store.user(request.cookies.get(COOKIE))
        if not user:
            raise HTTPException(401,'请先登录。')
        return user

    def own_job(request,jid):
        user=current(request)
        job=store.job(jid,user['id'])
        if not job:
            raise HTTPException(404,'找不到这个模型。')
        return job

    def rate_limit(request):
        key=request.client.host if request.client else 'unknown'
        now=time.monotonic()
        with lock:
            attempts=[t for t in limits.get(key,[]) if now-t<60]
            if len(attempts)>=12:
                raise HTTPException(429,'尝试次数较多，请一分钟后再试。')
            limits[key]=attempts+[now]

    def signed_in(user,request):
        result=JSONResponse({'user':{'username':user['username']}})
        secure=os.getenv('BLUEPRINT_SECURE_COOKIES')=='1' or request.url.scheme=='https'
        same_site=os.getenv('BLUEPRINT_COOKIE_SAMESITE','lax')
        if same_site=='none' and not secure:
            same_site='lax'
        result.set_cookie(COOKIE,store.session(user),max_age=604800,httponly=True,secure=secure,samesite=same_site,path='/')
        return result

    @app.get('/healthz')
    def health():
        return {'status':'ok','service':'blueprint3d-web'}

    @app.get('/api/me')
    def me(request:Request):
        user=store.user(request.cookies.get(COOKIE))
        return {'user':{'username':user['username']} if user else None,'neural_available':neural_available()}

    @app.post('/api/register')
    def register(data:Credentials,request:Request):
        rate_limit(request)
        username=data.username.strip()
        if not re.fullmatch(r'[\w.@-]{2,32}',username) or len(data.password)<8:
            raise HTTPException(400,'用户名限 2–32 位文字、数字或 . @ -；密码至少 8 位。')
        try:
            user=store.register(username,data.password)
        except ValueError as e:
            raise HTTPException(409,str(e))
        return signed_in(user,request)

    @app.post('/api/login')
    def login(data:Credentials,request:Request):
        rate_limit(request)
        user=store.verify(data.username.strip(),data.password)
        if not user:
            raise HTTPException(401,'用户名或密码不正确。')
        return signed_in(user,request)

    @app.post('/api/logout')
    def logout(request:Request):
        store.logout(request.cookies.get(COOKIE))
        response=JSONResponse({'ok':True})
        response.delete_cookie(COOKIE,path='/')
        return response

    def process(jid,directory):
        store.update_job(jid,'running')
        try:
            env={**os.environ,'OMP_NUM_THREADS':os.getenv('OMP_NUM_THREADS','2'),'MPLBACKEND':'Agg'}
            with (directory/'worker.log').open('w') as log:
                completed=subprocess.run([sys.executable,'-m','webapp.worker',str(directory)],cwd=ROOT,env=env,
                                         stdout=log,stderr=subprocess.STDOUT,timeout=720)
            if completed.returncode:
                error=(directory/'error.txt').read_text() if (directory/'error.txt').exists() else '生成失败，请重新尝试。'
                store.update_job(jid,'error',error=error[:300])
            else:
                result=json.loads((directory/'result.json').read_text())
                store.update_job(jid,'done',result=result)
        except subprocess.TimeoutExpired:
            store.update_job(jid,'error',error='处理超时，请裁剪图纸或改用线稿建模。')
        except Exception:
            store.update_job(jid,'error',error='服务暂时无法完成生成，请重试。')

    def enqueue(user,name,image,params,plan=None):
        if params.engine=='neural' and not neural_available():
            raise HTTPException(409,'服务器尚未启用增强识别，请选择线稿建模。')
        jid=uuid.uuid4().hex
        directory=store.directory/'jobs'/jid
        directory.mkdir(parents=True)
        try:
            image.save(directory/'input.png')
            (directory/'request.json').write_text(json.dumps({'params':params.model_dump(),'plan':plan},ensure_ascii=False))
            store.add_job(jid,user['id'],name,params.model_dump())
        except ValueError as e:
            shutil.rmtree(directory)
            raise HTTPException(429,str(e))
        pool.submit(process,jid,directory)
        return store.job(jid,user['id'])

    @app.get('/api/jobs')
    def jobs(request:Request):
        return {'jobs':store.jobs(current(request)['id'])}

    @app.post('/api/jobs',status_code=202)
    async def generate(request:Request,file:UploadFile=File(...),parameters:str=Form('{}')):
        user=current(request)
        raw=await file.read(12*1024*1024+1)
        if len(raw)>12*1024*1024:
            raise HTTPException(413,'图片不能超过 12 MB。')
        try:
            params=Parameters.model_validate_json(parameters)
        except ValidationError:
            raise HTTPException(422,'请检查尺寸范围，门高应低于墙高。')
        try:
            opened=Image.open(io.BytesIO(raw))
            if opened.format not in ['JPEG','PNG','WEBP'] or opened.width*opened.height>12_000_000 or min(opened.size)<64:
                raise ValueError()
            image=ImageOps.exif_transpose(opened).convert('RGB')
            image.thumbnail((2048,2048))
        except (ValueError,OSError,UnidentifiedImageError,Image.DecompressionBombError):
            raise HTTPException(400,'请选择清晰的 PNG、JPG 或 WebP 户型图，像素总量不超过 1200 万。')
        name=Path((file.filename or '户型图').replace('\\','/')).name[:100]
        return enqueue(user,name,image,params)

    @app.post('/api/jobs/manual',status_code=202)
    def manual(data:ManualDrawing,request:Request):
        user=current(request)
        from .manual import drawing_plan, drawing_image
        from .geometry import validate_plan
        params=data.params.model_copy(update={'engine':'linework'})
        plan=drawing_plan(params.width_m,data.depth_m,data.walls,data.doors)
        try:
            validate_plan(plan)
        except (ValueError,TypeError) as error:
            raise HTTPException(422,str(error))
        return enqueue(user,data.name.strip() or '手绘户型',drawing_image(plan),params,plan)

    @app.get('/api/jobs/{jid}')
    def detail(jid:str,request:Request):
        return own_job(request,jid)

    def completed_job(request, jid):
        job = own_job(request, jid)
        if job['status'] != 'done':
            raise HTTPException(409, '请等待户型模型生成完成后再布置。')
        return job

    @app.get('/api/jobs/{jid}/layout')
    def get_layout(jid: str, request: Request):
        completed_job(request, jid)
        # Normalize optional appearance fields without rewriting older saved layouts.
        return Layout.model_validate(store.layout(jid)).model_dump()

    @app.get('/api/jobs/{jid}/surfaces')
    def surfaces(jid: str, request: Request):
        completed_job(request, jid)
        from webapp.surfaces import get_surfaces
        return get_surfaces(store.directory / 'jobs' / jid)

    @app.put('/api/jobs/{jid}/layout')
    def put_layout(jid: str, data: Layout, request: Request):
        completed_job(request, jid)
        try:
            validate_bounds(data, store.directory / 'jobs' / jid)
        except ValueError as error:
            raise HTTPException(422, str(error))
        try:
            return store.save_layout(jid, data.model_dump())
        except ValueError as error:
            raise HTTPException(409, str(error))

    @app.get('/api/jobs/{jid}/furnished.glb')
    def furnished(jid: str, request: Request):
        completed_job(request, jid)
        content = export_glb(store.directory / 'jobs' / jid, store.layout(jid))
        return Response(content, media_type='model/gltf-binary',
                        headers={'Content-Disposition': 'attachment; filename="furnished.glb"'})

    @app.post('/api/jobs/{jid}/revise',status_code=202)
    def revise(jid:str,data:Revision,request:Request):
        old=own_job(request,jid)
        source_plan=(old.get('result') or {}).get('plan')
        if not source_plan:
            raise HTTPException(400,'请先使用线稿建模，再校正平面。')
        from .geometry import validate_plan
        plan={**source_plan,'walls':data.walls,'doors':data.doors,'method':'edited','note':'模型已按校正后的墙线和门洞重新生成。'}
        if data.walls != source_plan['walls']:
            plan['footprint'] = None
        try:
            validate_plan(plan)
        except (ValueError,TypeError) as e:
            raise HTTPException(422,str(e))
        params=data.params.model_copy(update={'engine':'linework'})
        if source_plan.get('source')=='manual':
            from .manual import drawing_image
            plan['note']='手绘模型已按当前墙线、门洞与尺寸重新生成。'
            return enqueue(current(request),old['name'],drawing_image(plan),params,plan)
        with Image.open(store.directory/'jobs'/jid/'input.png') as image:
            return enqueue(current(request),old['name'],image.copy(),params,plan)

    @app.get('/api/jobs/{jid}/files/{filename}')
    def download(jid:str,filename:str,request:Request):
        job=own_job(request,jid)
        allowed={'input.png','overlay.png','model.glb','model.obj','model.mtl','model.zip','mesh.json','result.json'}
        if filename not in allowed or (job['status']!='done' and filename!='input.png'):
            raise HTTPException(404,'文件尚未生成。')
        path=store.directory/'jobs'/jid/filename
        if not path.is_file():
            raise HTTPException(404,'找不到文件。')
        return FileResponse(path,filename=filename if filename.endswith(('.glb','.obj','.zip')) else None,
                            media_type='model/gltf-binary' if filename.endswith('.glb') else None)

    @app.get('/sample/{filename}')
    def sample(filename:str):
        base=ROOT/'examples/user-floorplan-2026-11-06'
        paths={'input.png':base/'input.png','model.glb':base/'model/floorplan.glb','preview.png':base/'model/preview.png'}
        if filename not in paths:
            raise HTTPException(404)
        return FileResponse(paths[filename])

    @app.get('/')
    def index():
        return FileResponse(STATIC/'index.html',headers={'Cache-Control':'no-cache'})

    app.mount('/static',StaticFiles(directory=STATIC,check_dir=False),name='static')
    return app


app=create_app()
