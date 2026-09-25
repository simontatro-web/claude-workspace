# jarvis-what-not-to-do

> Copied verbatim from Cowork (melange-wiki) on Sep 25 2026 (page last updated Sep 23, 2026).
> Cowork-only links kept as page names.
>
> Summary: The anti-pattern list for jarvis-1 — every action researched or measured that would damage, slow, or break the system, in one place. Jack asked Sep 23 2026 to know what NOT to do, not just what to do. Read before any driver update, filesystem decision, destructive command, hardware purchase or flag change.

Each rule links to the file holding the evidence. Ordered by how expensive the mistake is, worst first. *** VERIFICATION STATUS, STATED HONESTLY: rules 2-17 and 19-23 carry evidence already blind-verified in their source files. Rules 1 and 18 (the NTFS dirty-flag / Fast Startup / ntfs3-vs-ntfs-3g findings) are NEW as of Sep 23 2026 and their blind-verification pass was CUT OFF by a session limit before delivering a report. They rest on the ntfsheal project documentation, the Arch wiki's NTFS page and a driver benchmark comparison — good secondary sources, not primary kernel documentation. TREAT RULE 1 AS SOUND PRACTICE REGARDLESS (safe-eject costs nothing), BUT RE-VERIFY THE ntfs3-vs-ntfs-3g PERFORMANCE NUMBERS AND THE EXACT DIRTY-FLAG BEHAVIOUR BEFORE RELYING ON THEM FOR A DECISION. The NVIDIA driver-branch question in rule 2 is explicitly UNRESOLVED and is flagged as such in the rule itself. ***

## TIER 1 — MISTAKES THAT LOSE DATA OR BRICK THE STACK

*** 1. DO NOT YANK THE 4TB DRIVE OUT OF WINDOWS. EJECT IT PROPERLY. *** [NEW Sep 23 2026]
The drive is NTFS and holds ~1.5 TB that cost a 12-hour download. An NTFS volume disconnected unsafely sets a DIRTY FLAG, and Linux then refuses to mount it read-write — the error is the misleading `wrong fs type, bad option, bad superblock`, which looks like corruption and usually is not. Windows Fast Startup is the second trap: it writes a hiberfil.sys hibernation image, leaving the volume in a hibernated state that Linux will not mount read-write even after a "shutdown". RULES: use Safely Remove Hardware / eject before unplugging; fully shut down rather than hibernate, and turn Fast Startup OFF on that laptop. If it does come up dirty: `sudo ntfsfix -d /dev/sdX1` (ntfs-3g package) clears the flag, or mount read-only first to get the data off. Never run Windows chkdsk and a Linux write tool against it in the same session.

2. DO NOT UPDATE THE NVIDIA DRIVER. PIN IT.
Volta is at the end of its driver life. NVIDIA's own R580 data-center release notes still list NVIDIA V100 (Volta) as supported, while consumer-side reporting says the 580/590 branches end Maxwell/Pascal/Volta support. Those two disagree and I could not fully reconcile them — the data-center and GeForce branches are numbered and retired differently. The action is the same either way: an unattended driver upgrade is the most likely single way to break the CUDA stack on this box. `apt-mark hold` the driver packages and read the release notes for V100 before any deliberate change. Same rule one layer up: do not install "latest PyTorch" — 2.11 dropped sm_70 from its CUDA 12.8/13.0 binaries; the cu126 wheel is the one that works and must be pinned (video-generation-v100). And CUDA toolkit must stay 12.9 or older (local-model-landscape).

3. DO NOT pkill BY NAME, EVER.
A recurring incident pattern on this box: name-matching kills the production llama-server. The supervisor was deliberately built to only SIGTERM PIDs it started. Full history in jarvis-incidents. Kill by PID you recorded, or by `systemctl stop <unit>`.

