// This module contains no renderer state; plan, 3D and document validation share it.
export const SURFACE_MATERIALS={floor:['default','wood','tile','stone'],wall:['default','painted','wallpaper','tile','wood']};
export const SURFACE_BASE={floor:'#becacf',wall:'#e2e8ec'};
export const FLOOR_COLORS={original:null,oak:'#c8ad82',tile:'#deded3',stone:'#abb9c1'};
export const WALL_COLORS={original:null,ivory:'#eee9dc',white:'#f4f5ef',sage:'#cbd4c4'};
export function validateSurfaceStyle(style,kind){
  if(!style||typeof style!=='object'||!SURFACE_MATERIALS[kind]?.includes(style.material)||!/^#[0-9a-fA-F]{6}$/.test(style.color))throw Error('墙地面的材质或颜色无效。');
  return {material:style.material,color:style.color};
}
export function validateFinishes(data){
  if(!data||!Object.hasOwn(FLOOR_COLORS,data.floor)||!Object.hasOwn(WALL_COLORS,data.wall))throw Error('方案中的饰面无效。');
  const surfaces=data.surfaces??{};
  if(!surfaces||Array.isArray(surfaces)||typeof surfaces!=='object'||Object.keys(surfaces).length>4096)throw Error('墙地面区域数量无效。');
  const result={floor:data.floor,wall:data.wall,floorStyle:null,wallStyle:null,surfaces:{}};
  for(const kind of ['floor','wall'])if(data[kind+'Style']!=null)result[kind+'Style']=validateSurfaceStyle(data[kind+'Style'],kind);
  for(const [id,style] of Object.entries(surfaces)){
    if(!/^(floor|wall)-[a-f0-9]{16}$/.test(id))throw Error('墙地面区域编号无效。');
    result.surfaces[id]=validateSurfaceStyle(style,id.split('-')[0]);
  }
  return result;
}
export function surfaceStyle(finishes,kind,id){
  return finishes.surfaces?.[id]||finishes[kind+'Style']||{material:'default',color:(kind==='floor'?FLOOR_COLORS:WALL_COLORS)[finishes[kind]]||SURFACE_BASE[kind]};
}
export function setSurfaceStyle(finishes,kind,id,style){
  const next=validateFinishes(finishes);
  if(id){if(style)next.surfaces[id]=validateSurfaceStyle(style,kind);else delete next.surfaces[id];}
  else{
    next[kind+'Style']=style?validateSurfaceStyle(style,kind):null;
    for(const key of Object.keys(next.surfaces))if(key.startsWith(kind+'-'))delete next.surfaces[key];
  }
  return next;
}
