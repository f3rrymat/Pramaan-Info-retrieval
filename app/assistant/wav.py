"""Minimal WAV (RIFF, PCM) parsing, validation and merging. No external dependency."""
from __future__ import annotations

import struct
from dataclasses import dataclass


@dataclass
class Wav:
    channels: int
    sample_rate: int
    bits: int
    fmt_tag: int
    data: bytes

    @property
    def seconds(self) -> float:
        bps = self.sample_rate * self.channels * max(self.bits, 8) // 8
        return len(self.data) / bps if bps else 0.0


def parse(blob: bytes) -> Wav:
    """Parse a RIFF/WAVE file. Raises ValueError with a short, safe message."""
    if len(blob) < 44 or blob[:4] != b"RIFF" or blob[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    pos, fmt, data = 12, None, None
    while pos + 8 <= len(blob):
        cid, size = blob[pos:pos + 4], struct.unpack("<I", blob[pos + 4:pos + 8])[0]
        body = blob[pos + 8: pos + 8 + size] if size != 0xFFFFFFFF else blob[pos + 8:]
        if cid == b"fmt ":
            if len(body) < 16:
                raise ValueError("bad WAV header")
            tag, ch, rate, _, _, bits = struct.unpack("<HHIIHH", body[:16])
            fmt = (tag, ch, rate, bits)
        elif cid == b"data":
            data = body
            break
        pos += 8 + size + (size & 1)
    if fmt is None or data is None:
        raise ValueError("bad WAV header")
    tag, ch, rate, bits = fmt
    if ch < 1 or rate < 1000 or bits not in (8, 16, 24, 32):
        raise ValueError("unsupported WAV format")
    return Wav(ch, rate, bits, tag, data)


def build(channels: int, sample_rate: int, bits: int, data: bytes, fmt_tag: int = 1) -> bytes:
    block = channels * bits // 8
    hdr = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
    hdr += b"fmt " + struct.pack("<IHHIIHH", 16, fmt_tag, channels, sample_rate, sample_rate * block, block, bits)
    return hdr + b"data" + struct.pack("<I", len(data)) + data


def merge(parts: list) -> bytes:
    """Concatenate WAV files with the same format into one WAV."""
    if not parts:
        raise ValueError("no audio")
    ws = [parse(p) for p in parts]
    a = ws[0]
    if any((w.channels, w.sample_rate, w.bits, w.fmt_tag) != (a.channels, a.sample_rate, a.bits, a.fmt_tag) for w in ws[1:]):
        raise ValueError("audio chunks differ in format")
    return build(a.channels, a.sample_rate, a.bits, b"".join(w.data for w in ws), a.fmt_tag)


def silence(seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    """A silent mono 16-bit clip (tests and scripts/assistant_smoke.py)."""
    return build(1, sample_rate, 16, b"\x00\x00" * int(seconds * sample_rate))
