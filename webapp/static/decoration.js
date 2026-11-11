import {appearance,variantsFor,drawFurniture} from './furniture.js';
import {SURFACE_MATERIALS,surfaceStyle,setSurfaceStyle} from './surface-finishes.js';

const $=id=>document.getElementById(id);
const COLORS=[['暖米白','#e5d9c6'],['焦糖棕','#a56e46'],['雾蓝','#67869a'],['灰绿','#8f9e8c'],['豆沙红','#b77570'],['炭灰','#48525b'],['浅灰','#bec1bd']];
const SURFACE_COLORS=[['浅橡木','#c8ad82'],['暖白','#eee9dc'],['纯白','#f4f5ef'],['石灰','#abb9c1'],['灰绿','#cbd4c4'],['雾蓝','#91aabd'],['深灰','#68737b']];
const LABELS={furniture:'家具',floor:'地面',wall:'墙面'};

export class DecorationPanel {
  constructor({editor,viewer,toast,showPlan}){
    Object.assign(this,{editor,viewer,toast,showPlan});this.active=false;this.visible=true;this.materials={};this.kind='furniture';this.surfaceId=null;
    fetch('/static/material-profiles.json').then(r=>{if(!r.ok)throw Error();return r.json();}).then(data=>{this.materials=data;this.propertiesSignature=null;this.refresh();}).catch(()=>this.toast('材质库读取失败，请刷新页面。',true));
    $('decorate-toggle').addEventListener('click',()=>this.setMode(!this.active));
    $('decorate-close').addEventListener('click',()=>this.setMode(false));
    $('decorate-go-plan').addEventListener('click',showPlan);
    $('decorate-picker').addEventListener('change',e=>this.kind==='furniture'?this.select(e.target.value||null):this.selectSurface(this.kind,e.target.value||null));
    document.querySelectorAll('[data-decorate-kind]').forEach(button=>button.addEventListener('click',()=>{
      if(button.dataset.decorateKind==='furniture'){this.kind='furniture';this.surfaceId=null;this.editor.refresh();}
      else this.selectSurface(button.dataset.decorateKind,null);
    }));
    $('decorate-focus').addEventListener('click',()=>{
      if(!this.viewer()?.focusSelected())return;this.viewer().cut(true);$('cutaway').checked=true;
    });
    $('decorate-color').addEventListener('input',e=>this.apply({color:e.target.value}));
    $('decorate-reset').addEventListener('click',()=>{
      if(this.kind!=='furniture'){editor.change(()=>editor.document.finishes=setSurfaceStyle(editor.document.finishes,this.kind,this.surfaceId,null));return;}
      const selected=editor.selection(),definition=editor.catalog.find(c=>c.id===selected?.type);
      if(definition)this.apply({variant:'standard',material:'default',color:definition.color});
    });
    $('decorate-apply-all').addEventListener('click',()=>{
      if(this.kind==='furniture')return;const style=surfaceStyle(editor.document.finishes,this.kind,this.surfaceId);
      editor.change(()=>editor.document.finishes=setSurfaceStyle(editor.document.finishes,this.kind,null,style));this.surfaceId=null;this.refresh();
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
  reset(){this.propertiesSignature=null;this.kind='furniture';this.surfaceId=null;this.setMode(false);this.navigationChanged(false);}
  select(id){
    if(!this.editor.ready)return;this.kind='furniture';this.surfaceId=null;this.editor.selected=id;this.editor.pending=null;
    if(id&&!this.active)this.setMode(true);this.editor.refresh();this.viewer()?.select(id);
  }
  selectSurface(kind,id){
    if(!this.editor.ready)return;this.kind=kind;this.surfaceId=id;this.editor.selected=null;this.editor.pending=null;
    if(!this.active)this.setMode(true);this.editor.refresh();this.viewer()?.selectSurface(id);
  }
  apply(patch){
    try{
      if(this.kind!=='furniture'){
        const next={...surfaceStyle(this.editor.document.finishes,this.kind,this.surfaceId),...patch};
        this.editor.change(()=>this.editor.document.finishes=setSurfaceStyle(this.editor.document.finishes,this.kind,this.surfaceId,next));
        return;
      }
      const item=this.editor.selection();if(!item)return;
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
    $('model-help').textContent=active?'拖动环顾 · WASD / 方向键移动 · 点击家具或墙地面 · Esc 退出':'拖动旋转 · 滚轮缩放 · 点击家具或墙地面';
    $('cutaway').disabled=active;$('cutaway').checked=active?false:!!this.viewer()?.cutEnabled;
  }
  status(message,error){
    $('decorate-status').textContent=message;$('decorate-status').classList.toggle('save-error',error);
    $('decorate-reload').hidden=!this.editor.blocked;$('decorate-backup').hidden=!error;
  }
  refresh(){
    const editor=this.editor,isFurniture=this.kind==='furniture',label=LABELS[this.kind];
    for(const id of ['decorate-toggle','walk-toggle','decorate-save','decorate-export'])$(id).disabled=!editor.ready;
    $('decorate-undo').disabled=!editor.history.length;$('decorate-redo').disabled=!editor.future.length;
    document.querySelectorAll('[data-decorate-kind]').forEach(b=>{b.setAttribute('aria-pressed',String(b.dataset.decorateKind===this.kind));b.disabled=!editor.ready;});
    const selected=editor.selection(),definition=editor.catalog.find(c=>c.id===selected?.type),parts=(editor.surfaces||[]).filter(s=>s.kind===this.kind);
    const part=parts.find(s=>s.id===this.surfaceId);if(!isFurniture&&!part)this.surfaceId=null;
    const picker=$('decorate-picker'),list=isFurniture?editor.document.items.map((item,index)=>({id:item.id,name:`${index+1}. ${editor.catalog.find(c=>c.id===item.type)?.name||'家具'}`})):parts;
    const signature=JSON.stringify([this.kind,list.map(i=>[i.id,i.name])]);
    if(signature!==this.pickerSignature){
      this.pickerSignature=signature;picker.replaceChildren();const empty=document.createElement('option');empty.value='';empty.textContent=isFurniture?'在 3D 中点击，或从列表选择':'全部'+label;picker.append(empty);
      for(const item of list){const option=document.createElement('option');option.value=item.id;option.textContent=item.name;picker.append(option);}
    }
    $('decorate-picker-label').textContent='当前'+label;picker.setAttribute('aria-label','当前'+label);
    picker.value=isFurniture?(selected?.id||''):(this.surfaceId||'');
    const hasSelection=isFurniture?!!selected:editor.ready;
    $('decorate-empty').hidden=hasSelection;$('decorate-properties').hidden=!hasSelection;
    $('decorate-empty').textContent=list.length?'点击任意家具选择款式、材质和颜色；墙地面也可以直接点选。':'先到平面布置添加家具，或切换“地面 / 墙面”开始装修。';
    $('decorate-variant-section').hidden=!isFurniture;$('decorate-scope').hidden=isFurniture;$('decorate-apply-all').hidden=isFurniture||!part;
    $('decorate-focus').hidden=!isFurniture&&!part;$('decorate-focus').textContent=isFurniture?'近看家具':'近看区域';
    $('decorate-color-label').textContent=isFurniture?'主体颜色':'饰面颜色';
    $('decorate-reset').textContent=isFurniture?'恢复基础外观':part?'恢复全屋设置':'恢复基础饰面';
    if(hasSelection){
      const style=isFurniture?selected:surfaceStyle(editor.document.finishes,this.kind,this.surfaceId);
      $('decorate-name').textContent=isFurniture?definition?.name:(part?.name||'全部'+label);
      $('decorate-dimensions').textContent=isFurniture?`${selected.width} × ${selected.depth} × ${selected.height} m`:part?`${part.area.toFixed(2)} m²`:`${parts.length} 个可选区域`;
      $('decorate-scope').textContent=part?`仅修改当前${label}，其他区域保持原有搭配。`:`修改将应用到全部${label}，替换已有局部设置；可撤销。`;
      $('decorate-apply-all').textContent='应用到全部'+label;
      $('decorate-color').value=style.color;
      const properties=JSON.stringify([this.kind,this.surfaceId,style,definition?.id]);
      if(properties!==this.propertiesSignature){this.propertiesSignature=properties;this.renderOptions(style,definition);}
    }
    this.syncSelection();
  }
  syncSelection(){if(this.kind==='furniture')this.viewer()?.select(this.editor.selected);else this.viewer()?.selectSurface(this.surfaceId);}
  renderOptions(item,definition){
    $('decorate-variants').replaceChildren();
    if(this.kind==='furniture')for(const variant of variantsFor(definition)){
      const button=document.createElement('button');button.className='decorate-variant';button.type='button';button.setAttribute('aria-label','选择'+variant.name);
      button.setAttribute('aria-pressed',String((item.variant||'standard')===variant.id));
      const canvas=document.createElement('canvas');canvas.width=184;canvas.height=112;canvas.setAttribute('aria-hidden','true');
      const ctx=canvas.getContext('2d'),scale=Math.min(156/item.width,86/item.depth);ctx.translate(92,56);ctx.scale(scale,scale);
      drawFurniture(ctx,{...item,variant:variant.id,x:0,z:0,rotation:0},definition,scale/2);
      const text=document.createElement('span');text.textContent=variant.name;button.append(canvas,text);
      button.addEventListener('click',()=>this.apply({variant:variant.id}));$('decorate-variants').append(button);
    }
    $('decorate-materials').replaceChildren();
    for(const id of this.kind==='furniture'?['default',...(definition.materials||[])]:SURFACE_MATERIALS[this.kind]){
      const config=this.materials[id];if(!config)continue;
      const name=this.kind==='floor'&&id==='wood'?'木地板':this.kind==='wall'&&id==='painted'?'墙漆':config.name;
      const button=document.createElement('button');button.type='button';button.className='decorate-material';button.setAttribute('aria-label','选择'+name+'材质');
      button.setAttribute('aria-pressed',String((item.material||'default')===id));const chip=document.createElement('span');chip.className='material-chip';chip.setAttribute('aria-hidden','true');
      const texture=(this.kind!=='furniture'&&config.surfaceTexture)||config.texture;if(texture)chip.style.backgroundImage=`url('/static/materials/${texture}')`;
      button.append(chip,document.createTextNode(name));button.addEventListener('click',()=>this.apply({material:id}));$('decorate-materials').append(button);
    }
    $('decorate-colors').replaceChildren();
    for(const [name,color] of this.kind==='furniture'?COLORS:SURFACE_COLORS){
      const button=document.createElement('button');button.type='button';button.className='decorate-swatch';button.title=name;button.style.background=color;button.style.setProperty('--swatch',color);
      button.setAttribute('aria-label','颜色：'+name);button.setAttribute('aria-pressed',String(item.color.toLowerCase()===color));button.addEventListener('click',()=>this.apply({color}));$('decorate-colors').append(button);
    }
  }
}
