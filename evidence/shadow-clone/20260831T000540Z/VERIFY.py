#!/usr/bin/env python3
import hashlib,json,pathlib
p=pathlib.Path(__file__).parent
r=json.loads((p/'SHADOW_CLONE_DEPLOYMENT_RECEIPT.json').read_text())
claimed=r.pop('receipt_sha256')
raw=json.dumps(r,sort_keys=True,separators=(',',':'),default=str).encode()
actual=hashlib.sha256(raw).hexdigest()
assert actual==claimed,(actual,claimed)
print('PERMIT: Shadow Clone deployment receipt identity verified')
