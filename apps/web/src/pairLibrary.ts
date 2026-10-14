import catalog from '../../../reference/excipient-pairs/catalog.json';
export const materials=catalog.materials;
export const pairId=(a:string,b:string)=>[a,b].sort().join('--');
export const pairs=materials.flatMap((a,i)=>materials.slice(i+1).map(b=>({id:pairId(a.id,b.id),a,b,relation:catalog.relations.find(r=>pairId(...r.materials as [string,string])===pairId(a.id,b.id))})));
export function matchesMaterial(item:any,id:string){const m=materials.find(m=>m.id===id);return !!m&&[m.name,m.en,...m.aliases].some(n=>n.toLowerCase()===item.name?.trim().toLowerCase());}
export function pairResearchQuestion(a:string,b:string){
 const names=[a,b].map(id=>materials.find(m=>m.id===id)!).map(m=>`${m.name}（${m.en}）`);
 return `【辅料配对经验变化】针对${names.join('与')}，先核对冻结方案的实际变化及全部补差物料。不限药物/BCS检索原始配对、factorial、response surface、mixture design研究，区分固定两物料总量的一维互换与第三物料补差的双因素设计。逐研究取得完整设计矩阵、原始响应、重复误差、牌号粒径、工艺/润滑/内外加、介质与方法，按研究族去重。先来源图及可复算公式、条件范围与整处方留出，再评估当前药物迁移；缺证据保存具体缺口，不造系数，不将文献类比写成目标实测或擅自改种类/用量。无变化方案不执行无关配对研究。`;
}
