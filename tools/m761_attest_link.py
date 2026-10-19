#!/usr/bin/env python3
"""Prove M7.61 native ARM64 object + FINAL Mach-O symbols, never guest execution."""
import argparse
import json
import re
from pathlib import Path

def symbol_set(path):
    result=set()
    for line in Path(path).read_text(errors="replace").splitlines():
        match=re.search(r"\s[Tt]\s+_?(ar_m761_native_[0-9a-f]{8}|ar_m761_register_owner)$",line)
        if match:
            result.add(match.group(1))
    return result

def attest(manifest,object_symbols,final_symbols,architecture):
    report=json.loads(Path(manifest).read_text())
    expected={"ar_m761_native_"+row["pc"][2:].lower() for row in report["accepted"]}
    required=expected | {"ar_m761_register_owner"}
    object_found=symbol_set(object_symbols)
    macho_found=symbol_set(final_symbols)
    absent_object=sorted(required-object_found)
    absent_final=sorted(required-macho_found)
    if absent_object or absent_final:
        raise ValueError("UNLINKED M7.61 AOT. object=%s; final=%s" %
                         (absent_object,absent_final))
    arch=Path(architecture).read_text(errors="replace")
    if "arm64" not in arch:
        raise ValueError("Final iOS IPA architecture has not been proved ARM64")
    report.update({
      "compiled_apple_arm64":{"native_function_symbols":len(expected),
                              "installer_symbol":True,
                              "source":"xcrun nm -g compiled Apple arm64 object"},
      "linked_in_final_macho":{"native_function_symbols":len(expected),
                               "installer_symbol":True,
                               "source":"xcrun nm -g final IPA Mach-O + lipo arm64"},
      "registered_in_loaded_guest":"NÃO MEDIDO",
      "executed_on_iphone":"NÃO MEDIDO",
      "guest_filesystem":"NÃO MEDIDO",
      "first_rsx_command":"NÃO MEDIDO",
      "first_game_frame":"NÃO MEDIDO",
      "physical_test":"TESTE FÍSICO PENDENTE"
    })
    Path(manifest).write_text(json.dumps(report,indent=2,ensure_ascii=False,sort_keys=True)+"\n")
    print("M7.61 FINAL arm64: %d new native AOT symbols compiled and linked; device runtime registration NOT MEASURED" % len(expected))
    return report

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--manifest",required=True,type=Path)
    ap.add_argument("--object-nm",required=True,type=Path)
    ap.add_argument("--final-nm",required=True,type=Path)
    ap.add_argument("--lipo",required=True,type=Path)
    a=ap.parse_args()
    attest(a.manifest,a.object_nm,a.final_nm,a.lipo)
if __name__=="__main__":main()
