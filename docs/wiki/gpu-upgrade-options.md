# gpu-upgrade-options

> Copied verbatim from Cowork (melange-wiki) on Sep 25 2026 (page last updated Sep 10, 2026).
> Cowork-only links kept as page names.
>
> Summary: What GPUs can physically and electrically go in Jack's ASUS ESC4000 G3, current Sept 2026 market prices, and why upgrading now is a bad idea. Read before any GPU purchase or capacity question for the server.

Researched Sep 9 2026 by two independent agents against ASUS official docs, NVIDIA product briefs and live listings. Related: esc4000-parts-order, local-model-landscape

*** THE BINDING CONSTRAINT IS POWER, AND IT IS THE WALL OUTLET ***

- ASUS documents an input-voltage derating table for the ESC4000 G3's 1+1 redundant 1620W Platinum PSUs: 100-120Vac -> 1000W output. 120-140Vac -> 1200W. 180-240Vac -> 1620W. A 2000W SKU also exists; check the PSU label
- 1+1 is REDUNDANT, not additive. Budget is one PSU's output, not two
- On a normal 120V household outlet Jack has ~1000W TOTAL. Current draw: 2x E5-2699 v3 at 145W = 290W, plus board/16 DIMMs/fans/BMC/drives ~150-250W, plus 2x V100 at 250W = 500W. That is ~990W. HE IS ALREADY AT THE 120V CEILING under full load
- Adding two more GPUs of any kind requires a 208-240V circuit. That is the real prerequisite for any GPU expansion, not money

CHASSIS LIMITS (ASUS official docs):

- Max 4 double-width GPUs. 8x PCIe 3.0 x16 slots, "4 at x16 Link or 8 at x8 Link" — a 4-GPU config gets FULL x16 Gen3 each (2 CPUs x 40 lanes = 80; 4x16 = 64, rest for riser/IO)
- Per-GPU power design point 300W (from the ESC8000 G3 datasheet, same board generation; ASUS never published one for the G3)
- Card length: NO documented figure. Practical ceiling is the 267mm / 10.5in FHFL datacenter form factor the chassis was designed around
- GPUs mount in removable ACCELERATOR BRACKETS, 2 cards per bracket, each card screwed to a card-specific PLASTIC AIR DUCT. Passive cooling by chassis fans through that duct. An open-air consumer card has no duct that fits, and removing the duct breaks the GPU-zone airflow model
- POWER HARNESS IS PROPRIETARY: the "8 x VGA Power cables" run from the PDB, not the motherboard. System end is an ASUS 4-pin PDB connector; GPU end is 6-pin. Two variants: red/white for general GPUs, black/white for NVIDIA 300W+. ASUS warns verbatim that a 300W NVIDIA card "will not work, or may even cause damage to the system, if the dongle is not used"
- Modern datacenter cards (A100, A40) use CPU 8-pin EPS; L40S uses 16-pin 12VHPWR. NONE mate with this harness natively. Custom cables exist on eBay (search "GPU Power Cable ASUS ESC4000 G3 Server PDB")
- No official GPU QVL exists for the ESC4000 G3. The nearest list (ESC8000 G3) is Kepler/Maxwell era: Tesla M40/M60/K80/K40M/K10, GRID K1/K2, Quadro M6000, FirePro S9150, Xeon Phi. Nothing Pascal or newer was ever qualified

BIOS / LARGE-BAR RISK (this is what would bite on 48GB+ cards):

