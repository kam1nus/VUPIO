"""Exercise the actual Radar client with a failed network, without browser/audio IO."""
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'),'Node.js unavailable')
class RadarClientTests(unittest.TestCase):
    def test_network_stops_but_dead_sounds_are_replaced_and_errors_are_visible(self):
        script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync('web/radar.js','utf8');
async function scenario(code,expectedCalls){
 const elements=new Map(),events={},states=[];let clipCalls=0;
 const element=id=>{if(!elements.has(id))elements.set(id,{
  value:id==='radarRegion'?'us':'chart',dataset:{kind:'memes'},hidden:false,
  querySelectorAll:()=>[],replaceChildren(){},append(){},setAttribute(){},removeAttribute(){},
  addEventListener(name,fn){this[name]=fn;}
 });return elements.get(id);};
 const context={by:element,view:'radar',document:{addEventListener(name,fn){events[name]=fn;}},
  status:(id,text,error)=>states.push({text,error}),link:()=>({}),
  runJob:async(kind)=>{
   if(kind==='radar')return {title:'Myinstants',chart:true,playable_chart:true,limit:10,days:1,day:'2026-11-07',source_url:'https://www.myinstants.com/',rows:Array.from({length:5},(_,i)=>({source_id:String(i)}))};
   clipCalls++;const error=Error(code==='source_missing'?'Sound unavailable (HTTP 404)':code==='source_forbidden'?'Source denied download (HTTP 403)':'VPN DNS unavailable');error.code=code;throw error;
  },console,URL,AbortController,Date,Symbol};
 vm.runInNewContext(source,context);
 events['mimic:view']({detail:'radar'});
 for(let i=0;i<20;i++)await new Promise(resolve=>setImmediate(resolve));
 assert.equal(clipCalls,expectedCalls);
 assert.equal(states.at(-1).error,true);
 assert.match(states.at(-1).text,code==='source_missing'?/Unavailable sounds skipped: 5/:code==='source_forbidden'?/Source denied download/:/VPN DNS unavailable/);
}
(async()=>{await scenario('network_dns',1);await scenario('source_forbidden',3);await scenario('source_missing',5);console.log('Radar error-state checks passed');})().catch(error=>{console.error(error);process.exitCode=1;});
'''
        subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[1],check=True,capture_output=True,text=True,timeout=10)