4. DO NOT RUN MULTI-HOUR JOBS IN tmux.
A tmux-hosted download died and lost 242 GiB with no forensic trail — `tmux ls` came back "no server running" and the log was frozen at 0%. Use a systemd unit with `loginctl enable-linger`, logging with timestamps. glm-5.3-download

5. DO NOT mv LARGE MODEL FILES BETWEEN FILESYSTEMS.
mv across filesystems is copy-then-unlink; an interruption mid-467 GB leaves you guessing what survived. `rsync -av --partial`, verify sha256, then delete. And verify against HuggingFace's published sha256, not just source-vs-destination. model-storage-plan

6. DO NOT SWITCH DOWNLOAD BACKENDS MID-FILE.
Xet is chunk-based and deduplicating; the classic HTTP resumer appends from the existing file's SIZE. Switching mid-download can produce a silently corrupt 46 GB shard discovered only at load time. If a restart is needed, restart with the SAME backend. glm-5.3-download

7. DO NOT LET A DOWNLOAD'S TOTAL SHRINK UNNOTICED.
Xet once deleted 176 GiB of its own partials and progress went 79% → 11.8% with nobody watching. The health metric is bytes-on-disk growth vs bytes-sent over ≥10 minutes, plus a check that the total is not DECREASING. The pull scripts on the drive already alarm on this. glm-5.3-download

## TIER 2 — CHOICES THAT SILENTLY COST PERFORMANCE

8. DO NOT LOAD mmproj ON THE SAME SERVER PROCESS THAT NEEDS --cache-reuse.
Source-verified: the multimodal init block sets n_cache_reuse = 0 and also force-disables context shift. Vision on the agentic slot costs prompt-cache reuse on every turn. Run vision as a separate on-demand slot. prompt-cache-and-prefill-reuse

9. DO NOT ASSUME PROMPT CACHING IS WORKING. THE FAILURE IS SILENT.
The "forcing full prompt re-processing" line is emitted at TRACE (4) against a default threshold of INFO (3), so it never prints unless you pass -lv 4. On his hybrid Qwen class there are open upstream bugs reporting ~8 minutes per turn. prompt-cache-and-prefill-reuse

10. DO NOT PIN A CPU-RESIDENT MODEL TO ONE SOCKET JUST BECAUSE IT FITS.
Measured on this box: dual-socket interleaved STREAM Triad is 2x socket-local. An earlier single-threaded mbw result said the opposite and was wrong for multi-threaded decode. Interleave. system-performance-levers

11. DO NOT RUN 72 THREADS.
Measured: 36 threads socket-local was slightly slower than 18. Hyperthreading adds contention and no bandwidth for decode. Physical cores only, -t 36 total. (Prefill may differ — that is the one untested experiment, not an assumption.) power-thermals-and-tuning

12. DO NOT OVER-DRAFT SPECULATIVE DECODING.
Swept twice on this box: n_max peaks at 5 and is a monotonic loss past it (n=8 costs 33% on predictable work). Ignore "MoEs require long drafts" advice, which belongs to a different flag. jarvis-speed-tuning, model-pull-and-flags

13. DO NOT TAKE fp8 OR nvfp4 CHECKPOINTS. EVER.
Volta has no FP8 unit. This rules out umt5_xxl_fp8_e4m3fn_scaled, qwen_2.5_vl_7b_fp8_scaled, z_image_turbo_nvfp4 and every "_fp8" file, however attractive the size. A verifying agent recommended one of these; it was wrong. fast-house-extras

14. DO NOT ENABLE FLASH ATTENTION FOR LTX ON VOLTA.
Issue #36 on ai-bond/flash-attention-v100: LTX-2.3 on a V100-16GB throws NaN/Inf, and generation succeeds with flash attention disabled. Treat FA as a known NaN source here, not a free speed win. video-generation-v100

15. DO NOT TRUST LOW-BIT QUANTS FOR DIFFUSION ON VOLTA WITHOUT CHECKING FOR BLACK FRAMES.
Confirmed ggml/sd.cpp bug: all-black output on a V100 with Q4_0, root-caused to FP16 tensor-core accumulation. Prefer F16 where it fits, keep the VAE in FP32, and check the first render. video-generation-v100

