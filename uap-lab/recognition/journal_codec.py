"""Lossless observation payloads; legacy text journals remain readable."""
import json,zlib
PREFIX=b'FSJ1'

def encode_observations(raw):
    data=raw.encode('utf-8') if isinstance(raw,str) else raw
    if len(data)<512:return raw
    compressed=PREFIX+zlib.compress(data,1)
    return compressed if len(compressed)<len(data)*0.875 else raw

def decode_observations(raw):
    if isinstance(raw,bytes) and raw.startswith(PREFIX):raw=zlib.decompress(raw[len(PREFIX):])
    return json.loads(raw)
