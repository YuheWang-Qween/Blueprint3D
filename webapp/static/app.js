import {ModelViewer} from './viewer.bundle.js';
const $=id=>document.getElementById(id);
const state={user:null,register:false,file:null,active:null,jobs:[],viewer:null,plan:null,undo:[],tool:'wall',start:null,dirty:false,poll:null,loadId:0};
let toastTimer,thumbnailUrl;
function saved(key,value){try{if(value===undefined)return localStorage.getItem(key);if(value===null)localStorage.removeItem(key);else localStorage.setItem(key,value);}catch{}return null;}
function draftKey(){return 'blueprint3d.draft.'+state.user.username+'.'+state.active.id;}

function toast(message,error=false){$('toast').textContent=message;$('toast').classList.toggle('error',error);$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,4500);}
async function api(path,options={}){
  const response=await fetch(path,{credentials:'same-origin',...options,headers:{'X-Blueprint-Request':'1',...(options.body && !(options.body instanceof FormData)?{'Content-Type':'application/json'}:{}),...options.headers}});
  const data=await response.json().catch(()=>({detail:'服务暂时不可用，请稍后重试。'}));
  if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'请检查输入内容后重试。');
  return data;
}
function parameters(){return {width_m:Number($('width-m').value),wall_height:Number($('wall-height').value),door_height:Number($('door-height').value),wall_thickness:Number($('wall-thickness').value),engine:$('engine').value};}
function setParameters(p){for(const [key,id] of Object.entries({width_m:'width-m',wall_height:'wall-height',door_height:'door-height',wall_thickness:'wall-thickness',engine:'engine'}))if(p[key]!==undefined)$(id).value=p[key];}
function showAuth(){
  state.user=null;state.active=null;state.plan=null;state.jobs=[];clearTimeout(state.poll);
  $('studio').hidden=true;$('auth-screen').hidden=false;$('password').value='';$('confirm-password').value='';
  state.file=null;$('plan-file').value='';$('upload-title').textContent='上传户型图';$('upload-meta').textContent='PNG / JPG / WebP · 最大 12 MB';
  $('upload-thumbnail').hidden=true;$('generate').disabled=true;
  if(thumbnailUrl){URL.revokeObjectURL(thumbnailUrl);thumbnailUrl=null;}
}
$('auth-toggle').addEventListener('click',()=>{
  state.register=!state.register;$('auth-title').textContent=state.register?'创建你的工作台':'进入制图工作台';
  $('auth-subtitle').textContent=state.register?'用一个账户，保存你的图纸与建模结果。':'登录后保存图纸与模型，随时继续。';
  $('auth-submit').textContent=state.register?'创建账户并进入':'登录工作台';
  $('auth-toggle').textContent=state.register?'已有账户？直接登录':'还没有账户？创建账户';
  $('confirm-label').hidden=!state.register;$('confirm-password').required=state.register;
  $('password').autocomplete=state.register?'new-password':'current-password';$('password').minLength=state.register?8:1;
  $('auth-error').textContent='';
});
$('auth-form').addEventListener('submit',async event=>{
  event.preventDefault();$('auth-error').textContent='';
  if(state.register && $('password').value!==$('confirm-password').value){$('auth-error').textContent='两次输入的密码不一致。';return;}
  $('auth-submit').disabled=true;
  try{
    const data=await api(state.register?'/api/register':'/api/login',{method:'POST',body:JSON.stringify({username:$('username').value,password:$('password').value})});
    $('password').value='';$('confirm-password').value='';await enter(data.user);
  }catch(error){$('auth-error').textContent=error.message;}finally{$('auth-submit').disabled=false;}
});
$('logout').addEventListener('click',async()=>{try{await api('/api/logout',{method:'POST'});showAuth();}catch(e){toast(e.message,true);}});
async function enter(user){
  state.user=user;$('account-name').textContent=user.username;$('auth-screen').hidden=true;$('studio').hidden=false;
  $('auth-error').textContent='';
  try{
    if(!state.viewer)state.viewer=new ModelViewer($('viewer'));
    await showSample();
  }catch(e){viewerError('三维显示不可用，请确认浏览器支持 WebGL。模型文件仍可下载。');}
  const info=await api('/api/me');
  const existing=$('engine').querySelector('option[value=neural]');
  if(info.neural_available && !existing){const option=document.createElement('option');option.value='neural';option.textContent='增强识别 · 神经网络分割';$('engine').append(option);}
  if(!info.neural_available && existing)existing.remove();
  await refreshJobs();
  const remembered=saved('blueprint3d.active.'+user.username);
  const job=state.jobs.find(j=>j.id===remembered);
  if(job)await selectJob(job);
}
function viewerError(message){$('viewer-error').hidden=false;$('viewer-error').textContent=message;}
async function showSample(){
  state.active=null;state.plan=null;$('drawing-title').textContent='示例户型';$('status-badge').textContent='可旋转查看';$('status-badge').classList.remove('error');
  $('result-note').textContent='示例已按原图核对，尺寸为估算值。上传你自己的图纸开始建模。';
  $('result-meta').textContent='墙高 2.8 米 · 6 处平开门 · 1 处推拉隔断';
  $('source-image').src='/sample/input.png';$('viewer').hidden=false;$('viewer-error').hidden=true;$('downloads').hidden=true;$('progress').hidden=true;
  $('cutaway').checked=false;setView('model');await state.viewer?.load('/sample/model.glb');
}
function selectFile(file){
  if(!file)return;
  if(file.size>12*1024*1024){toast('图片不能超过 12 MB。',true);return;}
  state.file=file;$('upload-title').textContent=file.name;$('upload-meta').textContent=(file.size/1024).toFixed(0)+' KB · 点击更换';
  if(thumbnailUrl)URL.revokeObjectURL(thumbnailUrl);thumbnailUrl=URL.createObjectURL(file);
  $('upload-thumbnail').src=thumbnailUrl;$('upload-thumbnail').hidden=false;$('generate').disabled=false;$('model-error').textContent='';
}
$('plan-file').addEventListener('change',e=>selectFile(e.target.files[0]));
const zone=$('upload-zone');
for(const type of ['dragenter','dragover'])zone.addEventListener(type,e=>{e.preventDefault();zone.classList.add('drag-over');});
for(const type of ['dragleave','drop'])zone.addEventListener(type,e=>{e.preventDefault();zone.classList.remove('drag-over');});
zone.addEventListener('drop',e=>selectFile(e.dataTransfer.files[0]));
$('load-sample').addEventListener('click',async()=>{
  try{const r=await fetch('/sample/input.png');selectFile(new File([await r.blob()],'示例户型.png',{type:'image/png'}));toast('示例已选中，点击“生成 3D 模型”开始。');}catch(e){toast('示例加载失败，请稍后重试。',true);}
});
$('model-form').addEventListener('submit',async event=>{
  event.preventDefault();if(!state.file)return;
  if(parameters().door_height>=parameters().wall_height){$('model-error').textContent='门高需要低于墙高。';return;}
  $('generate').disabled=true;$('model-error').textContent='';
  const form=new FormData();form.append('file',state.file);form.append('parameters',JSON.stringify(parameters()));
  try{const job=await api('/api/jobs',{method:'POST',body:form});await selectJob(job);await refreshJobs();}
  catch(e){$('model-error').textContent=e.message;}finally{$('generate').disabled=!state.file;}
});
async function refreshJobs(){
  if(!state.user)return;
  try{
    const data=await api('/api/jobs');state.jobs=data.jobs;renderHistory();
    const active=state.jobs.find(j=>j.id===state.active?.id);
    if(active && active.status!==state.active.status)await selectJob(active);
    clearTimeout(state.poll);
    if(state.jobs.some(j=>['queued','running'].includes(j.status)))state.poll=setTimeout(refreshJobs,1500);
  }catch(e){toast(e.message,true);}
}
function renderHistory(){
  $('history-count').textContent=state.jobs.length;$('history-list').replaceChildren();
  if(!state.jobs.length){const p=document.createElement('p');p.className='empty-history';p.textContent='生成的模型会保存在这里。';$('history-list').append(p);return;}
  for(const job of state.jobs){
    const button=document.createElement('button');button.type='button';button.className='history-item'+(state.active?.id===job.id?' active':'');
    const icon=document.createElement('span');icon.className='history-symbol';icon.textContent='⌑';icon.setAttribute('aria-hidden','true');
    const text=document.createElement('span');text.className='history-copy';
    const name=document.createElement('span');name.className='history-name';name.textContent=job.name;
    const meta=document.createElement('span');meta.className='history-meta';meta.textContent=new Date(job.created*1000).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})+' · '+({queued:'排队中',running:'生成中',done:'已完成',error:'需重试'}[job.status]);
    text.append(name,meta);const dot=document.createElement('span');dot.className='history-dot '+job.status;
    button.append(icon,text,dot);button.addEventListener('click',()=>selectJob(job).catch(e=>toast(e.message,true)));$('history-list').append(button);
  }
}
async function selectJob(job){
  const loadId=++state.loadId;state.active=job;state.plan=null;state.undo=[];state.start=null;state.dirty=false;
  saved('blueprint3d.active.'+state.user.username,job.id);setParameters(job.params);
  $('drawing-title').textContent=job.name;$('source-image').src='/api/jobs/'+job.id+'/files/input.png';
  const pending=['queued','running'].includes(job.status);$('progress').hidden=!pending;$('progress-title').textContent=job.status==='queued'?'任务已排队':'正在生成 3D 模型';
  $('downloads').hidden=job.status!=='done';$('status-badge').textContent={queued:'等待处理',running:'生成中',done:'已生成',error:'生成未完成'}[job.status];
  $('status-badge').classList.toggle('error',job.status==='error');$('viewer-error').hidden=true;$('viewer').hidden=job.status!=='done';
  $('result-meta').textContent='';$('result-note').textContent=job.status==='error'?job.error:pending?'模型生成完成后会自动显示，可以切换到原始图纸查看。':'';
  if(job.status!=='done')viewerError(pending?'正在把图纸转换为三维模型…':job.error);
  setView('model');renderHistory();
  if(job.status==='done'){
    const result=job.result;state.plan=result.plan?structuredClone(result.plan):null;
    if(state.plan){try{const draft=JSON.parse(saved(draftKey()));if(draft&&Array.isArray(draft.walls)&&Array.isArray(draft.doors)){Object.assign(state.plan,draft);state.dirty=true;}}catch{}}
    $('result-note').textContent=result.note;
    $('result-meta').textContent=`总宽 ${job.params.width_m} 米 · 墙高 ${job.params.wall_height} 米 · ${result.triangles.toLocaleString()} 个三角面`;
    $('download-glb').href='/api/jobs/'+job.id+'/files/model.glb';$('download-zip').href='/api/jobs/'+job.id+'/files/model.zip';
    $('cutaway').checked=false;
    try{await state.viewer?.load('/api/jobs/'+job.id+'/files/model.glb');if(loadId===state.loadId)$('viewer-error').hidden=true;}
    catch(e){viewerError(e.message);}
  }
}
function setView(view){
  for(const name of ['model','edit','image']){$(name+'-view').hidden=name!==view;$('tab-'+name).setAttribute('aria-selected',String(name===view));}
  $('view-actions').hidden=view!=='model';
  if(view==='model')state.viewer?.resize();
  if(view==='edit')prepareEditor();
}
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>setView(b.dataset.view)));
$('view-top').addEventListener('click',()=>state.viewer?.top());$('view-reset').addEventListener('click',()=>state.viewer?.reset());
$('cutaway').addEventListener('change',e=>state.viewer?.cut(e.target.checked));

