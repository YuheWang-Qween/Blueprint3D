import {ModelViewer} from './viewer.bundle.js';
import {FurnishingEditor} from './furnishing-editor.js?v=manual-drawing-1';
import {DecorationPanel} from './decoration.js';
import {PlanEditor} from './plan-editor.js';
import {blankPlan,validateDraft,DRAWING_UNITS} from './plan-geometry.js';
const $=id=>document.getElementById(id);
const state={user:null,register:false,file:null,fileUsedFor:null,active:null,jobs:[],viewer:null,plan:null,manual:false,mode:'upload',busy:false,dirty:false,poll:null,loadId:0};
let toastTimer,thumbnailUrl;
function saved(key,value){try{if(value===undefined)return localStorage.getItem(key);if(value===null)localStorage.removeItem(key);else localStorage.setItem(key,value);}catch{}return null;}
function draftKey(){return 'blueprint3d.draft.'+state.user.username+'.'+state.active.id;}

function toast(message,error=false){$('toast').textContent=message;$('toast').classList.toggle('error',error);$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,4500);}
async function api(path,options={}){
  const response=await fetch(path,{credentials:'same-origin',...options,headers:{'X-Blueprint-Request':'1',...(options.body && !(options.body instanceof FormData)?{'Content-Type':'application/json'}:{}),...options.headers}});
  const data=await response.json().catch(()=>({detail:'服务暂时不可用，请稍后重试。'}));
  if(!response.ok){const error=Error(typeof data.detail==='string'?data.detail:'请检查输入内容后重试。');error.status=response.status;throw error;}
  return data;
}
function parameters(){return {width_m:Number($('width-m').value),wall_height:Number($('wall-height').value),door_height:Number($('door-height').value),wall_thickness:Number($('wall-thickness').value),engine:$('engine').value};}
function setParameters(p){for(const [key,id] of Object.entries({width_m:'width-m',wall_height:'wall-height',door_height:'door-height',wall_thickness:'wall-thickness',engine:'engine'}))if(p[key]!==undefined)$(id).value=p[key];}
function showAuth(){
  furnishing.reset();state.loadId++;
  state.user=null;state.active=null;state.plan=null;state.jobs=[];clearTimeout(state.poll);
  state.manual=false;state.busy=false;setCreationMode('upload');planEditor.load(null);setDrawingState(false);
  $('studio').hidden=true;$('auth-screen').hidden=false;$('password').value='';$('confirm-password').value='';
  state.file=null;state.fileUsedFor=null;$('plan-file').value='';$('upload-title').textContent='上传户型图';$('upload-meta').textContent='PNG / JPG / WebP · 最大 12 MB';
  $('manual-name').value='手绘户型';$('depth-m').value=9;
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
    if(!state.viewer)state.viewer=new ModelViewer($('viewer'),{onSelect:id=>decoration.select(id),onSurface:(kind,id)=>decoration.selectSurface(kind,id),onNavigation:active=>decoration.navigationChanged(active)});
    await showSample();
  }catch(e){viewerError('三维显示不可用，请确认浏览器支持 WebGL。模型文件仍可下载。');}
  const info=await api('/api/me');
  const existing=$('engine').querySelector('option[value=neural]');
  if(info.neural_available && !existing){const option=document.createElement('option');option.value='neural';option.textContent='增强识别 · 神经网络分割';$('engine').append(option);}
  if(!info.neural_available && existing)existing.remove();
  await refreshJobs();
  const remembered=saved('blueprint3d.active.'+user.username);
  if(remembered==='manual'){beginManual();return;}
  const job=state.jobs.find(j=>j.id===remembered);
  if(job)await selectJob(job);
}
function viewerError(message){$('viewer-error').hidden=false;$('viewer-error').textContent=message;}
async function showSample(){
  furnishing.reset();
  state.active=null;state.plan=null;state.manual=false;setDrawingState(false);planEditor.load(null);updateGenerate();$('drawing-title').textContent='示例户型';$('status-badge').textContent='可旋转查看';$('status-badge').classList.remove('error');
  $('result-note').textContent='示例已按原图核对，尺寸为估算值。可以上传户型图识别，也可以现场绘制。';
  $('result-meta').textContent='墙高 2.8 米 · 6 处平开门 · 1 处推拉隔断';
  $('source-image').src='/sample/input.png';$('viewer').hidden=false;$('viewer-error').hidden=true;$('downloads').hidden=true;$('progress').hidden=true;
  $('cutaway').checked=false;setView('model');await state.viewer?.load('/sample/model.glb');
}
function selectFile(file){
  if(!file)return;
  if(file.size>12*1024*1024){toast('图片不能超过 12 MB。',true);return;}
  setCreationMode('upload');
  state.file=file;state.fileUsedFor=null;$('upload-title').textContent=file.name;$('upload-meta').textContent=(file.size/1024).toFixed(0)+' KB · 点击更换';
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
  event.preventDefault();await generateModel();
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
  furnishing.reset();
  const loadId=++state.loadId;state.active=job;state.plan=null;state.manual=false;state.dirty=false;setDrawingState(false);planEditor.load(null);
  saved('blueprint3d.active.'+state.user.username,job.id);setParameters(job.params);
  $('generate').disabled=!state.file;
  $('drawing-title').textContent=job.name;$('source-image').src='/api/jobs/'+job.id+'/files/input.png';
  const pending=['queued','running'].includes(job.status);$('progress').hidden=!pending;$('progress-title').textContent=job.status==='queued'?'任务已排队':'正在生成 3D 模型';
  $('downloads').hidden=job.status!=='done';$('status-badge').textContent={queued:'等待处理',running:'生成中',done:'已生成',error:'生成未完成'}[job.status];
  $('status-badge').classList.toggle('error',job.status==='error');$('viewer-error').hidden=true;$('viewer').hidden=job.status!=='done';
  $('result-meta').textContent='';$('result-note').textContent=job.status==='error'?job.error:pending?'模型生成完成后会自动显示，可以切换到原始图纸查看。':'';
  if(job.status!=='done')viewerError(pending?'正在把图纸转换为三维模型…':job.error);
  setView('model');renderHistory();
  if(job.status==='done'){
    const result=job.result;state.plan=result.plan?structuredClone(result.plan):null;
    const manual=state.plan?.source==='manual';setCreationMode(manual?'manual':'upload');
    $('tab-edit').textContent=manual?'绘制平面':'校正平面';$('tab-image').textContent=manual?'手绘图纸':'原始图纸';
    if(manual){$('manual-name').value=job.name;$('manual-name').disabled=true;$('depth-m').value=Number((state.plan.height*job.params.width_m/state.plan.width).toFixed(2));$('depth-m').disabled=true;}
    if(state.plan){try{const draft=JSON.parse(saved(draftKey()));if(draft&&Array.isArray(draft.walls)&&Array.isArray(draft.doors)){Object.assign(state.plan,draft);state.dirty=true;}}catch{}}
    $('generate').disabled=!state.file&&!state.plan;
    $('result-note').textContent=result.note;
    const size=manual?`画布 ${job.params.width_m} × ${$('depth-m').value} 米`:`总宽 ${job.params.width_m} 米`;
    $('result-meta').textContent=`${size} · 墙高 ${job.params.wall_height} 米 · ${result.triangles.toLocaleString()} 个三角面`;
    $('download-glb').href='/api/jobs/'+job.id+'/files/model.glb';$('download-zip').href='/api/jobs/'+job.id+'/files/model.zip';
    $('cutaway').checked=false;
    const layoutReady=furnishing.load(job,state.user.username);
    try{await state.viewer?.load('/api/jobs/'+job.id+'/files/model.glb');if(loadId===state.loadId)$('viewer-error').hidden=true;}
    catch(e){viewerError(e.message);}
    await layoutReady;
  }
  updateGenerate();
}
function setView(view){
  if(state.manual&&view!=='edit')return;
  const wasFurnishing=document.querySelector('.work-layout').classList.contains('furnish-focus');
  for(const name of ['model','furnish','edit','image']){$(name+'-view').hidden=name!==view;$('tab-'+name).setAttribute('aria-selected',String(name===view));}
  document.querySelector('.work-layout').classList.toggle('furnish-focus',view==='furnish');
  $('view-actions').hidden=view!=='model';
  decoration.setVisible(view==='model');
  if(view==='model')state.viewer?.resize();
  if(view==='edit')prepareEditor();
  if(view==='furnish')furnishing.fit();
  if(innerWidth<=760&&(view==='furnish'||wasFurnishing||(state.manual&&view==='edit')))document.querySelector('.drawing-heading').scrollIntoView({block:'start'});
}
const furnishing=new FurnishingEditor({api,viewer:()=>state.viewer,toast,showModel:()=>{
  setView('model');$('cutaway').checked=true;state.viewer?.cut(true);decoration.setMode(true);
}});
const decoration=new DecorationPanel({editor:furnishing,viewer:()=>state.viewer,toast,showPlan:()=>setView('furnish')});
furnishing.onUpdate=()=>{
  if(!$('furnish-view').hidden&&furnishing.selected){decoration.kind='furniture';decoration.surfaceId=null;}
  decoration.refresh();
};
furnishing.onStatus=(message,error)=>decoration.status(message,error);furnishing.onReset=()=>decoration.reset();
furnishing.onPreview=()=>decoration.syncSelection();
$('furnish-start').addEventListener('click',()=>{setView('model');$('load-sample').click();$('generate').scrollIntoView({block:'center'});});
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>setView(b.dataset.view)));
$('view-top').addEventListener('click',()=>state.viewer?.top());$('view-reset').addEventListener('click',()=>state.viewer?.reset());
$('cutaway').addEventListener('change',e=>state.viewer?.cut(e.target.checked));

