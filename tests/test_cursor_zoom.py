"""Project real Three ground points to verify cursor anchoring throughout camera easing."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / 'dashboard/static/world3d/world.js'
NODE = shutil.which('node')
pytestmark = pytest.mark.skipif(not NODE, reason='node is needed')


def zoom_js(actions, setup=''):
    source = WORLD.read_text()
    handlers = source[source.index('  const blocked ='):source.index('  const observer =')]
    script = '(async()=>{const THREE=await import(' + json.dumps((ROOT / 'dashboard/static/vendor/three/three.module.min.js').as_uri()) + ');' + '''
      const window={},events=new Map(),followEvents=[];
      const rect={left:37,top:29,width:1200,height:800};
      const canvas={style:{},setAttribute(){},focus(){},setPointerCapture(){},hasPointerCapture(){return false},getBoundingClientRect(){return rect}};
      function listen(target,name,fn){events.set((target===canvas?'canvas:':'window:')+name,fn)}
      const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
      let followKey='worker',cameraManual=false,dragMode='pan',drag=null,hovered=null;
      const cam={az:.8,el:.4,r:80,tx:10,tz:-5},camT={...cam};
      const camera=new THREE.PerspectiveCamera(30,1.5,.5,900);
      camera.setViewOffset(1200,800,110,35,1200,800);camera.updateProjectionMatrix();
      const W={SPAN:100},tip={style:{}},pickables=[],onFollow=id=>followEvents.push(id),kick=()=>{},click=()=>{},pickAt=()=>null;
      const poke=()=>{},describe=()=>'',setViewState=()=>{},performance={now:()=>0};let innerWidth=1200;
      const fire=(name,values={})=>events.get(name)({target:canvas,button:0,pointerId:7,clientX:600,clientY:400,preventDefault(){},...values});
      const paint=()=>{camera.position.set(cam.tx+cam.r*Math.cos(cam.el)*Math.sin(cam.az),cam.r*Math.sin(cam.el),cam.tz+cam.r*Math.cos(cam.el)*Math.cos(cam.az));camera.lookAt(cam.tx,.6,cam.tz);camera.updateMatrixWorld()};
      const pointer=(x=.62,y=-.31)=>({clientX:rect.left+(x+1)*rect.width/2,clientY:rect.top+(1-y)*rect.height/2});
      const pointAt=p=>{const ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2((p.clientX-rect.left)/rect.width*2-1,1-(p.clientY-rect.top)/rect.height*2),camera);return ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0,1,0),0),new THREE.Vector3())};
      const errorAt=(point,p)=>{const got=point.clone().project(camera);return Math.hypot((got.x+1)*rect.width/2+rect.left-p.clientX,(1-got.y)*rect.height/2+rect.top-p.clientY)};
    ''' + handlers + '\n' + '''
      const step=(k=.13)=>{easeCamera(k);paint()};
      const wheel=(p,deltaY=-80,deltaMode=0)=>fire('canvas:wheel',{...p,deltaY,deltaMode});
    ''' + setup + '\npaint();\n' + actions + '})().catch(error=>{console.error(error);process.exitCode=1});'
    result = subprocess.run([NODE, '-e', script], text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize('setup', ['', 'cam.el=camT.el=1.45;', 'camT.az=1.2;camT.el=.7;camT.tx=40;camT.tz=12;'])
def test_ground_under_pointer_stays_fixed_every_eased_frame_with_offset_projection(setup):
    got = zoom_js('''
      const p=pointer(),point=pointAt(p);wheel(p);let maxError=0;
      for(let i=0;i<300;i++){step();maxError=Math.max(maxError,errorAt(point,p))}
      console.log(JSON.stringify({maxError,zooming,followKey,cameraManual,finite:Object.values(cam).every(Number.isFinite)}));
    ''', setup)
    assert got['maxError'] < 1e-6
    assert not got['zooming'] and got['followKey'] is None and got['cameraManual'] and got['finite']


def test_rapid_wheel_events_accumulate_radius_without_moving_anchor():
    got = zoom_js('''
      const p=pointer(),point=pointAt(p);
      for(let i=0;i<12;i++)wheel(p,-10);
      const pending=camT.r;let maxError=0;
      for(let i=0;i<200;i++){step();maxError=Math.max(maxError,errorAt(point,p))}
      console.log(JSON.stringify({pending,expected:80*Math.exp(-120*.0015),maxError}));
    ''')
    assert got['pending'] == pytest.approx(got['expected'])
    assert got['maxError'] < 1e-6


def test_moving_pointer_during_ongoing_zoom_anchors_the_new_visible_position():
    got = zoom_js('''
      let maxError=0;
      for(let i=0;i<12;i++){
        const p=pointer(.62-i*.08,-.31+i*.04),point=pointAt(p);
        wheel(p,i%3===0?30:-40);
        for(let j=0;j<4;j++){step();maxError=Math.max(maxError,errorAt(point,p))}
      }
      const p=pointer(-.26,.13),point=pointAt(p);wheel(p,-20);
      for(let i=0;i<200;i++){step();maxError=Math.max(maxError,errorAt(point,p))}
      console.log(JSON.stringify({maxError,finite:Object.values(cam).every(Number.isFinite)}));
    ''')
    assert got['maxError'] < 1e-6 and got['finite']


@pytest.mark.parametrize('delta,expected', [(-240, 9), (240, 400)])
def test_input_at_radius_limit_does_not_cancel_an_unfinished_anchored_zoom(delta, expected):
    got = zoom_js(f'''
      const p=pointer(),point=pointAt(p);
      for(let i=0;i<30;i++)wheel(p,{delta});
      const activeAtLimit=zooming,pending=camT.r;wheel(p,{delta});const stillActive=zooming;
      let maxError=0;for(let i=0;i<200;i++){{step();maxError=Math.max(maxError,errorAt(point,p))}}
      console.log(JSON.stringify({{pending,activeAtLimit,stillActive,maxError}}));
    ''')
    assert got['pending'] == expected and got['activeAtLimit'] and got['stillActive']
    assert got['maxError'] < 1e-6


@pytest.mark.parametrize('delta,mode', [(-48, 0), (-3, 1), (-.06, 2)])
def test_pixel_line_and_page_wheel_deltas_use_the_same_scale(delta, mode):
    got = zoom_js(f'''wheel(pointer(),{delta},{mode});console.log(JSON.stringify({{r:camT.r}}));''')
    assert got['r'] == pytest.approx(80 * __import__('math').exp(-48 * .0015))


def test_trackpad_delta_is_proportional_and_invalid_events_leave_camera_unchanged():
    got = zoom_js('''
      wheel(pointer(),0);wheel(pointer(),NaN);wheel(pointer(),Infinity);
      const unchanged={...camT};wheel(pointer(),-1);
      console.log(JSON.stringify({unchanged,r:camT.r}));
    ''')
    assert got['unchanged'] == {'az': .8, 'el': .4, 'r': 80, 'tx': 10, 'tz': -5}
    assert got['r'] == pytest.approx(80 * __import__('math').exp(-.0015))


def test_above_horizon_falls_back_to_bounded_finite_zoom_without_a_large_pan():
    got = zoom_js('''
      const p=pointer(.2,.99);wheel(p,-80);for(let i=0;i<120;i++)step();
      console.log(JSON.stringify({zooming,tx:cam.tx,tz:cam.tz,r:cam.r,finite:Object.values(cam).every(Number.isFinite)}));
    ''', 'cam.el=camT.el=.25;')
    assert not got['zooming'] and got['finite']
    assert got['tx'] == 10 and got['tz'] == -5 and 9 <= got['r'] < 80


def test_pan_releases_zoom_anchor_and_reduced_motion_can_finish_in_one_frame():
    got = zoom_js('''
      const p=pointer(),point=pointAt(p);wheel(p);step(1);
      const directError=errorAt(point,p);wheel(p,-30);
      fire('window:pointerdown');fire('window:pointermove',{clientX:700});
      console.log(JSON.stringify({directError,zooming,cameraManual}));
    ''')
    assert got['directError'] < 1e-6 and not got['zooming'] and got['cameraManual']


def test_idle_turntable_stops_when_cursor_zoom_takes_manual_control():
    spin_line = next(line for line in WORLD.read_text().splitlines() if 'camT.az += spin * dt' in line)
    got = zoom_js('''
      let spin=.1;const dt=.1,view={level:'WORLD'},motion=()=> 'full';followKey=null;
      const tick=()=>{''' + spin_line + '''\nstep()};
      const startAz=camT.az;tick();const idleTurned=camT.az>startAz;
      const p=pointer(),point=pointAt(p);wheel(p);
      const manualAz=camT.az;let maxError=0;
      for(let i=0;i<200;i++){tick();maxError=Math.max(maxError,errorAt(point,p))}
      console.log(JSON.stringify({idleTurned,stopped:camT.az===manualAz,cameraManual,zooming,maxError}));
    ''')
    assert got['idleTurned'] and got['stopped'] and got['cameraManual']
    assert not got['zooming'] and got['maxError'] < 1e-6
