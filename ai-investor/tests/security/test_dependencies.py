import tomllib
from pathlib import Path

BLACKLIST = {
    "pytr",
    "ccxt",
    "alpaca-trade-api",
    "alpaca-py",
    "ib-insync",
    "ib_insync",
    "robin-stocks",
    "degiro-connector",
    "selenium",
    "playwright",
}


def test_no_broker_or_automation_dependency():
    pyproject = tomllib.loads(
        (Path(__file__).parents[2] / "pyproject.toml").read_text(encoding="utf-8")
    )
    project = pyproject["project"]
    deps = list(project["dependencies"])
    for extra in project.get("optional-dependencies", {}).values():
        deps.extend(extra)
    names = {
        d.split(">")[0].split("=")[0].split("<")[0].split("[")[0].strip().lower() for d in deps
    }
    assert not names & BLACKLIST, names & BLACKLIST
