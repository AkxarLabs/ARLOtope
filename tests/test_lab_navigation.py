"""Exercise the map's real input handlers and travel controls without a GPU."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which('node')
ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / 'dashboard/static/world3d/world.js'
pytestmark = pytest.mark.skipif(not NODE, reason='node is needed')


def run_js(script):
    result = subprocess.run([NODE, '-e', script], text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def input_js(actions):
    source = WORLD.read_text()
    handlers = source[source.index('  const blocked ='):source.index('  const observer =')]
    return run_js('(async()=>{const THREE=await import(' + json.dumps((ROOT / 'dashboard/static/vendor/three/three.module.min.js').as_uri()) + ');' + '''
      const window={},events=new Map(),followEvents=[],clicks=[];
      const canvas={style:{},setAttribute(){},focus(){},setPointerCapture(){},hasPointerCapture(){return false},
        getBoundingClientRect(){return {height:800,width:1200,left:0,top:0}}};
      function listen(target,name,fn){events.set((target===canvas?'canvas:':'window:')+name,fn)}
      const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
      let followKey='worker',cameraManual=false,dragMode='pan',drag=null,hovered=null;
      const cam={az:0,el:1,r:80,tx:0,tz:0},camT={...cam},camera=new THREE.PerspectiveCamera(30,1.5,.5,900),W={SPAN:100},tip={style:{}},pickables=[];
      const onFollow=id=>followEvents.push(id),kick=()=>{},click=p=>clicks.push(p),pickAt=()=>({kind:'actor',key:'worker'});
      const poke=()=>{},describe=()=>'',setViewState=()=>{},performance={now:()=>0};let innerWidth=1200;
      const fire=(name,values={})=>events.get(name)({target:canvas,button:0,pointerId:7,clientX:100,clientY:100,preventDefault(){},...values});
    '''+handlers+'\n'+actions+'})().catch(error=>{console.error(error);process.exitCode=1});')


def test_pan_detaches_tracking_and_moves_the_camera_target():
    got = input_js('''
      fire('window:pointerdown');fire('window:pointermove',{clientX:200});
      const first={...camT};fire('window:pointerup',{clientX:200});
      console.log(JSON.stringify({followKey,cameraManual,followEvents,first,clicks}));
    ''')
    assert got['followKey'] is None and got['cameraManual']
    assert got['followEvents'] == [None]
    assert got['first']['tx'] < -1 and got['first']['tz'] == 0
    assert got['first']['az'] == 0 and got['clicks'] == []


@pytest.mark.parametrize('modifier', [{'button': 2}, {'shiftKey': True}])
def test_rotation_and_pan_are_separate_actions(modifier):
    got = input_js(f'''
      fire('window:pointerdown',{json.dumps(modifier)});
      fire('window:pointermove',{{clientX:200,clientY:150}});fire('window:pointerup');
      console.log(JSON.stringify({{camT,followKey,clicks}}));
    ''')
    assert got['camT']['az'] != 0 and got['camT']['el'] != 1
    assert got['camT']['tx'] == got['camT']['tz'] == 0
    assert got['followKey'] is None and got['clicks'] == []


def test_simple_click_still_opens_an_agent_and_keeps_follow_mode():
    got = input_js('''fire('window:pointerdown');fire('window:pointerup');
      console.log(JSON.stringify({followKey,cameraManual,clicks}));''')
    assert got == {'followKey': 'worker', 'cameraManual': False,
                   'clicks': [{'kind': 'actor', 'key': 'worker'}]}


def test_pointer_cancel_does_not_click_or_continue_a_drag():
    got = input_js('''fire('window:pointerdown');fire('window:pointercancel');
      fire('window:pointermove',{clientX:200});fire('window:pointerup');
      console.log(JSON.stringify({camT,clicks,followKey}));''')
    assert got['camT']['tx'] == 0 and got['clicks'] == [] and got['followKey'] == 'worker'


def test_zoom_leaves_follow_and_remains_inside_distance_bounds():
    got = input_js('''fire('canvas:wheel',{deltaY:-100});
      for(let i=0;i<200;i++)fire('canvas:wheel',{deltaY:-100});
      console.log(JSON.stringify({r:camT.r,followKey,cameraManual,followEvents}));''')
    assert got == {'r': 9, 'followKey': None, 'cameraManual': True, 'followEvents': [None]}


def test_pan_tracks_world_orientation_and_keyboard_is_available():
    got = input_js('''camT.az=Math.PI/2;fire('canvas:keydown',{key:'d'});
      console.log(JSON.stringify({camT,cameraManual,followKey}));''')
    assert abs(got['camT']['tx']) < 1e-10 and got['camT']['tz'] < 0
    assert got['cameraManual'] and got['followKey'] is None


def test_instant_travel_snaps_existing_and_new_display_paths_only():
    source = WORLD.read_text()
    sender = source[source.index('  function sendTo('):source.index('  function reconcile(')]
    controls = source[source.index('    setTravelSpeed(value)'):source.index('    layout()')]
    got = run_js('''
      let travelSpeed=1,currentMotion='full',kicks=0;
      const motion=()=>currentMotion,route=()=>[[1,1],[5,5]],kick=()=>kicks++;
      const execution={status:'running',elapsed:12};
      const actor={pos:[0,0],room:'hub',path:[[1,1]],speed:3,dest:{at:[5,5],room:'lab',ry:2},
        n:{group:{position:{set(x,y,z){this.at=[x,y,z]}},rotation:{y:0}}}};
      const actors=new Map([['a',actor]]);
    '''+sender+'\nconst controls={'+controls+'''};
      controls.setTravelSpeed(4);const fast=travelSpeed;
      controls.setTravelSpeed(0);
      const existing={pos:actor.pos.slice(),room:actor.room,path:actor.path.slice(),speed:actor.speed};
      sendTo(actor,{at:[9,2],room:'writing',ry:1});
      const fresh={pos:actor.pos.slice(),room:actor.room,path:actor.path.slice()};
      controls.setTravelSpeed(1);currentMotion='reduced';sendTo(actor,{at:[3,7],room:'review'});
      console.log(JSON.stringify({fast,existing,fresh,reduced:actor.pos,execution}));
    ''')
    assert got == {'fast': 4, 'existing': {'pos': [5, 5], 'room': 'lab', 'path': [], 'speed': 0},
                   'fresh': {'pos': [9, 2], 'room': 'writing', 'path': []}, 'reduced': [3, 7],
                   'execution': {'status': 'running', 'elapsed': 12}}


@pytest.mark.parametrize('modifier', ['metaKey', 'ctrlKey', 'altKey'])
@pytest.mark.parametrize('key', ['w', 'a', 's', 'd', '+', '-', 'Home', '0'])
def test_modified_keys_keep_browser_shortcuts_and_leave_navigation_unchanged(modifier, key):
    event = {modifier: True, 'key': key}
    got = input_js(f'''let prevented=false;const before={{...camT}};
      fire('canvas:keydown',{{...{json.dumps(event)},preventDefault(){{prevented=true}}}});
      console.log(JSON.stringify({{before,after:camT,prevented,followKey,cameraManual,followEvents,clicks}}));''')
    assert got['after'] == got['before'] and not got['prevented']
    assert got['followKey'] == 'worker' and not got['cameraManual']
    assert got['followEvents'] == [] and got['clicks'] == []