- Resizable BAR DOES NOT EXIST on this board and never will. BIOS 3803 (22 Nov 2019) is the final release; ReBAR arrived in vendor firmware in late 2020
- Above 4G Decoding is present and already Enabled on Jack's unit. SR-IOV defaults to DISABLED — an NVIDIA forum thread identified SR-IOV Disabled as "the primary culprit" preventing A100 recognition, so turn it ON for datacenter cards
- BAR1 needs: A40 wants 64 GiB BAR1, A100 40GB wants 64GB, A100 80GB wants 128GB. That needs a 64-bit prefetchable MMIO window far bigger than the default
- MMIOH Base and MMIO High Granularity Size are NOT in the documented BIOS menus, but they DO exist hidden in IntelRCSetup on ASUS Z10/C612 boards. Proven on a Z10PE-D8 WS with 2x E5-2699 v3 (same CPU, sibling board): user unhid them with AmiBCP and set MMCFG Base 3GB, MMIOH Base 56TB, MMIO High Granularity 1024GB, Enable SPLIT BARs, PCIe ASPM disabled — got 2x Arc A770 with full ReBAR working. So a 48/80GB card is probably makeable, at the cost of an unsupported BIOS mod
- Linux is meaningfully safer than Windows here: the kernel can renegotiate PCI resources at runtime with pci=realloc (and pci=nocrs as fallback)
- CSM must be disabled for large-BAR operation (already done on Jack's box)
- Bifurcation (x4x4x4x4): UNVERIFIED. IIO Configuration menu exists but ASUS never printed its contents

MARKET, SEPT 2026 — WORST GPU BUYING CONDITIONS IN A DECADE:

- DRAM contract prices +13-18% QoQ in Q3 2026, NAND +10-15%, and that is the SLOWDOWN (Q2 was ~+60% QoQ)
- NVIDIA PAUSED ALL NEW RTX GPUs FOR 2026. RTX 50 Super cancelled outright, RTX 60 series slipped to ~2028, reason given "memory supply is constrained"
- Retail GPUs running 20-50% over MSRP, up to 35% higher than six months ago. Entry-level shortages expected to worsen through H2 2026
- Only category clearly FALLING is used H100 ($6k-22k, down ~85% from the 2023 peak) as Blackwell displaces Hopper
- Direction is RISING. No sign of relief before 2027

PRICES (asking prices, not sold; Sept 2026):

- Tesla V100 32GB PCIe: $618-850 (GPUPoet 101 listings, $618 low / $810 avg; GPUDojo $650 used; eBay $646). THE VALUE OUTLIER. True drop-in: 250W, dual-slot passive, same connector, same thermals
- A30 24GB HBM2: $2,599 used / $3,890 new. 165W, dual-slot passive, CPU 8-pin, sm_80, 933 GB/s. CHEAPEST FORWARD-SAFE CARD
- A10 24GB: ~$3,299-3,500. 150W, SINGLE SLOT, passive, sm_86
- L4 24GB: ~$3,395-3,699. 72W, single-slot LP, NO aux power (slot powered), sm_89. Slow at generation (~23 tok/s), 300 GB/s class
- A40 48GB: $4,600 used / $5,699 new. 300W, dual-slot passive, CPU 8-pin, sm_86. CHEAPEST FORWARD-SAFE 48GB
- A100 40GB PCIe: ~$4,250 (grey-market CN listing; US price unverified; counterfeit/SXM-relabel risk on Chinese A100s)
- A100 80GB PCIe: $11,608 low / $20,766 avg
- RTX A6000 48GB: $4,100 used. 300W but ACTIVE BLOWER, PCIe 8-pin not EPS
- L40S 48GB: $5,999 new / $7,300 used. 350W (over the 300W design point) and 16-pin 12VHPWR. An OEM CPU 8-pin to 16-pin 350W cable exists, NVIDIA P/N 030-1636-000
- RTX PRO 6000 Blackwell 96GB: $15,999-16,000; Max-Q $24,000
- CONSUMER, ALL UNUSABLE IN THIS 2U: RTX 3090 ~$1,000 (350W, 2.5-3 slot, 313-336mm), RTX 4090 $3,200-3,679 (450W, 3-3.5 slot), RTX 5090 $4,699-5,700 (575W, 190% over MSRP). Wrong length, wrong slot width, axial fans deadhead against server static pressure, wrong power connectors
- NON-NVIDIA: ASRock Intel Arc Pro B60 Passive 24GB, ~$599-665, SINGLE SLOT PASSIVE 190x112x19mm, 1x 8-pin, 456 GB/s — purpose-built rackmount part, but ASRock restricts it to business customers and it was out of stock. Intel Arc Pro B70 32GB $950 (2026, 608 GB/s). AMD Radeon AI PRO R9700 32GB, $1,299 MSRP but $1,700-2,161 street, ROCm 7.x officially supported on Ubuntu 24.04, BUT prompt prefill 2.6-3.4x slower than a 5090 and vLLM support described as flaky

ARCHITECTURE SUPPORT (the real decision driver):

- Volta sm_70 (his V100s): REMOVED from CUDA 13.x, dropped from PyTorch 2.11. Dead end. PyTorch's stated reason: "Keeping Volta supports prevents us from updating CuDNN, which unfortunately dropped Volta support in its newer binaries"
- Turing sm_75: also removed in CUDA 13.0. Dead end
- Ampere sm_80 (A100/A30), sm_86 (A40/A10/A6000/3090), Ada sm_89 (L4/L40S/4090), Hopper 9.0, Blackwell 12.0: all safe on current CUDA and PyTorch

VERDICT GIVEN TO JACK: do not upgrade now. Four independent reasons — he is at the 120V power ceiling already, the GPU market is the worst in a decade and rising, big-VRAM cards risk an MMIOH BIOS mod on this 2015 platform, and he has not yet run a single model to learn what he actually needs. If he later does upgrade: a 240V circuit first, then either 2 more V100 32GB (~$1,300 for 96GB total, but stuck on CUDA 12.6/PyTorch 2.10) or A30/A40 for forward safety at 4x the price per GB.
