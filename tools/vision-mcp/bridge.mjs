import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { fileURLToPath } from 'node:url';
let input=''; for await (const part of process.stdin) input+=part;
const req=JSON.parse(input);
const client=new Client({name:'formulation-vision',version:'1.0.0'});
const transport=new StdioClientTransport({command:process.execPath,args:[fileURLToPath(new URL('./node_modules/@z_ai/mcp-server/build/index.js',import.meta.url))],env:{Z_AI_API_KEY:process.env.Z_AI_API_KEY,Z_AI_MODE:process.env.Z_AI_MODE,Z_AI_VISION_MODEL:process.env.Z_AI_VISION_MODEL,Z_AI_VISION_MODEL_MAX_TOKENS:'12000',Z_AI_VISION_MODEL_TEMPERATURE:'0',Z_AI_TIMEOUT:String(req.timeout_ms),Z_AI_RETRY_COUNT:'0'},stderr:'pipe'});
// Never forward vendor logs, prompts or credential-bearing exception messages.
transport.stderr?.resume();
let timer;
try {
 const result=await Promise.race([(async()=>{
  await client.connect(transport);
  const list=await client.listTools();
  if(req.action==='list')return {ok:true,tools:list.tools.map(t=>({name:t.name,inputSchema:t.inputSchema}))};
  if(!['extract_text_from_screenshot','analyze_data_visualization','analyze_image'].includes(req.tool)||!list.tools.some(t=>t.name===req.tool))return {ok:false,error_type:'VisionToolUnavailable'};
  const r=await client.callTool({name:req.tool,arguments:{image_source:req.image_path,prompt:req.prompt}},undefined,{timeout:req.timeout_ms});
  if(r.isError)return {ok:false,error_type:'VisionProviderError'};
  return {ok:true,text:r.content.filter(c=>c.type==='text').map(c=>c.text).join('\n')};
 })(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('timeout')),req.timeout_ms+2000);})]);
 process.stdout.write(JSON.stringify(result));
} catch(e) {process.stdout.write(JSON.stringify({ok:false,error_type:e.message==='timeout'?'VisionTimeout':'VisionMcpError'}));}
finally {clearTimeout(timer);await client.close().catch(()=>{});}
