#!/usr/bin/env python3
"""Offline verification of version-pinned scientific input bytes."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
def main():
    n=0
    for item in json.loads((ROOT/'vendor/MANIFEST.json').read_text()):
        b=(ROOT/item['path']).read_bytes()
        assert hashlib.sha256(b).hexdigest()==item['sha256'],item['path']
        assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==item['git_blob_sha1'],item['path']
        n+=1
    for item in json.loads((ROOT/'data/tzdb/manifest.json').read_text()):
        p=ROOT/'data/tzdb'/item['version']/item['zone']
        assert hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256'],str(p)
        n+=1
    print(f'PASS: {n} pinned source/data files')
if __name__=='__main__':main()
