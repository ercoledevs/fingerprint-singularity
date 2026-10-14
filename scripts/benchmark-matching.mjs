// CPU-only comparison: no Rust implementation and no projected speedup.
import {performance} from 'node:perf_hooks';
import {spawnSync} from 'node:child_process';
import {mkdir,writeFile} from 'node:fs/promises';
const api=await import(new URL('../artifacts/intensive-v04/vendor/0.4.0/dist/index.js',import.meta.url));
const snapshot={schema:'singularity/v3',probe:'web/v2',engine:'blink',scope:'benchmark',
  signals:{platform:'macos',cores:8,memory:8,language:'en',timezone:'UTC'},
  detail:{gpu:'a'.repeat(64),fonts:'b'.repeat(64),canvas:'c'.repeat(64)}};
const node=[];
for(const count of [1,16,64,256]){
  const candidates=Array.from({length:count},(_,i)=>({id:'candidate-'+i,snapshot}));
  for(let i=0;i<100;i++)api.matchResilient(snapshot,candidates);
  const values=[];
  for(let i=0;i<1000;i++){const t=performance.now();api.matchResilient(snapshot,candidates);values.push(performance.now()-t);}
  values.sort((a,b)=>a-b);node.push({count,p50Ms:values[500],p95Ms:values[950],p99Ms:values[990]});
}
const result=spawnSync(process.env.PYTHON||'python3',['-c',`
import json,platform,time
from singularity.kernel import match
data=json.loads(input()); snapshot=data['snapshot']; rows=[]
for count in [1,16,64,256]:
 candidates=[dict(id='candidate-'+str(i),snapshot=snapshot) for i in range(count)]
 for _ in range(100): match(snapshot,candidates)
 values=[]
 for _ in range(1000):
  start=time.perf_counter_ns();match(snapshot,candidates);values.append((time.perf_counter_ns()-start)/1000000)
 values.sort();rows.append(dict(count=count,p50Ms=values[500],p95Ms=values[950],p99Ms=values[990]))
print(json.dumps(dict(runtime=platform.python_version(),rows=rows)))
`],{input:JSON.stringify({snapshot})+'\n',encoding:'utf8',env:{...process.env,PYTHONPATH:'server'}});
if(result.status!==0)throw Error(result.stderr);
const report={source:'cpu-only-matching',warmups:100,samples:1000,node:{runtime:process.version,rows:node},
  python:JSON.parse(result.stdout),rust:null,
  note:'Validation and matching on valid identical contenders. No HTTP, MongoDB, lock contention or Rust comparator; cannot infer full-application throughput or Rust acceleration.'};
await mkdir('artifacts/intensive-v04',{recursive:true});
await writeFile('artifacts/intensive-v04/matching-performance.json',JSON.stringify(report,null,2));
console.log(JSON.stringify(report));