const canvas=$('plan-editor'),ctx=canvas.getContext('2d');let editorImage=new Image(),mapping={scale:1,x:0,y:0},hover=null;
function prepareEditor(){
  const enabled=!!state.plan;$('edit-empty').hidden=enabled;for(const id of ['editor-tools','editor-stage','edit-hint'])$(id).hidden=!enabled;
  $('save-edit').disabled=!state.dirty;
  if(enabled){editorImage=new Image();editorImage.onload=drawEditor;editorImage.src='/api/jobs/'+state.active.id+'/files/input.png';drawEditor();}
}
function drawEditor(){
  if(!state.plan||$('edit-view').hidden)return;
  const stage=$('editor-stage'),w=stage.clientWidth,h=stage.clientHeight;
  if(!w||!h)return;
  const dpr=Math.min(devicePixelRatio,2);canvas.width=w*dpr;canvas.height=h*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
  const scale=Math.min((w-30)/state.plan.width,(h-24)/state.plan.height);mapping={scale,x:(w-state.plan.width*scale)/2,y:(h-state.plan.height*scale)/2};
  ctx.save();ctx.translate(mapping.x,mapping.y);ctx.scale(scale,scale);ctx.globalAlpha=.65;
  if(editorImage.complete&&editorImage.naturalWidth)ctx.drawImage(editorImage,0,0,state.plan.width,state.plan.height);
  ctx.globalAlpha=1;
  const line=(points,color,width,dash=[])=>{ctx.strokeStyle=color;ctx.lineWidth=width/scale;ctx.setLineDash(dash);ctx.beginPath();ctx.moveTo(...points[0]);ctx.lineTo(...points[1]);ctx.stroke();};
  for(const l of state.plan.walls)line(l,'#247ca6',2.5);
  for(const l of state.plan.doors)line(l,'#d09423',6);
  if(state.start){ctx.beginPath();ctx.fillStyle='#bd7c1f';ctx.arc(...state.start.point,5/scale,0,Math.PI*2);ctx.fill();if(hover)line([state.start.point,snapEnd(hover)],'#bd7c1f',2,[5/scale,5/scale]);}
  ctx.restore();
}
new ResizeObserver(drawEditor).observe($('editor-stage'));
function project(point,line){const a=line[0],b=line[1],dx=b[0]-a[0],dy=b[1]-a[1],t=Math.max(0,Math.min(1,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/(dx*dx+dy*dy)));return [a[0]+t*dx,a[1]+t*dy];}
function nearest(point,lines){let result=null;lines.forEach((line,index)=>{const p=project(point,line),distance=Math.hypot(p[0]-point[0],p[1]-point[1]);if(!result||distance<result.distance)result={point:p,distance,index,line};});return result;}
function imagePoint(event){const rect=canvas.getBoundingClientRect();return [Math.max(0,Math.min(state.plan.width,(event.clientX-rect.left-mapping.x)/mapping.scale)),Math.max(0,Math.min(state.plan.height,(event.clientY-rect.top-mapping.y)/mapping.scale))];}
function snapEnd(point){
  if(state.tool==='door'&&state.start.line)return project(point,state.start.line);
  const a=state.start.point;return Math.abs(point[0]-a[0])>Math.abs(point[1]-a[1])?[point[0],a[1]]:[a[0],point[1]];
}
function changed(){state.dirty=true;saved(draftKey(),JSON.stringify({walls:state.plan.walls,doors:state.plan.doors}));$('save-edit').disabled=false;drawEditor();}
function remember(){state.undo.push(structuredClone({walls:state.plan.walls,doors:state.plan.doors}));if(state.undo.length>50)state.undo.shift();}
canvas.addEventListener('pointermove',event=>{if(!state.plan)return;hover=imagePoint(event);if(state.start)drawEditor();});
canvas.addEventListener('pointerdown',event=>{
  if(!state.plan)return;event.preventDefault();const point=imagePoint(event);
  if(state.tool==='erase'){
    const walls=nearest(point,state.plan.walls),doors=nearest(point,state.plan.doors);const target=doors&&(!walls||doors.distance<=walls.distance+3/mapping.scale)?{...doors,kind:'doors'}:walls?{...walls,kind:'walls'}:null;
    if(target&&target.distance*mapping.scale<14){remember();state.plan[target.kind].splice(target.index,1);changed();}return;
  }
  if(!state.start){
    if(state.tool==='door'){const near=nearest(point,state.plan.walls);if(!near||near.distance*mapping.scale>20){toast('请在墙线上选择门洞起点。');return;}state.start={point:near.point,line:near.line};}
    else{let chosen=point;for(const line of state.plan.walls)for(const p of line)if(Math.hypot(p[0]-point[0],p[1]-point[1])*mapping.scale<9)chosen=p;state.start={point:[...chosen]};}
    drawEditor();return;
  }
  const end=snapEnd(point);if(Math.hypot(end[0]-state.start.point[0],end[1]-state.start.point[1])<3){state.start=null;drawEditor();return;}
  remember();state.plan[state.tool==='door'?'doors':'walls'].push([state.start.point,end]);state.start=null;changed();
});
document.querySelectorAll('[data-tool]').forEach(b=>b.addEventListener('click',()=>{state.tool=b.dataset.tool;state.start=null;document.querySelectorAll('[data-tool]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));$('edit-instruction').textContent=state.tool==='erase'?'点击墙线或门洞将其擦除。':state.tool==='door'?'在同一面墙上依次选择门洞的起点、终点。':'依次点击起点、终点。墙线自动吸附横竖方向。';drawEditor();}));
$('undo-edit').addEventListener('click',()=>{const prev=state.undo.pop();if(prev){Object.assign(state.plan,prev);state.start=null;changed();}});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){state.start=null;drawEditor();}});
$('save-edit').addEventListener('click',async()=>{
  if(!state.plan||!state.active)return;$('save-edit').disabled=true;
  try{const job=await api('/api/jobs/'+state.active.id+'/revise',{method:'POST',body:JSON.stringify({params:parameters(),walls:state.plan.walls,doors:state.plan.doors})});saved(draftKey(),null);await selectJob(job);await refreshJobs();}
  catch(e){toast(e.message,true);$('save-edit').disabled=false;}
});
try{const me=await api('/api/me');if(me.user)await enter(me.user);else showAuth();}catch(e){$('auth-error').textContent=e.message;}
