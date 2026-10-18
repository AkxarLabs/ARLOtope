"""Lab-owned task completion projection, independent of process/turn success."""


def flag_runs(hub, runs):
    from kernel import studies, journal
    cache = {}
    for run in runs:
        run['needs_followup'] = False
        slug = run.get('subject')
        if run.get('status') != 'completed' or not slug or not (run.get('workflow_node') or run.get('assigned_step')):
            continue
        if slug not in cache:
            cache[slug] = studies.study(hub, slug)
        study = cache[slug]
        if not study or study['finished']:
            continue
        if run.get('workflow_node'):
            run['needs_followup'] = any(t['id'] == run['workflow_node'] and t['visit'] == run.get('workflow_visit')
                                       and t.get('run_id') == run['run_id'] for t in study.get('active_steps', []))
        elif study['step'] == run['assigned_step'] and not study.get('waiting'):
            since = str(run.get('started') or run.get('created') or '')[:19]
            events = journal.events(hub, slug)
            if isinstance(run.get('assigned_journal_index'), int):
                relevant = events[run['assigned_journal_index']:]
            else:
                relevant = [e for e in events if e['ts'] >= since]  # Older manifests have no cursor.
            run['needs_followup'] = not any(e['kind'] in ('move', 'wait', 'finish') for e in relevant)
    return runs
