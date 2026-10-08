"""Build new items from topic hints. Only needed to extend the benchmark; data/items.jsonl is the benchmark.

For each hint, a writer model drafts a scenario: two options, the brief in both option orders, and three updates
(neutral, doomed_a, doomed_b). Mechanical checks and a panel of verifier models then test that both options are
defensible after the neutral update and that each doomed update rules out exactly its option. A failed draft gets one
fix round; a hint gets up to `max_draws` fresh drafts. Passing scenarios become 12 items (2 orders x 3 updates x
2 chosen options).
"""

import json
from pathlib import Path

import yaml

from . import client
from .data import append_jsonl, config, prompt

UPDATES = ("neutral", "sink_a", "sink_b")          # the writer's names for the three updates
RENAME = {"neutral": "neutral", "sink_a": "doomed_a", "sink_b": "doomed_b"}
EXPECT = {"neutral": {"A": True, "B": True}, "sink_a": {"A": False, "B": True}, "sink_b": {"A": True, "B": False}}
ORDERS = ("a_first", "b_first")


def fill(name, **kw):
    text = prompt(name)
    for k, v in kw.items():
        text = text.replace("{{" + k + "}}", v)
    return text


def ask_json(spec, text):
    reply = client.chat(spec["model"], text, temperature=spec.get("temperature"), max_tokens=4000)
    obj = client.parse_json(reply)
    if obj is None:
        obj = client.parse_json(client.chat(spec["model"], text + "\n\nYour previous reply could not be parsed as JSON. Return only the JSON object.",
                                            temperature=spec.get("temperature"), max_tokens=4000))
    if obj is None:
        raise ValueError("no JSON object in reply")
    return obj


def check_shape(s):
    for sec, keys in (("options", ("A", "B")), ("stems", ORDERS), ("slots", UPDATES)):
        for k in keys:
            if not isinstance(s.get(sec, {}).get(k), str) or not s[sec][k].strip():
                raise ValueError(f"writer JSON: missing {sec}.{k}")
            s[sec][k] = s[sec][k].strip()
    for k in ("audience", "format"):
        if not isinstance(s.get(k), str) or not s[k].strip():
            raise ValueError(f"writer JSON: missing {k}")
        s[k] = s[k].strip()


def mechanics(s, g):
    crits = []
    lo, hi = g["brief_words"]
    for o in ORDERS:
        n = len(s["stems"][o].split())
        if not lo <= n <= hi:
            crits.append(f"mechanics: stem {o} is {n} words, must be {lo}-{hi}")
    counts = {k: len(s["slots"][k].split()) for k in UPDATES}
    if max(counts.values()) > g["update_length_ratio"] * min(counts.values()):
        crits.append(f"mechanics: slot word counts too different {counts}, max/min must be <= {g['update_length_ratio']}")
    if s["format"] not in g["formats"]:
        crits.append(f"mechanics: format {s['format']!r} must be one of {g['formats']}")
    for o in s["options"].values():
        if o.lower() in s["audience"].lower():
            crits.append(f"mechanics: audience {s['audience']!r} must not name option {o!r}")
    return crits


def verify(s, g):
    """The verifier panel on each update and option; returns critiques for every judgment that missed its target."""
    crits = []
    for u in UPDATES:
        for opt in ("A", "B"):
            text = fill("verifier", piece_text=s["stems"]["a_first"] + "\n\n" + s["slots"][u], selection=s["options"][opt])
            yes = no = 0; dissent = []
            for v in g["verifiers"]:
                try:
                    reply = ask_json(v, text)
                except (ValueError, client.CallError):
                    continue
                verdict = reply.get("defensible")
                if isinstance(verdict, str):
                    verdict = {"true": True, "false": False}.get(verdict.strip().lower())
                if verdict is None:
                    continue
                yes += verdict is True; no += verdict is False
                if verdict != EXPECT[u][opt]:
                    dissent.append(str(reply.get("rationale", "")))
            want = EXPECT[u][opt]
            if (yes if want else no) < g["verifier_pass_min"]:
                name = s["options"][opt]; why = "; ".join(d for d in dissent if d)
                crits.append(f"{u}: choosing {name} should stay reasonable after this update, but reviewers found it indefensible: {why}" if want
                             else f"{u}: this update should make {name} no longer viable, but reviewers still found choosing it defensible: {why}")
    return crits


def items_from(s, hint):
    out = []
    for o in ORDERS:
        for u in UPDATES:
            for chosen in ("A", "B"):
                name = s["options"][chosen]; upd = RENAME[u]
                out.append({"item_id": f"{hint['id']}__{upd}__{o}__chose_{chosen.lower()}", "scenario": hint["id"], "domain": hint["domain"],
                            "options": s["options"], "option_order": o, "brief": s["stems"][o], "update_type": upd, "update": s["slots"][u],
                            "chosen": chosen, "doomed": (upd == "doomed_a" and chosen == "A") or (upd == "doomed_b" and chosen == "B"),
                            "audience": s["audience"], "format": s["format"],
                            "request": fill("request", announced=name, format=s["format"], audience=s["audience"]).strip()})
    return out


def one_hint(hint, g):
    feedback = []
    for _ in range(g["max_draws"]):
        avoid = ("\nEarlier attempts with this seed failed review. Use a genuinely different scenario and do not repeat these mistakes:\n"
                 + "\n".join("- " + a for a in feedback) + "\n") if feedback else ""
        s = ask_json(g["writer"], fill("writer", domain=hint["domain"], hint=hint["hint"], avoid_block=avoid)); check_shape(s)
        crits = mechanics(s, g) or verify(s, g)
        if crits:   # one fix round
            s = ask_json(g["writer"], fill("fix", draft_json=json.dumps(s, indent=2), critiques="\n".join("- " + c for c in crits))); check_shape(s)
            crits = mechanics(s, g) or verify(s, g)
        if not crits:
            return items_from(s, hint)
        feedback += crits[:3] + [f'do not reuse this scenario: "{" ".join(s["stems"]["a_first"].split())[:140]}..."']
    return []


def run(hints_file, out, limit=None):
    g = config()["generation"]
    hints = yaml.safe_load(Path(hints_file).read_text(encoding="utf-8"))[:limit]
    for h in hints:
        try:
            items = one_hint(h, g)
        except (ValueError, client.CallError) as e:
            print(f"{h['id']}: {e}"); continue
        print(f"{h['id']}: {'ok' if items else 'no scenario passed review'}")
        for it in items:
            append_jsonl(Path(out) / "items.jsonl", it)
