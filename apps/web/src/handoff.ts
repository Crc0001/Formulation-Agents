// Identity is independent of whether a source reports salt or active-equivalent mass.
export function formulaIngredients(components:any[], apiName:string){
 const normal=(s:string)=>s.normalize('NFKC').replace(/\s+/g,'').toLowerCase();
 const identity=(s:string)=>normal(s).replace(/[（(](?:片芯|内容物|原料药|API)[）)]/gi,'').replace(/(?:半水合物|一水合物|二水合物|三水合物|水合物)$/,'');
 return components.map((c,i)=>({
  id:'m'+i,name:c.name,
  role:c.compartment==='shell'||/[（(](?:薄膜包衣|包衣|胶囊壳)[）)]/.test(c.name)?'shell':identity(c.name)===identity(apiName)||['salt','active_moiety'].includes(c.amount_basis)?'api':'excipient',
  amount_mg:c.amount_mg??'',brand:'',grade:c.grade??'',particle:''
 }));
}
export function baselineProblem(items:any[]):string{
 if(items.filter(x=>x.role==='api').length!==1)return '请在物料身份中明确选择一个原料药（API）；质量基准未知不代表它是辅料。';
 if(items.some(x=>x.amount_mg===''||!Number.isFinite(Number(x.amount_mg))||Number(x.amount_mg)<=0))return '仍有物料缺少有效的单单位用量；请核对原文，未知量不能作为零保存。';
 return '';
}

// Explicit research normalization, never an assertion that the source is per tablet.
export function researchNormalization(f:any, apiName:string, strength:string){
 const m=strength.trim().match(/^([0-9]+(?:\.[0-9]+)?)\s*(mg|毫克)$/i);
 if(!m||!(Number(m[1])>0))return null;
 const factors:Record<string,number>={mg:1,g:1000,kg:1000000};
 const core=f.components.filter((c:any)=>c.compartment==='fill');
 if(f.components.some((c:any)=>!['fill','shell'].includes(c.compartment)))return null;
 const api=core.filter((c:any)=>c.name.normalize('NFKC').replace(/\s/g,'')===apiName.normalize('NFKC').replace(/\s/g,''));
 if(api.length!==1||api[0].amount_basis==='salt'||core.length<2)return null;
 // All values must come from the same raw quantity column; do not mix unit-dose and raw quantities.
 const raw=core.map((c:any)=>typeof c.batch_amount==='number'&&c.batch_amount>0?c.batch_amount*(factors[c.batch_mass_unit]??NaN):NaN);
 if(raw.some((x:number)=>!Number.isFinite(x)||x<=0))return null;
 const factor=Number(m[1])/raw[core.indexOf(api[0])];
 const outer=f.components.filter((c:any)=>c.compartment==='shell');
 return {ingredients:formulaIngredients(core,apiName).map((x:any,i:number)=>({...x,amount_mg:Number((raw[i]*factor).toPrecision(12))})),
  screening_scope:outer.length?'core_or_fill':'whole_unit',
  fixed_outer_context:outer.length?'包衣/壳固定，不参与片芯补差；单项未知量不填零。组成：'+outer.map((c:any)=>c.name+'（'+(c.amount_mg!=null?c.amount_mg+' mg/单位；': '')+'原文列量：'+(c.batch_amount??'未知')+' '+(c.batch_mass_unit??'')+'；规格：'+(c.grade||'未知')+'）').join('；')+'。原处方说明：'+(f.applicability||''):'',
  mass_basis:'显式研究归一化，非原文每片量认定：以原文同一列原料量比例，API按项目 '+strength+' 设定；原文API折合 '+raw[core.indexOf(api[0])]+' mg，倍率 '+factor+'。片芯/内容物合计 '+Number((raw.reduce((a:number,b:number)=>a+b,0)*factor).toPrecision(12))+' mg/单位。API质量身份、效价及包衣总量须核对；不得据此宣称商业原研处方或目标实测。原文：'+(f.applicability||'')};
}
