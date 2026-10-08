"""Paths, items, prompts and the model roster."""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PROMPTS = ROOT / "prompts"
CONFIG = ROOT / "config" / "models.yaml"


def load_items(path=DATA / "items.jsonl"):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def prompt(name):
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")


def phrasings():
    return [l.strip() for l in prompt("elicit").splitlines() if l.strip()]


def config():
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def vignette(item):
    """The situation as the model sees it: the brief, then the update."""
    return item["brief"] + "\n\n" + item["update"]


def other(option):
    return "B" if option == "A" else "A"


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    out = []
    for l in open(path, encoding="utf-8"):
        if l.strip():
            try:
                out.append(json.loads(l))
            except json.JSONDecodeError:
                continue  # a line cut short by an interrupted write
    return out


def append_jsonl(path, row, lock=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, ensure_ascii=False) + "\n"
    if lock:
        with lock, open(path, "a", encoding="utf-8") as f:
            f.write(line)
    else:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)


def slug(model):
    return model.replace("/", "-")
