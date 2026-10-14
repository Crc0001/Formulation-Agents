function batchNumber(s:any):number|null{
 if(Number.isInteger(s.document_batch)&&s.document_batch>0)return s.document_batch;
 const title=String(s.document_title||s.title||'').replace(/\s/g,'');
 if(/征求意见|调出/.test(title))return null;
 const m=title.match(/第([零一二三四五六七八九十百\d]+)批/);if(!m)return null;
 if(/^\d+$/.test(m[1]))return Number(m[1]);
 let sum=0,n=0;for(const ch of m[1]){const d='零一二三四五六七八九'.indexOf(ch);if(d>=0)n=d;else{sum+=(n||1)*(ch==='百'?100:10);n=0}}return sum+n;
}
export function directoryCoverage(state:any){
 const groups=new Map<number,any[]>();
 for(const s of state?.sources||[]){if(/draft|removal/.test(s.status||''))continue;const b=batchNumber(s);if(!b)continue;groups.set(b,[...(groups.get(b)||[]),s])}
 const max=Math.max(0,...groups.keys(),...(state?.batches||[]).map((b:any)=>b.batch));
 return Array.from({length:max},(_,i)=>{
  const batch=i+1,sources=groups.get(batch)||[];
  const originals=sources.filter(s=>(s.document_batch===batch&&s.sha256)||s.attachments?.some((a:any)=>a.sha256&&['downloaded','rows_extracted_pending_review'].includes(a.status)));
  const tables=sources.filter(s=>s.row_count>0||s.rows>0);
  const status=originals.length?'original':tables.length?'table':'missing';
  return {batch,status,sources,originals,tables,rows:state?.batches?.find((b:any)=>b.batch===batch)?.rows||0};
 });
}
