"""Telemetry STUB plugin — interface proof only, NOT live telemetry.
Capability: telemetry.read (effect: read).
Returns mocked nvidia-smi-shaped rows, keyed by GPU UUID, so Phase 4 can
drop in the real provider without changing the core or the capability name.
MOCKED values are labelled mocked in every row. Never invent live values.
Real provider (Phase 4, R3 octominer_telemetry spirit): pinned-SSH nvidia-smi
by GPU UUID, fan/temp/VRAM/power, per-source failure isolation, unknown
when a source fails — never a hardcoded number.
"""
MOCK_GPUS = [
    {"nvidia_uuid": "GPU-ace423ce-ae61-803e-0734-a907283efe54", "name": "Tesla P100-PCIE-16GB",
     "temperature_c": 41, "memory_used_mib": 14898, "memory_total_mib": 16384,
     "utilization_percent": 12, "power_draw_w": 55, "fan_speed_percent": None},
    {"nvidia_uuid": "GPU-c2f0fffc-1e63-d3c5-bdb3-f103ec44d5b9", "name": "NVIDIA GeForce RTX 3060 Ti",
     "temperature_c": 31, "memory_used_mib": 4379, "memory_total_mib": 8192,
     "utilization_percent": 0, "power_draw_w": 28, "fan_speed_percent": None},
]


def create_plugin(config):
    host_id = (config or {}).get("host_id", "octominer1")

    def read_telemetry():
        rows = []
        for gpu in MOCK_GPUS:
            rows.append({**gpu, "host_id": host_id, "source": "mocked — NOT live",
                         "evidence_source": "telemetry_stub plugin, Phase 0 proof only"})
        return {"host_id": host_id, "mocked": True, "gpus": rows}

    class _Plugin:
        capabilities = {"telemetry.read": read_telemetry}

    return _Plugin()
