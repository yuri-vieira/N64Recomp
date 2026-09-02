#!/usr/bin/env python3
"""
N64Recomp translates `jal` into a direct C++ function call and never writes
anything to ctx->r31 (the MIPS $ra register) to do it -- it doesn't need to,
since the callee's own `jr $ra` return is *also* translated mechanically
into a plain C++ `return;`, so control flow relies on the native call stack
rather than the value of $ra at all.

That breaks down for hand-written functions that explicitly preserve $ra in
a temp register at entry (`move $tN, $ra`, i.e. `ctx->rN = ctx->r31 | 0;`
here) so it survives further nested calls that would otherwise clobber
$ra, then return later via `jr $tN` instead of `jr $ra` directly. N64Recomp
has no way to know that register is semantically "the return address" (it
just sees an indirect jump through an arbitrary register), so it emits a
LOOKUP_FUNC indirect-call attempt -- but ctx->r31 was never actually
populated by the calls in between (per the above), so the "preserved"
value the function saved at entry is garbage/zero, and the lookup fails.

This finds functions matching that exact pattern -- a register assigned
verbatim from ctx->r31 at entry and never reassigned afterward, later used
in a LOOKUP_FUNC call -- and replaces the bogus indirect call (plus its
goto/label wrapper) with a plain return, matching what the code actually
means.
"""
import glob
import re

FUNC_START_RE = re.compile(r'^RECOMP_FUNC void (\S+)\(', re.MULTILINE)
SAVE_RA_RE = re.compile(r'ctx->r(\d+) = ctx->r31 \| 0;')

def fix_function_body(body):
    fixed = 0
    for reg in {m.group(1) for m in SAVE_RA_RE.finditer(body)}:
        reassign_re = re.compile(r'ctx->r' + reg + r'\s*=')
        if len(reassign_re.findall(body)) != 1:
            # Reassigned elsewhere -- no longer just a preserved $ra, leave it alone.
            continue

        # Pattern A: a normal-looking indirect call site, wrapped in a
        # goto/label pair to skip the duplicated delay-slot instruction --
        # this is what a genuine function-pointer call would also look
        # like, so replace the whole [call ... label:] span with a return.
        call_re = re.compile(
            r'    LOOKUP_FUNC\(ctx->r' + reg + r'\)\(rdram, ctx\);\n        goto (\w+);\n'
        )
        while True:
            call_m = call_re.search(body)
            if call_m is None:
                break
            label = call_m.group(1)
            label_def_re = re.compile(r'^    ' + re.escape(label) + r':\n', re.MULTILINE)
            label_m = label_def_re.search(body, call_m.end())
            if label_m is None:
                break
            body = body[:call_m.start()] + "    return;\n" + body[label_m.end():]
            fixed += 1

        # Pattern B: an indirect *tail* call -- LOOKUP_FUNC(...) immediately
        # followed by a plain return, no goto/label wrapper (this is what
        # N64Recomp emits for "jr $reg" when $reg isn't $ra and isn't a
        # jump table). Here the call itself is the bogus part; the return
        # right after it is already exactly correct, so just drop the call.
        tailcall_re = re.compile(
            r'    LOOKUP_FUNC\(ctx->r' + reg + r'\)\(rdram, ctx\);\n(    return;\n)'
        )
        new_body, n = tailcall_re.subn(r'\1', body)
        if n:
            body = new_body
            fixed += n
    return body, fixed

def fix_file(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()

    starts = [m.start() for m in FUNC_START_RE.finditer(text)]
    if not starts:
        return 0
    starts.append(len(text))

    out = [text[:starts[0]]]
    total_fixed = 0
    for idx in range(len(starts) - 1):
        body = text[starts[idx]:starts[idx + 1]]
        body, fixed = fix_function_body(body)
        total_fixed += fixed
        out.append(body)

    if total_fixed:
        with open(path, "w", encoding="utf-8") as f:
            f.write(''.join(out))
    return total_fixed

def main():
    total = 0
    files_fixed = 0
    for path in sorted(glob.glob("RecompiledFuncs/funcs_*.c")):
        n = fix_file(path)
        if n:
            total += n
            files_fixed += 1
            print(f"{path}: fixed {n} $ra-preserving return(s)")
    print(f"Total: {total} fixed across {files_fixed} files")

if __name__ == "__main__":
    main()
