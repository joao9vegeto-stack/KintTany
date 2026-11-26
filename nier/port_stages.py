#!/usr/bin/env python3
"""Keep expensive Linux stages in Colab; route only native ARM64 host work to Mac."""
from __future__ import annotations

HOST_REQUIREMENTS = {
    "nvn": ("glslc_capture", "ue_decode", "oodle_packs", "ue_legacy"),
    "gl": ("gl_capture",),
    "vulkan": ("vk_capture",),
}
MAC_STAGES = frozenset({*HOST_REQUIREMENTS["nvn"], "gl_capture", "vk_capture", "jit_capture"})


def source_flags(sources: dict) -> list[str]:
    gfx = sources["graphics"][0]
    if gfx not in HOST_REQUIREMENTS:
        raise ValueError(f"Unsupported shader graphics backend: {gfx}")
    return sorted(k for k in HOST_REQUIREMENTS[gfx] if sources.get(k, (False, ""))[0])


def deferred_mac_stages(sources: dict, *, jit: bool = False,
                        linux_ue_complete: bool = False) -> list[str]:
    stage = set(source_flags(sources))
    if linux_ue_complete:
        if "ue_decode" not in stage:
            raise ValueError("Linux UE decode marked complete without an UE source")
        stage.discard("ue_decode")
    if jit:
        stage.add("jit_capture")
    return sorted(stage)


def require_valid_stage_list(stages: object) -> list[str]:
    if not isinstance(stages, list) or not all(isinstance(x, str) for x in stages):
        raise ValueError("Mac stage list must be an array of names")
    if stages != sorted(set(stages)) or not set(stages) <= MAC_STAGES:
        raise ValueError(f"Invalid, duplicated or unordered Mac stages: {stages!r}")
    return stages
