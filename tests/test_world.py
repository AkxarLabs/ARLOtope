"""The world (dashboard/static/world3d/): the room contract, and what the world decides from a snapshot.

Loads the real world scripts under node with a bare `window` (no DOM, no WebGL — registering furniture and
room looks, and the model that decides which rooms stand where and who goes in which, need neither) and checks
what the dashboard relies on: every lifecycle state lands in exactly one room, every built-in look keeps the
station contract, studies share the defined rooms, machine spaces do not overlap, and each agent follows
its task's room assignment.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest
import yaml

from conftest import REPO, kernel, load

NODE = shutil.which("node")
STATIC = REPO / "dashboard" / "static"
W3 = STATIC / "world3d"
CORE = ["kit.js", "components.js", "layout.js", "model.js"]
ROOM_FILES = sorted(p.name for p in (W3 / "rooms").glob("*.js"))
_FULL = kernel().model.view(REPO)      # the lab's definition as the dashboard has it: steps, workflows, rooms, procedures
_WF = _FULL
LIFECYCLE = [s["id"] for s in _FULL["steps"]]
WF_ROOM = {s["id"]: s["room"] for s in _FULL["steps"]}

pytestmark = pytest.mark.skipif(not NODE, reason="node is needed to load the world scripts")


def _node(body: str) -> dict:
    """Run `body` under node with the world scripts loaded (window.Lab3D as L, the manifest as WF)."""
    files = [str(W3 / f) for f in CORE] + [str(W3 / "rooms" / f) for f in ROOM_FILES]
    js = f"""
      global.window = global; const fs = require('fs');
      for (const f of {json.dumps(files)}) eval(fs.readFileSync(f, 'utf8'));
      const L = window.Lab3D, M = L.model, WF = {json.dumps(_FULL)};
      const out = (() => {{ {body} }})();
      console.log(JSON.stringify(out));
    """
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_floor_sources_stay_independent_through_theme_round_trips():
    """Real Three Sources must not mutate cached pixels when an existing scene changes theme."""
    js = f"""
      const fs = require('fs'); global.window = global;
      global.document = {{createElement: () => ({{getContext: () => ({{fillRect() {{}}}})}})}};
      eval(fs.readFileSync({json.dumps(str(W3 / 'kit.js'))}, 'utf8'));
      (async () => {{
        const THREE = await import('data:text/javascript;base64,' + fs.readFileSync(
          {json.dumps(str(STATIC / 'vendor/three/three.module.min.js'))}).toString('base64'));
        const L = Lab3D, day = L.kit(THREE, 'day'), night = L.kit(THREE, 'night');
        const a = day.floorMap('boards', 8, 6), b = day.floorMap('boards', 3, 2);
        const dayPixels = a.image, nightPixels = night.floorMap('boards', 8, 6).image;
        const root = new THREE.Group();
        root.add(day.box(8, .1, 6, 'white', 0, 0, 0, {{map: a}}));
        root.add(day.box(3, .1, 2, 'white', 0, 0, 0, {{map: b}}));
        const independent = a.source !== b.source, sharedPixels = a.image === b.image;
        let correct = true;
        for (let i = 0; i < 5; i++) {{
          night.setLook(null, root);
          correct &&= a.image === nightPixels && b.image === nightPixels;
          correct &&= day.floorMap('boards', 1, 1).image === dayPixels;
          day.setLook(null, root);
          correct &&= a.image === dayPixels && b.image === dayPixels;
          correct &&= night.floorMap('boards', 1, 1).image === nightPixels;
        }}
        console.log(JSON.stringify({{independent, sharedPixels, correct,
          stable: root.children[0].material.map === a && root.children[1].material.map === b,
          repeat: [a.repeat.x, a.repeat.y, b.repeat.x, b.repeat.y]}}));
      }})().catch(e => {{console.error(e); process.exitCode = 1}});
    """
    r = subprocess.run([NODE, '-e', js], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert got['independent'] and got['sharedPixels'] and got['correct'] and got['stable']
    assert got['repeat'] == pytest.approx([8 / 2.4, 6 / 2.4, 3 / 2.4, 1])


def test_full_and_unified_keep_all_agents_and_resolve_execution_machine():
    result=_node("""
      const items=[{id:'remote-study',machine:'gpu',has_project:true,state:'active'}];
      const runs=[{run_id:'remote',subject:'remote-study',skill:'experiment',level:'project',remote:{machine:'gpu'}},
        {run_id:'local',subject:'remote-study',skill:'analyze',level:'hub'}];
      const agents=[{id:'r',run_id:'remote',status:'working'}, {id:'l',run_id:'local',status:'working'},
        {id:'q',machine:'gpu',status:'asking'}];
      const s={workflow:WF,world_view:'full',items,runs,agents,machines:[{id:'gpu',name:'Compute',state:'connected'},{id:'empty',state:'connected'},{id:'unused',state:'idle'}]};
      const list=M.roomList(s),rooms=Object.fromEntries(list.map(r=>[r.id,r])),plan=M.placeRooms(list,WF);
      const places=agents.map(a=>M.placeAgent(s,a,rooms));
      const unified={...s,world_view:'unified'},ulist=M.roomList(unified),urooms=Object.fromEntries(ulist.map(r=>[r.id,r]));
      return {groups:M.machineGroups(s).map(m=>m.id),places,ids:list.map(r=>r.id),
        overlap:new Set(Object.values(plan).map(p=>p.cell.join(','))).size!==list.length,
        card:M.roomOfItem(s,items[0],rooms),unified:agents.map(a=>M.placeAgent(unified,a,urooms)),
        unifiedRooms:ulist.map(r=>r.id),unchanged:s.agents.length===3&&s.runs.length===2&&items[0].id==='remote-study'};
    """)
    assert result['groups']==['local','empty','gpu']
    assert result['places'][0]['room'].startswith('machine/gpu/')
    assert not result['places'][1]['room'].startswith('machine/')
    assert result['places'][2]['room']=='machine/gpu/hub' and not result['places'][2]['desk']
    assert result['card'].startswith('machine/gpu/')
    assert not result['overlap'] and result['unchanged']
    assert len(result['unified'])==3 and not any(r.startswith('machine/') for r in result['unifiedRooms'])


def test_terminal_agents_and_nested_children_use_their_execution_machine():
    result=_node("""
      const s={workflow:WF,world_view:'full',items:[{id:'local-study',machine:'local',state:'active',has_project:true}],
        agents:[{id:'a',machine:'gpu',subject:'local-study',status:'working'},{id:'b',parent:'a'},
          {id:'c',parent:'b',subject:'local-study',status:'asking'}],machines:[{id:'gpu',state:'connected'}]};
      const rooms=Object.fromEntries(M.roomList(s).map(r=>[r.id,r]));
      const placed=s.agents.map(a=>({machine:M.machineOf(s,a),room:M.placeAgent(s,a,rooms).room}));
      const cycle={agents:[{id:'x',parent:'y'},{id:'y',parent:'x'}]};
      return {placed,cycle:M.machineOf(cycle,cycle.agents[0])};
    """)
    assert all(p['machine']=='gpu' and p['room'].startswith('machine/gpu/') for p in result['placed'])
    assert result['cycle']=='local'


def test_every_lifecycle_state_lives_in_exactly_one_room():
    owners = {}
    for r in _WF["rooms"]:
        for st in r["steps"]:
            assert st not in owners, f"{st} claimed by {owners[st]} and {r['id']}"
            owners[st] = r["id"]
    assert set(LIFECYCLE) <= set(owners), set(LIFECYCLE) - set(owners)
    assert {st: owners[st] for st in LIFECYCLE} == WF_ROOM
    assert not any(r.get('per_project') for r in _WF['rooms'])


def test_theme_changes_reuse_geometry_and_update_materials():
    """Use real Three materials without a GPU; mode changes must keep object identity."""
    js = f"""
      const fs=require('fs'),{{pathToFileURL}}=require('url');global.window=global;
      eval(fs.readFileSync({json.dumps(str(W3 / 'kit.js'))},'utf8'));
      (async()=>{{
        const T=await import(pathToFileURL({json.dumps(str(STATIC / 'vendor/three/three.module.min.js'))}));
        const L=Lab3D,day=L.kit(T,'day'),night=L.kit(T,'night'),root=new T.Group();
        eval(fs.readFileSync({json.dumps(str(W3 / 'newt.js'))},'utf8'));
        const newt=L.makeNewt(day),skin=[];root.add(newt.group);
        newt.group.traverse(o=>{{if(o.isMesh&&o.material.userData.labColor==='#fbeee0')skin.push(o.material)}});
        if(!skin.length)throw Error('Missing newt skin');
        const box=day.box(1,1,1,'wood',0,0,0,{{glow:'lamp',gi:{{day:.2,night:1.8}},rough:.4}});
        const geometry=box.geometry,material=box.material,decor=new T.Group(),light=new T.PointLight();
        decor.userData.labNightOnly=true;light.userData.labNightIntensity=18;
        root.add(box,decor,light);night.setLook(null,root);
        if(box.geometry!==geometry||box.material!==material)throw Error('Replaced geometry or material');
        if(material.color.getHexString()!==new T.Color(night.col('wood')).getHexString())throw Error('Stale palette');
        if(material.emissiveIntensity!==1.8||material.roughness!==.4||!decor.visible||!light.visible)throw Error('Night values');
        day.setLook(null,root);
        if(material.emissiveIntensity!==.2||decor.visible||light.visible)throw Error('Day values');
        const before=skin.map(m=>m.color.getHexString());
        night.setLook(null,root);
        if(skin.some((m,i)=>m.color.getHexString()!==before[i]||m.emissiveIntensity!==.45))throw Error('Newt changed skin identity at night');
      }})().catch(e=>{{console.error(e);process.exit(1)}});
    """
    result=subprocess.run([NODE,'-e',js],capture_output=True,text=True,timeout=30)
    assert result.returncode == 0, result.stderr


def test_rooms_combine_task_layers_from_multiple_workflows():
    out = _node("""
      WF.rooms.push({id:'combined',label:'Replication',steps:[]});
      WF.workflows[0].nodes={seed:{room:'combined',instructions:'Plan.'}};
      WF.workflows.push({id:'another',path:['analysis'],nodes:{analysis:{room:'combined',procedure:'analyze'}}});
      const s={workflow:WF,items:[{id:'study',state:'seed',workflow:WF.workflows[0].id,has_project:true}]};
      const list=M.roomList(s),rooms=Object.fromEntries(list.map(r=>[r.id,r]));
      return {groups:list.filter(r=>r.base.id==='combined'),
        at:M.placeOfRun(s,{subject:'study',workflow_node:'seed',skill:'workflow-task'},rooms),
        procedures:M.procsOf(WF,[],'combined')};
    """)
    assert len(out['groups']) == 1 and set(out['groups'][0]['states']) == {'seed', 'analysis'}
    assert out['at'] == 'combined'
    assert set(out['procedures']) == {'task:seed', 'analyze'}


def test_parallel_agents_use_their_own_task_rooms_and_share_explicit_custom_rooms():
    got = _node("""
      WF.rooms.push({id:'replication',title:'Replication',steps:[]});
      WF.workflows.push({id:'custom',path:['analysis','writing','replicate'],nodes:{
        writing:{room:'replication',instructions:'Independent review.'},
        replicate:{room:'replication',instructions:'Replicate.'}}});
      const items=[{id:'a',state:'analysis',workflow:'custom',has_project:true},
        {id:'b',state:'writing',workflow:'custom',has_project:true}];
      const runs=[{run_id:'analysis',subject:'a',workflow_node:'analysis',skill:'workflow-task'},
        {run_id:'review',subject:'a',workflow_node:'writing',skill:'workflow-task'},
        {run_id:'replicate',subject:'b',workflow_node:'replicate',skill:'workflow-task'},
        {run_id:'older',subject:'a',assigned_step:'writing',skill:'workflow-task'}];
      const s={workflow:WF,items,runs},list=M.roomList(s),rooms=Object.fromEntries(list.map(r=>[r.id,r]));
      return {at:runs.map(r=>M.placeOfRun(s,r,rooms)),custom:list.filter(r=>r.id==='replication').length};
    """)
    assert got == {'at': [WF_ROOM['analysis'], 'replication', 'replication', 'replication'], 'custom': 1}


def test_every_room_has_a_look_that_keeps_the_station_contract():
    """Stations and props stand inside the room, props name known furniture, stations are [x, z, facing]."""
    got = _node("return { rooms: L.rooms, comps: Object.keys(L.components) };")
    assert {r["id"] for r in _WF["rooms"]} == set(got["rooms"]), "every shipped room has its look"
    for f in ROOM_FILES:
        assert f[:-3] in got["rooms"], f"{f} defines a room keyed by its file name"
    for key, r in got["rooms"].items():
        hw, hd = r["size"][0] / 2, r["size"][1] / 2
        for kind in ("stations", "roleStation"):
            for name, p in r[kind].items():
                assert len(p) == 3 and abs(p[0]) < hw and abs(p[1]) < hd, (key, kind, name, p)
        for pr in r["props"]:
            assert pr["c"] in got["comps"], f"{key}: unknown furniture {pr['c']}"
            assert abs(pr["at"][0]) <= hw and abs(pr["at"][1]) <= hd, (key, pr)
    lab = got["rooms"]["lab"]
    assert lab["size"][0] >= 13, "the shared experiment room has space for several agents"
    assert {"experiment", "improve", "analyze"} <= set(lab["stations"]) and "experiment-runner" in lab["roleStation"]


SNAP = {
    "items": [
        {"id": "moe", "title": "Sparse MoE", "state": "active", "has_project": True, "project_type": "ml"},
        {"id": "rl", "title": "RL", "state": "active", "has_project": True},
        {"id": "ana", "title": "Probes", "state": "analysis", "has_project": True},
        {"id": "old", "title": "Done", "state": "final", "has_project": True},
        {"id": "new", "title": "New", "state": "proposal", "gate_signed": True},
        {"id": "lit", "title": "Lit", "state": "lit-review"},
    ],
    "runs": [
        {"run_id": "r1", "skill": "spawn-project", "subject": "new", "status": "running"},
        {"run_id": "r2", "skill": "experiment", "subject": "moe", "status": "running"},
        {"run_id": "r3", "skill": "lit-review", "subject": "lit", "status": "running"},
        {"run_id": "r4", "skill": "ask", "status": "running"},
        {"run_id": "r5", "skill": "write-paper", "subject": "paper", "status": "running"},
        {"run_id": "r6", "skill": "analyze", "subject": "ana", "status": "running"},
    ],
}


def test_studies_and_project_creation_never_create_rooms():
    got = _node(f"""
      const s = Object.assign({json.dumps(SNAP)}, {{ workflow: WF }});
      const list = M.roomList(s), none = M.roomList({{ workflow: WF, items: [], runs: [] }});
      WF.rooms.forEach(r=>r.per_project=true); // Old saved definitions must not restore duplication.
      return {{ ids:list.map(r=>r.id),none:none.map(r=>r.id),legacy:M.roomList(s).map(r=>r.id),
                titles:list.map(r=>r.title),generated:list.some(r=>r.building||r.empty||r.study) }};""")
    assert got['ids'] == got['none'] == got['legacy'] == [r['id'] for r in _WF['rooms']]
    assert not got['generated'] and 'Sparse MoE' not in got['titles']


def test_studies_do_not_change_the_defined_room_layout():
    got = _node("""
      const items = Array.from({ length: 9 }, (_, i) => ({ id: 'p' + i, title: 'P' + i, state: 'active', has_project: true }));
      const s = { workflow: WF, items, runs: [] };
      const a = M.placeRooms(M.roomList(s), WF), b = M.placeRooms(M.roomList(s), WF);
      return { a, same: JSON.stringify(a) === JSON.stringify(b),
        empty:JSON.stringify(a)===JSON.stringify(M.placeRooms(M.roomList({workflow:WF,items:[],runs:[]}),WF)) };""")
    cells = [tuple(v["cell"]) for v in got["a"].values()]
    assert got["same"], "the same lab lays out the same way every time"
    assert len(cells) == len(set(cells)) and (0, 0) not in cells, "one room per plot, the plaza kept free"
    assert got['empty'] and len(cells) == len(_WF['rooms'])
    assert all(v["facing"] in "nesw" for v in got["a"].values())


def test_every_run_stands_where_its_work_is():
    got = _node(f"""
      const s = Object.assign({json.dumps(SNAP)}, {{ workflow: WF }});
      const rooms = Object.fromEntries(M.roomList(s).map(r => [r.id, r]));
      return Object.fromEntries(s.runs.map(r => [r.run_id, M.placeOfRun(s, r, rooms)]));""")
    assert got == {"r1": WF_ROOM['setup'], "r2": WF_ROOM['active'], "r3": WF_ROOM["lit-review"], "r4": "hub", "r5": "writing", "r6": WF_ROOM["analysis"]}


def test_world_scripts_load_only_in_the_isolated_view():
    html = (STATIC / 'index.html').read_text(encoding='utf-8')
    assert 'world3d/' not in html and 'vendor/three/' not in html
    view = (STATIC / 'lab-view.html').read_text(encoding='utf-8')
    order = ['vendor/three/three.module.min.js', 'world3d/kit.js', 'world3d/newt.js',
             'world3d/characters.js', 'world3d/components.js', 'world3d/layout.js', 'world3d/model.js',
             'arlotope:rooms3d', 'world3d/world.js', 'ui/lab-view.js']
    positions = [view.index(item) for item in order]
    assert positions == sorted(positions)
    assert 'rapier' not in view and 'design.js' not in view


def test_the_server_puts_every_built_in_room_on_the_page():
    serve = load("dashboard/serve")
    page = serve._with_rooms3d((STATIC / "lab-view.html").read_text(encoding="utf-8"), "world3d/rooms/")
    for f in ROOM_FILES:
        assert f'<script src="world3d/rooms/{f}"></script>' in page, f
    assert "arlotope:rooms3d" not in page
    assert page.index("world3d/model.js") < page.index("rooms/" + ROOM_FILES[0]) < page.index("world3d/world.js")




def test_the_cast_offers_characters_and_falls_back_to_the_newt():
    files = [str(W3 / f) for f in ["kit.js", "newt.js", "characters.js"]]
    js = f"""global.window = global; const fs = require('fs');
      for (const f of {json.dumps(files)}) eval(fs.readFileSync(f, 'utf8'));
      console.log(JSON.stringify({{ cast: window.Lab3D.CHARACTERS, make: typeof window.Lab3D.makeCharacter }}));"""
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    ids = [c["id"] for c in got["cast"]]
    assert ids[0] == "newt" and set(ids) == {"human", "robot", "newt"} and got["make"] == "function"
    assert all(c["label"] for c in got["cast"])




def test_the_world_names_no_procedure_stage_or_room():
    """The lifecycle is the lab's to change: the world's code reads rooms, steps and procedures (and how a
    procedure's run shows, its `world:` key) from the manifest, and never names one of the default ones."""
    names = set(_FULL["procedures"]) | {r["id"] for r in _FULL["rooms"]} | {s["id"] for s in _FULL["steps"]}
    names -= {"completed", "failed", "timeout", "killed", "queued", "running"}   # a run's status: the executor's, not the lifecycle's
    files = [W3 / f for f in ["world.js", "model.js", "layout.js", "characters.js", "newt.js", "kit.js", "components.js"]]
    files += [STATIC / "ui" / f for f in ["answers.js", "artifacts.js"]]
    for path in files:
        f = path.name
        src = re.sub(r"/\*.*?\*/|(?<![:'\"])//[^\n]*", "", path.read_text(encoding="utf-8"), flags=re.S)   # code, not comments
        named = sorted(n for n in names if f"'{n}'" in src or f'"{n}"' in src)
        assert not named, f"{f} names {named} — read it from the workflow instead"


def test_a_study_without_a_project_uses_the_same_task_room():
    got = _node(f"""
      const s = Object.assign({json.dumps(SNAP)}, {{ workflow: WF }});
      s.items = s.items.concat([{{ id: 'tgt', title: 'Target', state: 'active', has_project: false }}]);
      s.runs = s.runs.concat([{{ run_id: 'later', skill: 'spawn-project', subject: 'tgt', status: 'queued', not_before: '2999-01-01T00:00:00' }}]);
      const list = M.roomList(s), rooms = Object.fromEntries(list.map(r => [r.id, r]));
      return {{ room: M.roomOfItem(s, s.items.find(i => i.id === 'tgt'), rooms), count:list.length }};""")
    assert got == {'room': WF_ROOM['active'], 'count': len(_WF['rooms'])}


# ── where an agent works: the furniture for what it is doing ──

def test_furniture_offers_the_spots_its_hand_placed_stations_already_use():
    """A piece's `stands` reproduce where the built-in looks stand their procedures (so an agent at work on a call
    stands where the room's designer would have put it), turned with the piece, facing it."""
    out = _node("""
      const lab = L.rooms.lab, study = L.rooms.study;
      const near = (spots, at) => (spots || []).some(p => Math.hypot(p[0] - at[0], p[1] - at[1]) < 0.06 && Math.abs(Math.cos(p[2] - at[2]) - 1) < 1e-6);
      const ul = M.standsOf(lab.props), us = M.standsOf(study.props);
      return { improve: near(ul.edit, lab.stations.improve), analyze: near(ul.edit, lab.stations.analyze),
               experiment: near(ul.run, lab.stations.experiment), critic: near(ul.plan, lab.roleStation['ideation-critic']),
               shelves: (us.read || []).filter(p => Math.abs(p[1] - (-2.3)) < 0.06 && Math.abs(p[2] - Math.PI) < 1e-6).length,
               spawn: near(us.search, study.stations['spawn-project']),
               kinds: Object.keys(ul).sort() };
    """)
    assert all(out[k] for k in ("improve", "analyze", "experiment", "critic", "spawn")), out
    assert out["shelves"] == 4                   # the Study's two bookshelves: two readers at each, facing it
    assert {"read", "edit", "run", "bash", "spawn", "plan"} <= set(out["kinds"])


def test_an_agent_stands_in_its_runs_room_at_your_desk_when_it_asks():
    out = _node("""
      const proc = Object.keys(WF.procedures).find(p => WF.procedures[p].level === 'project');
      const step = WF.steps.find(s=>s.do===proc), rid=step.room;
      const s = { items: [{ id: 'moe', state: step.id, has_project: true }], runs: [
        { run_id: 'r1', skill: proc, subject: 'moe', status: 'running' }, { run_id: 'r2', skill: proc, subject: 'moe', status: 'waiting_input' }],
        workflow: WF };
      const rooms = Object.fromEntries(M.roomList(s).map(r => [r.id, r]));
      const at = a => { const p = M.placeAgent(s, a, rooms); return [p.room, p.desk, p.kind, p.pose]; };
      return { sub: at({ id: 'run:r1/t', run_id: 'r1', parent: 'run:r1', status: 'working', doing: { kind: 'read' } }),
               asks: at({ id: 'run:r2', run_id: 'r2', status: 'asking', doing: null }),
               quiet: at({ id: 'run:r1', run_id: 'r1', status: 'stalled', doing: null }),
               mine: at({ id: 'w:x', status: 'idle', subject: 'moe', target: 'moe', doing: null }),
               lab: rid };
    """)
    assert out["sub"] == [out["lab"], False, "read", "work"]           # a subagent works in its run's room, by its call
    assert out["asks"][1:] == [True, None, "wait"]                     # asking you: at your desk, hand up
    assert out["quiet"][3] == "sleep" and out["mine"] == [out["lab"], False, None, "idle"]
