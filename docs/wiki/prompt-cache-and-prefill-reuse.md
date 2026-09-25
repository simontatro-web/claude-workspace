# prompt-cache-and-prefill-reuse

> Copied verbatim from Cowork (melange-wiki) on Sep 25 2026 (page last updated Sep 23, 2026).
> Cowork-only links kept as page names.
>
> Summary: Sep 23 2026 source-verified research into llama.cpp prompt caching, KV cache reuse, context checkpoints and slot save/restore on jarvis-1 — why Jack's hybrid Qwen 27B re-processes whole prompts, which flags actually help, and the mmproj-vs-cache-reuse tradeoff. Read before tuning llama-server, before building any harness, and before adding vision to a slot.

Companions: llama-server-live-unit (the live flags), jarvis-speed-tuning, agent-harnesses (why this multiplies harness value), system-performance-levers. Everything in the first three sections was read by me directly from llama.cpp master source on Sep 23 2026, then re-verified line by line by an independent agent: 10/10, 100%.

## *** WHY THIS MATTERS MORE THAN ALMOST ANYTHING ELSE ON THIS BOX ***

Prefill is the binding constraint on every model here. At the MEASURED 145 t/s prompt speed, a 10,000-token prefix costs 69 seconds to ingest. A harness making 30 calls that each re-process that prefix burns ~35 minutes of pure prefill per problem before a single useful token. Prompt caching is what removes it. *** AND THERE IS A REPORTED WORST CASE ON EXACTLY HIS MODEL CLASS: llama.cpp issue #20225, "Qwen 3.5 Full prompt re-processing on every conversation turn", reports ~8 MINUTES PER TURN on a 27B hybrid. Thirty harness calls at that rate is four hours. ***

## THE FLAGS AND THEIR DEFAULTS — all verified against tools/server/README.md on master

| flag | default | what it does | | --cache-prompt / --no-cache-prompt | enabled | basic prompt caching | | --cache-reuse N | *** 0, i.e. OFF *** | "min chunk size to attempt reusing from the cache via KV shifting" | | --context-shift | disabled | context shift on infinite generation | | -ctxcp, --ctx-checkpoints | 32 | max context checkpoints per slot | | -cms, --checkpoint-min-step | 8192 | min token spacing between checkpoints (0 = no minimum) | | -cram, --cache-ram | 8192 MiB | max cache size (-1 no limit, 0 disable) | | --slot-save-path PATH | disabled | enables the /slots save/restore/erase endpoints | | --reasoning-preserve | enabled | keep reasoning trace in full history | *** --checkpoint-every-n-tokens NO LONGER EXISTS. *** Removed; the surviving flags are -ctxcp and -cms in common/arg.cpp.

## *** CORRECTION TO model-pull-and-flags: -lv 4 IS REQUIRED. THE NOTE SAYING IT IS UNNECESSARY IS WRONG. ***

That file's "Correction 3" states the re-processing message is a LOG_WRN at level 2 and therefore prints at default verbosity. Traced through the actual source, it is not:

- server-context.cpp:3380 emits it with SLT_TRC
- server-common.h:27 maps SLT_TRC -> LOG_TRC
- common/log.h:121 gives LOG_TRC the verbosity LOG_LEVEL_TRACE, and :24-28 define TRACE = 4, INFO = 3, WARN = 2
- common/log.cpp:30 sets the default threshold to LOG_DEFAULT_LLAMA = INFO = 3, and the gate is if (verbosity <= threshold) 4 > 3, so the message is SUPPRESSED by default. Run with -lv 4 or you will never see it. This matters because the failure is otherwise completely silent: the server just quietly re-processes everything. THE CURRENT MESSAGE TEXT also changed and now names the cause, so an old grep string will not match: forcing full prompt re-processing due to lack of cache data (likely due to SWA or hybrid/recurrent memory, see https://github.com/ggml-org/llama.cpp/pull/13194#issuecomment-2868343055)

## *** THE BIG TRADEOFF NOBODY KNEW: LOADING mmproj DISABLES --cache-reuse ENTIRELY. ***

server-context.cpp:1179-1182, in the multimodal init block:

cpp

```bash
if (params_base.n_cache_reuse) {
    params_base.n_cache_reuse = 0;
    SRV_WRN("%s\n", "cache_reuse is not supported by multimodal, it will be disabled");
```

}

The same block also force-disables ctx_shift (:1174-1177). And the per-request gate at :3229-3231 is:

cpp

```bash
const bool can_cache_reuse =
    llama_memory_can_shift(llama_get_memory(ctx_tgt)) &&
    !slot.prompt.tokens.has_mtmd;
```

*** THIS DIRECTLY CONFLICTS WITH system-performance-levers LEVER #2, which recommends adding the mmproj to the 27B judge as the "highest value" multimodal choice. *** Vision on that slot costs cache reuse on every agentic turn. For a harness or any repeated-prefix workload, cache reuse is almost certainly worth more than vision. Decide per slot, and do not take both on the same server process — run vision as a separate on-demand slot instead.

## GOOD NEWS: THE HYBRID ARCHITECTURE ITSELF DOES NOT BLOCK SHIFTING

