"""Provider settings on the execution machine. Keys never enter Lab configuration."""
import ctx
import provider_access
import remote_projects


def _call(machine, action, **body):
    if machine and machine != 'local':
        return remote_projects.rpc(machine, 'providers', {'action':action, **body})
    if action == 'catalog':
        return provider_access.view(body.get('provider'),body.get('backend'),body.get('refresh') is True)
    return provider_access.connect(action,body.get('provider'),body.get('key'),body.get('backend'))


def view(query):
    try:
        return _call(query.get('machine'),'catalog',refresh=query.get('refresh')=='1',provider=query.get('provider'),backend=query.get('backend')),200
    except (ValueError,OSError) as error:
        return {'error':str(error)},400


def save(body):
    try:
        if body.get('action') not in ('connect','disconnect'):
            raise ValueError('Choose connect or disconnect.')
        result=_call(body.get('machine'),body.get('action'),provider=body.get('provider'),key=body.get('key'),backend=body.get('backend'))
        ctx.pi_log({'action':'provider.'+body['action'],'provider':body.get('provider'),'backend':result.get('backend'),'machine':body.get('machine')})
        return result,200
    except (ValueError,OSError) as error:
        return {'error':str(error)},400
