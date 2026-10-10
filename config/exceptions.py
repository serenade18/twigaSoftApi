from rest_framework.views import exception_handler


def _first_message(detail):
    if isinstance(detail, list):
        return _first_message(detail[0]) if detail else ''
    if isinstance(detail, dict):
        return _first_message(next(iter(detail.values()), ''))
    return str(detail)


def api_exception_handler(exc, context):
    """Shape errors as {"error": "<message for the user>", "fields": {...}} as the frontend expects."""
    response = exception_handler(exc, context)
    if response is None:
        return None
    detail = response.data
    body = {'error': _first_message(detail)}
    if isinstance(detail, dict) and set(detail) - {'detail', 'non_field_errors'}:
        body['fields'] = {
            key: [str(m) for m in (value if isinstance(value, list) else [value])]
            for key, value in detail.items() if key != 'non_field_errors'
        }
    response.data = body
    return response
