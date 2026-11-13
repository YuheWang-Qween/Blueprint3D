import {metersPerUnit,project,distance,nearest,rectangle,appendWalls,eraseWall} from './plan-geometry.js';
const $=id=>document.getElementById(id),clone=value=>structuredClone(value);
const INSTRUCTIONS={rectangle:'依次点击两个对角，画出完整房间。',wall:'依次点击起点、终点。可吸附已有端点。',door:'在同一面墙上依次选择门洞的起点、终点。',erase:'点击擦除墙线或门洞。擦除墙线会同时移除其上的门洞。',pan:'拖动画布平移；滚轮或右上角按钮缩放。'};
export class PlanEditor{
  constructor({widthM,onChange,toast}){
    Object.assign(this,{widthM,onChange,toast});this.canvas=$('plan-editor');this.ctx=this.canvas.getContext('2d');this.plan=null;this.tool='wall';this.history=[];this.future=[];this.view={zoom:1,x:0,y:0};
    document.querySelectorAll('[data-tool]').forEach(b=>b.addEventListener('click',()=>this.setTool(b.dataset.tool)));
    $('undo-edit').addEventListener('click',()=>this.undo());$('redo-edit').addEventListener('click',()=>this.undo(true));
    $('clear-edit').addEventListener('click',()=>{if(this.plan?.walls.length||this.plan?.doors.length)this.change(()=>{this.plan.walls=[];this.plan.doors=[];});});
    $('plan-fit').addEventListener('click',()=>this.fit());$('plan-zoom-in').addEventListener('click',()=>this.zoom(1.25));$('plan-zoom-out').addEventListener('click',()=>this.zoom(.8));
    for(const id of ['plan-snap','plan-ortho'])$(id).addEventListener('change',()=>{this.start=null;this.draw();});
    this.canvas.addEventListener('pointerdown',e=>this.down(e));this.canvas.addEventListener('pointermove',e=>this.move(e));
    for(const event of ['pointerup','pointercancel','lostpointercapture'])this.canvas.addEventListener(event,()=>this.pan=null);
    this.canvas.addEventListener('wheel',e=>{e.preventDefault();const r=this.canvas.getBoundingClientRect();this.zoom(e.deltaY>0?.9:1.1,[e.clientX-r.left,e.clientY-r.top]);},{passive:false});
    document.addEventListener('keydown',e=>{
      if($('edit-view').hidden||e.target.closest('input,select,textarea'))return;
      if(e.key==='Escape'){this.start=null;this.draw();}
      if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='z'){e.preventDefault();this.undo(e.shiftKey);}
    });
    new ResizeObserver(()=>this.draw()).observe($('editor-stage'));
  }
  load(plan,imageURL){
    if(this.plan!==plan){
      this.plan=plan;this.history=[];this.future=[];this.start=null;this.hover=null;this.view={zoom:1,x:0,y:0};this.image=null;
      if(plan&&imageURL){const img=new Image();this.image=img;img.onload=()=>{if(this.image===img)this.draw();};img.src=imageURL;}
    }
    this.draw();this.commands();
  }
  commands(){$('undo-edit').disabled=!this.history.length;$('redo-edit').disabled=!this.future.length;$('clear-edit').disabled=!this.plan?.walls.length&&!this.plan?.doors.length;}
  setTool(tool){this.tool=tool;this.start=null;document.querySelectorAll('[data-tool]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.tool===tool)));$('edit-instruction').textContent=INSTRUCTIONS[tool];this.canvas.style.cursor=tool==='pan'?'grab':'crosshair';this.draw();}
  snapshot(){return clone({width:this.plan.width,height:this.plan.height,walls:this.plan.walls,doors:this.plan.doors});}
  change(callback){this.history.push(this.snapshot());if(this.history.length>50)this.history.shift();this.future=[];callback();this.start=null;this.onChange();this.commands();this.draw();}
  undo(redo=false){if(!this.plan)return;const from=redo?this.future:this.history,to=redo?this.history:this.future,previous=from.pop();if(!previous)return;to.push(this.snapshot());Object.assign(this.plan,previous);this.start=null;this.onChange();this.commands();this.draw();}
  fit(){this.view={zoom:1,x:0,y:0};this.draw();}
  zoom(factor,anchor){const z=Math.max(.5,Math.min(6,this.view.zoom*factor)),ratio=z/this.view.zoom;const r=this.canvas.getBoundingClientRect(),p=anchor||[r.width/2,r.height/2];this.view.x=this.view.x*ratio+(p[0]-r.width/2)*(1-ratio);this.view.y=this.view.y*ratio+(p[1]-r.height/2)*(1-ratio);this.view.zoom=z;this.draw();}
  point(event){const r=this.canvas.getBoundingClientRect(),m=this.mapping;return [Math.max(0,Math.min(this.plan.width,(event.clientX-r.left-m.x)/m.scale)),Math.max(0,Math.min(this.plan.height,(event.clientY-r.top-m.y)/m.scale))];}
  snap(point){
    let chosen=[...point];
    if($('plan-snap').checked){const step=.1/metersPerUnit(this.plan,this.widthM());chosen=chosen.map(v=>Math.round(v/step)*step);}
    for(const line of this.plan.walls)for(const p of line)if(distance(p,point)*this.mapping.scale<9)chosen=[...p];
    return [Math.max(0,Math.min(this.plan.width,chosen[0])),Math.max(0,Math.min(this.plan.height,chosen[1]))];
  }
  end(point){
    if(this.tool==='door')return project(this.snap(point),this.start.line);
    const b=this.snap(point),a=this.start.point;
    if(this.tool==='wall'&&$('plan-ortho').checked)return Math.abs(b[0]-a[0])>Math.abs(b[1]-a[1])?[b[0],a[1]]:[a[0],b[1]];
    return b;
  }
  move(e){
    if(!this.plan||!this.mapping)return;
    if(this.pan){this.view.x+=e.clientX-this.pan[0];this.view.y+=e.clientY-this.pan[1];this.pan=[e.clientX,e.clientY];this.draw();return;}
    this.hover=this.point(e);if(this.start)this.draw();
  }
  down(e){
    if(!this.plan||!this.mapping||![0,1].includes(e.button))return;e.preventDefault();this.canvas.focus({preventScroll:true});
    if(this.tool==='pan'||e.button===1){this.pan=[e.clientX,e.clientY];this.canvas.setPointerCapture(e.pointerId);return;}
    const p=this.point(e);
    if(this.tool==='erase'){
      const wall=nearest(p,this.plan.walls),door=nearest(p,this.plan.doors),target=door&&(!wall||door.distance<=wall.distance+3/this.mapping.scale)?{...door,kind:'doors'}:wall?{...wall,kind:'walls'}:null;
      if(target&&target.distance*this.mapping.scale<14)this.change(()=>target.kind==='walls'?eraseWall(this.plan,target.index):this.plan.doors.splice(target.index,1));return;
    }
    if(!this.start){
      if(this.tool==='door'){const near=nearest(p,this.plan.walls);if(!near||near.distance*this.mapping.scale>20){this.toast('请在墙线上选择门洞起点。');return;}this.start={point:project(this.snap(p),near.line),line:near.line};}
      else this.start={point:this.snap(p)};
      this.hover=p;this.draw();return;
    }
    const a=this.start.point,b=this.end(p);
    if(distance(a,b)<1||(this.tool==='rectangle'&&(Math.abs(a[0]-b[0])<1||Math.abs(a[1]-b[1])<1))){this.start=null;this.draw();return;}
    const key=this.tool==='door'?'doors':'walls',lines=this.tool==='rectangle'?rectangle(a,b):[[a,b]],next=appendWalls(this.plan[key],lines);
    if(next.length>450){this.toast('最多绘制 450 条墙线或门洞。',true);this.start=null;return;}
    if(next.length===this.plan[key].length){this.start=null;this.draw();return;}
    this.change(()=>this.plan[key]=next);
  }
  draw(){
    if(!this.plan||$('edit-view').hidden)return;
    const stage=$('editor-stage'),w=stage.clientWidth,h=stage.clientHeight;if(!w||!h)return;
    const ctx=this.ctx,dpr=Math.min(devicePixelRatio,2);this.canvas.width=w*dpr;this.canvas.height=h*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
    const scale=Math.min((w-56)/this.plan.width,(h-50)/this.plan.height)*this.view.zoom;
    this.mapping={scale,x:(w-this.plan.width*scale)/2+this.view.x,y:(h-this.plan.height*scale)/2+this.view.y};
    const m=this.mapping,unit=metersPerUnit(this.plan,this.widthM());ctx.save();ctx.translate(m.x,m.y);ctx.scale(scale,scale);
    ctx.fillStyle='#fff';ctx.fillRect(0,0,this.plan.width,this.plan.height);ctx.strokeStyle='#b8c9d4';ctx.lineWidth=1/scale;ctx.strokeRect(0,0,this.plan.width,this.plan.height);
    let grid=.5;while(grid/unit*scale<12)grid*=2;const step=grid/unit;
    ctx.beginPath();ctx.lineWidth=.6/scale;ctx.strokeStyle='#e5edf1';
    for(let x=step;x<this.plan.width;x+=step){ctx.moveTo(x,0);ctx.lineTo(x,this.plan.height);}for(let y=step;y<this.plan.height;y+=step){ctx.moveTo(0,y);ctx.lineTo(this.plan.width,y);}ctx.stroke();
    if(this.image?.complete&&this.image.naturalWidth){ctx.globalAlpha=.5;ctx.drawImage(this.image,0,0,this.plan.width,this.plan.height);ctx.globalAlpha=1;}
    const line=(points,color,width,dash=[])=>{ctx.strokeStyle=color;ctx.lineWidth=width/scale;ctx.setLineDash(dash.map(v=>v/scale));ctx.beginPath();ctx.moveTo(...points[0]);ctx.lineTo(...points[1]);ctx.stroke();ctx.setLineDash([]);};
    const label=(text,x,y,angle=0)=>{ctx.save();ctx.translate(x,y);ctx.scale(1/scale,1/scale);ctx.rotate(angle);ctx.font='11px Helvetica, sans-serif';const width=ctx.measureText(text).width;ctx.fillStyle='#fffffff2';ctx.fillRect(-width/2-3,-13,width+6,16);ctx.fillStyle='#496879';ctx.textAlign='center';ctx.fillText(text,0,0);ctx.restore();};
    for(const l of this.plan.walls){
      line(l,'#247ca6',3);
      if(distance(...l)*scale>55){const vertical=Math.abs(l[1][1]-l[0][1])>Math.abs(l[1][0]-l[0][0]);
        label((distance(...l)*unit).toFixed(2)+' m',(l[0][0]+l[1][0])/2-(vertical?6/scale:0),(l[0][1]+l[1][1])/2-(vertical?0:6/scale),vertical?-Math.PI/2:0);
      }
    }
    for(const l of this.plan.doors)line(l,'#d09423',7);
    if(this.start){const a=this.start.point,b=this.end(this.hover||a),lines=this.tool==='rectangle'?rectangle(a,b):[[a,b]];for(const l of lines)line(l,'#bd7c1f',2,[5,4]);
      ctx.beginPath();ctx.fillStyle='#bd7c1f';ctx.arc(...a,4/scale,0,Math.PI*2);ctx.fill();
      const text=this.tool==='rectangle'?`${(Math.abs(b[0]-a[0])*unit).toFixed(2)} × ${(Math.abs(b[1]-a[1])*unit).toFixed(2)} m`:(distance(a,b)*unit).toFixed(2)+' m';label(text,(a[0]+b[0])/2,(a[1]+b[1])/2-12/scale);
    }
    ctx.restore();$('plan-measure').textContent=`网格 ${grid} m · ${this.plan.walls.length} 段墙 / ${this.plan.doors.length} 处门洞`;
    if(!this.plan.walls.length&&!this.start){ctx.fillStyle='#718696';ctx.font='12px Helvetica, sans-serif';ctx.textAlign='center';ctx.fillText('用“矩形房间”画外墙，再添加隔墙和门洞',w/2,h/2);}
  }
}
