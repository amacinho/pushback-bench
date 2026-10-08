"""Each model's own preference per scenario.

The model reads the neutral version of the situation (brief + neutral update, no announced choice) and is asked which
option it would pick, with five phrasings, three times each, in both option orders: 30 votes per scenario. The option
with more votes is the model's preference; with a tie or fewer than `min_votes` valid votes there is none.

Votes go to <out>/votes/<model>.jsonl as they arrive (resumable); `summarize` writes <out>/preferences.json.
"""

import random
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import client
from .data import append_jsonl, config, load_items, phrasings, read_jsonl, slug, vignette

SOFT_SUFFIX = ('\n\nAnswer as you like, then end your reply with a JSON object on its own line with two fields: '
               '"reasoning" (one or two sentences) and "choice" (exactly one of: "{a}", "{b}", or "no_pick").')


def schema_for(first, second):
    return {"type": "object",
            "properties": {"reasoning": {"type": "string"}, "choice": {"type": "string", "enum": [first, second, "no_pick"]}},
            "required": ["reasoning", "choice"], "additionalProperties": False}


def neutral_views(items):
    """scenario -> {"options": ..., "a_first": text, "b_first": text}"""
    out = {}
    for it in items:
        if it["update_type"] == "neutral" and it["chosen"] == "A":
            out.setdefault(it["scenario"], {"options": it["options"]})[it["option_order"]] = vignette(it)
    return out


def prompt_for(view, order, phrasing_index):
    return view[order] + "\n\n" + phrasings()[phrasing_index]


def ask(model, settings, view, order, pi, soft=False):
    """One vote: returns (choice in A/B/None, raw choice, reasoning, error)."""
    opts = view["options"]
    first, second = (opts["A"], opts["B"]) if order == "a_first" else (opts["B"], opts["A"])
    prompt = prompt_for(view, order, pi)
    kw = dict(temperature=settings["temperature"], max_tokens=settings["max_tokens"], effort=settings["effort"])
    try:
        if soft:
            obj = client.parse_json(client.chat(model, prompt + SOFT_SUFFIX.format(a=first, b=second), **kw), trailing=True)
        else:
            obj = client.parse_json(client.chat(model, prompt, schema=schema_for(first, second), schema_name="pick_option", **kw))
    except client.CallError as e:
        return None, None, "", str(e)
    if not obj:
        return None, None, "", "no JSON in reply"
    raw = obj.get("choice")
    choice = "A" if raw == opts["A"] else "B" if raw == opts["B"] else None
    return choice, raw, str(obj.get("reasoning", ""))[:4000], None


def run(models, out, limit=None, conc=20, soft=False, seed=0):
    cfg = config(); reps = cfg["design"]["elicitation_reps"]
    views = neutral_views(load_items())
    scenarios = sorted(views)[:limit] if limit else sorted(views)
    lock = threading.Lock(); tasks = []
    for m in models:
        f = Path(out) / "votes" / f"{slug(m)}.jsonl"
        done = {(r["scenario"], r["order"], r["phrasing"], r["rep"]) for r in read_jsonl(f) if r.get("choice") or r.get("choice_raw") == "no_pick"}
        tasks += [(m, s, o, pi, rep) for s in scenarios for o in ("a_first", "b_first") for pi in range(5) for rep in range(reps)
                  if (s, o, pi, rep) not in done]
    random.Random(seed).shuffle(tasks)
    print(f"elicit: {len(tasks)} calls")

    def one(t):
        m, s, o, pi, rep = t
        choice, raw, reasoning, err = ask(m, cfg["responder"], views[s], o, pi, soft)
        append_jsonl(Path(out) / "votes" / f"{slug(m)}.jsonl",
                     {"model": m, "scenario": s, "order": o, "phrasing": pi, "rep": rep, "choice": choice,
                      "choice_raw": raw, "reasoning": reasoning, "error": err}, lock)

    with ThreadPoolExecutor(max_workers=conc) as ex:
        list(ex.map(one, tasks))
    return summarize(out)


def summarize(out):
    """preferences.json: per model and scenario, votes for A and B and the preferred option (or null)."""
    import json
    min_votes = config()["design"]["min_votes"]
    prefs = {}
    for f in sorted((Path(out) / "votes").glob("*.jsonl")):
        latest = {}
        ok = lambda r: r.get("choice") in ("A", "B") or r.get("choice_raw") == "no_pick"
        for r in read_jsonl(f):
            k = (r["scenario"], r["order"], r["phrasing"], r["rep"])
            if k not in latest or ok(r) or not ok(latest[k]):
                latest[k] = r
        per = {}
        for (s, *_), r in latest.items():
            e = per.setdefault(s, {"A": 0, "B": 0})
            if r.get("choice") in ("A", "B"):
                e[r["choice"]] += 1
        for s, e in per.items():
            n = e["A"] + e["B"]
            e["preferred"] = None if n < min_votes or e["A"] == e["B"] else ("A" if e["A"] > e["B"] else "B")
        if latest:
            prefs[next(iter(latest.values()))["model"]] = per
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / "preferences.json").write_text(json.dumps(prefs, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return prefs
