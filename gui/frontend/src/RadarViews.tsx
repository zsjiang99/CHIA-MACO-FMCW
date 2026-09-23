import {useLayoutEffect,useRef,useState} from 'react';
import type {CSSProperties,Dispatch,SetStateAction} from 'react';
import {fmt,kernel} from './studio';
import type {Entry,RadarMapping} from './radar';

const fuName=(entry:Entry,id:number)=>{
 const tile=entry.architecture?.tiles[String(id)];
 if(!tile)return 'GENERIC';
 if(tile.accessMem)return 'LD / ST';
 if(tile.supportedFUs.includes('Mul'))return 'MUL / ALU';
 return 'ALU / CTRL';
};

function ArraySvg({entry,mapping,cycle,selected,onSelect,routes=false}:{entry:Entry;mapping?:RadarMapping;cycle?:number;selected:number;onSelect:(id:number)=>void;routes?:boolean}){
 const n=mapping?.candidate.rows??Number(entry.design.tile_size.split('x')[0]);
 const svg=useRef<SVGSVGElement>(null),viewWidth=750,[viewHeight,setViewHeight]=useState(620);
 useLayoutEffect(()=>{const element=svg.current;if(!element)return;const resize=()=>{const {clientWidth,clientHeight}=element;if(clientWidth&&clientHeight){const next=viewWidth*clientHeight/clientWidth;setViewHeight(current=>Math.abs(current-next)>.5?next:current);}};resize();const observer=new ResizeObserver(resize);observer.observe(element);return()=>observer.disconnect();},[]);
 const content={x:viewWidth*.1,y:viewHeight*.1,w:viewWidth*.8,h:viewHeight*.8},spmWidth=92,gap=viewWidth*.045;
 const arrayLeft=content.x+spmWidth+gap,arrayWidth=content.w-spmWidth-gap,slotWidth=arrayWidth/n,slotHeight=content.h/n;
 const tileHeight=Math.min(slotHeight*.58,slotWidth*.68/1.35),tileWidth=tileHeight*1.35,halfW=tileWidth/2,halfH=tileHeight/2;
 const stepX=n>1?(arrayWidth-tileWidth)/(n-1):0,stepY=n>1?(content.h-tileHeight)/(n-1):0;
 const x=(id:number)=>arrayLeft+halfW+(id%n)*stepX;
 const y=(id:number)=>content.y+halfH+Math.floor(id/n)*stepY;
 const ii=Math.max(mapping?.mapping_ii??1,1);
 const placements=mapping?.schedule.placements.filter(p=>cycle==null||p.cycle%ii===cycle)??[];
 const visibleLinks=mapping?.schedule.links.filter(l=>cycle==null||l.cycle==null||l.cycle%ii===cycle)??[];
 const routeLinks=[...new Map(visibleLinks.map(link=>[`${link.source}:${link.target}`,link])).values()];
 const memory=entry.architecture?.memory.interface_tiles??Array.from({length:n},(_,i)=>i*n);
 const op=(id:number)=>placements.find(p=>p.pe===id);
 const spm={x:content.x,y:content.y,w:spmWidth,h:content.h};
 const routeSegment=(source:number,target:number)=>{
  const sx=x(source),sy=y(source),tx=x(target),ty=y(target),vx=tx-sx,vy=ty-sy;
  const scale=Math.min(vx===0?Infinity:halfW/Math.abs(vx),vy===0?Infinity:halfH/Math.abs(vy));
  return {x1:sx+vx*scale,y1:sy+vy*scale,x2:tx-vx*scale,y2:ty-vy*scale};
 };
 const defaultLinks=Array.from({length:n*n},(_,id)=>[
  ...(id%n<n-1?[{srcTile:id,dstTile:id+1},{srcTile:id+1,dstTile:id}]:[]),
  ...(id<n*(n-1)?[{srcTile:id,dstTile:id+n},{srcTile:id+n,dstTile:id}]:[]),
 ]).flat();
 const configuredLinks=(entry.architecture?.links?.length?entry.architecture.links:defaultLinks).filter(link=>link.srcTile<n*n&&link.dstTile<n*n&&link.srcTile!==link.dstTile);
 const directions=new Set(configuredLinks.map(link=>`${link.srcTile}:${link.dstTile}`));
 const pairs=[...new Map(configuredLinks.map(link=>{const a=Math.min(link.srcTile,link.dstTile),b=Math.max(link.srcTile,link.dstTile);return [`${a}:${b}`,{a,b}];})).values()];
 const suffix=routes?'mapping':'architecture',baseArrow=`base-arrow-${suffix}`,memoryArrow=`memory-arrow-${suffix}`,routeArrow=`route-arrow-${suffix}`;
 const memoryRoutes=routes?memory.flatMap(id=>{const placement=op(id);if(!placement||!/^\s*(?:%\S+\s*=\s*)?(load|store)\b/i.test(placement.instruction))return [];return [{id,store:/^\s*store\b/i.test(placement.instruction)}];}):[];
 const cycleColors=['#fff113','#75d561','#f2cb67','#ffac73','#f3993a','#b3ff04','#c2ffff'];
 const cycleStyle={'--cycle-color':cycleColors[(cycle??0)%cycleColors.length]} as CSSProperties;
 return <svg ref={svg} style={cycleStyle} viewBox={`0 0 ${viewWidth} ${viewHeight}`} preserveAspectRatio="xMidYMid meet" role="img" aria-label={`${n} by ${n} CGRA`}>
  <defs>
   <marker id={baseArrow} viewBox="0 0 7 7" markerWidth="7" markerHeight="7" markerUnits="userSpaceOnUse" refX="6" refY="3.5" orient="auto-start-reverse"><path className="mesh-arrow" d="M0 0 7 3.5 0 7Z"/></marker>
   <marker id={memoryArrow} viewBox="0 0 7 7" markerWidth="7" markerHeight="7" markerUnits="userSpaceOnUse" refX="6" refY="3.5" orient="auto-start-reverse"><path className="memory-arrow" d="M0 0 7 3.5 0 7Z"/></marker>
   <marker id={routeArrow} viewBox="0 0 8 8" markerWidth="8" markerHeight="8" markerUnits="userSpaceOnUse" refX="7" refY="4" orient="auto"><path className="route-arrow" d="M0 0 8 4 0 8Z"/></marker>
  </defs>
  <rect className="spm" x={spm.x} y={spm.y} width={spm.w} height={spm.h} rx="3"/><text className="spm-title" x={spm.x+spm.w/2} y={spm.y+spm.h/2-10} textAnchor="middle">Data</text><text className="spm-title" x={spm.x+spm.w/2} y={spm.y+spm.h/2+10} textAnchor="middle">SPM</text><text className="tile-sub" x={spm.x+spm.w/2} y={spm.y+spm.h/2+39} textAnchor="middle">{entry.architecture?.memory.banks??'—'} banks</text>
  {Array.from({length:n*n},(_,id)=>{const p=op(id),tile=entry.architecture?.tiles[String(id)];return <g key={id} className={`flow-tile radar-pe ${selected===id?'selected':''} ${p?'occupied':''} ${tile?.accessMem?'memory':''}`} role="button" tabIndex={0} aria-label={`Processing element ${id}`} onClick={()=>onSelect(id)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect(id);}}}>
   <title>{p?`node ${p.node} · cycle ${p.cycle} · ${p.instruction}`:`Tile ${id} · ${fuName(entry,id)}`}</title>
   <rect x={x(id)-halfW} y={y(id)-halfH} width={tileWidth} height={tileHeight} rx="3"/>
   <text x={x(id)} y={y(id)-2} textAnchor="middle">{p?`Op ${p.node}`:`Tile ${id}`}</text>
   <text className="tile-sub" x={x(id)} y={y(id)+16} textAnchor="middle">{p?`c${p.cycle}`:fuName(entry,id)}</text>
  </g>;})}
  {pairs.map(({a,b})=>{const segment=routeSegment(a,b);return <line key={`mesh-${a}-${b}`} className="mesh" {...segment} markerStart={directions.has(`${b}:${a}`)?`url(#${baseArrow})`:undefined} markerEnd={directions.has(`${a}:${b}`)?`url(#${baseArrow})`:undefined}/>;})}
  {memory.map(id=><line key={`memory-${id}`} className="memory-bus" x1={spm.x+spm.w} y1={y(id)} x2={x(id)-halfW} y2={y(id)} markerStart={`url(#${memoryArrow})`} markerEnd={`url(#${memoryArrow})`}/>)}
  {routes&&routeLinks.filter(link=>link.source!==link.target).map((link,i)=>{const segment=routeSegment(link.source,link.target);return <line key={`route-${i}-${link.source}-${link.target}`} className="route" {...segment} markerEnd={`url(#${routeArrow})`}/>;})}
  {memoryRoutes.map(({id,store})=><line key={`memory-route-${id}`} className="route memory-route" x1={store?x(id)-halfW:spm.x+spm.w} y1={y(id)} x2={store?spm.x+spm.w:x(id)-halfW} y2={y(id)} markerEnd={`url(#${routeArrow})`}/>)}
 </svg>;
}

