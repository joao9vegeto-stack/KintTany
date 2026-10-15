#!/usr/bin/env python3
"""Read-only PS3 SELF/SFO metadata probe. Does not decrypt or copy executable data."""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
from pathlib import Path

class PreflightError(ValueError):
    pass

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def read_sfo(path: Path) -> dict:
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b'\x00PSF':
        raise PreflightError('PARAM.SFO invalido: assinatura PSF ausente')
    version, keys, values, count = struct.unpack_from('<IIII', data, 4)
    if count > 4096 or keys > len(data) or values > len(data) or 20 + count * 16 > len(data):
        raise PreflightError('PARAM.SFO invalido: indices fora do arquivo')
    fields = {}
    for idx in range(count):
        key_offset, typ, length, maximum, val_offset = struct.unpack_from('<HHIII', data, 20 + idx * 16)
        key_pos = keys + key_offset
        val_pos = values + val_offset
        if key_pos >= len(data) or val_pos > len(data) or length > len(data) - val_pos or length > maximum:
            raise PreflightError('PARAM.SFO invalido: campo fora dos limites')
        terminator = data.find(b'\x00', key_pos)
        if terminator < 0 or terminator >= values:
            raise PreflightError('PARAM.SFO invalido: chave nao terminada')
        name = data[key_pos:terminator].decode('utf-8', 'replace')
        if not name or name in fields:
            raise PreflightError('PARAM.SFO invalido: campo repetido ou vazio')
        raw = data[val_pos:val_pos + length]
        if typ == 0x0404 and length == 4:
            val = struct.unpack('<I', raw)[0]
        elif typ in (0x0204, 0x0004):
            val = raw.rstrip(b'\x00').decode('utf-8', 'replace')
        else:
            val = f'<{len(raw)} bytes; tipo 0x{typ:04x}>'
        if name == 'LICENSE':
            continue
        fields[name] = val
    return {
        'source': path.name, 'size_bytes': len(data), 'sha256': _sha256(path),
        'psf_version': f'0x{version:08x}', 'fields': fields
    }

def read_self(path: Path) -> dict:
    data = path.read_bytes()
    if len(data) < 0x90 or data[:4] != b'SCE\x00':
        raise PreflightError('EBOOT.BIN invalido: nao e SELF/SCE reconhecido')
    elf_offset = data.find(b'\x7fELF', 0x20, min(len(data), 4096))
    if elf_offset < 0 or elf_offset + 64 > len(data):
        raise PreflightError('SELF nao contem cabecalho ELF identificavel')
    ident = data[elf_offset:elf_offset + 16]
    if ident[4] != 2 or ident[5] != 2:
        raise PreflightError('ELF incorporado nao e ELF64 big endian')
    fields = struct.unpack_from('>HHIQQQIHHHHHH', data, elf_offset + 16)
    elf_type, machine, version, entry, program_offset, section_offset, flags, ehsz, phsz, phcnt, shsz, shcnt, shindex = fields
    if machine != 21 or version != 1:
        raise PreflightError('ELF incorporado nao e PPU PowerPC64 valido')
    return {
        'source': path.name, 'size_bytes': len(data), 'sha256': _sha256(path),
        'container': 'SCE SELF', 'embedded_elf_offset': elf_offset,
        'embedded_architecture': 'PowerPC64 PPU (ELF64 big endian)',
        'entry_point': f'0x{entry:x}', 'elf_program_headers': phcnt,
        'encrypted_payload_readable': False,
        'warning': 'Cabecalho ELF interno nao e um EBOOT.ELF descriptografado; nao o renomeie nem extraia com recorte de bytes.'
    }

def inventory(eboot: Path, sfo: Path) -> dict:
    return {
        'schema': 'ascension-recomp/package-preflight-v1',
        'self': read_self(eboot), 'param_sfo': read_sfo(sfo),
        'linkage': 'ID de titulo fornecido apenas pelo SFO; a correspondencia criptografica do EBOOT requer descriptografia/validacao adicional',
        'note': 'Metadata only. The game payload is not uploaded or copied.'
    }

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--eboot', type=Path, required=True)
    parser.add_argument('--sfo', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    opts = parser.parse_args()
    try:
        report = inventory(opts.eboot, opts.sfo)
        opts.out.parent.mkdir(parents=True, exist_ok=True)
        opts.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print('OK: SELF PPU + PARAM.SFO analisados, sem descriptografar.')
        print('TITLE_ID:', report['param_sfo']['fields'].get('TITLE_ID', 'desconhecido'))
        print('Manifest:', opts.out)
        return 0
    except (PreflightError, OSError, struct.error) as e:
        parser.exit(2, f'ERRO: {e}\n')

if __name__ == '__main__':
    raise SystemExit(main())
