"""Judge-human agreement on the hand-labeled replies in validation/labels.jsonl.

Each row holds a reply, its human labels (labeled blind, without model names or judge labels) and the judge's labels.
Per field: replies compared, raw agreement, Cohen's kappa with a 95% bootstrap interval over replies.
"""

import collections
import math
import random

from .data import ROOT, read_jsonl

FIELDS = [("dissent", "remark: silent / mention / push back"), ("pushed_back", "remark: push back or not"),
          ("request_reflected", "message: chosen option / something else / none"), ("draft_hedges", "message hedges"),
          ("draft_reasons", "message gives reasons"), ("draft_argument", "strength: none / gesture / developed case"),
          ("draft_reservations", "strength: concedes a downside")]


def kappa(pairs):
    n = len(pairs); po = sum(a == b for a, b in pairs) / n
    ch = collections.Counter(a for a, _ in pairs); cj = collections.Counter(b for _, b in pairs)
    pe = sum((ch[c] / n) * (cj[c] / n) for c in set(ch) | set(cj))
    return ((po - pe) / (1 - pe) if pe < 1 else float("nan")), po


def interval(pairs, draws=2000, seed=0):
    rng = random.Random(seed); ks = []
    for _ in range(draws):
        k = kappa([pairs[rng.randrange(len(pairs))] for _ in pairs])[0]
        if not math.isnan(k):
            ks.append(k)
    ks.sort()
    return (ks[int(0.025 * len(ks))], ks[min(len(ks) - 1, int(0.975 * len(ks)))]) if len(ks) > 50 else (float("nan"), float("nan"))


def table(path=ROOT / "validation" / "labels.jsonl"):
    rows = read_jsonl(path)
    for r in rows:
        for side in ("human", "judge"):
            d = r[side].get("dissent")
            if d:
                r[side]["pushed_back"] = "yes" if d == "case" else "no"
    out = []
    for f, name in FIELDS:
        pairs = [(r["human"][f], r["judge"][f]) for r in rows if f in r["human"] and f in r["judge"] and not (r["human"][f] == "na" and r["judge"][f] == "na")]
        if len(pairs) < 4:
            continue
        k, po = kappa(pairs); lo, hi = interval(pairs)
        out.append({"field": f, "name": name, "n": len(pairs), "agreement": po, "kappa": k, "ci": (lo, hi)})
    return out


def report():
    lines = ["| field | replies | agreement | kappa [95% CI] |", "|---|---|---|---|"]
    lines += [f"| {t['name']} | {t['n']} | {100 * t['agreement']:.0f}% | {t['kappa']:.2f} [{t['ci'][0]:.2f}, {t['ci'][1]:.2f}] |" for t in table()]
    return "\n".join(lines)
