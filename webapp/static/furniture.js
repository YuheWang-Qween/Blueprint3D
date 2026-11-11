// Shared plan geometry. All distances are meters in the source GLB frame.
import {validateFinishes,FLOOR_COLORS,WALL_COLORS} from './surface-finishes.js';
export const FLOORS=FLOOR_COLORS;
export const WALLS=WALL_COLORS;
export const emptyLayout=()=>({version:1,revision:0,items:[],finishes:validateFinishes({floor:'original',wall:'original'})});
export const radians=degrees=>degrees*Math.PI/180;
export const angle=value=>((value%360)+360)%360;
export const variantsFor=definition=>[{id:'standard',name:definition.standardName||'基础款',parts:definition.parts},...(definition.variants||[])];
export const partsFor=(definition,variant='standard')=>variantsFor(definition).find(v=>v.id===variant)?.parts||definition.parts;
export function appearance(item,definition,patch){
  const variant=patch.variant??item.variant??'standard',material=patch.material??item.material??'default';
  if(!variantsFor(definition).some(v=>v.id===variant)||!['default',...(definition.materials||[])].includes(material))throw Error('这件家具不支持所选款式或材质。');
  const color=patch.color??item.color;
  if(!/^#[0-9a-fA-F]{6}$/.test(color))throw Error('请选择有效颜色。');
  // Changing appearance never moves or resizes the rough-layout footprint.
  return {...item,variant,material,color};
}
export function extent(item){
  const a=radians(item.rotation),c=Math.abs(Math.cos(a)),s=Math.abs(Math.sin(a));
  return {x:(c*item.width+s*item.depth)/2,z:(s*item.width+c*item.depth)/2};
}
export function fitItem(item,bounds){
  const e=extent(item);
  if(e.x*2>bounds.maxX-bounds.minX||e.z*2>bounds.maxZ-bounds.minZ)return false;
  item.x=Math.max(bounds.minX+e.x,Math.min(bounds.maxX-e.x,item.x));
  item.z=Math.max(bounds.minZ+e.z,Math.min(bounds.maxZ-e.z,item.z));
  return true;
}
export function contains(item,x,z){
  const a=radians(item.rotation),dx=x-item.x,dz=z-item.z;
  return Math.abs(dx*Math.cos(a)+dz*Math.sin(a))<=item.width/2 &&
    Math.abs(-dx*Math.sin(a)+dz*Math.cos(a))<=item.depth/2;
}
export function meshBounds(meshes){
  const bounds={minX:Infinity,minZ:Infinity,maxX:-Infinity,maxZ:-Infinity};
  for(const mesh of meshes)for(let i=0;i<mesh.positions.length;i+=3){
    bounds.minX=Math.min(bounds.minX,mesh.positions[i]);bounds.maxX=Math.max(bounds.maxX,mesh.positions[i]);
    bounds.minZ=Math.min(bounds.minZ,-mesh.positions[i+1]);bounds.maxZ=Math.max(bounds.maxZ,-mesh.positions[i+1]);
  }
  if(!Object.values(bounds).every(Number.isFinite))throw Error('模型没有可用的平面数据。');
  return bounds;
}
export function validateLayout(data,catalog,bounds){
  if(data?.version!==1||!Array.isArray(data.items)||data.items.length>200)throw Error('方案格式无效，最多放置 200 件设施。');
  const finishes=validateFinishes(data.finishes);
  const ids=new Set();
  const items=data.items.map(item=>{
    if(!catalog.some(c=>c.id===item.type)||!/^[a-zA-Z0-9_-]{1,64}$/.test(item.id)||ids.has(item.id))throw Error('设施类型或编号无效。');
    ids.add(item.id);
    for(const [key,low,high] of [['width',.1,8],['depth',.1,8],['height',.05,4.5],['rotation',0,359.999999],['x',-2000,2000],['z',-2000,2000]]){
      if(typeof item[key]!=='number'||!Number.isFinite(item[key])||item[key]<low||item[key]>high)throw Error('设施尺寸或坐标超出范围。');
    }
    if(!/^#[0-9a-fA-F]{6}$/.test(item.color))throw Error('设施颜色无效。');
    const e=extent(item);
    if(item.x-e.x<bounds.minX-.002||item.x+e.x>bounds.maxX+.002||item.z-e.z<bounds.minZ-.002||item.z+e.z>bounds.maxZ+.002)throw Error('方案中的设施超出户型范围。');
    const normalized=Object.fromEntries(['id','type','x','z','width','depth','height','rotation','color'].map(k=>[k,item[k]]));
    return appearance(normalized,catalog.find(c=>c.id===item.type),{variant:item.variant,material:item.material});
  });
  return {version:1,revision:0,items,finishes};
}

export function drawFurniture(ctx,item,definition,scale=1){
  ctx.save();ctx.translate(item.x,item.z);ctx.rotate(radians(item.rotation));
  // Draw lower parts first so the plan shows cushions, pillows and sanitary fixtures.
  for(const part of [...partsFor(definition,item.variant)].sort((a,b)=>(a.position[1]+a.size[1]/2)-(b.position[1]+b.size[1]/2))){
    const x=part.position[0]*item.width,z=part.position[2]*item.depth,w=part.size[0]*item.width,d=part.size[2]*item.depth;
    ctx.fillStyle=part.color==='body'?item.color:part.color;ctx.strokeStyle='#5b655f';ctx.lineWidth=.65/scale;
    ctx.beginPath();
    if(part.shape==='cylinder')ctx.ellipse(x,z,w/2,d/2,0,0,Math.PI*2);
    else if(part.shape==='rounded-box'&&ctx.roundRect)ctx.roundRect(x-w/2,z-d/2,w,d,Math.min(w,d)*.12);
    else ctx.rect(x-w/2,z-d/2,w,d);
    ctx.fill();ctx.stroke();
  }
  ctx.restore();
}
