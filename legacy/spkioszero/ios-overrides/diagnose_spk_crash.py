#!/usr/bin/env python3
"""
Diagnóstico do crash de DRAGON BALL: Sparking! ZERO.

Lê um módulo NSO0 original, descomprime o segmento text se necessário,
verifica seu hash quando o cabeçalho solicita essa verificação e imprime
disassembly ARM64 em torno dos offsets observados no log.

Uso:

    python3 dm/ios/tools/diagnose_spk_crash.py \
        /caminho/para/ExeFS/main \
        --output crash_diagnostic.txt

Observações importantes:

- Este script NÃO modifica o jogo.
- Este script NÃO gera IPA.
- Os offsets são relativos ao módulo main observado no log fornecido.
- O NSO original pode não conter exatamente o mesmo código executado
  depois que o rewriter aplica suas alterações.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path

try:
    import lz4.block
except ImportError:
    print(
        "ERRO: dependência lz4 ausente. Instale com: "
        "python3 -m pip install lz4",
        file=sys.stderr,
    )
    raise SystemExit(1)

try:
    from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
except ImportError:
    print(
        "ERRO: dependência capstone ausente. Instale com: "
        "python3 -m pip install capstone",
        file=sys.stderr,
    )
    raise SystemExit(1)


# Offsets obtidos do log enviado pelo usuário.
TARGETS = (
    ("PC: instrução que causou o SIGSEGV", 0x1EB0D40),
    ("LR: endereço de retorno registrado", 0x1E5BBBC),
    ("Backtrace: primeiro endereço", 0x1E4E87C),
    ("Backtrace: segundo endereço", 0x1EAB078),
    ("Backtrace: terceiro endereço", 0x1E4DB34),
)

# Proteção contra cabeçalhos inválidos que aleguem um text gigantesco.
MAX_TEXT_SIZE = 1024 * 1024 * 1024


def fail(message: str) -> None:
    raise RuntimeError(message)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        fail(f"Leitura fora do cabeçalho no offset 0x{offset:x}")
    return struct.unpack_from("<I", data, offset)[0]


def load_nso_text(path: Path) -> dict:
    """
    Lê os campos relevantes de um NSO0 e retorna seu segmento text.

    Cabeçalho NSO:
      0x0c: flags
      0x10: offset do segmento text no arquivo
      0x14: offset do segmento text na memória
      0x18: tamanho descomprimido do text
      0x40: build ID de 32 bytes
      0x60: tamanho armazenado do text
      0xa0: SHA-256 esperado do text
    """

    data = path.read_bytes()

    if len(data) < 0x100:
        fail(f"Arquivo pequeno demais para um cabeçalho NSO: {path}")

    if data[:4] != b"NSO0":
        fail(f"O arquivo não começa com NSO0: {path}")

    flags = read_u32(data, 0x0C)

    # O loader do nxnative identifica compressão zstd pelo bit 7.
    if flags & (1 << 7):
        fail(
            "Este NSO informa compressão zstd. "
            "Este diagnóstico suporta apenas NSO sem compressão "
            "ou com segmento text comprimido em LZ4."
        )

    text_file_offset = read_u32(data, 0x10)
    text_memory_offset = read_u32(data, 0x14)
    text_size = read_u32(data, 0x18)
    text_compressed_size = read_u32(data, 0x60)

    if text_size == 0 or text_size > MAX_TEXT_SIZE:
        fail(f"Tamanho de text inválido: 0x{text_size:x}")

    compressed = bool(flags & 1)
    stored_size = text_compressed_size if compressed else text_size

    if stored_size == 0:
        fail("O tamanho armazenado do segmento text é zero.")

    end = text_file_offset + stored_size

    if text_file_offset < 0x100 or end > len(data):
        fail(
            "Segmento text fora dos limites do arquivo: "
            f"offset=0x{text_file_offset:x}, "
            f"tamanho=0x{stored_size:x}, "
            f"arquivo=0x{len(data):x}"
        )

    stored_text = data[text_file_offset:end]

    if compressed:
        try:
            text = lz4.block.decompress(
                stored_text,
                uncompressed_size=text_size,
            )
        except Exception as exc:
            fail(f"Falha ao descomprimir text com LZ4: {exc}")
    else:
        text = stored_text

    if len(text) != text_size:
        fail(
            "Tamanho de text divergente: "
            f"esperado=0x{text_size:x}, obtido=0x{len(text):x}"
        )

    expected_hash = data[0xA0:0xC0]
    actual_hash = hashlib.sha256(text).digest()

    # No NSO0, o bit 3 solicita verificação do hash de text.
    hash_check_enabled = bool(flags & (1 << 3))

    if hash_check_enabled and expected_hash != actual_hash:
        fail(
            "Hash SHA-256 do segmento text não confere: "
            f"esperado={expected_hash.hex()}, "
            f"obtido={actual_hash.hex()}"
        )

    return {
        "path": str(path),
        "file_size": len(data),
        "file_sha256": sha256_hex(data),
        "flags": flags,
        "build_id": data[0x40:0x60].hex(),
        "text_file_offset": text_file_offset,
        "text_memory_offset": text_memory_offset,
        "text_size": text_size,
        "text_compressed": compressed,
        "text_stored_size": stored_size,
        "text_sha256": actual_hash.hex(),
        "hash_check_enabled": hash_check_enabled,
        "text": text,
    }


def dump_target(
    disassembler: Cs,
    text: bytes,
    text_memory_offset: int,
    label: str,
    target: int,
    radius: int,
) -> list[str]:
    lines = [
        "",
        "=" * 78,
        f"{label}",
        f"Offset solicitado: main+0x{target:x}",
        "=" * 78,
    ]

    text_end = text_memory_offset + len(text)

    if not (text_memory_offset <= target < text_end):
        lines.append(
            "FORA DO SEGMENTO TEXT: "
            f"text=0x{text_memory_offset:x}..0x{text_end:x}"
        )
        return lines

    start = max(text_memory_offset, target - radius)
    end = min(text_end, target + radius + 4)

    # Instruções ARM64 têm 4 bytes e são alinhadas.
    start = (start + 3) & ~3
    end = end & ~3

    begin_in_text = start - text_memory_offset
    end_in_text = end - text_memory_offset

    code = text[begin_in_text:end_in_text]

    decoded_count = 0

    for instruction in disassembler.disasm(code, start):
        decoded_count += 1
        marker = " >>>" if instruction.address == target else "    "
        raw = instruction.bytes.hex()

        lines.append(
            f"{marker} main+0x{instruction.address:08x} "
            f"{raw:<8}  "
            f"{instruction.mnemonic:<10} "
            f"{instruction.op_str}"
        )

    if decoded_count == 0:
        lines.append(
            "Nenhuma instrução decodificada nessa região. "
            "Confira se o arquivo e os offsets correspondem ao crash."
        )

    return lines


def create_report(info: dict, radius: int) -> str:
    disassembler = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    disassembler.skipdata = True

    lines = [
        "DIAGNÓSTICO DE CRASH — NSO ORIGINAL",
        "",
        "Este relatório NÃO prova que o módulo em execução era idêntico",
        "ao NSO original: o rewriter ou patches podem alterar o código.",
        "",
        f"Arquivo: {info['path']}",
        f"Tamanho: {info['file_size']} bytes",
        f"SHA-256 do arquivo: {info['file_sha256']}",
        f"Build ID NSO completo: {info['build_id']}",
        f"Build ID — primeiros 16 bytes: {info['build_id'][:32]}",
        f"Flags NSO: 0x{info['flags']:08x}",
        f"Text: offset no arquivo = 0x{info['text_file_offset']:x}",
        f"Text: offset em memória = 0x{info['text_memory_offset']:x}",
        f"Text: tamanho descomprimido = 0x{info['text_size']:x}",
        f"Text: tamanho armazenado = 0x{info['text_stored_size']:x}",
        f"Text comprimido com LZ4: {'sim' if info['text_compressed'] else 'não'}",
        f"SHA-256 do text descomprimido: {info['text_sha256']}",
        (
            "Hash do text exigido pelo cabeçalho: "
            + ("sim, verificado" if info["hash_check_enabled"] else "não")
        ),
        "",
        "Referência do log do crash:",
        "  sig=11",
        "  addr=0x14be6b408",
        "  pc=main+0x1eb0d40",
        "  lr=main+0x1e5bbbc",
        "",
        "A seta >>> marca o offset exato, quando decodificado.",
    ]

    for label, target in TARGETS:
        lines.extend(
            dump_target(
                disassembler=disassembler,
                text=info["text"],
                text_memory_offset=info["text_memory_offset"],
                label=label,
                target=target,
                radius=radius,
            )
        )

    lines.extend(
        [
            "",
            "=" * 78,
            "FIM DO RELATÓRIO",
            "=" * 78,
            "",
        ]
    )

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Diagnostica offsets ARM64 de um NSO0 original."
    )

    parser.add_argument(
        "nso",
        type=Path,
        help="Caminho para o arquivo ExeFS/main.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("crash_diagnostic.txt"),
        help="Arquivo de relatório. Padrão: crash_diagnostic.txt",
    )

    parser.add_argument(
        "--radius",
        type=int,
        default=128,
        help="Quantidade de bytes de contexto em cada lado. Padrão: 128.",
    )

    args = parser.parse_args()

    if args.radius < 4 or args.radius > 4096:
        parser.error("--radius deve estar entre 4 e 4096 bytes")

    if not args.nso.is_file():
        parser.error(f"Arquivo não encontrado: {args.nso}")

    try:
        info = load_nso_text(args.nso)
        report = create_report(info, args.radius)

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")

        print(report)
        print(f"Relatório salvo em: {args.output}")

        return 0

    except Exception as exc:
        print(f"ERRO no diagnóstico: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
