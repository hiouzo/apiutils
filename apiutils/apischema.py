import click


def build_object(data, descriptions):
    properties = {}
    for name, value in data.items():
        schema = build_schema(value, descriptions)
        if descriptions and name in descriptions:
            schema.update(description=descriptions[name])
        properties[name] = schema
    schema = {
        'type': 'object',
    }
    if properties:
        schema.update(properties=properties)
    return schema


def build_array(data, descriptions):
     if len(data):
        items = build_schema(data[0], descriptions)
     else:
        items = build_schema(None)
     return {
        'type': 'array',
        'items': items
     }


def build_number(data):
    return {
        'type': 'number',
        'example': data,
    }


def build_boolean(data):
    return {
        'type': 'boolean',
        'example': 'true' if data else 'false'
    }


def build_null(data):
    return {
        'type': 'null',
    }


def build_string(data):
    return {
        'type': 'string',
        'example': data
    }


def build_schema(data, descriptions=None):
    if isinstance(data, dict):
        return build_object(data, descriptions)
    elif isinstance(data, list):
        return build_array(data, descriptions)
    elif isinstance(data, bool):
        return build_boolean(data)
    elif isinstance(data, int):
        return build_number(data)
    elif data is None:
        return build_null(data)
    else:
        return build_string(data)


@click.command()
def run():
    import sys
    import json

    text = sys.stdin.read()
    data = json.loads(text)
    schema = build_schema(data)
    print(json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    run()
