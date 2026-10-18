"""Execute a graph task's report, then speak the existing fake harness protocol."""
import os
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))

if os.environ.get('NEWTS_GATE_JUDGE') and '--version' not in sys.argv and sys.argv[1:3] != ['auth', 'status']:
    manifest = json.loads(Path(os.environ['NEWTS_RUN_DIR']).with_suffix('.json').read_text(encoding='utf-8'))
    cfg = manifest['judge']
    path = Path.cwd() / cfg['output']
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'decision':'proceed','reason':'Fixture evidence meets the rubric.',
                               'evidence':cfg['evidence']}), encoding='utf-8')

if '--version' not in sys.argv and sys.argv[1:3] != ['auth', 'status'] and os.environ.get('NEWTS_RUN_NODE'):
    from kernel import branches, model, studies
    hub = Path(os.environ['NEWTS_HUB'])
    slug, sid = os.environ['NEWTS_RUN_SUBJECT'], os.environ['NEWTS_RUN_NODE']
    s = studies.study(hub, slug)
    node = next(n for n in branches.nodes(model.workflow(s['workflow'], hub), model.steps(hub)) if n['id'] == sid)
    root = Path(s['project']) if s.get('project') else hub / 'studies' / slug
    for rel in node.get('outputs', []):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"Evidence for {sid} from {os.environ['NEWTS_RUN_ID']}\n", encoding='utf-8')
    studies.move(hub, slug, 'done', note='Fixture task finished.')

from fake_claude import main

raise SystemExit(main())
