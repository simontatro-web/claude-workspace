# deep-research-optimization

> Copied verbatim from Cowork (melange-wiki) on Sep 25 2026 (page last updated Sep 23, 2026).
> Cowork-only links kept as page names.
>
> Summary: Sep 23 2026 research into how to make jarvis-1 do MASSIVE-depth deep research — the harness that already benchmarks on his exact model class, why SearXNG is no longer the answer, the search backends and their real prices, the 80% prefill saving from content extraction, and how to absorb huge amounts of source material without blowing context. Read before building or tuning the research pipeline.

Supersedes the deep-research planning in agent-harnesses ("search is the real blocker", SearXNG as the leading candidate). Companions: prompt-cache-and-prefill-reuse (the prefill work this depends on), jarvis-model-research (embedding/reranker), jarvis-orchestrator.

## *** FINDING 1: THE HARNESS ALREADY EXISTS AND IT IS BENCHMARKED ON HIS EXACT MODEL CLASS. ***

LearningCircuit/local-deep-research — built specifically for local/private deployment.

- *** IT SPEAKS llama-server DIRECTLY: the README lists llama.cpp via the OpenAI-compatible endpoint at http://localhost:8080/v1 as a first-class provider *** (alongside Ollama and LM Studio), and states it supports "any service speaking the OpenAI chat-completions API". Port 8080 is already Jack's production llama-server.
- BENCHMARKS, community-reported, on an RTX 3090: | model | SimpleQA | xbench-DeepSearch | | Qwen3.6-27B | 95.7% (287/300) | 77.0% (77/100) | | Qwen3.5-9B | 91.2% (182/200) | 59.0% | | gpt-oss-20B | 85.4% (295/346) | — | The 27B row is Jack's model class, and gpt-oss-20B is already on his download list, so he can reproduce the comparison himself.
- Search engines built in: arXiv, PubMed, Semantic Scholar, NASA ADS, Wikipedia, GitHub, Wayback, The Guardian, Elasticsearch, SearXNG, plus Tavily / SerpAPI / Brave, and local documents via LangChain retrievers.
- Caveats: accuracy figures are self-reported and configuration-specific; llm.model has no default and must be set; its MCP server has no authentication or rate limiting and is local-use only — do not expose it, especially given the shell tool server in jarvis-what-not-to-do rule 23. ALTERNATIVES CONSIDERED: langchain-ai/open_deep_research (0.4344 RACE on Deep Research Bench, most actively maintained, but benchmark ~1 yr old); assafelovic/gpt-researcher (vendor-claimed first place on DeepResearchGym, no independent corroboration); stanford-oval/storm (repo quiet ~10 months, produces outlines not finished reports). local-deep-research wins on one thing that matters more than benchmark rank: it was designed for exactly this hardware shape.

## *** FINDING 2: SearXNG IS NO LONGER A WORKING SEARCH BACKEND. THIS OVERTURNS THE PLAN IN agent-harnesses. ***

SearXNG's own maintainer discussion #5651, January 2026, on the state of the major engines: | engine | state | | Google | completely down | | Bing | returns irrelevant results | | Brave | rate-limited | | DuckDuckGo | CAPTCHA challenges | Maintainer, verbatim: "We have refrained from integrating real browsers so far because these solutions are too resource-intensive for a public server and the many small installations on devices such as Raspberry", while conceding "the ongoing problems with the major web search providers raise doubts as to whether we will be able to maintain this strategy in the future." A contributor demonstrated that Playwright-driven real-browser requests DO bypass the blocks, but session cookies expire fast and it is too heavy for public instances. *** THE INSIGHT THAT FOLLOWS, AND IT IS THE BEST NEWS IN THIS FILE: JACK ALREADY HAS THE THING SEARXNG REFUSES TO SHIP. *** His headed Chrome on Xvfb with a CDP bridge (agent-harnesses) is precisely the real-browser approach the maintainers say they cannot afford. His browser-tools server is worth more as a search backend than a SearXNG install would be. Do not spend an evening deploying SearXNG on the old assumption.

## *** FINDING 3: PAID SEARCH DISSOLVES THE BLOCKER FOR CENTS. THE CHEAPEST OPTION IS ~$0.30 PER 1,000 QUERIES. ***

