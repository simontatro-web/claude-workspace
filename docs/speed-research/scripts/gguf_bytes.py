#!/usr/bin/env python3
# Read-only. Sums a GGUF model's tensor bytes by kind (routed experts, lookup tables, MTP layers, the rest)
# from the file headers only, and estimates the bytes read per generated token:
#   everything that is not a routed expert, lookup table or MTP layer, plus routed experts x used/total.
# Works on split models (pass the -00001-of-0000N file). Prints under ~2,500 characters. No dependencies.
# Usage: python3 ~/speed/scripts/gguf_bytes.py <model.gguf> [measured decode t/s ...]
#   Each measured t/s is converted to the effective memory bandwidth it implies.
import glob, os, re, signal, struct, sys
signal.signal(signal.SIGPIPE, signal.SIG_DFL)  # quiet exit when piped into head

TYPES = {0: "F32", 1: "F16", 2: "Q4_0", 3: "Q4_1", 6: "Q5_0", 7: "Q5_1", 8: "Q8_0", 9: "Q8_1", 10: "Q2_K", 11: "Q3_K",
         12: "Q4_K", 13: "Q5_K", 14: "Q6_K", 15: "Q8_K", 16: "IQ2_XXS", 17: "IQ2_XS", 18: "IQ3_XXS", 19: "IQ1_S",
         20: "IQ4_NL", 21: "IQ3_S", 22: "IQ2_S", 23: "IQ4_XS", 24: "I8", 25: "I16", 26: "I32", 27: "I64", 28: "F64",
         29: "IQ1_M", 30: "BF16", 34: "TQ1_0", 35: "TQ2_0", 39: "MXFP4", 40: "NVFP4", 41: "Q1_0", 42: "Q2_0"}
SCALAR = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d"}

class Reader:
    def __init__(self, path):
        self.f = open(path, "rb")
    def get(self, fmt):
        n = struct.calcsize(fmt)
        return struct.unpack(fmt, self.f.read(n))[0]
    def string(self):
        return self.f.read(self.get("<Q")).decode("utf-8", "replace")
    def value(self, t):
        if t in SCALAR:
            return self.get(SCALAR[t])
        if t == 8:
            return self.string()
        if t == 9:
            at, n = self.get("<I"), self.get("<Q")
            if at in SCALAR and n > 64:  # skip long numeric arrays, keep their length
                self.f.seek(n * struct.calcsize(SCALAR[at]), 1)
                return ["len", n]
            return [self.value(at) for _ in range(n)]
        raise ValueError("unknown GGUF value type %d" % t)

def parse(path):
    r = Reader(path)
    if r.f.read(4) != b"GGUF":
        raise ValueError(path + " is not a GGUF file")
    r.get("<I")
    nt, nkv = r.get("<Q"), r.get("<Q")
    kv = {}
    for _ in range(nkv):
        k = r.string()
        v = r.value(r.get("<I"))
        kv[k] = len(v) if isinstance(v, list) and v[:1] != ["len"] else (v[1] if isinstance(v, list) else v)
    infos = []
    for _ in range(nt):
        name = r.string()
        nd = r.get("<I")
        dims = [r.get("<Q") for _ in range(nd)]
        infos.append([name, r.get("<I"), r.get("<Q"), dims])
    align = int(kv.get("general.alignment", 32))
    start = (r.f.tell() + align - 1) // align * align
    size = os.path.getsize(path)
    infos.sort(key=lambda x: x[2])
    out = []
    for i, (name, t, off, dims) in enumerate(infos):  # sizes from offsets: exact for any tensor type
        end = infos[i + 1][2] if i + 1 < len(infos) else size - start
        out.append((name, t, end - off))
    return kv, out

def summarize(first):
    m = re.match(r"(.*)-00001-of-(\d{5})\.gguf$", first)
    files = sorted(glob.glob("%s-*-of-%s.gguf" % (m.group(1), m.group(2)))) if m else [first]
    kv, tensors = {}, []
    for f in files:
        k, t = parse(f)
        kv = kv or k
        tensors += t
    arch = kv.get("general.architecture", "?")
    g = lambda key, d=0: kv.get("%s.%s" % (arch, key), d)
    nl, ne, nu, nn = int(g("block_count")), int(g("expert_count")), int(g("expert_used_count")), int(g("nextn_predict_layers"))
    cat = {"experts": 0, "lookup": 0, "mtp": 0, "rest": 0}
    types, big = {}, []
    for name, t, b in tensors:
        lm = re.match(r"blk\.(\d+)\.", name)
        if (lm and nn and int(lm.group(1)) >= nl - nn) or "nextn" in name:
            c = "mtp"
        elif "_exps" in name:
            c = "experts"
        elif "token_embd" in name:
            c = "lookup"
        else:
            c = "rest"
            big.append((b, name, TYPES.get(t, "type%d" % t)))
        cat[c] += b
        types[TYPES.get(t, "type%d" % t)] = types.get(TYPES.get(t, "type%d" % t), 0) + b
    per_tok = cat["rest"] + (cat["experts"] * nu / ne if ne else cat["experts"])
    return kv, arch, g, (nl, ne, nu, nn), files, tensors, cat, types, big, per_tok

def main():
    if len(sys.argv) < 2:
        sys.exit("usage: gguf_bytes.py model.gguf [measured t/s ...]")
    kv, arch, g, (nl, ne, nu, nn), files, tensors, cat, types, big, per_tok = summarize(sys.argv[1])
    GB = 1e9
    total = sum(cat.values())
    print("%s | layers %d (MTP layers %d) | experts %d, used %d | hidden %s | trained ctx %s | vocab %s" % (
        arch, nl, nn, ne, nu, g("embedding_length", "?"), g("context_length", "?"), kv.get("tokenizer.ggml.tokens", "?")))
    print("files %d | tensors %d | %.2f GB total (%.1f GiB)" % (len(files), len(tensors), total / GB, total / 2**30))
    print("routed experts : %7.2f GB -> per token %.2f GB (%d of %d)" % (cat["experts"] / GB, cat["experts"] * nu / max(ne, 1) / GB, nu, ne))
    print("everything else: %7.2f GB -> per token %.2f GB (read in full every token)" % (cat["rest"] / GB, cat["rest"] / GB))
    print("lookup tables  : %7.2f GB -> per token ~0 (only the looked-up rows)" % (cat["lookup"] / GB))
    print("MTP layers     : %7.2f GB -> not read by plain decoding" % (cat["mtp"] / GB))
    print("per-token read estimate: %.2f GB | routed-expert share %.0f%% (what the CPU still reads if all other tensors sit on a GPU)" % (
        per_tok / GB, 100.0 * (per_tok - cat["rest"]) / per_tok if per_tok else 0))
    for tps in sys.argv[2:]:
        print("measured %s t/s x %.2f GB = %.1f GB/s effective" % (tps, per_tok / GB, float(tps) * per_tok / GB))
    print("largest other tensors: " + "; ".join("%s %s %.2f GB" % (n, ty, b / GB) for b, n, ty in sorted(big, reverse=True)[:5]))
    print("bytes by type: " + ", ".join("%s %.1f GB" % (k, v / GB) for k, v in sorted(types.items(), key=lambda x: -x[1])[:8]))

if __name__ == "__main__":
    main()
