import {emptyLayout,angle,extent,fitItem,contains,meshBounds,validateLayout,drawFurniture} from './furniture.js';
import {setSurfaceStyle,surfaceStyle} from './surface-finishes.js';
import {planToWorld} from './plan-geometry.js';

const $=id=>document.getElementById(id);
const clone=value=>structuredClone(value);
const content=layout=>JSON.stringify({items:layout.items,finishes:layout.finishes});
function download(blob,name){
  const url=URL.createObjectURL(blob),link=document.createElement('a');
  link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),30000);
}

export class FurnishingEditor {
  constructor({api,viewer,toast,showModel}){
    Object.assign(this,{api,viewer,toast,showModel});
    this.canvas=$('furnish-canvas');this.ctx=this.canvas.getContext('2d');
    this.document=emptyLayout();this.catalog=[];this.history=[];this.future=[];this.token=0;
    this.view={scale:1,x:0,y:0};this.ready=false;this.selected=null;this.pending=null;
    this.catalogPromise=fetch('/static/furniture-catalog.json').then(r=>{if(!r.ok)throw Error('设施库加载失败，请刷新重试。');return r.json();});
    this.catalogPromise.catch(()=>{});
    new ResizeObserver(()=>{if(this.ready&&!$('furnish-view').hidden)this.fit();}).observe($('furnish-stage'));
    $('furniture-category').addEventListener('change',()=>this.renderCatalog());
    $('furniture-properties').addEventListener('submit',event=>{
      event.preventDefault();const item=this.selection();if(!item)return;
      const next={...item};for(const key of ['width','depth','height','rotation'])next[key]=Number($('furniture-'+key).value);
      next.color=$('furniture-color').value;
      if(!fitItem(next,this.bounds)){this.toast('设施大于户型范围，请缩小尺寸。',true);return;}
      try{validateLayout({...this.document,items:[next]},this.catalog,this.bounds);}catch(e){this.toast(e.message,true);return;}
      this.change(()=>Object.assign(item,next));
    });
    $('furniture-rotate').addEventListener('click',()=>this.rotate());
    $('furniture-copy').addEventListener('click',()=>this.duplicate());
    $('furniture-delete').addEventListener('click',()=>this.remove());
    for(const kind of ['floor','wall'])$(kind+'-finish').addEventListener('change',e=>this.change(()=>{this.document.finishes=setSurfaceStyle(this.document.finishes,kind,null,null);this.document.finishes[kind]=e.target.value;}));
    $('furnish-undo').addEventListener('click',()=>this.undo());$('furnish-redo').addEventListener('click',()=>this.undo(true));
    $('furnish-fit').addEventListener('click',()=>this.fit());
    $('furnish-zoom-in').addEventListener('click',()=>this.zoom(1.25));$('furnish-zoom-out').addEventListener('click',()=>this.zoom(.8));
    $('furnish-grid').addEventListener('change',()=>this.draw());
    $('furnish-save').addEventListener('click',async()=>{if(await this.flush())this.toast('布置方案已保存。');});
    $('furnish-reload').addEventListener('click',()=>{if(this.job)this.load(this.job,this.user,true);});
    $('furnish-to-3d').addEventListener('click',()=>{this.viewer()?.setLayout(this.document,this.catalog);this.showModel();});
    $('furnish-export-json').addEventListener('click',()=>this.exportJSON());
    $('furnish-import').addEventListener('click',()=>$('furnish-import-file').click());
    $('furnish-import-file').addEventListener('change',e=>this.importJSON(e.target.files[0]));
    $('furnish-export-glb').addEventListener('click',()=>this.exportGLB());
    this.canvas.addEventListener('pointerdown',e=>this.pointerDown(e));
    this.canvas.addEventListener('pointermove',e=>this.pointerMove(e));
    this.canvas.addEventListener('pointerup',()=>this.pointerUp());
    this.canvas.addEventListener('pointercancel',()=>this.pointerUp(true));
    this.canvas.addEventListener('lostpointercapture',()=>{if(this.drag)this.pointerUp(true);});
    this.canvas.addEventListener('contextmenu',e=>e.preventDefault());
    this.canvas.addEventListener('wheel',e=>{if(!this.ready)return;e.preventDefault();const r=this.canvas.getBoundingClientRect();this.zoom(Math.exp(-e.deltaY*.0015),e.clientX-r.left,e.clientY-r.top);},{passive:false});
    this.canvas.addEventListener('dragover',e=>{if(this.ready){e.preventDefault();e.dataTransfer.dropEffect='copy';}});
    this.canvas.addEventListener('drop',e=>{e.preventDefault();if(!this.ready)return;const type=e.dataTransfer.getData('application/x-blueprint-furniture');if(this.catalog.some(c=>c.id===type))this.add(type,this.point(e));});
    document.addEventListener('keydown',e=>this.key(e));
    document.addEventListener('keyup',e=>{if(e.code==='Space')this.space=false;});
    window.addEventListener('blur',()=>{this.space=false;this.pointerUp(true);});
  }
  storageKey(){return `blueprint3d.layout.${this.user}.${this.job.id}`;}
  stash(){
    if(!this.job||!this.user)return;
    try{if(this.dirty)localStorage.setItem(this.storageKey(),JSON.stringify(this.document));else localStorage.removeItem(this.storageKey());}catch{}
  }
  reset(){
    this.token++;clearTimeout(this.saveTimer);this.ready=false;this.job=null;this.user=null;this.drag=null;this.selected=null;this.pending=null;
    this.document=emptyLayout();this.dirty=false;this.saving=null;this.blocked=false;this.history=[];this.future=[];
    this.surfaces=[];this.surfacePaths=[];this.viewer()?.setSurfaces([]);
    this.viewer()?.setLayout(null,[]);$('furnish-workspace').hidden=true;$('furnish-empty').hidden=false;
    $('furnish-empty-text').textContent='生成模型后，即可放入床、沙发、橱柜和卫浴设施。';$('furnish-start').hidden=false;
    this.onReset?.();
  }
  async load(job,user,discardDraft=false){
    this.reset();this.job=job;this.user=user;
    if(!job||job.status!=='done')return;
    const token=this.token;$('furnish-empty-text').textContent='正在读取户型与布置方案…';$('furnish-start').hidden=true;
    try{
      const [catalog,meshes,document,surfaces]=await Promise.all([this.catalogPromise,this.api(`/api/jobs/${job.id}/files/mesh.json`),this.api(`/api/jobs/${job.id}/layout`),this.api(`/api/jobs/${job.id}/surfaces`)]);
      if(token!==this.token)return;
      this.catalog=catalog;this.meshes=meshes;this.bounds=meshBounds(meshes);this.document={...validateLayout(document,catalog,this.bounds),revision:document.revision};
      this.surfaces=surfaces.surfaces;this.viewer()?.setSurfaces(this.surfaces);
      this.surfacePaths=this.surfaces.filter(s=>s.kind==='floor').map(part=>{
        const path=new Path2D();for(let i=0;i<part.indices.length;i+=3){
          const vertices=part.indices.slice(i,i+3).map(n=>[part.positions[n*3],part.positions[n*3+2]]);
          path.moveTo(...vertices[0]);path.lineTo(...vertices[1]);path.lineTo(...vertices[2]);path.closePath();
        }return {part,path};
      });
      this.paths=meshes.map(mesh=>{
        const path=new Path2D(),p=mesh.positions;
        for(let i=0;i<mesh.indices.length;i+=3){
          const [a,b,c]=mesh.indices.slice(i,i+3).map(index=>[p[index*3],-p[index*3+1]]);
          const winding=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
          if(Math.abs(winding)<.000001)continue;
          // Top and underside triangles project onto the same footprint. Keep
          // one winding so the canvas nonzero fill does not cancel the floor.
          path.moveTo(...a);path.lineTo(...(winding>0?b:c));path.lineTo(...(winding>0?c:b));path.closePath();
        }
        return {path,kind:mesh.kind};
      }).sort((a,b)=>(a.kind==='floor'?-1:1)-(b.kind==='floor'?-1:1));
      this.prepareWalls(job);
      let draft=null;
      try{draft=JSON.parse(localStorage.getItem(this.storageKey()));if(discardDraft){localStorage.removeItem(this.storageKey());draft=null;}}catch{}
      if(draft){
        try{
          const valid=validateLayout(draft,catalog,this.bounds);this.dirty=content(valid)!==content(this.document);this.document={...valid,revision:document.revision};
          if(this.dirty&&draft.revision!==document.revision)this.blocked=true;
        }catch{this.toast('本机旧草稿格式无效，已读取服务器保存的方案。',true);}
      }
      this.ready=true;$('furnish-workspace').hidden=false;$('furnish-empty').hidden=true;
      this.renderCatalog();this.refresh();this.fit();this.preview();
      if(this.blocked)this.status('其他页面已更新；可先导出本机方案，再重新读取。',true);
      else if(this.dirty){this.status('已恢复本机草稿');this.scheduleSave();}
      else this.status('已保存到当前账户');
    }catch(e){if(token===this.token){$('furnish-empty-text').textContent=e.message;this.toast(e.message,true);}}
  }
  prepareWalls(job){
    this.walls=[];this.doors=[];
    const plan=job.result?.plan;if(!plan)return;
    Object.assign(this,planToWorld(plan,job.params.width_m));
  }
  selection(){return this.document.items.find(item=>item.id===this.selected);}
  status(message,error=false){$('furnish-status').textContent=message;$('furnish-status').classList.toggle('save-error',error);$('furnish-reload').hidden=!this.blocked;this.onStatus?.(message,error);}
  renderCatalog(){
    const group=$('furniture-category').value,host=$('furniture-catalog');host.replaceChildren();
    for(const definition of this.catalog.filter(c=>group==='all'||c.category===group)){
      const button=document.createElement('button');button.type='button';button.className='furniture-card';button.draggable=true;
      button.dataset.type=definition.id;button.setAttribute('aria-label','放置'+definition.name);button.setAttribute('aria-pressed',String(this.pending===definition.id));
      const icon=document.createElement('canvas');icon.width=116;icon.height=100;icon.setAttribute('aria-hidden','true');
      const ctx=icon.getContext('2d'),s=Math.min(92/definition.width,80/definition.depth);ctx.translate(58,50);ctx.scale(s,s);
      drawFurniture(ctx,{...definition,x:0,z:0,rotation:0},definition,s/2);
      const name=document.createElement('strong');name.textContent=definition.name;
      const dimensions=document.createElement('span');dimensions.textContent=`${Math.round(definition.width*1000)} × ${Math.round(definition.depth*1000)}`;
      button.append(icon,name,dimensions);
      button.addEventListener('click',()=>{this.pending=this.pending===definition.id?null:definition.id;this.refresh();});
      button.addEventListener('dragstart',e=>{e.dataTransfer.setData('application/x-blueprint-furniture',definition.id);e.dataTransfer.effectAllowed='copy';this.pending=null;this.refresh();});
      host.append(button);
    }
  }
  refresh(){
    const item=this.selection(),definition=this.catalog.find(c=>c.id===item?.type);
    $('furnish-count').textContent=`${this.document.items.length} 件设施`;$('placed-total').textContent=this.document.items.length;
    $('selection-empty').hidden=!!item;$('furniture-properties').hidden=!item;
    $('selected-name').textContent=definition?.name||'设施属性';$('selected-tag').textContent=definition?.category||'';
    if(item){for(const key of ['width','depth','height','rotation','color'])$('furniture-'+key).value=item[key];}
    for(const kind of ['floor','wall'])$(kind+'-finish').value=this.document.finishes[kind];
    $('furnish-undo').disabled=!this.history.length;$('furnish-redo').disabled=!this.future.length;
    $('placed-items').replaceChildren();
    if(!this.document.items.length){const p=document.createElement('p');p.className='muted-copy';p.textContent='从左侧设施库开始。';$('placed-items').append(p);}
    this.document.items.forEach((item,index)=>{
      const button=document.createElement('button');button.className='placed-item';button.type='button';button.setAttribute('aria-pressed',String(this.selected===item.id));
      button.textContent=`${index+1}. ${this.catalog.find(c=>c.id===item.type).name}`;const size=document.createElement('span');size.textContent=`${item.width} × ${item.depth} m`;button.append(size);
      button.addEventListener('click',()=>{this.selected=item.id;this.pending=null;this.refresh();this.draw();});$('placed-items').append(button);
    });
    const pending=this.catalog.find(c=>c.id===this.pending);
    $('placement-prompt').hidden=!pending;$('placement-prompt').textContent=pending?`点击图纸放置${pending.name} · Esc 取消`:'';
    this.canvas.style.cursor=pending?'crosshair':'default';
    document.querySelectorAll('.furniture-card').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.type===this.pending)));
    this.draw();
    this.onUpdate?.();
  }
  remember(snapshot){this.history.push(snapshot);if(this.history.length>60)this.history.shift();this.future=[];}
  change(action){
    if(!this.ready)return;const before=content(this.document);action();
    if(before!==content(this.document)){this.remember(JSON.parse(before));this.changed();}else this.refresh();
  }
  changed(){this.dirty=true;this.stash();this.refresh();this.preview();this.status(this.blocked?'服务器方案已更新，请先导出本机方案再重新读取。':'等待保存…',this.blocked);this.scheduleSave();}
  preview(){this.viewer()?.setLayout(this.document,this.catalog);this.viewer()?.select(this.selected);this.onPreview?.();}
  scheduleSave(){clearTimeout(this.saveTimer);if(!this.blocked&&!this.drag)this.saveTimer=setTimeout(()=>this.save(),800);}
  async flush(){
    const token=this.token;
    while(this.ready&&token===this.token&&this.dirty){if(!await this.save())return false;}
    return this.ready&&token===this.token;
  }
  async save(){
    if(!this.ready)return false;if(!this.dirty)return true;if(this.blocked){this.status('方案有更新冲突，请先导出本机方案再重新读取。',true);return false;}
    if(this.saving)return this.saving;
    clearTimeout(this.saveTimer);const token=this.token,job=this.job,snapshot=clone(this.document),serialized=content(snapshot);
    this.status('正在保存…');
    this.saving=(async()=>{
      try{
        const response=await this.api(`/api/jobs/${job.id}/layout`,{method:'PUT',body:JSON.stringify(snapshot)});
        if(token!==this.token)return false;
        this.document.revision=response.revision;this.dirty=content(this.document)!==serialized;this.stash();
        this.status(this.dirty?'等待保存…':'已保存到当前账户');if(this.dirty)this.scheduleSave();return true;
      }catch(e){
        if(token===this.token){this.blocked=e.status===409;this.stash();this.status(this.blocked?e.message:'保存失败，本机草稿已保留。'+e.message,true);}return false;
      }finally{if(token===this.token)this.saving=null;}
    })();
    return this.saving;
  }
  add(type,point){
    if(this.document.items.length>=200){this.toast('每份方案最多放置 200 件设施。',true);return;}
    const source=this.catalog.find(c=>c.id===type),item={id:crypto.randomUUID(),type,x:point.x,z:point.z,width:source.width,depth:source.depth,height:source.height,rotation:0,color:source.color};
    this.snap(item);if(!fitItem(item,this.bounds)){this.toast('设施大于户型范围，请先选择较小的设施。',true);return;}
    this.change(()=>{this.document.items.push(item);this.selected=item.id;this.pending=null;});this.canvas.focus({preventScroll:true});
  }
  rotate(){const item=this.selection();if(!item)return;const next={...item,rotation:angle(item.rotation+90)};if(!fitItem(next,this.bounds)){this.toast('旋转后超出户型范围，请缩小设施。',true);return;}this.change(()=>Object.assign(item,next));}
  duplicate(){const item=this.selection();if(!item||this.document.items.length>=200)return;const next={...item,id:crypto.randomUUID(),x:item.x+.25,z:item.z+.25};fitItem(next,this.bounds);this.change(()=>{this.document.items.push(next);this.selected=next.id;});}
  remove(){if(this.selection())this.change(()=>{this.document.items=this.document.items.filter(item=>item.id!==this.selected);this.selected=null;});}
  undo(redo=false){
    const from=redo?this.future:this.history,to=redo?this.history:this.future;if(!from.length)return;
    to.push(JSON.parse(content(this.document)));Object.assign(this.document,from.pop());
    if(!this.selection())this.selected=null;this.pending=null;this.changed();
  }
  snap(item){
    if(!$('furnish-snap').checked)return;
    item.x=Math.round(item.x*10)/10;item.z=Math.round(item.z*10)/10;
    const e=extent(item),half=this.job.params.wall_thickness/2;
    let bestX=.14,bestZ=.14,x=item.x,z=item.z;
    for(const [a,b] of this.walls){
      if(Math.abs(a[0]-b[0])<.01 && item.z+e.z>Math.min(a[1],b[1]) && item.z-e.z<Math.max(a[1],b[1])){
        for(const target of [a[0]-half-e.x,a[0]+half+e.x])if(Math.abs(item.x-target)<bestX){bestX=Math.abs(item.x-target);x=target;}
      }
      if(Math.abs(a[1]-b[1])<.01 && item.x+e.x>Math.min(a[0],b[0]) && item.x-e.x<Math.max(a[0],b[0])){
        for(const target of [a[1]-half-e.z,a[1]+half+e.z])if(Math.abs(item.z-target)<bestZ){bestZ=Math.abs(item.z-target);z=target;}
      }
    }
    item.x=x;item.z=z;
  }
  point(e){const r=this.canvas.getBoundingClientRect();return {x:(e.clientX-r.left-this.view.x)/this.view.scale,z:(e.clientY-r.top-this.view.y)/this.view.scale};}
  pointerDown(e){
    if(!this.ready)return;e.preventDefault();this.canvas.focus({preventScroll:true});const p=this.point(e);
    if(e.button!==0||this.space){this.drag={pan:true,px:e.clientX,py:e.clientY,view:{...this.view}};this.canvas.setPointerCapture(e.pointerId);return;}
    if(this.pending){this.add(this.pending,p);return;}
    const item=[...this.document.items].reverse().find(item=>contains(item,p.x,p.z));this.selected=item?.id||null;this.refresh();
    if(item){clearTimeout(this.saveTimer);this.drag={id:item.id,offsetX:item.x-p.x,offsetZ:item.z-p.z,before:content(this.document)};this.canvas.setPointerCapture(e.pointerId);}
  }
  pointerMove(e){
    if(!this.drag)return;
    if(this.drag.pan){this.view.x=this.drag.view.x+e.clientX-this.drag.px;this.view.y=this.drag.view.y+e.clientY-this.drag.py;this.draw();return;}
    const item=this.selection();if(!item)return;const p=this.point(e);item.x=p.x+this.drag.offsetX;item.z=p.z+this.drag.offsetZ;this.snap(item);fitItem(item,this.bounds);this.draw();
  }
  pointerUp(cancel=false){
    if(!this.drag)return;const drag=this.drag;this.drag=null;
    if(drag.pan)return;
    if(cancel){Object.assign(this.document,JSON.parse(drag.before));this.changed();return;}
    if(drag.before!==content(this.document)){this.remember(JSON.parse(drag.before));this.changed();}
    else if(this.dirty)this.scheduleSave();
  }
  key(e){
    if(!this.ready||$('furnish-view').hidden||e.target.closest('input,select,textarea'))return;
    if(e.code==='Space'){if(e.target.closest('button'))return;e.preventDefault();this.space=true;return;}
    if(e.key==='Escape'){this.pending=null;this.selected=null;this.refresh();return;}
    if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='z'){e.preventDefault();this.undo(e.shiftKey);return;}
    if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='d'){e.preventDefault();this.duplicate();return;}
    if(e.key.toLowerCase()==='r'){e.preventDefault();this.rotate();return;}
    if(['Delete','Backspace'].includes(e.key)){e.preventDefault();this.remove();return;}
    if(e.key.startsWith('Arrow')&&this.selection()){
      e.preventDefault();const item=this.selection(),step=e.shiftKey ? .1 : .01;
      this.change(()=>{item.x+=e.key==='ArrowRight'?step:e.key==='ArrowLeft'?-step:0;item.z+=e.key==='ArrowDown'?step:e.key==='ArrowUp'?-step:0;fitItem(item,this.bounds);});
    }
  }
  fit(){
    if(!this.ready)return;const w=this.canvas.clientWidth,h=this.canvas.clientHeight;if(!w||!h)return;
    const b=this.bounds,scale=Math.min((w-80)/(b.maxX-b.minX),(h-70)/(b.maxZ-b.minZ));
    this.baseScale=scale;this.view={scale,x:(w-(b.maxX+b.minX)*scale)/2,y:(h-(b.maxZ+b.minZ)*scale)/2};this.draw();
  }
  zoom(factor,x=this.canvas.clientWidth/2,y=this.canvas.clientHeight/2){
    if(!this.ready)return;const old=this.view.scale,next=Math.max(this.baseScale*.5,Math.min(this.baseScale*6,old*factor));
    this.view.x=x-(x-this.view.x)*next/old;this.view.y=y-(y-this.view.y)*next/old;this.view.scale=next;this.draw();
  }
  draw(){
    if(!this.ready||$('furnish-view').hidden)return;
    const w=this.canvas.clientWidth,h=this.canvas.clientHeight;if(!w||!h)return;
    const dpr=Math.min(devicePixelRatio,2),ctx=this.ctx,{scale,x,y}=this.view,b=this.bounds;
    this.canvas.width=w*dpr;this.canvas.height=h*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.fillStyle='#f5f6f3';ctx.fillRect(0,0,w,h);
    ctx.save();ctx.translate(x,y);ctx.scale(scale,scale);
    if($('furnish-grid').checked){
      ctx.strokeStyle='#e1e6e1';ctx.lineWidth=.5/scale;ctx.beginPath();
      for(let p=Math.ceil(-x/scale);p<(w-x)/scale;p++){ctx.moveTo(p,-y/scale);ctx.lineTo(p,(h-y)/scale);}
      for(let p=Math.ceil(-y/scale);p<(h-y)/scale;p++){ctx.moveTo(-x/scale,p);ctx.lineTo((w-x)/scale,p);}ctx.stroke();
    }
    const floor=surfaceStyle(this.document.finishes,'floor').color,wall='#66766f';
    for(const path of this.paths.filter(p=>p.kind==='floor')){ctx.fillStyle=floor;ctx.fill(path.path);}
    for(const {part,path} of this.surfacePaths){ctx.fillStyle=surfaceStyle(this.document.finishes,'floor',part.id).color;ctx.fill(path);}
    for(const path of this.paths.filter(p=>p.kind!=='floor')){ctx.fillStyle=wall;ctx.fill(path.path);}
    // A linework door is a real opening below its lintel. Mark it on the plan.
    for(const [a,c] of this.doors){ctx.lineWidth=this.job.params.wall_thickness*1.2;ctx.strokeStyle=floor;ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...c);ctx.stroke();ctx.lineWidth=1.2/scale;ctx.strokeStyle='#ae7b2b';ctx.setLineDash([4/scale,3/scale]);ctx.stroke();ctx.setLineDash([]);}
    for(const item of this.document.items)drawFurniture(ctx,item,this.catalog.find(c=>c.id===item.type),scale);
    const selected=this.selection();
    if(selected){
      ctx.save();ctx.translate(selected.x,selected.z);ctx.rotate(selected.rotation*Math.PI/180);ctx.strokeStyle='#bd7d18';ctx.lineWidth=2/scale;ctx.setLineDash([5/scale,3/scale]);ctx.strokeRect(-selected.width/2-.035,-selected.depth/2-.035,selected.width+.07,selected.depth+.07);ctx.setLineDash([]);
      ctx.fillStyle='#f2b441';for(const px of [-selected.width/2,selected.width/2])for(const pz of [-selected.depth/2,selected.depth/2])ctx.fillRect(px-3/scale,pz-3/scale,6/scale,6/scale);ctx.restore();
    }
    ctx.strokeStyle='#9aa89e';ctx.lineWidth=.8/scale;ctx.beginPath();const dy=b.minZ-18/scale;ctx.moveTo(b.minX,dy);ctx.lineTo(b.maxX,dy);for(const px of [b.minX,b.maxX]){ctx.moveTo(px,dy-4/scale);ctx.lineTo(px,dy+4/scale);}ctx.stroke();
    ctx.font=`${11/scale}px "PingFang SC",sans-serif`;ctx.textAlign='center';ctx.fillStyle='#738176';ctx.fillText(`${(b.maxX-b.minX).toFixed(2)} m`,(b.minX+b.maxX)/2,dy-5/scale);
    ctx.restore();$('furnish-scale').textContent=`网格 1 m · ${Math.round(scale/this.baseScale*100)}%`;
  }
  exportJSON(){
    if(!this.ready)return;const data={format:'blueprint3d-layout',version:1,model_id:this.job.id,layout:JSON.parse(JSON.stringify(this.document))};
    download(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}),'blueprint3d-layout.json');
  }
  async importJSON(file){
    $('furnish-import-file').value='';if(!file||!this.ready)return;const token=this.token;
    try{
      if(file.size>1024*1024)throw Error('方案文件不能超过 1 MB。');
      const data=JSON.parse(await file.text());if(token!==this.token)return;
      if(data.format!=='blueprint3d-layout'||data.version!==1||data.model_id!==this.job.id)throw Error('请选择当前户型导出的方案文件，避免尺寸和位置错位。');
      const valid=validateLayout(data.layout,this.catalog,this.bounds);
      this.change(()=>{this.document.items=valid.items;this.document.finishes=valid.finishes;this.selected=null;});this.toast('方案已导入，可撤销本次替换。');
    }catch(e){this.toast(e instanceof SyntaxError?'不是有效的 JSON 方案文件。':e.message,true);}
  }
  async exportGLB(){
    if(!this.ready)return;const token=this.token;$('furnish-export-glb').disabled=true;
    try{
      if(!await this.flush())throw Error('请先保存当前方案，再下载模型。');if(token!==this.token)return;
      const response=await fetch(`/api/jobs/${this.job.id}/furnished.glb`,{credentials:'same-origin'});
      if(!response.ok)throw Error('布置模型下载失败，请重新登录或稍后重试。');
      const blob=await response.blob();if(token!==this.token)return;download(blob,'blueprint3d-furnished.glb');this.toast('已下载包含家具款式与墙地面材质的模型。');
    }catch(e){this.toast(e.message,true);}finally{$('furnish-export-glb').disabled=false;}
  }
}
