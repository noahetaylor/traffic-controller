r"""Project file resolution for the EE traffic-signal RL project.

Every script in this project used to live in the same folder as its data, so it
could refer to files by bare name ("donmills_final.net.xml"). After the Aug 2026
reorganisation the files live in typed subfolders, so bare names no longer
resolve. EE() restores that convenience:

    from ee_paths import EE
    NET = EE("donmills_final.net.xml")   -> ...\ee-project\networks\donmills_final.net.xml

Reading an existing file: EE() finds it wherever it lives, so you never have to
remember which subfolder holds what.

Writing a new file: EE() routes it by extension to the folder it belongs in --
.net/.rou/.nod/.edg.xml to networks/, .add.xml to signals/, .png to figures/,
.zip/.npy to models/, and everything else (tripinfo dumps, SUMO logs, result
CSVs) to outputs/. So `--tripinfo-output EE("rl_13.xml")` lands in outputs/
without the caller thinking about it.

Scripts can therefore be run from anywhere; paths are anchored to this file's
location, not to the current working directory.
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCRIPTS  = ROOT / "scripts"
DATA     = ROOT / "data"
NETWORKS = ROOT / "networks"
SIGNALS  = ROOT / "signals"
MODELS   = ROOT / "models"
FIGURES  = ROOT / "figures"
OUTPUTS  = ROOT / "outputs"
DOCS     = ROOT / "docs"

# The cloned sumo-rl repo and the virtualenv deliberately stayed outside the
# project folder (a Windows venv bakes absolute paths into its shims, and the
# repo is upstream reference material, not project code).
SUMO_RL_REPO = Path(os.environ.get("SUMO_RL_REPO", Path.home() / "sumo-rl"))

_SEARCH_ORDER = (NETWORKS, SIGNALS, DATA, MODELS, FIGURES, OUTPUTS, DOCS, ROOT, SCRIPTS)


def _folder_for_new(name: str) -> Path:
    """Where a not-yet-existing file should be created, based on its suffix."""
    lower = name.lower()
    if lower.endswith((".net.xml", ".rou.xml", ".nod.xml", ".edg.xml", ".osm.xml")):
        return NETWORKS
    if lower.endswith(".add.xml"):
        return SIGNALS
    if lower.endswith(".png"):
        return FIGURES
    if lower.endswith((".zip", ".npy")):
        return MODELS
    if not Path(name).suffix:
        # Stable-Baselines3 saves/loads by extension-less name and appends .zip
        # itself, e.g. model.save("dqn_donmills_am") -> dqn_donmills_am.zip.
        return MODELS
    # tripinfo dumps, collision dumps, SUMO logs, result CSVs
    return OUTPUTS


def EE(name) -> str:
    """Resolve a project file (or directory) by bare name.

    Returns an absolute path as a string, so it drops straight into
    subprocess argument lists and SUMO/sumo-rl keyword arguments.
    """
    name = str(name)
    p = Path(name)
    if p.is_absolute():
        return str(p)

    # Already-qualified relative paths ("./best_13", "models/x.zip") and any
    # existing file win over extension routing.
    for base in _SEARCH_ORDER:
        candidate = base / p
        if candidate.exists():
            return str(candidate)
        # SB3 model handles are extension-less but stored as .zip; return the
        # handle (no suffix) so SB3 can append its own.
        if not p.suffix and candidate.with_suffix(".zip").exists():
            return str(candidate)

    if len(p.parts) > 1:
        return str(ROOT / p)
    return str(_folder_for_new(name) / name)


def ee_path(name) -> Path:
    """Same as EE(), but returns a pathlib.Path."""
    return Path(EE(name))
