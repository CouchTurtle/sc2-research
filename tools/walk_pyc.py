#!/usr/bin/env python3
"""Walk hardwareupdater.pyc bytecode and list all functions with signatures + dis."""
import marshal, dis, sys, io

with open('/tmp/hu_extracted/hardwareupdater.py', 'rb') as f:
    top = marshal.loads(f.read())

# Find all nested code objects (functions, methods, classes)
def collect(co, path="", out=None):
    if out is None: out = []
    for const in co.co_consts:
        if hasattr(const, 'co_consts'):
            full_path = f"{path}.{const.co_name}" if path else const.co_name
            out.append((full_path, const))
            collect(const, full_path, out)
    return out

funcs = collect(top, "<module>")
funcs.insert(0, ("<module>", top))

print(f"=== Total code objects: {len(funcs)} ===\n")

# List with key info
for name, co in funcs:
    args = co.co_varnames[: co.co_argcount]
    sig = ', '.join(args)
    # First docstring if any (first const if string and large)
    doc = ""
    if co.co_consts and isinstance(co.co_consts[0], str) and len(co.co_consts[0]) > 5:
        doc = co.co_consts[0][:80].replace("\n", " ")
    n_consts = sum(1 for c in co.co_consts if isinstance(c, (str, int, bytes)))
    print(f"  {name:<60s}({sig})   consts={n_consts}")
    if doc:
        print(f"    doc: {doc}")

print("\n=== Interesting consts per function ===")
for name, co in funcs:
    interesting = []
    for c in co.co_consts:
        if isinstance(c, str) and len(c) > 4 and not c.startswith('<') and '\n' not in c:
            if any(k.lower() in c.lower() for k in ['fw_', 'message_', 'serial', 'hidapi',
                                                     'magic', 'header', 'read', 'write',
                                                     'usb', 'esb', 'ble', 'sof', 'eof']):
                interesting.append(c)
        elif isinstance(c, int) and c > 1000:
            interesting.append(f"int:{c} (0x{c:x})")
        elif isinstance(c, bytes) and len(c) > 0:
            interesting.append(f"bytes:{c!r}")
    if interesting:
        print(f"\n  {name}:")
        for c in interesting[:15]:
            print(f"    {c}")
