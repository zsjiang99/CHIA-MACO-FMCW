import {useEffect,useState} from 'react';

export type Mapping={candidate:{kernel:string;rows:number;columns:number;unroll_factor:number;fu_profile?:string;memory_banks?:number;bank_kib?:number};success:boolean;mapping_ii:number|null;dfg_nodes:number|null;elapsed_seconds?:number;error?:string};
export type Plan={tile_size:string;unroll_factors:number[];reasoning:string;fu_profile?:string;memory_banks?:number;bank_kib?:number};
export type Measured={design:Plan;frame_estimate:{estimated_cycles:number;valid:boolean}};
export type AgentEvent={sequence:number;round:number;kind:string;role?:string;error?:string;candidate?:Mapping['candidate'];designs?:Plan[];design?:Plan;success?:boolean;mapping_ii?:number;banks?:number;bank_kib?:number};
export type Workload={description:string;samples:number;chirps:number;rx:number;dtype:string;objective:'cycles'|'spm_energy';max_pes:number};
export type Progress={completed:number;total:number;raw_results?:Mapping[];round?:number;rounds_total?:number;llm_calls?:number;prompt_tokens?:number;completion_tokens?:number;elapsed_seconds?:number;workload?:Workload;events?:AgentEvent[];rounds?:Array<{iteration:number;llm_choice:Plan;measured_winner:Measured|null;confidence:number}>;model_identity?:{model_path?:string;served_model?:string;quantization?:string}};
type Job={id:string;kind:string;state:string;error?:string;progress?:Progress};

export const fmt=(value:number|null|undefined,digits=0)=>value==null?'—':value.toLocaleString(undefined,{maximumFractionDigits:digits});
export const kernel=(name:string)=>({fmcw_window:'Window',fmcw_fft_stage:'FFT',fmcw_transpose:'Transpose',fmcw_accumulate_power:'Power',fmcw_cfar_2d:'CA-CFAR'}[name]??name);

export async function api<T>(url:string,init?:RequestInit):Promise<T>{
 const response=await fetch('/api'+url,init);
 const data=await response.json();
 if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));
 return data;
}

export function useJob(){
 const [job,setJob]=useState<Job|null>(null),[error,setError]=useState(''),[starting,setStarting]=useState(false);
 useEffect(()=>{const id=localStorage.getItem('maco-job');if(id)api<Job>('/jobs/'+id).then(setJob).catch(()=>localStorage.removeItem('maco-job'));},[]);
 useEffect(()=>{if(job?.state!=='running')return;const timer=setInterval(()=>api<Job>('/jobs/'+job.id).then(setJob).catch(e=>setError(String(e))),1000);return()=>clearInterval(timer);},[job?.id,job?.state]);
 async function startSpec(spec:Record<string,unknown>){
  setStarting(true);setError('');
  try{const result=await api<{id:string}>('/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:'maco-agent',...spec})});localStorage.setItem('maco-job',result.id);setJob({id:result.id,kind:'maco-agent',state:'running'});return true;}
  catch(e){setError(String(e));return false;}
  finally{setStarting(false);}
 }
 return{job,error,starting,startSpec};
}
