import type {Mapping,Plan,Progress} from './studio';
export const kernels=['fmcw_window','fmcw_fft_stage','fmcw_transpose','fmcw_accumulate_power','fmcw_cfar_2d'];
export type Schedule={available:boolean;memory_on_left?:boolean;placements:Array<{node:number;pe:number;cycle:number;instruction:string}>;dfg_edges?:Array<{source:number;target:number}>;links:Array<{source:number;target:number;cycle?:number}>};
export type RadarMapping=Mapping&{resource_mii:number;recurrence_mii:number;fu_utilization_percent:number|null;xbar_utilization_percent:number|null;log_index:number;schedule:Schedule;candidate:Mapping['candidate']&{register_count:number;control_memory:number;bypass_constraint:number}};
export type ArchitectureConfig={tiles:Record<string,{supportedFUs:string[];accessMem:boolean;disabled?:boolean}>;links?:Array<{srcTile:number;dstTile:number}>;control_memory?:number;memory:{banks:number;bank_kib:number;capacity_kib:number;interface_tiles:number[];model:string};fu_profile:string;multiplier_tiles:number;scope:string};
export type MemoryMetrics={read_nj?:number;write_nj?:number;area_mm2?:number;access_ns?:number;dynamic_energy_uj?:number|null;estimated_reads?:number;estimated_writes?:number;source?:string;scope?:string;activity_source?:string;excluded?:string[];error?:string};
export type EnergyMetrics={total_dynamic_energy_uj:number;core_dynamic_energy_uj:number;sram_dynamic_energy_uj:number;components_uj:Record<string,number>;source:string;scope:string};
export type Entry={id:string;event:number;round:number;design:Plan;mappings:RadarMapping[];architecture?:ArchitectureConfig|null;memory?:MemoryMetrics|null;energy?:EnergyMetrics|null;frame_estimate:{valid:boolean;estimated_cycles:number|null;breakdown:Record<string,{estimated_cycles:number;scheduled_loop_groups:number;measured_mapping_ii:number}>}};
export type Implementation={state:string;design_id:string;current:string|null;detail?:{stage:string;completed:number;total:number};stages:Record<'verify'|'synth'|'layout',{state:string;job_id?:string;error?:string;result?:Record<string,unknown>}>};
export type RadarData={run:string;entries:Entry[];progress:Progress;implementation?:Implementation|null;workload?:import('./studio').Workload;baseline_comparable?:boolean;baseline:{id:string;design:Plan;frame_estimate:Entry['frame_estimate']};reference?:{evaluations:number;elapsed_seconds:number;best_estimated_cycles:number};run_summary?:{evaluations:number;llm_calls:number;elapsed_seconds:number}|null;native_validation?:{passed:number;total:number};best_validated_feasible:null};
export const cycles=(e:Entry)=>e.frame_estimate.estimated_cycles;
export const bestIndex=(entries:Entry[],objective:'cycles'|'energy'='cycles')=>entries.reduce((best,e,i)=>{
 const score=(v:Entry)=>objective==='energy'?(v.energy?.total_dynamic_energy_uj??Infinity):(cycles(v)??Infinity);
 return score(e)<score(entries[best])?i:best;
},0);