export function ArchitectureWorkbench({entry,selected,setSelected}:{entry:Entry;selected:number;setSelected:Dispatch<SetStateAction<number>>}){
 return <section className="flow-panel architecture-panel"><header><h2>CGRA Architecture</h2><span>{entry.design.tile_size}</span></header>
  <div className="architecture-body"><div className="architecture-canvas"><ArraySvg entry={entry} selected={selected} onSelect={setSelected}/></div></div>
 </section>;
}

export function ArchitectureModeling({entry,selected}:{entry:Entry;selected:number}){
 const n=entry.mappings[0].candidate.rows,tile=entry.architecture?.tiles[String(selected)],supported=new Set(tile?.supportedFUs??[]);
 const fus=[['add','Add'],['mul','Mul'],['div','Div'],['fadd','FAdd'],['fmul','FMul'],['cmp','Cmp'],['logic','Logic'],['sel','Sel'],['load','Ld'],['store','St']];
 const link=(target:number)=>entry.architecture?.links?.some(l=>l.srcTile===selected&&l.dstTile===target)??false;
 const row=Math.floor(selected/n),col=selected%n;
 const directions=[['NW',row>0&&col>0?selected-n-1:-1],['N',row>0?selected-n:-1],['NE',row>0&&col<n-1?selected-n+1:-1],['W',col>0?selected-1:-1],['E',col<n-1?selected+1:-1],['SW',row<n-1&&col>0?selected+n-1:-1],['S',row<n-1?selected+n:-1],['SE',row<n-1&&col<n-1?selected+n+1:-1]] as Array<[string,number]>;
 return <section className="flow-panel architecture-modeling"><header><h2>CGRA Modeling</h2><span>Tile {selected}</span></header>
  <div className="parameter-top"><label>Rows <output>{n}</output></label><label>Columns <output>{n}</output></label><label>Per-bank SRAM <output>{entry.architecture?.memory.bank_kib??'—'} KiB</output></label><label>Config memory <output>{entry.mappings[0]?.candidate.control_memory??entry.architecture?.control_memory??'—'}</output></label></div>
  <div className="parameter-groups"><section><h3>SPM outgoing links</h3><div className="spm-link-grid">{[0,1,2,3].map(i=><label className="check-row" key={i}><input type="checkbox" checked={i<(tile?.accessMem?1:0)} readOnly/>link {i}</label>)}</div></section>
   <section><h3>Functional units</h3><div className="fu-grid">{fus.map(([label,name])=><label className="check-row" key={name}><input type="checkbox" checked={supported.has(name)||(['add','cmp','logic','sel'].includes(label)&&supported.size>0)} readOnly/>{label}</label>)}</div></section>
   <section><h3>Crossbar outgoing links</h3><div className="direction-grid">{directions.map(([name,target])=><label className="check-row" key={name}><input type="checkbox" checked={target>=0&&link(target)} readOnly/>{name}</label>)}</div></section>
  </div>
 </section>;
}

