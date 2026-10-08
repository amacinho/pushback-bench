"""Command line: pushback {elicit,collect,grade,analyze,generate,agreement}."""

import argparse

from . import analyze, collect, elicit, generate, grade, validation
from .data import config


def main():
    ap = argparse.ArgumentParser(prog="pushback")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, help_ in [("elicit", "each model's preferred option per scenario"), ("collect", "ask the models for the messages"),
                        ("grade", "judge the replies"), ("analyze", "compute the statistics")]:
        p = sub.add_parser(name, help=help_)
        p.add_argument("--out", required=True, help="run folder")
        if name != "analyze":
            p.add_argument("--models", help="comma-separated OpenRouter ids (default: all in config/models.yaml)")
            p.add_argument("--limit", type=int, help="only the first N scenarios (elicit), items (collect) or replies per model (grade)")
            p.add_argument("--conc", type=int, default=20, help="parallel calls")
        if name == "elicit":
            p.add_argument("--soft", action="store_true", help="ask for a trailing JSON line instead of a schema (for models that reject schemas)")
    p = sub.add_parser("generate", help="build new items from topic hints")
    p.add_argument("hints"); p.add_argument("--out", required=True); p.add_argument("--limit", type=int)
    p = sub.add_parser("agreement", help="judge-human agreement on the hand-labeled validation set")
    a = ap.parse_args()
    models = a.models.split(",") if getattr(a, "models", None) else config()["models"]
    if a.cmd == "elicit":
        elicit.run(models, a.out, a.limit, a.conc, a.soft)
    elif a.cmd == "collect":
        collect.run(models, a.out, a.limit, a.conc)
    elif a.cmd == "grade":
        grade.run(a.out, models if a.models else None, a.limit, a.conc)
    elif a.cmd == "analyze":
        print(analyze.report(a.out))
    elif a.cmd == "generate":
        generate.run(a.hints, a.out, a.limit)
    elif a.cmd == "agreement":
        print(validation.report())


if __name__ == "__main__":
    main()
