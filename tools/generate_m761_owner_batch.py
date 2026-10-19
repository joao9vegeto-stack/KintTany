#!/usr/bin/env python3
"""M7.61 reproducible PPC64 native AOT owner batch (NPUA80918).

Only finite independently SHA-gated PPC spans are fed to the existing
static lifter.  Every rejected span is reported with PC/opcode/reason.
No runtime PowerPC decoding, JIT, interpreter or fabricated instructions.
The compressed span records are a *partial* code inventory, NOT GOWA.ELF.
Do not upload generated C, raw game bytes or original ELF as CI artifacts.
"""
import argparse
import base64
import hashlib
import json
import re
import struct
import zlib
from pathlib import Path
from ppu_cfg_lifter import PPUImage, PROLOGUE, Unsupported, lift

ELF_SHA = "4bf75c897b82d1beb25514cbadaff3d03e1b0c7bf849fa5d289be4f9183462b5"
SPAN_DATA_SHA = "255fa308fa8a46efe448a0259f7b39392b8c1972aa01901299fedd5cfdc569f7"
STOP_PC = 0x003e16e0
PACKED = "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"

def spans():
    payload = zlib.decompress(base64.b64decode(PACKED, validate=True))
    if hashlib.sha256(payload).hexdigest() != SPAN_DATA_SHA:
        raise ValueError("Original owner batch fingerprint mismatch")
    pos, result, entries = 0, [], set()
    while pos < len(payload):
        if pos + 6 > len(payload):
            raise ValueError("Truncated span descriptor")
        pc, count = struct.unpack_from(">IH", payload, pos)
        pos += 6
        if pc in entries or pc & 3 or not (1 <= count <= 512) or pos + count*4 > len(payload):
            raise ValueError("Duplicate, unaligned or invalid owner span")
        entries.add(pc)
        words = struct.unpack_from(">" + str(count) + "I", payload, pos)
        pos += count*4
        result.append((pc, words))
    if len(result) != 26 or STOP_PC not in entries:
        raise ValueError("Incomplete owner discovery snapshot")
    # A span ends at the original non-linked BCLR/BLR; never read beyond it.
    for pc, words in result:
        end = words[-1]
        if end >> 26 != 19 or (end >> 1) & 1023 != 16 or end & 1:
            raise ValueError("Span lacks PPC BCLR terminator at 0x%08x" % (pc + 4*len(words)-4))
    return result

def authenticate(path):
    data = Path(path).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != ELF_SHA:
        raise ValueError("GOWA.ELF SHA mismatch: " + digest)
    image = PPUImage(path)
    for pc, words in spans():
        if tuple(image.words(pc, pc + len(words)*4)) != tuple(words):
            raise ValueError("ELF executable PT_LOAD disagreement at 0x%08x" % pc)
    return digest