| API | free tier | pay-as-you-go | returns full content? | | Serper | 2,500 free on signup | *** 5/mo in credits (~1,000 q) | $5 per 1,000 | snippets only | | Tavily | 1,000 credits/month, no card | $0.008/query = $8 per 1,000 | yes, extracted markdown | | Exa | ~1,000 trial credits | $7-15 per 1,000 | semantic relevance | | Firecrawl | 1,000 credits free | credit-based | yes | Latency: Brave fastest at ~669 ms; Perplexity Sonar slowest at ~11 s. *** DO THE ARITHMETIC FOR HIS ACTUAL VOLUME: a deep-research pass is 5-10 searches. One hundred full research passes is ~1,000 searches = 30 CENTS on Serper, and the first 2,500 are free. *** The "search is the real blocker" framing that has been on file since Sep 14 is solved by a signup and pocket change. Tavily's free 1,000/month with extraction included is also genuinely enough for a personal research system and needs no card. AND THE FREE ACADEMIC ENGINES ARE BETTER FOR HIS GOALS ANYWAY: arXiv, PubMed, Semantic Scholar and NASA ADS are unblocked, API-stable, free, and aimed straight at goals — biology/medicine, longevity, astrophysics, consciousness. Use them as the primary path and general web search as the fallback, not the reverse.

## *** FINDING 4: THE BIGGEST SPEED LEVER IN THE WHOLE PIPELINE IS CONTENT EXTRACTION. 80-82% FEWER TOKENS, FREE. ***

Measured on real pages: Cloudflare docs page 9,541 tokens raw HTML vs 1,678 tokens cleaned markdown = 82% reduction; a blog post 16,180 vs 3,150 = 80%. WHAT THAT IS WORTH ON JARVIS-1 AT THE MEASURED 145 t/s PREFILL: | 20-page research pass | tokens | prefill time | | raw HTML | ~190,800 | *** ~22 minutes *** | | extracted markdown | ~33,600 | *** ~3.9 minutes *** | An 18-minute saving per pass, for a 44-millisecond-per-page binary. Nothing else in this file comes close.

### THE EXTRACTOR TO USE, FROM A PROPER BENCHMARK (2,008 pages, 1,613 domains, 7 page types, 12 extractors — the Web Content Extraction Benchmark)

| system | F1 | speed | | *** rs-trafilatura *** | 0.859 | 44 ms/page | | MinerU-HTML (0.6B neural) | 0.827 | 1,570 ms | | Trafilatura (Python) | 0.791 | 94 ms | | dom-smoothie | 0.762 | 27 ms | | ReaderLM-v2 (1.5B neural) | 0.741 | 10,410 ms | *** THE WINNER IS ALSO NEARLY THE FASTEST. AND THE TWO NEURAL EXTRACTORS ARE BOTH SLOWER AND WORSE. *** SO: DO NOT USE AN LLM TO EXTRACT PAGE CONTENT. ReaderLM-v2 is 236x slower than rs-trafilatura for 12 F1 points less. On Jack's box that would mean minutes of GPU time per page for a worse result. Add this to jarvis-what-not-to-do in spirit. GENRE WARNING FROM THE SAME BENCHMARK: on articles every extractor lands within 1-3 points (0.825-0.932), but forums vary by 33 points, collections 27, products 26. Extraction quality is genre-dependent, so spot-check on forum and doc pages rather than assuming article-grade results.

## *** FINDING 5: HOW TO GET "MASSIVE DEPTH" WITHOUT BLOWING CONTEXT — AND THE HONEST COST ***