export function MappingWorkbench({entry,run,stage,cycle,setCycle,selected,setSelected}:{entry:Entry;run:string;stage:number;cycle:number;setCycle:Dispatch<SetStateAction<number>>;selected:number;setSelected:Dispatch<SetStateAction<number>>}){
 const m=entry.mappings[stage],ii=Math.max(m.mapping_ii??1,1);
 const slot=Math.min(cycle,ii-1);
 const operations=m.schedule.placements.filter(p=>p.cycle%ii===slot),active=operations.find(p=>p.pe===selected);
 return <section className="flow-panel mapping-panel"><header><h2>Mapping</h2><div className="cycle-controls"><button onClick={()=>setCycle((slot-1+ii)%ii)} aria-label="Previous cycle">‹</button><strong>{kernel(m.candidate.kernel)} · cycle {slot}</strong><span>/ II {ii}</span><button onClick={()=>setCycle((slot+1)%ii)} aria-label="Next cycle">›</button></div></header>
  <div className="mapping-body"><div className="mapping-canvas"><ArraySvg entry={entry} mapping={m} cycle={slot} selected={selected} onSelect={setSelected} routes/></div></div>
  <footer className="mapping-footer"><span>{operations.length} operations</span><span>FU {fmt(m.fu_utilization_percent,1)}%</span><span>routes {fmt(m.xbar_utilization_percent,1)}%</span><span>{active?`Tile ${selected}: node ${active.node}`:`Tile ${selected}: idle`}</span><a href={`/api/radar/log/${run}/${m.log_index}`} target="_blank">Evidence ↗</a></footer>
 </section>;
}