- src/llama-memory-recurrent.cpp:716 — get_can_shift() returns true ("shifting the pos is trivial for recurrent models")
- src/llama-memory-hybrid.cpp:133 — get_can_shift() returns mem_attn->get_can_shift(), i.e. it delegates to the ATTENTION half So --cache-reuse should work on Jack's 27B provided no mmproj is loaded. The full-reprocessing problem is a SEPARATE mechanism: recurrent state cannot be partially rolled back, so checkpoints are the only rewind path, and when the checkpoint-validity test rejects them the server resets to zero. THE FREE DIAGNOSTIC, and it prints at DEFAULT verbosity (unlike the TRC message): set --cache-reuse 256 and watch for SLT_WRN "cache reuse is not supported - ignoring n_cache_reuse = %d" (:3233-3235, WARN = 2). Silence means it is working.

## *** THE HYBRID CHECKPOINT BUG IS OPEN UPSTREAM, AND MASTER SHIPS A WORKAROUND, NOT A FIX ***

The source carries an acknowledged-broken marker: [TAG_CHECKPOINTS_FIX_POS_MIN] at server-context.cpp:2358-2361, "TODO: here we incorrectly deterimne that the saved checkpoint data covers the [pos_min, pos_max] range — this is not true for SWA models", and the cur.pos_max > pos_next test at :3357-3360 is explicitly labelled a workaround for it. OPEN ISSUES ON HIS EXACT MODEL FAMILY: #24055 (checkpoints always invalidated on hybrid/recurrent — on hybrids pos_min effectively equals full sequence length so the validity check always fails), #20225 (Qwen 3.5, ~8 min per turn on a 27B hybrid), #22746 (Qwen 3.6 27B, same log line), #18497 ("cache-reuse not effective in qwen3-next"), #19394 (Qwen3-Coder-Next), #22384 (DeltaNet/Mamba checkpoint restore), and an ik_llama mirror at ikawrakow#1762. Partial fixes merged (#24176 interval checkpointing, #24411 skip-instead-of-erase, #25592 record pos_min = pos_max for hybrid); the root-cause PR #24797 was unreviewed. MITIGATIONS, cheapest first: stabilise the prompt prefix and stop mutating conversation history between turns; keep --reasoning-preserve on; lower -cms below 8192 if agent turns are shorter than that, which creates more checkpoints at real memory cost; budget tokens pre-flight to avoid slot eviction; and, highest leverage, use a FULL-ATTENTION model for the agentic slot where the KV cache can simply be truncated. --swa-full does NOT help: Qwen 3.5/3.6 builds log n_swa = 0, so SWA is not the trigger — the hybrid recurrent component is.

## CHECKPOINT MEMORY COST — ARCHITECTURE-DEPENDENT BY ~9x, AND IT CAN OOM A CARD

No official figure; the server prints the real size at runtime (server-context.cpp:2369-2370, "created context checkpoint %d of %d (... size = %.3f MiB)"). Published data points (llama.cpp discussion #21480), both at q8_0 KV over 8192 tokens: ~63 MiB per checkpoint for Qwen 3 35B-A3B vs ~531 MiB for Gemma 4 26B-A4B. Qwen's recurrent/efficient attention is the reason it is 9x cheaper. With the default -ctxcp 32, a full list is ~2 GB in the Qwen case. Issues #23371 and #23181 report checkpoint-driven VRAM growth and OOM. Treat 50-500 MiB per checkpoint as the observed range and bound it with -cram and -ctxcp rather than assuming.

## --slot-save-path: WHAT IT REALLY GIVES, AND THE TRAP FOR HYBRID MODELS

Registers POST /slots/{id_slot} (server.cpp:291) with ?action=save|restore|erase, each taking a JSON filename written under the given directory. Without the flag it returns "This server does not support slots action. Start it with --slot-save-path". IT DOES SURVIVE A RESTART: save calls llama_state_seq_save_file, restore calls llama_state_seq_load_file; the file carries LLAMA_STATE_SEQ_MAGIC + version, the token list and the sequence state. *** TWO TRAPS. *** First, there is NO model-identity or context-config hash in the file — it restores cleanly into a server running a different model or different context settings and then silently misbehaves. Second, and decisive here: issue #25913, open — the save file contains tokens and KV cells but NOT the context checkpoints, and restore calls slot->prompt.clear(). On hybrid/recurrent models a restored slot reports a healthy n_restored and then re-processes everything anyway. SO: do not build the harness around slot save/restore for the 27B yet. Test it and read the actual time-to-first-token, do not trust n_restored.

## WHAT TO ACTUALLY DO, IN ORDER

- Run with -lv 4 once and watch a multi-turn conversation. If the re-processing line appears every turn, this is costing him minutes per turn and everything below matters. If it does not, the rest is optional tuning.
- Add --cache-reuse 256 and confirm no "not supported" warning at default verbosity.
- Decide mmproj vs cache reuse per slot. Do not run both on one process.
- Measure time-to-first-token across a growing conversation. Flat TTFT across turns is the broken signature; it should fall after the first turn.
- Only then tune -cms, -ctxcp and -cram against the checkpoint sizes the server logs. ENGINE ESCAPE HATCH IF IT STAYS BROKEN: vLLM (v0.26.0) has hybrid KV support with Mamba caching marked experimental, and SGLang (v0.5.16) has dedicated int8-compressed radix caches per recurrent state. Both are gated on Volta support, which is the separate question in v100-speed-frontier.