const planEditor=new PlanEditor({widthM:()=>parameters().width_m,onChange:changed,toast});
function manualKey(){return 'blueprint3d.manual.'+state.user.username;}
function setDrawingState(active){
  document.querySelector('.work-layout').classList.toggle('drawing-active',active);
  for(const id of ['tab-model','tab-furnish','tab-image'])$(id).disabled=active;
  $('tab-edit').textContent=active?'绘制平面':'校正平面';
  $('tab-image').textContent='原始图纸';
}
function setCreationMode(mode){
  state.mode=mode;const manual=mode==='manual';
  $('mode-upload').setAttribute('aria-pressed',String(!manual));$('mode-manual').setAttribute('aria-pressed',String(manual));
  $('upload-fields').hidden=manual;$('manual-fields').hidden=!manual;$('depth-field').hidden=!manual;$('engine-field').hidden=manual;$('load-sample').hidden=manual;
  const existingManual=manual&&!state.manual&&state.active?.result?.plan?.source==='manual';
  $('depth-m').disabled=!manual||existingManual;$('depth-m').required=manual;$('manual-name').required=manual;$('manual-name').disabled=!!existingManual;
  $('width-label').textContent=manual?'画布宽度':'户型总宽';
  $('source-hint').textContent=manual?'先画闭合外墙，再加隔墙、标门洞。按画布标尺生成真实比例。':'没有标注尺寸时，先输入估算值。生成后对照原图核对墙线和门洞。';
  $('start-manual').textContent=state.manual?'回到绘图':state.user&&saved(manualKey())?'继续手绘草稿':'开始绘制';
  $('manual-status').textContent=state.manual?'草稿已保存在此浏览器。':'';
  updateGenerate();
}
$('mode-manual').addEventListener('click',()=>setCreationMode('manual'));
$('mode-upload').addEventListener('click',async()=>{
  if(state.manual){stashManual();saved('blueprint3d.active.'+state.user.username,null);await showSample();}
  setCreationMode('upload');
});
$('start-manual').addEventListener('click',()=>beginManual());
function stashManual(){
  if(!state.manual||!state.plan||!state.user)return;
  const data={version:1,name:$('manual-name').value.trim()||'手绘户型',params:{...parameters(),engine:'linework'},depth_m:Number($('depth-m').value),walls:state.plan.walls,doors:state.plan.doors};
  try{localStorage.setItem(manualKey(),JSON.stringify(data));$('manual-status').textContent='草稿已保存在此浏览器。';}
  catch{$('manual-status').textContent='浏览器未能保存草稿，请保持页面打开并及时生成模型。';}
}
function beginManual(){
  if(state.manual){setView('edit');return;}
  let draft;
  try{draft=JSON.parse(saved(manualKey()));if(draft)validateDraft(draft);}catch{draft=null;toast('手绘草稿无法读取，已打开空白画布。',true);}
  if(draft){setParameters(draft.params);$('depth-m').value=draft.depth_m;$('manual-name').value=draft.name;}
  setCreationMode('manual');$('engine').value='linework';
  if(!$('model-form').reportValidity())return;
  furnishing.reset();state.loadId++;state.active=null;state.manual=true;state.plan=draft?validateDraft(draft):blankPlan(parameters().width_m,Number($('depth-m').value));state.dirty=!!state.plan.walls.length;
  state.file=null;state.fileUsedFor=null;$('plan-file').value='';$('upload-thumbnail').hidden=true;$('upload-title').textContent='选择或拖入户型图';
  saved('blueprint3d.active.'+state.user.username,'manual');setCreationMode('manual');setDrawingState(true);
  $('drawing-title').textContent=$('manual-name').value.trim()||'手绘户型';$('status-badge').textContent='绘制中';$('status-badge').classList.remove('error');
  $('downloads').hidden=true;$('progress').hidden=true;$('model-error').textContent='';$('result-meta').textContent='';
  $('result-note').textContent='手绘草稿保存在此浏览器；生成模型后保存到当前账户。';
  setView('edit');planEditor.setTool('rectangle');stashManual();updateGenerate();renderHistory();
}
function updateGenerate(){
  const ready=state.active?.status==='done'&&state.plan;
  const pending=['queued','running'].includes(state.active?.status);
  const fresh=state.file&&(!pending||state.fileUsedFor!==state.active?.id);
  const allowed=state.manual?state.plan?.walls.length>=3:state.mode==='manual'?ready&&state.plan.source==='manual':fresh||(ready&&state.plan.source!=='manual');
  $('generate').disabled=state.busy||!allowed;
  $('save-edit').disabled=state.busy||!(state.manual?state.plan?.walls.length>=3:ready&&state.dirty);
  $('save-edit').textContent=state.manual?'生成 3D 模型':'更新 3D 模型';
}
function prepareEditor(){
  const enabled=!!state.plan;$('edit-empty').hidden=enabled;
  for(const id of ['editor-tools','editor-stage','editor-ruler','edit-hint'])$(id).hidden=!enabled;
  planEditor.load(state.plan,state.plan?.source==='manual'||!state.active?null:'/api/jobs/'+state.active.id+'/files/input.png');updateGenerate();
}
function changed(){
  state.dirty=true;
  if(state.manual){$('width-m').value=state.plan.width/DRAWING_UNITS;$('depth-m').value=state.plan.height/DRAWING_UNITS;stashManual();}
  else if(state.active&&state.user)saved(draftKey(),JSON.stringify({walls:state.plan.walls,doors:state.plan.doors}));
  updateGenerate();
}
$('manual-name').addEventListener('input',()=>{if(state.manual){$('drawing-title').textContent=$('manual-name').value.trim()||'手绘户型';stashManual();}});
for(const id of ['width-m','depth-m','wall-height','door-height','wall-thickness'])$(id).addEventListener('change',()=>{
  if(state.manual){
    const width=Number($('width-m').value),depth=Number($('depth-m').value);
    if(width<2||width>100||depth<2||depth>100||!Number.isFinite(width+depth))return;
    if([...state.plan.walls,...state.plan.doors].some(line=>line.some(p=>p[0]>width*DRAWING_UNITS||p[1]>depth*DRAWING_UNITS))){
      $('width-m').value=state.plan.width/DRAWING_UNITS;$('depth-m').value=state.plan.height/DRAWING_UNITS;toast('新画布尺寸会截断已画墙线，请先移动或擦除超出的墙线。',true);return;
    }
    if(state.plan.width!==width*DRAWING_UNITS||state.plan.height!==depth*DRAWING_UNITS)planEditor.change(()=>{state.plan.width=width*DRAWING_UNITS;state.plan.height=depth*DRAWING_UNITS;});
    else stashManual();
    planEditor.fit();
  }else{if(state.plan?.source==='manual')$('depth-m').value=Number((state.plan.height*parameters().width_m/state.plan.width).toFixed(2));planEditor.draw();}
});
async function generateModel(reviseOnly=false){
  if(state.busy||!$('model-form').reportValidity())return;
  const reviseReady=state.active?.status==='done'&&state.plan;
  const useFresh=!reviseOnly&&state.mode==='upload'&&state.file&&(state.fileUsedFor!==state.active?.id||!reviseReady);
  if(!state.manual&&!useFresh&&!reviseReady)return;
  const params=parameters();if(params.door_height>=params.wall_height){$('model-error').textContent='门高需要低于墙高。';toast('门高需要低于墙高。',true);return;}
  if(state.manual&&state.plan.walls.length<3){toast('请先闭合外墙或画出一个完整房间。',true);return;}
  const oldDraft=state.active&&state.user?draftKey():null,previous=state.active?.id;
  state.busy=true;updateGenerate();$('model-error').textContent='';
  try{
    let job;
    if(state.manual){
      stashManual();job=await api('/api/jobs/manual',{method:'POST',body:JSON.stringify({name:$('manual-name').value.trim()||'手绘户型',depth_m:Number($('depth-m').value),params:{...params,engine:'linework'},walls:state.plan.walls,doors:state.plan.doors})});
    }else if(useFresh){
      const form=new FormData();form.append('file',state.file);form.append('parameters',JSON.stringify(params));
      job=await api('/api/jobs',{method:'POST',body:form});state.fileUsedFor=job.id;
    }else{
      job=await api('/api/jobs/'+previous+'/revise',{method:'POST',body:JSON.stringify({params,walls:state.plan.walls,doors:state.plan.doors})});
      if(state.fileUsedFor===previous)state.fileUsedFor=job.id;
      if(oldDraft)saved(oldDraft,null);
    }
    await selectJob(job);await refreshJobs();
  }catch(e){$('model-error').textContent=e.message;toast(e.message,true);}
  finally{state.busy=false;updateGenerate();}
}
$('save-edit').addEventListener('click',()=>generateModel(true));
try{const me=await api('/api/me');if(me.user)await enter(me.user);else showAuth();}catch(e){$('auth-error').textContent=e.message;}
