"""ACP's flat elicitation schemas. No general JSON-Schema runtime is needed."""
import math
import re
from datetime import date, datetime
from urllib.parse import urlsplit


def choices(field):
    values = field.get('enum')
    if values is None:
        options = field.get('oneOf', field.get('anyOf', []))
        if not isinstance(options, list) or any(not isinstance(o, dict) or not isinstance(o.get('const'), str) for o in options):
            raise ValueError('Enum choices must be strings.')
        values = [o['const'] for o in options]
    if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
        raise ValueError('Enum choices must be strings.')
    return values


def schema_fields(schema):
    if not isinstance(schema, dict) or schema.get('type', 'object') != 'object':
        raise ValueError('A form needs an object schema.')
    fields = schema.get('properties', {})
    required = schema.get('required') or []
    if not isinstance(fields, dict) or not isinstance(required, list) or any(not isinstance(k, str) or k not in fields for k in required):
        raise ValueError('Invalid form fields or required fields.')
    for name, field in fields.items():
        if not isinstance(field, dict) or field.get('type', 'string') not in ('string', 'number', 'integer', 'boolean', 'array'):
            raise ValueError(f'Unsupported form field: {name}')
        if field.get('type') == 'array':
            items = field.get('items') or {}
            if not isinstance(items, dict) or items.get('type', 'string') != 'string' or not choices(items):
                raise ValueError('Array fields must offer string choices.')
        elif any(k in field for k in ('enum', 'oneOf')):
            if not choices(field):
                raise ValueError('Offer at least one enum choice.')
        for key in ('minimum','maximum','minLength','maxLength','minItems','maxItems'):
            if key in field and (isinstance(field[key], bool) or not isinstance(field[key], (int,float)) or not math.isfinite(field[key])):
                raise ValueError('Invalid form constraint: '+key)
        if field.get('pattern'):
            try:
                re.compile(field['pattern'])
            except (TypeError, re.error):
                raise ValueError('Invalid form pattern.') from None
    return fields


def validate_content(schema, content):
    fields = schema_fields(schema)
    if not isinstance(content, dict) or any(k not in fields for k in content):
        raise ValueError('Submit the fields in this form.')
    if any(k not in content for k in schema.get('required', [])):
        raise ValueError('Complete the required fields.')
    for name, value in content.items():
        f = fields[name]
        kind = f.get('type', 'string')
        valid = {'string': isinstance(value, str), 'boolean': isinstance(value, bool),
                 'integer': isinstance(value, int) and not isinstance(value, bool),
                 'number': isinstance(value, (int, float)) and not isinstance(value, bool),
                 'array': isinstance(value, list)}[kind]
        if not valid:
            raise ValueError(f'{name}: expected {kind}.')
        if kind in ('integer', 'number'):
            if not math.isfinite(value) or ('minimum' in f and value < f['minimum']) or ('maximum' in f and value > f['maximum']):
                raise ValueError(f'{name}: outside the allowed range.')
        if kind == 'string':
            if len(value) < f.get('minLength', 0) or ('maxLength' in f and len(value) > f['maxLength']):
                raise ValueError(f'{name}: invalid length.')
            if f.get('pattern') and not re.search(f['pattern'], value):
                raise ValueError(f'{name}: does not match the required pattern.')
            fmt = f.get('format')
            try:
                if fmt == 'date':
                    date.fromisoformat(value)
                elif fmt == 'date-time':
                    datetime.fromisoformat(value.replace('Z', '+00:00'))
                elif fmt == 'email' and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
                    raise ValueError()
                elif fmt == 'uri' and not urlsplit(value).scheme:
                    raise ValueError()
            except ValueError:
                raise ValueError(f'{name}: invalid {fmt}.') from None
        offered = choices(f)
        if offered and value not in offered:
            raise ValueError(f'{name}: choose one of the offered values.')
        if kind == 'array':
            offered = choices(f['items'])
            if any(not isinstance(v, str) or v not in offered for v in value) or len(set(value)) != len(value):
                raise ValueError(f'{name}: invalid choices.')
            if len(value) < f.get('minItems', 0) or ('maxItems' in f and len(value) > f['maxItems']):
                raise ValueError(f'{name}: invalid number of choices.')
    return content


def request(params):
    mode = params.get('mode')
    if mode == 'form':
        schema_fields(params.get('requestedSchema'))
    elif mode == 'url':
        u = urlsplit(params.get('url') or '')
        if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password or not params.get('elicitationId'):
            raise ValueError('Invalid external interaction URL.')
    else:
        raise ValueError('Unsupported elicitation mode.')
    return {k: params[k] for k in ('mode', 'message', 'requestedSchema', 'url', 'elicitationId') if k in params}


def response(params, item):
    action = item.get('action', 'accept')
    if action not in ('accept', 'decline', 'cancel'):
        raise ValueError('Choose accept, decline or cancel.')
    result = {'action': action}
    if action == 'accept' and params['mode'] == 'form':
        result['content'] = validate_content(params['requestedSchema'], item.get('content', {}))
    return result
