import {useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {api,fmt,kernel,useJob} from './studio';
import type {AgentEvent,Progress,Workload} from './studio';
import {ArchitectureModeling,ArchitectureWorkbench,MappingWorkbench} from './RadarViews';
import type {Entry,Implementation,RadarData} from './radar';
import {bestIndex,cycles,kernels} from './radar';
import './radar.css';

type Interpretation={workload:Workload;unsupported:string[]};
type SearchMethod='full_maco'|'hardware_only'|'single_agent';
const defaultPrompt='FMCW range–Doppler detection, 256 samples per chirp, 128 chirps per frame, 4 RX channels, FP32 complex. Minimize estimated cycles/frame; compare 2×2, 4×4, and 6×6 CGRAs and legal per-kernel unroll factors.';
const displayPrompt=(workload:Workload)=>workload.description.replace(/Minimize SRAM(?: dynamic)? energy(?: per frame|\/frame)?\.?/i,'').trim();
const stageFailure=(stage:'verify'|'synth'|'layout',error?:string)=>{
 const label=stage==='synth'?'Synthesis':stage==='verify'?'RTL verification':'Layout';
 return /timed?\s*out|timeout/i.test(error??'')?`${label} timed out. Open the log for details.`:`${label} failed. Open the log for details.`;
};

const roleName=(role?:string)=>({CGRACoDesigner:'Co-designer',CGRAFixer:'Design checker',CoarseGrainedJudge:'Shortlist reviewer',FineGrainedJudge:'Final reviewer'}[role??'']??role??'Agent');
const eventText=(e:AgentEvent)=>{
 const stage=kernel(e.candidate?.kernel??'kernel');
 switch(e.kind){
  case 'run_started':return 'Exploration started';
  case 'round_started':return `Started search round ${e.round}`;
  case 'agent_started':return `${roleName(e.role)} started`;
  case 'agent_returned':return `${roleName(e.role)} finished`;
  case 'agent_failed':return `${roleName(e.role)} failed`;
  case 'proposed':return `Proposed ${e.designs?.length??0} designs`;
  case 'repaired':return `Checked ${e.designs?.length??0} designs`;
  case 'default_fu_added':return 'Added required Mul to Tile 0';
  case 'candidate_rejected':return 'Rejected an invalid design';
  case 'shortlisted':return `Shortlisted ${e.designs?.length??0} designs`;
  case 'predicted':return 'Selected a design for evaluation';
  case 'budget_skipped':return 'Skipped a design: mapping limit reached';
  case 'evaluation_started':return `Started mapping ${stage}`;
  case 'evaluation_finished':return e.success===false?`${stage} mapping failed`:`Mapped ${stage}${e.mapping_ii!=null?` · II = ${e.mapping_ii}`:''}`;
  case 'cache_hit':return `Reused the previous ${stage} mapping`;
  case 'memory_evaluation_started':return `Evaluating ${e.banks??'—'} × ${e.bank_kib??'—'} KiB SRAM with CACTI`;
  case 'memory_evaluation_failed':return 'CACTI SRAM evaluation failed';
  case 'design_measured':return 'Completed design evaluation';
  case 'feedback':return 'Returned measured results to the agents';
  case 'run_finished':return 'Exploration finished';
  case 'run_failed':return 'Exploration failed';
  default:return 'Updated exploration state';
 }
};

function Field({label,value}:{label:string;value:string|number}){return <label className="flow-field"><span>{label}</span><output>{value}</output></label>;}

function PipelinePanel({entry,workload,stage,setStage}:{entry:Entry;workload?:Workload;stage:number;setStage:(n:number)=>void}){
 const notes=['Hann coefficient multiply','Range / Doppler butterflies','Strided matrix exchange','RX magnitude accumulation','Guard / training-cell detection'];
 const specs=[['Samples/chirp',workload?.samples??'—'],['Chirps/frame',workload?.chirps??'—'],['RX channels',workload?.rx??'—'],['Precision',workload?.dtype==='float32'?'FP32':workload?.dtype??'—']];
 return <section className="flow-panel pipeline-panel"><header><h2>Workload</h2><span>FMCW Radar</span></header><div className="workload-summary"><h3>FMCW Range–Doppler Detection</h3><div className="workload-specs">{specs.map(([label,value])=><div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div></div><div className="pipeline-label"><strong>Kernel Pipeline</strong></div><nav aria-label="FMCW processing pipeline">{kernels.map((name,i)=><button key={name} className={stage===i?'active':''} onClick={()=>setStage(i)}><b>{i+1}</b><span><strong>{kernel(name)}</strong>{stage===i&&<small>{notes[i]}</small>}</span><em>{entry.mappings[i].mapping_ii==null?'—':`II ${entry.mappings[i].mapping_ii}`}</em></button>)}</nav></section>;
}

function KernelPanel({entry,stage,setStage}:{entry:Entry;stage:number;setStage:(n:number)=>void}){
 const m=entry.mappings[stage];
 const graph=useRef<HTMLDivElement>(null),drag=useRef({active:false,x:0,y:0,left:0,top:0});
 const nodes=m.schedule.placements,edges=m.schedule.dfg_edges??[];
 const slots=[...new Set(nodes.map(n=>n.cycle))].sort((a,b)=>a-b),grouped=new Map(slots.map(c=>[c,nodes.filter(n=>n.cycle===c)]));
 const maxGroup=Math.max(1,...[...grouped.values()].map(group=>group.length)),width=Math.max(520,slots.length*86+60),height=Math.max(240,maxGroup*52+48);
 const position=new Map<number,{x:number;y:number}>();
 slots.forEach((cycle,i)=>grouped.get(cycle)!.forEach((n,j)=>position.set(n.node,{x:42+i*86,y:34+j*52})));
 const opcode=(instruction:string)=>{
  const raw=instruction.match(/=\s*([a-z][\w.]*)\b/i)?.[1]??instruction.match(/^\s*([a-z][\w.]*)\b/i)?.[1]??'op';
  return raw==='getelementptr'?'addr':raw.replace(/^llvm\./,'').slice(0,7);
 };
 const kind=(instruction:string)=>{const value=opcode(instruction);return /load|store|addr/.test(value)?'memory':/br|ret|phi|cmp|sel/.test(value)?'control':'compute';};
 return <section className="flow-panel kernel-panel"><header><h2>Kernel</h2></header><div className="kernel-controls">
  <div className="kernel-form">
   <div className="kernel-row"><label>Application</label><output>fmcw_mapping.c</output><span className="kernel-status">Compiled ✓</span></div>
   <div className="kernel-row"><label>Kernel</label><select aria-label="Radar processing stages" value={stage} onChange={e=>setStage(+e.target.value)}>{kernels.map((name,i)=><option key={name} value={i}>{kernel(name)}</option>)}</select><span className="kernel-status">Mapped ✓</span></div>
   <div className="kernel-row compiler-row"><label>Compiler</label><div className="compiler-factors"><div><span>Unroll</span><strong>×{m.candidate.unroll_factor}</strong></div><div><abbr title="Vectorization">Vector</abbr><strong>{m.candidate.architecture_vectorization??'none'}</strong></div></div></div>
  </div>
  <div className="graph-metrics"><strong>Data-Flow Graph</strong><label><span>RecMII</span><output>{m.recurrence_mii}</output></label><label><span>ResMII</span><output>{m.resource_mii}</output></label><label><span>Achieved II</span><output>{m.mapping_ii??'—'}</output></label></div>
  <div className="dfg-canvas" ref={graph} onPointerDown={e=>{const el=graph.current;if(!el)return;drag.current={active:true,x:e.clientX,y:e.clientY,left:el.scrollLeft,top:el.scrollTop};el.setPointerCapture(e.pointerId);}} onPointerMove={e=>{const el=graph.current,d=drag.current;if(!el||!d.active)return;el.scrollLeft=d.left-(e.clientX-d.x);el.scrollTop=d.top-(e.clientY-d.y);}} onPointerUp={e=>{drag.current.active=false;graph.current?.releasePointerCapture(e.pointerId);}} onPointerCancel={()=>{drag.current.active=false;}}>{nodes.length?<svg style={{width,height}} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet" role="img" aria-label={`${kernel(m.candidate.kernel)} data-flow graph`}>
   <defs><marker id="dfg-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0 0 7 3.5 0 7Z"/></marker></defs>
   {edges.map((e,i)=>{const a=position.get(e.source),b=position.get(e.target);if(!a||!b)return null;const dx=b.x-a.x,dy=b.y-a.y,length=Math.max(Math.hypot(dx,dy),1),ox=18*dx/length,oy=18*dy/length;return <line key={i} className="dfg-edge" x1={a.x+ox} y1={a.y+oy} x2={b.x-ox} y2={b.y-oy} markerEnd="url(#dfg-arrow)"/>;})}
   {nodes.map(n=>{const p=position.get(n.node)!;return <g className={`dfg-node ${kind(n.instruction)}`} key={n.node}><title>Node {n.node} · cycle {n.cycle}\n{n.instruction}</title><circle cx={p.x} cy={p.y} r="18"/><text x={p.x} y={p.y+3} textAnchor="middle">{opcode(n.instruction).slice(0,5)}</text></g>;})}
  </svg>:<span>DFG unavailable</span>}</div>
  <footer className="dfg-summary"><span>{nodes.length} operations</span><span>{edges.length} dependencies</span><span>Mapping time {fmt(m.elapsed_seconds,2)} s</span></footer>
 </div></section>;
}

function MacoPanel({entry,workload,prompt,setPrompt,method,setMethod,objective,setObjective,onRun,busy,error,progress,implementation,onExport,archived}:{entry:Entry;workload?:Workload;prompt:string;setPrompt:(s:string)=>void;method:SearchMethod;setMethod:(value:SearchMethod)=>void;objective:'cycles'|'energy';setObjective:(value:'cycles'|'energy')=>void;onRun:()=>void;busy:boolean;error:string;progress?:Progress;implementation?:Implementation|null;onExport:()=>void;archived:boolean}){
 const events=[...(progress?.events??[])].reverse();
 const explorationFailed=events.some(e=>e.kind==='run_failed');
 const configMemory=entry.design.config_mem??entry.architecture?.control_memory??entry.mappings[0]?.candidate.control_memory;
 const energyGoal=workload?.objective==='energy',primaryLabel=energyGoal?'Dynamic energy/frame':'Frame estimate',primaryValue=energyGoal?(entry.energy?.total_dynamic_energy_uj==null?'—':fmt(entry.energy.total_dynamic_energy_uj,2)):(cycles(entry)==null?'—':fmt(cycles(entry)!/1e6,2)),primaryUnit=energyGoal?'µJ/frame':'M cycles';
 const steps=[['explore','Explore'],['verify','Generate & Verify RTL'],['synth','Synthesize']] as const;
 const mainDone=implementation?.stages.verify.state==='passed'&&implementation.stages.synth.state==='passed';
 const flowState=(name:string)=>name==='explore'?(explorationFailed?'failed':implementation?'passed':busy?'running':events.some(e=>e.kind==='run_finished')?'passed':'pending'):(implementation?.stages[name as 'verify'|'synth']?.state??'pending');
 const position=mainDone?3:implementation?.current==='synth'?2:implementation?.current==='verify'?1:0;
 const percentage=implementation?position/3*100:busy?Math.min(100/3,(100/3)*(progress?.completed??0)/(progress?.total??30)):events.some(e=>e.kind==='run_finished')?100/3:0;
 const current=explorationFailed?'Flow stopped':mainDone?'Flow complete':implementation?.current?steps.find(([key])=>key===implementation.current)?.[1]:busy?'Explore':implementation?.state==='failed'?'Flow stopped':'Ready to explore';
 return <section className={`flow-panel maco-panel ${archived?'archived':''}`}><header><h2>RACO Design Assistant</h2><i className={busy?'busy':''}/></header>
  {archived?<section className="design-intent archive-intent"><h3>Earlier search · seed 37</h3><p>One CGRA shared across five FMCW kernels. The agents propose array size and compiler unroll; CHIA returns actual mapper feedback.</p><a href="/?mode=live">Configure a new search ↗</a></section>:<form className="design-intent" onSubmit={e=>{e.preventDefault();onRun();}}><h3>Design Intent</h3><label htmlFor="workload-description">Describe your workload and design requirements</label><textarea id="workload-description" value={prompt} onChange={e=>setPrompt(e.target.value)}/><label>Exploration method</label><div className="method-select" role="group" aria-label="Exploration method"><button type="button" title="Four-agent hardware/compiler co-design" className={method==='full_maco'?'active':''} onClick={()=>setMethod('full_maco')}>Multi-agent</button><button type="button" title="Architecture search with fixed compiler settings" className={method==='hardware_only'?'active':''} onClick={()=>setMethod('hardware_only')}>Hardware only</button><button type="button" title="One-agent hardware/compiler co-design" className={method==='single_agent'?'active':''} onClick={()=>setMethod('single_agent')}>Single agent</button></div><label>Goal</label><div className="objective-select" role="group" aria-label="Optimization goal"><button type="button" className={objective==='cycles'?'active':''} onClick={()=>setObjective('cycles')}>Performance</button><button type="button" className={objective==='energy'?'active':''} onClick={()=>setObjective('energy')}>Energy</button></div><button className="run-button" disabled={busy||!prompt.trim()}>{busy?'Exploration running…':'Run exploration'}</button>{error&&<p className="inline-error">{error}</p>}</form>}
  {archived?<section className="design-flow round-decisions"><h3>Feedback changed the choice</h3>{progress?.rounds?.map(round=><div className="round-decision" key={round.iteration}><b>R{round.iteration}</b><span>Judge: {round.llm_choice.tile_size}<br/>Tool best: {round.measured_winner?.design.tile_size??'—'}</span><strong>{round.measured_winner?.frame_estimate.estimated_cycles==null?'—':`${fmt(round.measured_winner.frame_estimate.estimated_cycles/1e6,2)}M`}</strong></div>)}</section>:<section className="design-flow"><h3>Design Flow</h3><div className="flow-status" aria-label="Automated design flow">{steps.map(([key,label],i)=><div key={key} className={`flow-step ${flowState(key)}`}><b>{flowState(key)==='passed'?'✓':flowState(key)==='failed'?'×':i+1}</b><span>{label}</span></div>)}</div><div className="flow-progress"><progress aria-label="End-to-end flow progress" value={percentage} max="100"/><span>{current}</span></div>{implementation?.detail&&<p className="flow-detail">{implementation.detail.stage}</p>}{!mainDone&&implementation?.state==='failed'&&<p className="flow-error">{stageFailure(implementation.current as 'verify'|'synth',implementation.stages[implementation.current as 'verify'|'synth']?.error)}</p>}</section>}
  <section className="selected-design"><h3>Best Measured Design</h3><div className="primary-result"><span>{primaryLabel}</span><strong>{primaryValue}<small>{primaryUnit}</small></strong></div><dl><div><dt>Array size</dt><dd>{entry.design.tile_size}</dd></div><div><dt>Frame estimate</dt><dd>{cycles(entry)==null?'—':`${fmt(cycles(entry)!/1e6,2)} M cycles`}</dd></div>{archived?<><div><dt>Kernel unroll</dt><dd>[{entry.design.unroll_factors?.join(', ')??'—'}]</dd></div><div><dt>Hardware status</dt><dd>Not validated</dd></div></>:<><div><dt>Config memory{configMemory!=null&&configMemory>16?' (earlier run)':''}</dt><dd>{configMemory??'—'}</dd></div><div><dt>SRAM</dt><dd>{entry.architecture?`${entry.architecture.memory.banks} × ${entry.architecture.memory.bank_kib} KiB`:'—'}</dd></div></>}</dl>{!archived&&<button className="secondary-button" onClick={onExport}>Export architecture</button>}</section>
  <section className="agent-trace"><h3>Tool and agent audit trail</h3><div className="trace-events">{events.map(e=><div className="trace-event" key={e.sequence}><span>{String(e.sequence).padStart(2,'0')}</span><p>{eventText(e)}</p></div>)}</div></section>
 </section>;
}

function ArchivedEvidence({data,entry}:{data:RadarData;entry:Entry}){
 const selected=entry.frame_estimate.breakdown,cfar=selected.fmcw_cfar_2d,share=cfar&&cycles(entry)?100*cfar.estimated_cycles/cycles(entry)!:null;
 return <section className="implementation-stack archive-evidence">
  <section className="flow-panel verification-panel"><header><h2>Agent vs. Reference</h2></header><div className="evidence-content"><div className="evidence-pair"><span>Agent · {data.run_summary?.evaluations??'—'} mappings</span><strong>{fmt((cycles(entry)??0)/1e6,2)}M cycles</strong></div><div className="evidence-pair"><span>Full reference · {data.reference?.evaluations??'—'} mappings</span><strong>{data.reference?`${fmt(data.reference.best_estimated_cycles/1e6,2)}M cycles`:'—'}</strong></div><p>Same best estimate. Agent {fmt(data.run_summary?.elapsed_seconds,1)} s; reference {fmt(data.reference?.elapsed_seconds,1)} s. Single seed; no matched-budget search claim.</p></div></section>
  <section className="flow-panel report-panel"><header><h2>What the cost counts</h2></header><div className="evidence-content"><div className="evidence-pair"><span>CA-CFAR share</span><strong>{fmt(share,1)}%</strong></div><p>Sum of scheduled loop groups × mapper II. Memory stalls, transfer and clock are unmeasured.</p></div></section>
  <section className="flow-panel layout-panel"><header><h2>Evidence &amp; limits</h2></header><div className="evidence-content"><div className="evidence-badge">ARCHIVED RUN · MAPPER ESTIMATE</div><p>Native C vs NumPy: exact detection masks agree in {data.native_validation?.passed??'—'}/{data.native_validation?.total??'—'} scenes.</p><p>Candidate RTL and full-frame CGRA execution are not validated. No measured FPS, full-chip area or energy.</p><a href="/api/radar/demo/trace" target="_blank" rel="noreferrer">Download agent trace ↗</a><a href="/api/download/maco" target="_blank" rel="noreferrer">Download exhaustive reference ↗</a></div></section>
 </section>;
}

type HardwareResult={action:string;status:string;job_id?:string;rtl_regression?:string;fp32_regression?:string;fp32_cases?:number;core_area_mm2?:number;tile_area_mm2?:number;memory?:{area_mm2:number;power_mw:number;source:string};layout?:string;elapsed_seconds?:number;error?:string};
type HardwareJob={id:string;kind:string;state:string;started_at?:number;error?:string;progress?:{stage:string;completed:number;total:number};result?:HardwareResult};

function ImplementationPanel({entry,implementation,hardware,run}:{entry:Entry;implementation?:Implementation|null;hardware?:HardwareJob|null;run:string}){
 const[active,setActive]=useState<HardwareJob|null>(null),[results,setResults]=useState<Record<string,HardwareResult>>({}),[error,setError]=useState(''),[rtlSource,setRtlSource]=useState(''),[rtlError,setRtlError]=useState('');
 const auto=implementation?.design_id===entry.id?implementation:null;
 const mainDone=auto?.stages.verify.state==='passed'&&auto.stages.synth.state==='passed';
 const layoutStage=auto?.stages.layout;
 useEffect(()=>{if(!active||active.state!=='running')return;const poll=async()=>{try{const job=await api<HardwareJob>(`/jobs/${active.id}`);setActive(job);if(job.state!=='running'){if(job.result){const result={...job.result,job_id:job.id};setResults(v=>({...v,[result.action]:result}));}setError(job.result?.error??job.error??'');}}catch(e){setError(String(e));}};const timer=setInterval(()=>void poll(),1000);return()=>clearInterval(timer);},[active?.id,active?.state]);
 useEffect(()=>{const id=auto?.stages.verify.state==='passed'?run:results.verify?.job_id;if(!id)return;let live=true;setRtlSource('');setRtlError('');fetch(`/api/jobs/${id}/rtl`).then(response=>response.ok?response.text():Promise.reject(Error(`RTL request returned ${response.status}`))).then(source=>{if(live)setRtlSource(source);}).catch(reason=>{if(live)setRtlError(String(reason));});return()=>{live=false;};},[auto?.stages.verify.state,results.verify?.job_id,run]);
 async function launch(action:'verify'|'synth'|'layout'){if(active?.state==='running')return;setError('');try{const job=await api<HardwareJob>('/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:`cgra-${action}`,architecture:{design:entry.design,architecture:entry.architecture},...(action==='layout'?{source_run:run}:{})})});setActive({...job,state:'running'});}catch(e){setError(String(e));}}
 const result=(name:'verify'|'synth'|'layout')=>(auto?.stages[name].result as HardwareResult|undefined)??results[name];
 const verify=result('verify'),synth=result('synth'),layout=result('layout'),synthComplete=synth?.status==='passed',coreArea=synthComplete?(synth.core_area_mm2??synth.tile_area_mm2):undefined,sramArea=synthComplete?synth.memory?.area_mm2:undefined,dynamicEnergy=synthComplete?entry.energy?.total_dynamic_energy_uj:undefined,busy=active?.state==='running'||hardware?.state==='running',running=(name:string)=>active?.state==='running'&&active.kind===`cgra-${name}`;
 const task=(name:'verify'|'synth')=>auto?<div className="hardware-progress"><span>{auto.stages[name].state==='running'?(auto.current===name?auto.detail?.stage??'Running…':'Running…'):auto.stages[name].state==='passed'?'Completed':auto.stages[name].state==='failed'?'Failed':'Queued'}</span>{auto.stages[name].error&&<span className="hardware-error">{stageFailure(name,auto.stages[name].error)}</span>}{auto.stages[name].state!=='pending'&&<a className="job-log" href={`/api/jobs/${run}/implementation/${name}/log`} target="_blank">Log ↗</a>}</div>:active?.kind===`cgra-${name}`?<><div className="hardware-progress">{active.state==='running'&&<progress value={active.progress?.completed??0} max={active.progress?.total??4}/>}<span>{active.state==='running'?(active.progress?.stage??'Starting CGRA-Flow'):(active.result?.status==='passed'?'Completed':'Task failed')}</span></div><a className="job-log" href={`/api/jobs/${active.id}/log`} target="_blank">Task log ↗</a>{error&&<p className="hardware-error">{stageFailure(name,error)}</p>}</>:name==='synth'&&hardware?.kind==='cgra-synth'?<div className="hardware-progress"><span>Independent job · {hardware.state==='running'?(hardware.progress?.stage??'starting'):hardware.state==='completed'?'completed':'failed'}{hardware.state==='running'&&hardware.started_at?` · ${Math.floor((Date.now()/1000-hardware.started_at)/60)} min`:''}</span><a className="job-log" href={`/api/jobs/${hardware.id}`} target="_blank">Job status ↗</a></div>:null;
 const layoutJob=active?.kind==='cgra-layout'?active:null;
 const generation=verify?.status==='passed'?'Generated':auto?.current==='verify'||running('verify')?'Generating':'Not run';
 return <section className="implementation-stack"><section className="flow-panel verification-panel"><header><h2>RTL Generation &amp; Verification</h2></header>
  <div className="tool-output rtl-output" tabIndex={0}><strong>Generated SystemVerilog</strong>{auto&&task('verify')}{rtlSource?<pre>{rtlSource}</pre>:<span>{rtlError||(generation==='Not run'?'Not generated yet':'Loading generated RTL…')}</span>}{auto?.stages.verify.state==='passed'&&<a className="job-log" href={`/api/jobs/${run}/rtl`} target="_blank" rel="noreferrer">Open full SystemVerilog ↗</a>}</div>
  {!auto&&<button className="panel-action" disabled={busy} onClick={()=>void launch('verify')}>{running('verify')?'Generating RTL and running tests…':'Generate RTL & Run Tests'}</button>}
 </section>
  <section className="flow-panel report-panel"><header><h2>Area &amp; Energy</h2></header><div className="report-values"><Field label="CGRA logic area" value={coreArea==null?'—':`${fmt(coreArea,4)} mm²`}/><Field label="SRAM area" value={sramArea==null?'—':`${fmt(sramArea,4)} mm²`}/><Field label="Dynamic energy/frame" value={dynamicEnergy==null?'—':`${fmt(dynamicEnergy,2)} µJ`}/></div>{task('synth')}{!auto&&<button className="panel-action" disabled={busy} onClick={()=>void launch('synth')}>{running('synth')?'Synthesizing…':'Synthesize'}</button>}</section>
  <section className="flow-panel layout-panel"><header><h2>Layout</h2><span>Optional</span></header>{layout?.layout&&(auto||layout.job_id)?<img className="cgra-layout" src={`/api/jobs/${layoutStage?.job_id??layout.job_id??run}/layout`} alt="OpenROAD CGRA layout"/>:<><div className="layout-fields"><Field label="Platform" value="ASAP7"/><Field label="Flow configuration" value="config.mk"/><Field label="Timing constraints" value="constraint.sdc"/></div><p className="layout-note">{mainDone?'Run layout when needed.':'Available after RTL verification and synthesis.'}</p></>}<button className="panel-action" disabled={!mainDone||busy||layoutStage?.state==='passed'||layoutStage?.state==='running'} onClick={()=>void launch('layout')}>{running('layout')||layoutStage?.state==='running'?'OpenROAD running…':layoutStage?.state==='passed'?'Layout complete':'Run layout'}</button>{layoutStage?.state!=='pending'&&layoutStage&&<div className="hardware-progress"><span>{layoutStage.state==='running'?'OpenROAD running…':layoutStage.state==='passed'?'Completed':'Failed'}</span>{layoutStage.error&&<span className="hardware-error">{stageFailure('layout',layoutStage.error)}</span>}{layoutStage.job_id&&<a className="job-log" href={`/api/jobs/${layoutStage.job_id}/log`} target="_blank">Task log ↗</a>}</div>}{!layoutStage?.job_id&&layoutJob&&<div className="hardware-progress"><span>{layoutJob.state==='running'?'OpenROAD running…':layoutJob.state==='completed'?'Completed':'Failed'}</span><a className="job-log" href={`/api/jobs/${layoutJob.id}/log`} target="_blank">Task log ↗</a></div>}{error&&<p className="hardware-error">{stageFailure('layout',error)}</p>}</section></section>;
}

function LoadingWorkbench({error}:{error?:string}){return <div className="flow-workspace loading-shell" aria-busy={!error}>
 <div className="left-stack"><section className="flow-panel pipeline-panel"><header><h2>Workload</h2><span>FMCW Radar</span></header></section><section className="flow-panel kernel-panel"><header><h2>Kernel</h2></header></section></div>
 <section className="flow-panel architecture-panel"><header><h2>CGRA Architecture</h2></header><div className={'compact-loading '+(error?'load-error':'')}>{!error&&<i/>}<span>{error?'Measured design is temporarily unavailable.':'Loading latest measured design…'}</span></div></section>
 <section className="flow-panel architecture-modeling"><header><h2>CGRA Modeling</h2></header></section>
 <section className="flow-panel maco-panel"><header><h2>RACO Design Assistant</h2></header></section>
 <section className="flow-panel mapping-panel"><header><h2>Mapping</h2></header></section>
 <section className="implementation-stack"><section className="flow-panel verification-panel"><header><h2>Verification</h2></header></section><section className="flow-panel report-panel"><header><h2>Report Area/Power</h2></header></section><section className="flow-panel layout-panel"><header><h2>Layout</h2></header></section></section>
 </div>;}

function App(){
 const params=new URLSearchParams(location.search),demo=params.get('mode')!=='live'&&params.get('demo')!=='0';
 const cacheKey=demo?'maco-radar-demo':'maco-radar-design';
 const[data,setData]=useState<RadarData|null>(()=>{try{return JSON.parse(localStorage.getItem(cacheKey)??'null');}catch{return null;}}),[error,setError]=useState('');
 const[stage,setStageState]=useState(0),[cycle,setCycle]=useState(0),[selectedPE,setSelectedPE]=useState(0);
 const[prompt,setPromptState]=useState(defaultPrompt),[method,setMethod]=useState<SearchMethod>('full_maco'),[objective,setObjective]=useState<'cycles'|'energy'>('cycles'),[inputError,setInputError]=useState(''),[interpreting,setInterpreting]=useState(false);
 const[hardware,setHardware]=useState<HardwareJob|null>(null);
 const edited=useRef(false),jobs=useJob();
 useEffect(()=>{if(demo)return;let live=true;const poll=async()=>{try{const health=await api<{active_job:string|null}>('/health');const id=health.active_job??localStorage.getItem('maco-hardware-job');if(!id)return;const job=await api<HardwareJob>(`/jobs/${id}`);if(job.kind.startsWith('cgra-')&&live){localStorage.setItem('maco-hardware-job',id);setHardware(job);}}catch{}};void poll();const timer=setInterval(()=>void poll(),2000);return()=>{live=false;clearInterval(timer);};},[demo]);
 useEffect(()=>{let active=true;const poll=()=>api<RadarData>(demo?'/radar/demo':'/radar/design').then(async d=>{if(!active)return;setError('');if(!d.entries?.length){if(!localStorage.getItem(cacheKey)){const fallback=await api<RadarData>('/radar/demo');if(active)setData(fallback);}return;}setData(d);localStorage.setItem(cacheKey,JSON.stringify(d));if(!edited.current&&d.workload?.description){setPromptState(displayPrompt(d.workload));setObjective(d.workload.objective);}}).catch(e=>active&&setError(String(e)));poll();const timer=demo?undefined:setInterval(poll,2000);return()=>{active=false;clearInterval(timer);};},[cacheKey,demo]);
 const entries=data?.entries??[],index=entries.length?bestIndex(entries,data?.workload?.objective):0,entry=entries[index];
 const running=jobs.job?.state==='running',progress=jobs.job?.kind==='maco-agent'&&jobs.job.progress?jobs.job.progress:data?.progress;
 const failedEvent=[...(progress?.events??[])].reverse().find(event=>event.kind==='run_failed');
 const rawFailure=!running&&failedEvent?(failedEvent.error??'Exploration failed'):jobs.job?.state==='failed'?(jobs.job.error??'Exploration failed'):'';
 const jobFailure=rawFailure.includes('Fixer produced no executable bounded designs')?'No valid design: missing required Mul. Rerun exploration.':rawFailure;
 const displayImplementation=data&&entry&&data.implementation?.design_id===entry.id?data.implementation:null;
 const selectedImplementation=jobs.job?.kind==='maco-agent'&&data?.run!==jobs.job.id?null:displayImplementation;
 const setStage=(value:number)=>{setStageState(value);setCycle(0);setSelectedPE(0);};
 const setPrompt=(value:string)=>{edited.current=true;setPromptState(value);};
 async function run(){if(running||interpreting||!prompt.trim())return;setInterpreting(true);setInputError('');try{const result=await api<Interpretation>('/workload/interpret',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({description:prompt})});if(result.unsupported.length){setInputError(result.unsupported.join(' '));return;}const workload={...result.workload,objective};await jobs.startSpec({workload,interpretation:{...result,workload},rounds:1,method});}catch(e){setInputError(String(e));}finally{setInterpreting(false);}}
 function exportArch(){if(!entry)return;const content=JSON.stringify({design:entry.design,architecture:entry.architecture,memory:entry.memory},null,2),url=URL.createObjectURL(new Blob([content],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='maco-selected-architecture.json';a.click();URL.revokeObjectURL(url);}
 return <main className="cgra-web"><header className="app-bar"><strong>RACO: An Agentic End-to-End Framework for FMCW CGRA Exploration, Compilation, Synthesis and Evaluation</strong><nav aria-label="Experiment mode"><a className={demo?'active':''} href="/?demo=1">Earlier demo</a><a className={!demo?'active':''} href="/?mode=live">Live exploration</a></nav></header>
  {!entry||!data?<LoadingWorkbench error={error}/>:<div className="flow-workspace">
   <div className="left-stack"><PipelinePanel entry={entry} workload={data.workload} stage={stage} setStage={setStage}/><KernelPanel entry={entry} stage={stage} setStage={setStage}/></div>
   <ArchitectureWorkbench entry={entry} selected={selectedPE} setSelected={setSelectedPE}/>
   <ArchitectureModeling entry={entry} selected={selectedPE}/>
   <MacoPanel entry={entry} workload={data.workload} prompt={prompt} setPrompt={setPrompt} method={method} setMethod={setMethod} objective={objective} setObjective={value=>{edited.current=true;setObjective(value);}} onRun={()=>void run()} busy={running||interpreting||jobs.starting} error={inputError||jobFailure||jobs.error} progress={progress} implementation={selectedImplementation} onExport={exportArch} archived={demo}/>
   <MappingWorkbench entry={entry} run={data.run} stage={stage} cycle={cycle} setCycle={setCycle} selected={selectedPE} setSelected={setSelectedPE}/>
   {demo?<ArchivedEvidence data={data} entry={entry}/>:<ImplementationPanel entry={entry} implementation={displayImplementation} hardware={hardware} run={data.run}/>}
  </div>}
 </main>;
}

export function mount(){createRoot(document.getElementById('root')!).render(<App/>);}
