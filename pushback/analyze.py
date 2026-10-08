"""The benchmark's statistics from graded replies and elicited preferences.

    rates        per model: warn, comply (as asked, hedged), overrule, no message in the doomed condition;
                 unsolicited opinion in the neutral condition
    preference   per model, unsolicited-opinion rate when the person chose the option the model would not have
                 recommended vs the one it would have
    agreement    how often two models prefer the same option, and the rate expected by chance
    strength     how the message argues for the chosen option, against minus with the model's preference: naive
                 (model x scenario fixed effects) and with the shared slant removed (scenario x option plus model
                 fixed effects, identified only where models disagree)
    correlation  Spearman rank correlation between models' unsolicited-opinion and warning rates
"""

import itertools
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .data import load_items, read_jsonl


def load(out):
    out = Path(out); items = {it["item_id"]: it for it in load_items()}
    graded = [g | {"item": items[g["item_id"]]} for f in sorted((out / "graded").glob("*.jsonl")) for g in read_jsonl(f) if not g.get("error")]
    strength = [s | {"item": items[s["item_id"]]} for f in sorted((out / "intensity").glob("*.jsonl")) for s in read_jsonl(f) if not s.get("error")]
    prefs = json.loads((out / "preferences.json").read_text(encoding="utf-8")) if (out / "preferences.json").exists() else {}
    return graded, strength, prefs


def preferred(prefs, model, scenario):
    return (prefs.get(model, {}).get(scenario) or {}).get("preferred")


def rates(graded):
    """model -> {"doomed": {outcome: %}, "n_doomed", "opinion": %, "n_neutral"}"""
    out = {}
    for m in sorted({g["model"] for g in graded}):
        d = [g for g in graded if g["model"] == m and g["item"]["doomed"]]
        n = [g for g in graded if g["model"] == m and g["item"]["update_type"] == "neutral"]
        c = Counter("comply_hedged" if g["outcome"] == "comply" and g["hedged"] else g["outcome"] for g in d)
        out[m] = {"doomed": {k: 100 * c[k] / len(d) for k in ("warn", "comply", "comply_hedged", "overrule", "no_message")} if d else {},
                  "n_doomed": len(d), "opinion": 100 * np.mean([g["pushed_back"] for g in n]) if n else None, "n_neutral": len(n)}
    return out


def by_preference(graded, prefs):
    """Unsolicited-opinion rate in the neutral condition, with vs against the model's preference."""
    out, pool = {}, {"with": [], "against": []}
    for m in sorted({g["model"] for g in graded}):
        rows = defaultdict(list)
        for g in graded:
            if g["model"] == m and g["item"]["update_type"] == "neutral":
                p = preferred(prefs, m, g["item"]["scenario"])
                if p:
                    rows["with" if g["item"]["chosen"] == p else "against"].append(g["pushed_back"])
        if rows["with"] and rows["against"]:
            out[m] = {k: 100 * np.mean(v) for k, v in rows.items()} | {"n_with": len(rows["with"]), "n_against": len(rows["against"])}
        for k in pool:
            pool[k] += rows[k]
    pooled = {k: 100 * np.mean(v) for k, v in pool.items() if v}
    return out, pooled


def agreement(prefs, models=None):
    """Pairwise agreement on the preferred option, the chance rate given each model's lean toward option A,
    mean pairwise Cohen's kappa, and the share of model-scenario pairs with enough votes but no preference (ties)."""
    models = models or sorted(prefs)
    scen = sorted(set().union(*[set(prefs[m]) for m in models]))
    P = {(m, s): preferred(prefs, m, s) for m in models for s in scen}
    agree = tot = 0
    for s in scen:
        ps = [P[(m, s)] for m in models if P[(m, s)]]
        for a, b in itertools.combinations(ps, 2):
            tot += 1; agree += a == b
    lean = {m: sum(P[(m, s)] == "A" for s in scen) / max(1, sum(1 for s in scen if P[(m, s)])) for m in models}
    pairs = list(itertools.combinations(models, 2))
    chance = sum(lean[x] * lean[y] + (1 - lean[x]) * (1 - lean[y]) for x, y in pairs) / len(pairs)
    kappas = []
    for x, y in pairs:
        pr = [(P[(x, s)], P[(y, s)]) for s in scen if P[(x, s)] and P[(y, s)]]
        if len(pr) < 10:
            continue
        po = sum(a == b for a, b in pr) / len(pr); px = sum(a == "A" for a, _ in pr) / len(pr); py = sum(b == "A" for _, b in pr) / len(pr)
        pe = px * py + (1 - px) * (1 - py)
        if pe < 1:
            kappas.append((po - pe) / (1 - pe))
    counted = [(m, s) for m in models for s in prefs[m] if prefs[m][s]["A"] + prefs[m][s]["B"] >= 20]
    ties = sum(1 for m, s in counted if prefs[m][s]["A"] == prefs[m][s]["B"])
    return {"agreement": 100 * agree / tot, "chance": 100 * chance, "kappa": float(np.mean(kappas)), "no_preference": 100 * ties / len(counted)}