16. DO NOT USE --mlock ON A MODEL THAT DOES NOT FIT RAM.
For a model that survives only by mmap paging (MiMo at ~498 GiB), mlock converts a graceful slowdown into an OOM kill. Pick by residency, not habit. model-storage-plan

17. DO NOT REQUEST A QUANTIZED V CACHE WITHOUT -fa.
llama.cpp hard-throws: `quantized V cache was requested, but this requires Flash Attention`. model-pull-and-flags

18. DO NOT MOUNT THE MODEL DRIVE WITH ntfs-3g IF ntfs3 IS AVAILABLE. [NEW Sep 23 2026]
ntfs-3g is FUSE and crosses the kernel/userspace boundary per operation; ntfs3 is the in-kernel driver (Linux 5.15+, so Ubuntu 24.04 has it) and is dramatically faster, especially on writes. Mount explicitly with `-t ntfs3` and confirm with `mount | grep`. *** NOTE A REAL CONFLICT WITH model-storage-plan: that plan specifies mkfs.ext4 and /mnt/hdd, i.e. it assumed an ext4 drive. The drive actually holds NTFS because it was filled from Windows. Reformatting is not possible without somewhere to put 1.5 TB. *** The workable resolution: keep NTFS, mount ntfs3, treat that drive as the COLD library, and promote hot models to the 990 PRO (ext4) — which is the tiering the storage plan already recommends, so nothing else changes.

## TIER 3 — PURCHASES AND CONFIGURATION TO AVOID

19. DO NOT BUY SMR DRIVES OR DRAM-LESS NVMe.
SMR rewrites overlapping tracks and collapses sustained writes. Micro Center labels SMR in its own titles. And a DRAM-less Inland TN320 died in three hours on this box; the same Silicon Motion XT family should be refused on principle. model-storage-plan, nvme-drive-failure

20. DO NOT TURN ECC OFF ON THE V100s. IT BUYS NOTHING.
MEASURED: usable VRAM stayed at 16,144 MiB per card with ECC disabled, and NVIDIA's Volta whitepaper says ECC is active "without a bandwidth or capacity penalty". An earlier note claiming ~1 GiB per card was wrong and is retracted. Turn it back on. system-performance-levers

21. DO NOT RUN A GPU RENDER CONCURRENTLY WITH A SUSTAINED TWO-CARD LLM LOAD.
15 A basement circuit. A trip mid-write on a single-drive box is the uncontrolled shutdown behind the whole NVMe failure saga. This is an uptime and data-integrity rule, not a power-cost rule — power cost is explicitly not a concern for Jack. power-thermals-and-tuning, jarvis-system-gaps

22. DO NOT PUT A DATABASE OR ANYTHING WRITE-CRITICAL ON THE USB DRIVE PATH.
Write-barrier/FUA semantics are bridge-dependent and several bridges are kernel-quirked BROKEN_FUA. A USB bus reset mid-write remounts read-only. Mount by UUID with `nofail`. Model files only. model-storage-plan

23. DO NOT GIVE THE UNCENSORED MODEL ACCESS TO THE SHELL TOOL SERVER OR THE SECRETS PATH.
The box runs an unrestricted shell tool server reachable over Tailscale (jarvis-run-host-commands) and will now also host an uncensored 27B. Those two must not meet. The secrets isolation rule is GAP 3 in jarvis-system-gaps; treat it as binding now that the model is actually arriving.

## THE META-RULE THIS SESSION KEEPS PROVING

A correction is a claim, not a verdict. Today a verification agent was right about one thing and wrong about two others, and an earlier stored "correction" about -lv 4 was itself wrong in the dangerous direction. Re-read the primary source before overwriting a stored fact, and prefer reading the actual code over reading about it.
