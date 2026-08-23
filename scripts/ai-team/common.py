from pathlib import Path
import json
import yaml

ROOT = Path(__file__).resolve().parents[2]
AI = ROOT / ".ai-team"

def load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def dump_yaml(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)

def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)
