#!/usr/bin/env python3
"""
Targeted patches to specific generated functions in RecompiledFuncs, needed
to get past crashes caused by game state that isn't correctly populated yet
(root cause not fully understood -- see the "level/room data not loaded"
notes in the session's plan document). Unlike fix_unclosed_funcs.py/
fix_undefined_labels.py (which fix N64Recomp's own translation gaps), these
are workarounds for real, not-yet-understood data problems, so they're kept
separate and applied AFTER those two scripts and after
fix_ra_preserving_returns.py.

Run this after every regeneration of RecompiledFuncs (fresh N64Recomp CLI
run + the three fixup scripts) to reapply them. Each patch is idempotent
(skipped with a warning if the expected original text isn't found, e.g.
because N64Recomp's output changed).
"""
import os

PATCHES = [
    {
        "file": "funcs_42.c",
        "desc": "func_15001A08: osRomBase-area read returns garbage (0xFF7B0000) through a path that bypasses recomp_mem_addr -- root cause not found. Hardcode the value this code actually needs.",
        "old": """L_15001A60:
    // 0x15001A60: lw          $t0, 0x308($t0)
    ctx->r8 = MEM_W(ctx->r8, 0X308);""",
        "new": """L_15001A60:
    // 0x15001A60: lw          $t0, 0x308($t0)
    // [patch] This reads a value at 0x80000308 that this runtime never
    // correctly populates (something writes 0xFF7B0000 there through a
    // path that bypasses recomp_mem_addr -- confirmed deterministic across
    // runs with a watchpoint, root cause not yet found). The following
    // code ORs this against cart-domain address constants expecting an
    // osRomBase-shaped value (0xB0000000), so hardcode that directly
    // rather than reading corrupted memory.
    ctx->r8 = 0xB0000000;""",
    },
    {
        "file": "funcs_42.c",
        "desc": "func_15002248: skip a table-building loop that reads uninitialized list entries (forces the function's own pre-existing 'nothing to do' early exit).",
        "old": """    // 0x15002324: slti        $at, $t7, 0x2
    ctx->r1 = SIGNED(ctx->r15) < 0X2 ? 1 : 0;
    // 0x15002328: bne         $at, $zero, L_15002520
    if (ctx->r1 != 0) {""",
        "new": """    // 0x15002324: slti        $at, $t7, 0x2
    ctx->r1 = SIGNED(ctx->r15) < 0X2 ? 1 : 0;
    // 0x15002328: bne         $at, $zero, L_15002520
    // [patch] Force this function's existing "not enough entries, skip the
    // table-building loop" path. The table this loop reads is populated
    // with garbage/tiny values (root cause not found -- see session notes
    // on the func_15001A08/osRomBase investigation, likely related), so
    // treat it the same as the legitimate "nothing to do" case rather than
    // dereferencing bad data.
    if (1) {""",
    },
    {
        "file": "funcs_117.c",
        "desc": "func_15002008: same as func_15002248 above (apparent sibling function, identical pattern).",
        "old": """    // 0x15002080: blez        $s4, L_1500220C
    if (SIGNED(ctx->r20) <= 0) {""",
        "new": """    // 0x15002080: blez        $s4, L_1500220C
    // [patch] Same underlying garbage-table issue as func_15002248 (its
    // apparent sibling function) -- force the existing "nothing to
    // process" early-exit path instead of dereferencing bad table data.
    if (1) {""",
    },
    # func_150A3A70 used to be force-disabled here (its real body scans a
    # variable-length record chain that crashed on a wild pointer a few
    # dozen iterations in). Re-enabled: diagnostic logging confirmed the
    # gating flag (byte at 0x800DBE62, set by func_150038A0) genuinely
    # reads 1 throughout a normal run -- this subsystem is meant to be
    # active. The "wild pointer crash" no longer reproduces now that
    # address translation is hardened (TO_PTR routes through the software
    # TLB, recomp_mem_addr uses the masked phys value, out-of-range reads
    # land on a safe scratch page instead of a guard-region fault) --
    # verified stable (no crash) over multiple runs. L_150A4A94 (the
    # flag-off target) is outside N64Recomp's detected boundary for this
    # function, a decomp symbol-boundary gap unrelated to this patch, and
    # is already handled generically by fix_undefined_labels.py.
    {
        "file": "funcs_118.c",
        "desc": "static_5_150A49F4: companion patch to func_150A3A70 above (shares its labels -- same root cause).",
        "old": """RECOMP_FUNC void static_5_150A49F4(uint8_t* rdram, recomp_context* ctx) {
    uint64_t hi = 0, lo = 0, result = 0;
    int c1cs = 0;
L_150A3BAC:
    // 0x150A49F4: sll         $t0, $a0, 2""",
        "new": """RECOMP_FUNC void static_5_150A49F4(uint8_t* rdram, recomp_context* ctx) {
    uint64_t hi = 0, lo = 0, result = 0;
    int c1cs = 0;
    // [patch] This shares labels (L_150A3BAC, L_150A3F5C) with
    // func_150A3A70 -- both are fragments of the same real coroutine-style
    // routine that N64Recomp's boundary detection split apart, and the
    // underlying data it reads isn't populated by anything traced so far
    // (crashes on a wild read otherwise). Same call as func_150A3A70's
    // patch: no-op until this subsystem is understood.
    return;
L_150A3BAC:
    // 0x150A49F4: sll         $t0, $a0, 2""",
    },
    {
        "file": "funcs_114.c",
        "desc": "func_1510E950: guard an unbounded list-walk dereference (part 1/3 -- the per-entry read).",
        "old": """L_1510EA9C:
    // 0x1510EA9C: lw          $t6, 0x90($sp)
    ctx->r14 = MEM_W(ctx->r29, 0X90);
    // 0x1510EAA0: addiu       $at, $zero, 0x1
    ctx->r1 = ADD32(0, 0X1);
    // 0x1510EAA4: lbu         $t7, 0x0($t6)
    ctx->r15 = MEM_BU(ctx->r14, 0X0);""",
        "new": """L_1510EA9C:
    // 0x1510EA9C: lw          $t6, 0x90($sp)
    ctx->r14 = MEM_W(ctx->r29, 0X90);
    // 0x1510EAA0: addiu       $at, $zero, 0x1
    ctx->r1 = ADD32(0, 0X1);
    // 0x1510EAA4: lbu         $t7, 0x0($t6)
    // [patch] Same underlying garbage-table issue as func_15002248/
    // func_15002008 (a list this code walks isn't populated correctly
    // yet). The 0x108 count patch above doesn't cover every path that
    // reaches this loop, so also guard the dereference itself: accept
    // only addresses that land within our actual RDRAM buffer.
    ctx->r15 = (((uint32_t)ctx->r14 - 0x80000000u) < 0x20000000u) ? MEM_BU(ctx->r14, 0X0) : 3;""",
    },
    # func_1510E950 part 2/3 (forcing the loop's iteration count to 0) used
    # to be here. Re-enabling func_150A3A70's real logic revealed why: this
    # loop is fed by func_150A3A70 (call chain func_10001194 -> func_15007830
    # -> func_15007B3C -> func_150045C4 -> func_1510E7A4 -> func_1510E950 ->
    # func_150A3A70 -> recomp_cart_domain_ptr, observed live), which was the
    # thing actually populating the list this loop walks -- with it disabled,
    # the list genuinely was empty/garbage, and zeroing the count was masking
    # that instead of fixing it. Removed now that the real producer is back;
    # the part 1/3 dereference guard and part 3/3 iteration cap below stay as
    # safety nets regardless of whether the count is ever wrong again.
    {
        "file": "funcs_114.c",
        "desc": "func_1510E950: declare a shadow loop counter immune to MIPS register clobbering (part 0/3, at function entry).",
        "old": """RECOMP_FUNC void func_1510E950(uint8_t* rdram, recomp_context* ctx) {
    uint64_t hi = 0, lo = 0, result = 0;
    int c1cs = 0;
    // 0x1510E950: addiu       $sp, $sp, -0x148""",
        "new": """RECOMP_FUNC void func_1510E950(uint8_t* rdram, recomp_context* ctx) {
    uint64_t hi = 0, lo = 0, result = 0;
    int c1cs = 0;
    // [patch] The L_1510EA9C list-walk loop below counts iterations in
    // $s3 (ctx->r19), a callee-saved register -- but one of the calls made
    // per iteration eventually reaches func_150A3A70's coroutine-resume
    // path (L_150A3F5C), which restores $s0-$s7/$fp/$gp/$ra from its own
    // saved state as part of a real, intentional suspend/resume mechanism
    // unrelated to this function's use of $s3 as a plain loop counter.
    // That clobbers ctx->r19 out from under this loop the moment the real
    // per-entry count (now correctly non-zero after func_150A3A70 was
    // re-enabled) exceeds 0, so the loop never recognizes it reached its
    // real, small target and only stops via the iteration-cap safety net
    // below. A shadow counter that plain C++ scope rules keep safe from
    // whatever the recompiled callee does to MIPS registers sidesteps the
    // register-sharing conflict without needing to change the coroutine's
    // own (real, intentional) register semantics.
    uint32_t list_walk_shadow_counter = 0;
    // 0x1510E950: addiu       $sp, $sp, -0x148""",
    },
    {
        "file": "funcs_114.c",
        "desc": "func_1510E950: reset the shadow loop counter alongside $s3 (part 0.5/3, at the loop's entry point).",
        "old": """    // 0x1510EA34: or          $s3, $zero, $zero
    ctx->r19 = 0 | 0;""",
        "new": """    // 0x1510EA34: or          $s3, $zero, $zero
    ctx->r19 = 0 | 0;
    list_walk_shadow_counter = 0;""",
    },
    {
        "file": "funcs_114.c",
        "desc": "func_1510E950: guard an unbounded list-walk dereference (part 3/3 -- use the shadow counter for the exit check, plus a hard iteration cap as a safety net for paths the count patch doesn't cover).",
        "old": """    // 0x1510F3DC: addiu       $s3, $s3, 0x1
    ctx->r19 = ADD32(ctx->r19, 0X1);
    // 0x1510F3E0: addiu       $t1, $t2, 0x1
    ctx->r9 = ADD32(ctx->r10, 0X1);
    // 0x1510F3E4: bne         $s3, $t9, L_1510EA9C
    if (ctx->r19 != ctx->r25) {""",
        "new": """    // 0x1510F3DC: addiu       $s3, $s3, 0x1
    ctx->r19 = ADD32(ctx->r19, 0X1);
    list_walk_shadow_counter++;
    // 0x1510F3E0: addiu       $t1, $t2, 0x1
    ctx->r9 = ADD32(ctx->r10, 0X1);
    // 0x1510F3E4: bne         $s3, $t9, L_1510EA9C
    // [patch] Two independent issues on this exit check:
    // 1. $s3 (ctx->r19) is a callee-saved register that a coroutine
    //    reached from within this loop's body (func_150A3A70's resume
    //    path) legitimately restores as part of its own state -- see the
    //    function-entry comment. Use the shadow counter instead, which
    //    plain C++ scoping keeps safe from whatever the recompiled callee
    //    does to MIPS registers.
    // 2. The 0x108 count patch upstream doesn't cover every path into
    //    this loop, and when it's reached with a stale/garbage count this
    //    effectively never terminates. Cap iterations as a hard safety
    //    net regardless of why the natural exit condition might not fire.
    if (list_walk_shadow_counter != ctx->r25 && list_walk_shadow_counter < 100000) {""",
    },
]

def main():
    applied = 0
    skipped = 0
    for patch in PATCHES:
        path = os.path.join("RecompiledFuncs", patch["file"])
        if not os.path.exists(path):
            print(f"SKIP (file not found): {path}")
            skipped += 1
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()
        if patch["new"] in text:
            print(f"already applied: {patch['file']}: {patch['desc'][:60]}...")
            applied += 1
            continue
        if patch["old"] not in text:
            print(f"SKIP (original text not found, N64Recomp output may have changed): {patch['file']}: {patch['desc'][:60]}...")
            skipped += 1
            continue
        text = text.replace(patch["old"], patch["new"], 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"applied: {patch['file']}: {patch['desc'][:60]}...")
        applied += 1
    print(f"\nTotal: {applied} applied/already-applied, {skipped} skipped")

if __name__ == "__main__":
    main()