[SOURCE: Anthropic's own guidance on multi-agent systems] *** Multi-agent systems consume "3-10x more tokens than single-agent approaches" for equivalent tasks. *** On a 69 t/s box that is 3-10x the wall clock, not 3-10x the money. That is the real price of depth here. Their three conditions for it being worth it, all of which deep research meets:

- Context protection — when subtasks generate high volumes (1000+ tokens) irrelevant to later work. *** A research subagent reading five pages generates ~8,000 tokens of source text and returns a 500-token note. The orchestrator never sees the 8,000. That is the mechanism that makes unlimited depth possible on a limited context. ***
- Parallelization — independent research facets run concurrently. This pairs with the continuous-batching finding in system-performance-levers: parallel subagents are exactly the workload llama-server's slots are built for, so the 3-10x token cost does NOT become 3-10x wall clock if they run concurrently rather than sequentially.
- Specialization — focused toolsets; 20+ tools create selection problems. *** THE DESIGN PRINCIPLE, QUOTED: "context-centric decomposition" rather than problem-centric division — group work by REQUIRED CONTEXT, not by work type. *** Problem-based splits create coordination overhead that negates the benefit. AND THE PATTERN THEY SINGLE OUT AS CONSISTENTLY WORKING IS ONE JACK ALREADY HAS PROVEN ON THIS BOX: "The verification subagent pattern consistently succeeds because it bypasses handoff context loss — verifiers only need success criteria and artifacts, not full implementation history." That is the blind-verification pass he already asks for, and it is also the GVS5H ledger pattern (fresh instances coordinating through a shared filesystem holding a plan, notes and the current solution) that is already connected and proven on jarvis-1. The coding harness generalizes to research unchanged. ANTHROPIC'S OWN CAVEAT, worth keeping: teams have spent months on elaborate multi-agent systems only to find better prompting on a single agent matched them. Start single-agent, add agents only where one of the three conditions actually bites.

## THE BUILD ORDER THAT FOLLOWS

- Fix prefill first — --cache-reuse, the -lv 4 check, and no mmproj on the research slot (prompt-cache-and-prefill-reuse). Everything below is multiplied by this.
- Put rs-trafilatura in front of every page read. 80% fewer tokens, 44 ms, free. Biggest single win.
- Sign up for Serper (2,500 free) and/or Tavily (1,000/month free). Skip SearXNG.
- Wire the academic engines first — arXiv, PubMed, Semantic Scholar, NASA ADS — because they are free, unblocked and aimed at his actual goals.
- Install local-deep-research pointed at http://localhost:8080/v1 and reproduce the 27B benchmark on his own hardware before trusting the 95.7% figure.
- Only then add parallel subagents, running them concurrently across llama-server slots so the 3-10x token cost does not become 3-10x wall clock.

## THE CEILING, RESTATED HONESTLY

agent-harnesses already records it and nothing here changes it: a local 27B scoring 34 on the AA index cannot self-verify to Jack's stated 95% accuracy bar. The loop, the citations and the verification subagent make research auditable; they do not make it frontier-accurate. The 95.7% SimpleQA figure is short-factoid accuracy, which is a much easier task than the multi-source synthesis he actually wants.

## *** Sep 24 2026 — WHAT THE RESEARCH PIPELINE NEEDED FROM THE FAST HOUSE. D:\models\pull_research.py, ~15 GB, plus 19 wheelhouse packages. ***

Jack at the fast house: "I want the jarvis system to be able to perform massive massive massive, accurate research, and use these findings." *** THE ANSWER THAT FOLLOWS FROM THIS FILE'S OWN FINDINGS: the bottleneck is prefill, extraction, a search backend and the 95%-bar ceiling. NONE of the first three is a download. So the downloads target the two places where they DO help — retrieval precision, and MEASURING whether the research is accurate. ***

### RETRIEVAL PRECISION — the reranker was the weak link and nobody had noticed

mradermacher/Qwen3-Reranker-4B-GGUF (~3-4 GB at Q4/Q5). The base Qwen/Qwen3-Reranker-4B is 2,485,454 downloads, the most-downloaded reranker on HF, against the 0.6B (1,299,433) that was the only one on the list. WHY IT IS THE BIGGEST LEVER IN THE RETRIEVAL HALF: the embedder casts a wide cheap net over millions of chunks; the RERANKER decides which 5 of the top 100 the model actually reads. An error there puts a wrong page in front of the model, and a wrong page is exactly how a "grounded" system still emits a confident wrong answer. Keep 0.6B for bulk, use 4B on the final shortlist; llama-server --reranking serves both. GGUF availability confirmed across 8 repos (Voodisss, mradermacher, QuantFactory, Mungert, giladgd, DevQuasar, prithivMLmods, plus an i1 variant). Also queued as an experiment: Qwen/Qwen3-VL-Reranker-2B (737,894 downloads) — ranks IMAGES against a text query, because a lot of real source material is figures and scanned pages that a text reranker cannot see. Safetensors, transformers not llama.cpp.

### *** MEASURING ACCURACY — THIS IS THE PART THAT WAS COMPLETELY MISSING, AND THIS FILE ALREADY DEMANDED IT ***

Build step 5 says to install local-deep-research and "reproduce the 27B benchmark on his own hardware before trusting the 95.7% figure." That is impossible without the dataset. Now queued, all small:

- basicv8vc/SimpleQA (3,663 dl) and google/simpleqa-verified (3,337 dl) — the exact benchmark behind the Qwen3.6-27B 95.7% (287/300) claim. Run both: a gap between them measures dataset noise rather than model quality. The honest limit stays attached: SimpleQA is SHORT-FACTOID accuracy, far easier than multi-source synthesis, so a high score does NOT mean the deep-research output is 95% accurate.
- *** wandb/RAGTruth-processed (1,884 dl) — THE ONE THAT TESTS THE ANTI-HALLUCINATION GATE ITSELF. *** Span-level annotated hallucinations in RAG answers: given a source and a generated answer, which exact spans are unsupported. So it is the test set for HHEM-2.1-Open (queued in pull_orch.py) on Jack's own box. Without it the groundedness checker is one more unverified component; with it, it has a measured false-positive and false-negative rate. That is the difference between a grounded pipeline and a pipeline that claims to be grounded.
- google/frames-benchmark (multi-hop over several documents, much closer to the real job), hotpotqa/hotpot_qa (supporting sentences labelled, so RETRIEVAL can be scored separately from ANSWERING — when accuracy drops, this says which half broke), dgslibisey/MuSiQue (built so shortcuts fail, the best at exposing a pipeline guessing from priors). Ids unverified; pull_data.py logs NOT AVAILABLE and continues if one moved.

### PDFs — a second parser, because it is a different job from OCR

ds4sd/docling-models, a few hundred MB: layout analysis plus table-structure recognition. DeepSeek-OCR (queued) reads SCANNED pages; docling reconstructs LAYOUT and TABLES from born-digital PDFs. A PDF dumped as raw text loses the table structure that usually carries the actual numbers, which for biomedical and astrophysics sources is where the result lives.

### WHEELHOUSE ADDITIONS (19 packages) — the extraction lever is a pip install, and its tail is the painful part

trafilatura (the Python binding of the 80-82%-token-reduction extractor), local-deep-research, langchain + langchain-community, sentence-transformers, faiss-cpu, hnswlib, sqlite-vec, rank-bm25 (BM25 plus vector is the hybrid retrieval baseline that beats either alone), pymupdf, pypdf, docling, beautifulsoup4, lxml, readability-lxml, duckduckgo-search, tavily-python, arxiv, biopython (PubMed E-utilities), libzim (reads the ZIM corpora directly from Python).

### THE OFFLINE ANGLE THAT MAKES THIS DIFFERENT FROM EVERY OTHER DEEP-RESEARCH SETUP

Build step 4 says wire the academic engines first because they are free and aimed at his goals. After tonight he does not need their APIs for the bulk of it: PMC (166 GB, 8.3M full-text papers), PubMed (51.8 GB, ~38M abstracts), openly-licensed arXiv, proof-pile-2's 29B-token arXiv subset and 25 Stack Exchange sites are all LOCAL. So the same queries answer with zero latency, zero rate limit, zero cost and no CAPTCHA, and the paid search APIs become the fallback for the recent and the general rather than the primary path. That inverts the usual failure mode of local deep research, which is that the search layer is the flakiest part. CEILING UNCHANGED, and it is not a download problem: a local 27B at ~34 on the AA index cannot self-verify to a 95% bar. All of this makes research AUDITABLE and MEASURABLE, not frontier-accurate.

## *** Sep 24 2026 — THE OVERNIGHT RESEARCH ARCHITECTURE JACK ASKED FOR, SPEC'D. D:\models\RESEARCH-SPEC.md. ***

Jack: "I want to say research x, then jarvis asks me questions about it to scope it more, then the research could run all night, switching models, and running independently, to fully sweep as wide as it can." Spec written to the drive so it survives a usage limit.

### THE TWO DESIGN DECISIONS EVERYTHING ELSE FOLLOWS FROM

- *** "ACCURATE" IS A PER-CLAIM PROPERTY, NOT A PER-REPORT PROPERTY. *** A 4,000-word report cannot be checked; a table of 180 claims each carrying a source id, a VERBATIM quote and span offsets can be checked mechanically, row by row. So the pipeline's real output is a CLAIM TABLE and the readable report is generated from it at the end. This is what makes the HHEM gate, re-fetch verification and disagreement flagging possible at all.
- *** "AS WIDE AS IT CAN" NEEDS A MEASURED STOPPING RULE: SATURATION. *** Keep reading a branch until the last N documents yield no NEW claims. Novelty rate is a column in SQLite, so "we swept as wide as we could" becomes defensible instead of felt.

### THE SCOPING INTERVIEW — output is a CONTRACT, and one question carries most of the value

27B, 6-8 questions, writes research_brief to SQLite: the question, 3-7 sub-questions, inclusion/exclusion, ranked source classes, what DONE looks like (target claim count, min sources, coverage per sub-question), the deliverable shape, and a hard budget in wall clock, documents and tokens — mandatory, because of the runaway-retry incident. *** THE BEST SINGLE QUESTION TO ASK HIM IS "WHAT WOULD CHANGE THE ANSWER", because it defines which evidence is worth hunting. *** The brief is then the spec every later stage is scored against, which is why the verification-subagent pattern survives handoff: a verifier needs only success criteria plus artifact.

### COMPREHENSIVENESS IS A CONSTRUCTION PROBLEM, NOT AN EFFORT PROBLEM

Build a QUERY MATRIX (sub-question x source class x time window x terminology variant) into a frontier table before searching. That turns research into a crawl with a work queue: dedupe by URL and content hash, resume after a crash, report coverage as ROWS. Terminology variants beat query count, and for biomedical work expand through MeSH rather than model-guessed synonyms (PubMed ships the vocabulary). *** CITATION CHASING IS WHERE DEPTH COMES FROM: enqueue each key paper's references AND its citing papers. The local PMC XML already carries reference lists, so much of this runs with NO network; OpenAlex and Semantic Scholar are free for the rest. *** Cap hops at 2-3 and record hop count per document so late-night drift is visible afterwards.

### THE PER-DOCUMENT LOOP, AND THE POINT IS THAT ONLY TWO OF SIX STEPS USE A BIG MODEL

fetch (Chrome/CDP or a local ZIM/PMC read) → extract with rs-trafilatura, 44 ms, 80-82% fewer tokens → triage with the router 1.7B on CPU, GBNF-forced label (thousands of keep/discard calls a night, none touching a GPU) → rank with Qwen3-Reranker-4B (0.6B for the wide pass) → read + claim-extract with Flash-Next, emitting claims as JSON with verbatim quotes and offsets → gate with HHEM-2.1-Open on CPU, dropping unsupported claims before any big model sees them. Once per night, not per document: synthesis over the claim table with GLM-5.3 FULL (1.6-4 t/s is irrelevant for one pass while asleep, and it is the index-45 ceiling), adversarial review by a DIFFERENT architecture (27B or Flash-Next), then 27B polish. SWAP RULES from what is already measured: GLM-5.3-Flash (system RAM) and the 27B (VRAM) genuinely co-reside, so escalation costs only tokens. GLM-5.3 FULL at 435 GiB does NOT — treat the synthesis pass as an EXCLUSIVE SLOT the supervisor stops other models for, the same mechanism video rendering needs.

### *** THROUGHPUT, DERIVED FROM THIS BOX'S OWN MEASURED CONSTANTS — THIS IS THE HONEST SHAPE OF "MASSIVE" ***

At 145 t/s prefill, ~30 t/s decode, 1,678 tokens per extracted page: ~11.6 s prefill + ~6.7 s for a 200-token claim note = ~18 s per document single-stream = ~1,600 documents in an 8-hour night. With 3 concurrent slots and continuous batching, plan on 2,000-3,000 documents a night [ESTIMATE — batching helps decode far more than prefill, and prefill dominates here]. A few thousand documents per night, not millions. Still more reading than a person does in a year.

### THE ACCURACY STACK, ORDERED BY WHAT EACH IS WORTH

- HHEM gate on every claim — mechanical, CPU-cheap, and the only component whose own error rate is CALIBRATABLE, against RAGTruth, which is now on the drive.
- Re-fetch verification on a sample: re-download the source and string-match the quote. Catches the one failure a groundedness model cannot — a citation that never contained the text.
- *** NUMBERS ARE NEVER PARAPHRASED. *** Every figure appears as a verbatim quote plus unit, and anything derived is recomputed by code. Model-restated numbers are where confident wrongness lives.
- Two-architecture disagreement (GLM synthesises, Qwen reviews) with disagreements as FLAGGED ROWS, never silently averaged. Helps on grounded claims only; on judgment it is two opinions.
- Self-consistency: three passes over the same claim table, keep what appears in ≥2, flag the rest. Cheap across parallel slots.
- Nightly calibration with SimpleQA and FRAMES, score stored. An untracked pipeline drifts and nobody knows which change did it.

### INDEPENDENCE

systemd user unit + loginctl enable-linger, never tmux (a tmux download died here and took 242 GiB with no forensic trail). SQLite is the state, not the context window: research_brief, frontier, documents, claims, verdicts, runs, checkpointed per document. Hard caps in CODE not in the prompt. Daily audit log (WANT 20). ntfy with documents read / claims kept / claims dropped / coverage per sub-question. Morning artifact includes an explicit "what I could not establish" section — the most valuable part and the easiest to omit.

### THE CEILING, AND THE RIGHT USE OF A FRONTIER MODEL

A local 27B at ~34 cannot self-verify to 95% on multi-source synthesis. The design makes research auditable, measurable and comprehensive, not frontier-accurate. *** THE CHEAP ESCALATION THAT ACTUALLY WORKS: hand a frontier model the brief + the claim table + the flagged disagreements and ask it to audit the SYNTHESIS. One call over compressed evidence rather than raw sources. The local box does the thousands of hours of reading; the expensive model checks the conclusion. *** And the 95.7% SimpleQA number must never be quoted as the pipeline's accuracy.
