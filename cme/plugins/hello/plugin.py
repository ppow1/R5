"""Hello example plugin — proves the loader, nothing else.
Capability: hello.greet (effect: read, no hardware, no shell, no core access).
"""


def create_plugin(config):
    name = (config or {}).get("greeting_name", "Riverview")

    def greet(who="Pat"):
        return {"message": f"Hello {who}, from {name} via plugin hello.greet.", "plugin": "r5.hello"}

    class _Plugin:
        capabilities = {"hello.greet": greet}

    return _Plugin()