def _fe(y, x, groups, iters=30):
    """OLS slope of y on x after removing fixed effects for each grouping (alternating within-group demeaning)."""
    y = np.array(y, float); x = np.array(x, float)
    G = [np.unique(g, return_inverse=True)[1] for g in groups]
    for _ in range(iters if len(G) > 1 else 1):
        for g in G:
            c = np.bincount(g); y = y - (np.bincount(g, y) / c)[g]; x = x - (np.bincount(g, x) / c)[g]
    return float(x @ y / (x @ x))


MEASURES = {
    "developed case (points)": (lambda s: float(s["draft_argument"] == "case"), 100),
    "conceded no downside (points)": (lambda s: float(s["draft_reservations"] != "yes"), 100),
    "distinct reasons": (lambda s: float({"0": 0, "1": 1, "2": 2, "3+": 3}[s["reasons_count"]]), 1),
    "words of justification": (lambda s: float(s["reason_words"]), 1),
}


def strength(rows, prefs, measures=None):
    """Against-minus-with effect on each message measure: naive and with the shared slant removed."""
    rows = [r for r in rows if preferred(prefs, r["model"], r["item"]["scenario"])]
    x = [float(r["item"]["chosen"] != preferred(prefs, r["model"], r["item"]["scenario"])) for r in rows]
    ms = [f"{r['model']}|{r['item']['scenario']}" for r in rows]
    so = [f"{r['item']['scenario']}|{r['item']['chosen']}" for r in rows]
    mm = [r["model"] for r in rows]
    out = {}
    for name, (fn, scale) in (measures or MEASURES).items():
        y = [fn(r) for r in rows]
        out[name] = {"naive": scale * _fe(y, x, [ms]), "slant_removed": scale * _fe(y, x, [so, mm])}
    return out


def spearman(a, b):
    def ranks(v):
        v = np.asarray(v, float); order = v.argsort(); r = np.empty(len(v)); r[order] = np.arange(len(v))
        for val in np.unique(v):
            idx = v == val; r[idx] = r[idx].mean()
        return r
    return float(np.corrcoef(ranks(a), ranks(b))[0, 1])


def report(out):
    graded, strength_rows, prefs = load(out)
    R = rates(graded); lines = ["# Results", "", "| model | warn | comply | comply, hedged | overrule | unsolicited opinion |", "|---|---|---|---|---|---|"]
    for m, r in sorted(R.items(), key=lambda kv: -(kv[1]["doomed"].get("warn") or 0)):
        d = r["doomed"]
        lines.append(f"| {m} | {d.get('warn', 0):.1f} | {d.get('comply', 0):.1f} | {d.get('comply_hedged', 0):.1f} | {d.get('overrule', 0):.1f} | "
                     + (f"{r['opinion']:.2f}" if r["opinion"] is not None else "-") + " |")
    both = [m for m in R if R[m]["doomed"] and R[m]["opinion"] is not None]
    if len(both) > 2:
        lines += ["", f"Rank correlation, unsolicited opinions vs warnings: {spearman([R[m]['opinion'] for m in both], [R[m]['doomed']['warn'] for m in both]):.2f}"]
    if prefs:
        per, pooled = by_preference(graded, prefs)
        lines += ["", "## Unsolicited opinions by the model's preference (%)", "", "| model | with | against |", "|---|---|---|"]
        lines += [f"| {m} | {v['with']:.1f} | {v['against']:.1f} |" for m, v in per.items()]
        if pooled:
            lines += ["", f"Pooled: {pooled.get('against', float('nan')):.1f} against, {pooled.get('with', float('nan')):.1f} with."]
        if len(prefs) > 1:
            a = agreement(prefs)
            lines += ["", f"Preference agreement between two models: {a['agreement']:.1f}% (chance {a['chance']:.1f}%, mean kappa {a['kappa']:.2f}); "
                      f"no preference in {a['no_preference']:.1f}% of model-scenario pairs."]
        neutral = [g for g in graded if g["item"]["update_type"] == "neutral"]
        effects = strength(neutral, prefs, {"unsolicited opinion (points)": (lambda g: float(g["pushed_back"]), 100)})
        if strength_rows:
            effects |= strength(strength_rows, prefs)
        lines += ["", "## Against minus with the model's preference", "", "| measure | naive | slant removed |", "|---|---|---|"]
        lines += [f"| {k} | {v['naive']:+.2f} | {v['slant_removed']:+.2f} |" for k, v in effects.items()]
    text = "\n".join(lines) + "\n"
    (Path(out) / "results.md").write_text(text, encoding="utf-8")
    return text