def emit():
    body, installed, rejected = [], [], []
    for pc, words in spans():
        name = "ar_m761_native_%08x" % pc
        try:
            src, hist = lift(words, pc, name)
            if not src.startswith(PROLOGUE):
                raise ValueError("AOT lifter contract changed")
            code = src[len(PROLOGUE):]
            # Source lifter emits no-op labels except when branch GOTOs use them.
            # Preserve labels: they are part of validated guest CFG semantics.
            lines = []
            for line in code.splitlines():
                lines.append(line)
                if (re.search(r"\bar_(?:read|write)(?:8|16|32|64)\(", line)
                    and not line.lstrip().startswith("extern ")):
                    if not line.strip().endswith(";"):
                        raise ValueError("unexpected memory operation syntax")
                    lines.append("    if (ar_last_error()!=AR_OK) return AR_MEM_FAULT;")
            body.append("\n".join(lines) + "\n")
            installed.append((pc, words, hist))
        except (Unsupported, ValueError) as err:
            # The first word is NOT necessarily the failing instruction.
            # Isolate each opcode under the strict existing lifter, never
            # fabricate a PC or silently replace unsupported code with NOP.
            offender = None
            for index, word in enumerate(words):
                try:
                    lift((word, 0x4e800020), pc+4*index, "ar_m761_opcode_check",
                         allow_terminal_conditional=True)
                except (Unsupported, ValueError) as one:
                    offender = {"pc": "0x%08X" % (pc+4*index),
                                "opcode": "0x%08X" % word,
                                "reason": str(one)}
                    break
            if offender is None:
                offender = {"pc": "NÃO ISOLADO", "opcode": "NÃO ISOLADO",
                            "span_start": "0x%08X" % pc,
                            "reason": "Combined-CFG rejection: " + str(err)}
            rejected.append(offender)
    if not any(pc == STOP_PC for pc, _, _ in installed) or len(installed) < 2:
        raise ValueError("Required physical stop or safe bulk coverage not translated: " + repr(rejected))
    # Entire authenticated span list is prechecked BEFORE any ar_register call.
    # Runtime compares executable ELF bytes and live guest RAM to original words.
    expected = []
    for pc, words, _ in installed:
        words_c = ",".join("UINT32_C(0x%08x)" % w for w in words)
        expected.append("static const uint32_t m761_%08x[] = {%s};" % (pc, words_c))
    entries = "\n".join("  {UINT32_C(0x%08x),%du,m761_%08x,ar_m761_native_%08x}," %
                       (pc, len(words), pc, pc) for pc, words, _ in installed)
    installer = r"""
typedef struct {uint32_t pc,count;const uint32_t*words;ar_ppu_fn fn;} ar_m761_span;
static const ar_m761_span ar_m761_owner_spans[] = {
__ENTRIES__
};
int ar_m761_register_owner(const uint8_t*elf,size_t len) {
 if(!elf || len<64u) return AR_BAD_ARGS;
 const size_t count=sizeof(ar_m761_owner_spans)/sizeof(ar_m761_owner_spans[0]);
 for(size_t k=0;k<count;k++) {
  const ar_m761_span*q=&ar_m761_owner_spans[k];
  for(uint32_t i=0;i<q->count;i+=4u) {
    uint32_t w[6]={0};
    const uint32_t n=(q->count-i<4u)?q->count-i:4u;
    if(ar_m712_exec_window(elf,len,q->pc+i*4u,w)!=AR_OK ||
       w[4]<n || !(w[5]&1u)) return AR_BAD_ARGS;
    for(uint32_t j=0;j<n;j++) {
      const uint32_t at=q->pc+4u*(i+j);
      if(w[j]!=q->words[i+j] ||
         ar_read32(at)!=q->words[i+j] ||
         ar_last_error()!=AR_OK) return AR_BAD_ARGS;
    }
  }
 }
 for(size_t k=0;k<count;k++) {
    const ar_m761_span*q=&ar_m761_owner_spans[k];
    const int result=ar_register(q->pc,q->fn);
    /* Preserve the older signed owner on an existing/duplicate guest PC. */
    if(result!=AR_OK && result!=AR_DUPLICATE) return result;
 }
 return AR_OK;
}
"""
    source = ('/* M7.61 Apple ARM64 static guest translation; NEVER an interpreter. */\n'
              '#include "ppu_bridge.h"\n'
              'extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);\n'
              + PROLOGUE + "\n".join(body) + "\n" + "\n".join(expected) + "\n"
              + installer.replace("__ENTRIES__", entries))
    report = {
      "schema": "ascension-m761-owner-batch-1", "source_elf_sha256": ELF_SHA,
      "discovered_structural_spans": len(spans()),
      "discovered_structural_words": sum(len(w) for _,w in spans()),
      "generated_native_entries": len(installed),
      "generated_native_ppc_words": sum(len(w) for _,w,_ in installed),
      "accepted": [{"pc": "0x%08X" % p,"end": "0x%08X" % (p+4*len(w)),
                    "words":len(w),"word_sha256":hashlib.sha256(struct.pack(">"+str(len(w))+"I",*w)).hexdigest(),
                    "opcode_histogram": hist} for p,w,hist in installed],
      "rejected": rejected,
      "compiled_apple_arm64": "NÃO MEDIDO",
      "linked_in_final_macho": "NÃO MEDIDO",
      "executed_on_iphone": "NÃO MEDIDO",
      "note": "Structural function candidates, not Ghidra-confirmed boundaries; no FS/RSX claims."
    }
    return source, report

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--report", type=Path)
    ap.add_argument("--verify-elf", type=Path)
    args = ap.parse_args()
    if args.verify_elf: authenticate(args.verify_elf)
    source, report = emit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(source)
    if args.report:
        args.report.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("M7.61 native AOT batch: %d/%d structural spans translated; %d genuine PPC words; physical execution NOT MEASURED" %
          (report["generated_native_entries"],report["discovered_structural_spans"],
           report["generated_native_ppc_words"]))

if __name__ == "__main__":
    main()
