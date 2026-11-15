#!/usr/bin/env python3
"""Single source of truth for the Colab -> Drive -> GitHub Actions preparation manifest."""
from __future__ import annotations

PREPARED_MANIFEST_KEYS = (
    "format",
    "project",
    "title_id",
    "package_version",
    "display_version",
    "base_content_version",
    "update_content_version",
    "nx2apple_tag",
    "engine_pin",
    "profile_type",
    "profile_source",
    "profile_relative_dir",
    "modules",
    "main_build_id",
    "main_sha256",
    "rewrite_audit",
    "graphics_api",
    "jit_required",
    "shader_source_flags",
    "shader_source_reasons",
    "shader_source_audit",
    "shader_chain",
    "romfs_relative_path",
    "romfs_id_relative_path",
    "romfs_size",
    "romfs_sha256",
    "aoc_relative_dir",
    "aoc_count",
    "aoc_title_ids",
    "aoc_contents",
    "aoc_images",
    "dlc_content_meta_count",
    "dlc_content_meta",
    "survey_relative_path",
    "survey_size",
    "survey_sha256",
    "input_package_count",
    "input_nsp_count",
    "input_xci_count",
    "input_update_nsp_count",
    "input_dlc_nsp_count",
    "input_packages",
)


def copy_prepared_manifest(source: dict) -> dict:
    """Copy every canonical prep field; fail before large restores if the schema is incomplete."""
    if not isinstance(source, dict):
        raise ValueError("Canonical preparation manifest is not a JSON object.")
    missing = [key for key in PREPARED_MANIFEST_KEYS if key not in source]
    if missing:
        raise ValueError("Preparation manifest is missing canonical fields: " + ", ".join(missing))
    return {key: source[key] for key in PREPARED_MANIFEST_KEYS}


def prepared_manifest_mismatches(left: dict, right: dict) -> list[str]:
    """Return missing or unequal canonical fields, preserving comparison order."""
    if not isinstance(left, dict) or not isinstance(right, dict):
        return ["<manifest is not a JSON object>"]
    issues = []
    for key in PREPARED_MANIFEST_KEYS:
        if key not in left:
            issues.append(key + " (missing from left manifest)")
        elif key not in right:
            issues.append(key + " (missing from right manifest)")
        elif left[key] != right[key]:
            issues.append(key)
    return issues
