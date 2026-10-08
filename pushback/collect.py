"""Ask each model for the message, item by item.

Design per scenario: six cells (each doomed update with each chosen option, the neutral update with each chosen
option), `reps` replies each. Every cell uses one option order per scenario, balanced across scenarios within the cell.
Replies go to <out>/replies/<model>.jsonl as they arrive; reruns skip what is already there.
"""

import random
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import client
from .data import append_jsonl, config, load_items, read_jsonl, slug, vignette

CELLS = [("doomed_a", "A"), ("doomed_a", "B"), ("doomed_b", "A"), ("doomed_b", "B"), ("neutral", "A"), ("neutral", "B")]


def balanced(rng, values, n):
    reps = list(values) * (n // len(values)) + list(values)[: n % len(values)]
    rng.shuffle(reps)
    return reps


def design(items, seed=0):
    """The items to run: one per scenario and cell, with option orders balanced within each cell."""
    by = {(it["scenario"], it["update_type"], it["option_order"], it["chosen"]): it for it in items}
    scenarios = sorted({it["scenario"] for it in items})
    plan = []
    for update, chosen in CELLS:
        rng = random.Random(f"{seed}|{update}|{chosen}")
        for s, order in zip(scenarios, balanced(rng, ["a_first", "b_first"], len(scenarios))):
            plan.append(by[(s, update, order, chosen)])
    return plan


def prompt_for(item):
    return vignette(item) + "\n\n" + item["request"]


def run(models, out, limit=None, conc=20, seed=0):
    cfg = config(); reps = cfg["design"]["reps"]; st = cfg["responder"]
    plan = design(load_items(), seed)
    if limit:
        plan = plan[:limit]
    lock = threading.Lock(); tasks = []
    for m in models:
        f = Path(out) / "replies" / f"{slug(m)}.jsonl"
        done = {(r["item_id"], r["rep"]) for r in read_jsonl(f) if r.get("reply")}
        tasks += [(m, it, rep) for it in plan for rep in range(reps) if (it["item_id"], rep) not in done]
    random.Random(seed).shuffle(tasks)
    print(f"collect: {len(tasks)} calls")

    def one(t):
        m, it, rep = t
        try:
            reply, err = client.chat(m, prompt_for(it), temperature=st["temperature"], max_tokens=st["max_tokens"], effort=st["effort"]), None
        except client.CallError as e:
            reply, err = "", str(e)
        append_jsonl(Path(out) / "replies" / f"{slug(m)}.jsonl", {"model": m, "item_id": it["item_id"], "rep": rep, "reply": reply, "error": err}, lock)

    with ThreadPoolExecutor(max_workers=conc) as ex:
        list(ex.map(one, tasks))
