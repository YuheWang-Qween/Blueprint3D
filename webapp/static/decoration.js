import {appearance,variantsFor,drawFurniture} from './furniture.js';

const $=id=>document.getElementById(id);
const COLORS=[['暖米白','#e5d9c6'],['焦糖棕','#a56e46'],['雾蓝','#67869a'],['灰绿','#8f9e8c'],['豆沙红','#b77570'],['炭灰','#48525b'],['浅灰','#bec1bd']];

export class DecorationPanel {
  constructor({editor,viewer,toast,showPlan}){
    Object.assign(this,{editor,viewer,toast,showPlan});this.active=false;this.visible=true;this.materials={};
    fetch('/static/material-profiles.json').then(r=>{if(!r.ok)throw Error();return r.json();}).then(data=>{this.materials=data;this.propertiesSignature=null;this.refresh();}).catch(()=>this.toast('材质库读取失败，请刷新页面。',true));
    $('decorate-toggle').addEventListener('click',()=>this.setMode(!this.active));
    $('decorate-close').addEventListener('click',()=>this.setMode(false));
    $('decorate-go-plan').addEventListener('click',showPlan);
    $('decorate-picker').addEventListener('change',e=>this.select(e.target.value||null));
    $('decorate-focus').addEventListener('click',()=>{
      if(!this.viewer()?.focusSelected())return;this.viewer().cut(true);$('cutaway').checked=true;
    });
    $('decorate-color').addEventListener('input',e=>this.apply({color:e.target.value}));
    $('decorate-reset').addEventListener('click',()=>{
      const selected=editor.selection(),definition=editor.catalog.find(c=>c.id===selected?.type);
      if(definition)this.apply({variant:'standard',material:'default',color:definition.color});
    });
    $('decorate-undo').addEventListener('click',()=>editor.undo());$('decorate-redo').addEventListener('click',()=>editor.undo(true));
    $('decorate-save').addEventListener('click',async()=>{if(await editor.flush())toast('精装修方案已保存。');});
    $('decorate-export').addEventListener('click',()=>editor.exportGLB());
    $('decorate-backup').addEventListener('click',()=>editor.exportJSON());
    $('decorate-reload').addEventListener('click',()=>{if(editor.job)editor.load(editor.job,editor.user,true);});
    $('walk-toggle').addEventListener('click',()=>this.walk(!this.viewer()?.navigation.active));
    $('walk-exit').addEventListener('click',()=>this.walk(false));
    document.querySelectorAll('[data-walk]').forEach(button=>{
      button.addEventListener('pointerdown',e=>{e.preventDefault();button.setPointerCapture(e.pointerId);this.viewer()?.walkKey(button.dataset.walk,true);});
      for(const type of ['pointerup','pointercancel','lostpointercapture'])button.addEventListener(type,()=>this.viewer()?.walkKey(button.dataset.walk,false));
    });
    document.addEventListener('keydown',e=>{
      if(!this.active||!this.visible||e.target.closest('input,select,textarea'))return;
      if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='z'){e.preventDefault();editor.undo(e.shiftKey);}
    });
  }
  setMode(enabled){
    if(enabled&&!this.editor.ready){this.toast('请先生成模型，再进入精装修。');return;}
    this.active=enabled;$('decorate-panel').hidden=!enabled;$('model-view').classList.toggle('decoration-open',enabled);
    document.querySelector('.work-layout').classList.toggle('decoration-focus',enabled&&this.visible);
    $('decorate-toggle').setAttribute('aria-pressed',String(enabled));$('decorate-toggle').textContent=enabled?'退出精装修':'进入精装修';
    this.viewer()?.setDecorating(enabled);this.refresh();this.viewer()?.resize();
  }
  setVisible(visible){this.visible=visible;document.querySelector('.work-layout').classList.toggle('decoration-focus',this.active&&visible);this.viewer()?.setVisible(visible);}
  reset(){this.propertiesSignature=null;this.setMode(false);this.navigationChanged(false);}
  select(id){
    if(!this.editor.ready)return;this.editor.selected=id;this.editor.pending=null;
    if(id&&!this.active)this.setMode(true);
    this.editor.refresh();this.viewer()?.select(id);
  }
  apply(patch){
    const item=this.editor.selection();if(!item)return;
    try{
      const definition=this.editor.catalog.find(c=>c.id===item.type),next=appearance(item,definition,patch);
      this.editor.change(()=>Object.assign(item,next));
    }catch(e){this.toast(e.message,true);}
  }
  walk(enabled){
    if(!this.editor.ready)return;
    if(enabled&&!this.active)this.setMode(true);
    if(!this.viewer()?.setWalking(enabled)){this.toast('没有找到可进入的空闲地面，请先在平面布置中留出通道。',true);return;}
    this.viewer().renderer.domElement.focus({preventScroll:true});
  }
  navigationChanged(active){
    $('walk-toggle').setAttribute('aria-pressed',String(active));$('walk-toggle').textContent=active?'退出室内':'室内查看';
    $('walk-overlay').hidden=!active;$('walk-pad').hidden=!active;
    $('model-help').textContent=active?'拖动环顾 · WASD / 方向键移动 · 点击家具 · Esc 退出':'拖动旋转 · 滚轮缩放 · 点击家具精装修';
    $('cutaway').disabled=active;$('cutaway').checked=active?false:!!this.viewer()?.cutEnabled;
  }
  status(message,error){
    $('decorate-status').textContent=message;$('decorate-status').classList.toggle('save-error',error);
    $('decorate-reload').hidden=!this.editor.blocked;$('decorate-backup').hidden=!error;
  }
  refresh(){
    const editor=this.editor;
    for(const id of ['decorate-toggle','walk-toggle','decorate-save','decorate-export'])$(id).disabled=!editor.ready;
    $('decorate-undo').disabled=!editor.history.length;$('decorate-redo').disabled=!editor.future.length;
    const selected=editor.selection(),definition=editor.catalog.find(c=>c.id===selected?.type);
    const picker=$('decorate-picker'),list=editor.document.items.map((item,index)=>({id:item.id,name:`${index+1}. ${editor.catalog.find(c=>c.id===item.type)?.name||'家具'}`}));
    const signature=JSON.stringify(list);
    if(signature!==this.pickerSignature){
      this.pickerSignature=signature;picker.replaceChildren();const empty=document.createElement('option');empty.value='';empty.textContent='在 3D 中点击，或从列表选择';picker.append(empty);
      for(const item of list){const option=document.createElement('option');option.value=item.id;option.textContent=item.name;picker.append(option);}
    }
    picker.value=selected?.id||'';$('decorate-empty').hidden=!!selected;$('decorate-properties').hidden=!selected;
    $('decorate-empty').textContent=list.length?'点击模型中的沙发、床或桌椅，选择款式、材质和颜色。':'这份户型还没有家具。先到平面布置添加设施，再回来精装修。';
    if(selected&&definition){
      $('decorate-name').textContent=definition.name;$('decorate-dimensions').textContent=`${selected.width} × ${selected.depth} × ${selected.height} m`;
      $('decorate-color').value=selected.color;
      const properties=JSON.stringify([selected.id,selected.variant,selected.material,selected.color,selected.width,selected.depth]);
      if(properties!==this.propertiesSignature){this.propertiesSignature=properties;this.renderOptions(selected,definition);}
    }
    this.viewer()?.select(selected?.id||null);
  }
  renderOptions(item,definition){
    $('decorate-variants').replaceChildren();
    for(const variant of variantsFor(definition)){
      const button=document.createElement('button');button.className='decorate-variant';button.type='button';button.setAttribute('aria-label','选择'+variant.name);
      button.setAttribute('aria-pressed',String((item.variant||'standard')===variant.id));
      const canvas=document.createElement('canvas');canvas.width=184;canvas.height=112;canvas.setAttribute('aria-hidden','true');
      const ctx=canvas.getContext('2d'),scale=Math.min(156/item.width,86/item.depth);ctx.translate(92,56);ctx.scale(scale,scale);
      drawFurniture(ctx,{...item,variant:variant.id,x:0,z:0,rotation:0},definition,scale/2);
      const label=document.createElement('span');label.textContent=variant.name;button.append(canvas,label);
      button.addEventListener('click',()=>this.apply({variant:variant.id}));$('decorate-variants').append(button);
    }
    $('decorate-materials').replaceChildren();
    for(const id of ['default',...(definition.materials||[])]){
      const config=this.materials[id];if(!config)continue;
      const button=document.createElement('button');button.type='button';button.className='decorate-material';button.setAttribute('aria-label','选择'+config.name+'材质');
      button.setAttribute('aria-pressed',String((item.material||'default')===id));const chip=document.createElement('span');chip.className='material-chip';chip.setAttribute('aria-hidden','true');
      if(config.texture)chip.style.backgroundImage=`url('/static/materials/${config.texture}')`;
      button.append(chip,document.createTextNode(config.name));button.addEventListener('click',()=>this.apply({material:id}));$('decorate-materials').append(button);
    }
    $('decorate-colors').replaceChildren();
    for(const [name,color] of COLORS){
      const button=document.createElement('button');button.type='button';button.className='decorate-swatch';button.title=name;button.style.background=color;button.style.setProperty('--swatch',color);
      button.setAttribute('aria-label','颜色：'+name);button.setAttribute('aria-pressed',String(item.color.toLowerCase()===color));button.addEventListener('click',()=>this.apply({color}));$('decorate-colors').append(button);
    }
  }
}
