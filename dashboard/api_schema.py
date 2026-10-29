"""Discoverable API operations generated from the actual route tables."""

FIELDS={
    '/api/starter': ('Create or attach a study; saving starts no agent.',
        {'confirm':{'type':'boolean'},'title':{'type':'string'},'question':{'type':'string'},
         'slug':{'type':'string'},'workflow':{'type':'string'},'local':{'type':'string'},
         'repo':{'type':'string'},'machine':{'type':'string'},'entry':{'type':'object'}}),
    '/api/workflow/run': ('Queue the ready tasks of a study.',{'study':{'type':'string'},'retry':{'type':'boolean'}}),
    '/api/assistant/message': ('Ask the workspace assistant; the answer is saved separately.',
        {name:{'type':'string'} for name in ('text','study','run','agent','backend','model','preset')}),
    '/api/run': ('Start an agent task through the existing executor.',
        {**{name:{'type':'string'} for name in ('prompt','skill','target','preset','role','backend','model','parent')},'confirm':{'type':'boolean'},
         'context':{'type':'object','properties':{'mode':{'enum':['fresh','continue','native-fork']},'run_id':{'type':'string'},'handoff':{'type':'boolean'}}}}),
    '/api/providers': ('Save or remove an API provider connection on the selected machine.',
        {'action':{'enum':['connect','disconnect']},'provider':{'type':'string'},
         'key':{'type':'string','writeOnly':True,'format':'password'},'machine':{'type':'string'}}),
    '/api/agent-settings': ('Save agent presets or study role assignments.',{'settings':{'type':'object'},'study':{'type':'string'}}),
}


def describe(reads,writes,files,compose_ops):
    paths={}
    for method,routes in [('get',set(reads)|set(files)|{'/api/ping','/api/events','/api/session'}),('head',files),('post',writes)]:
        for route in sorted(routes):
            label=route.removeprefix('/api/').replace('/',' · ')
            description,fields=FIELDS.get(route,(label,{})) if method=='post' else (label,{})
            if route=='/api/compose':
                description='Edit a workflow/skill/room draft, then explicitly publish it.' if method=='post' else 'Inspect the current workflow/skill/room draft and its changes.'
                fields={'op':{'enum':sorted(set(compose_ops)|{'publish','undo'})},'workflow':{'type':'string'},'nodes':{'type':'array','items':{'type':'object'}},'path':{'type':'string'},'text':{'type':'string'}}
            operation={'operationId':method+'_'+route.strip('/').replace('/','_').replace('-','_'),
                'summary':description,'responses':{'200':{'description':'Operation result. Errors use an error field and an HTTP error status.'}},
                'security':[{'localSession':[]}]}
            if route in ('/api/ping','/api/session'):
                operation['security']=[]
            if method=='post':
                operation['requestBody']={'required':True,'content':{'application/json':{'schema':{'type':'object','properties':fields,'additionalProperties':True}}}}
            paths.setdefault(route,{})[method]=operation
    return {'openapi':'3.1.0','info':{'title':'ARLOtope local API','version':'1',
        'description':'The dashboard and CLI use these same routes. Additional request fields remain owned and validated by each operation. X-Arlotope-Local: 1 targets the owning Lab even when its dashboard is showing a connected Lab.'},'paths':paths,
        'components':{'securitySchemes':{'localSession':{'type':'apiKey','in':'cookie','name':'arlotope_<port>',
            'description':'GET /api/session from loopback to receive the HttpOnly session cookie. Use an SSH tunnel for another machine.'}}}}
