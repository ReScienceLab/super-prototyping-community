"""The repo's two jobs, run by its workflows.

    python .github/community.py check <pr-checkout> <login> <user id>
        A pull request's projects, against the base branch checked out here. Reads the pull
        request's files and runs `sp pack --check` on them; runs nothing of theirs. PR,
        CHANGED_FILES and GITHUB_REPOSITORY in the environment name the pull request.

    python .github/community.py index
        Rewrites index.json from projects/, after a push to main.

Standard library only, beside `sp` and `gh` on PATH.
"""

import json, os, subprocess, sys
from datetime import datetime
from pathlib import Path

THUMBNAIL = (2400, 1260)  # what `sp pack -o` draws: an Open Graph image, twice over
PHONE = (478, 980)        # the artboard a board with no size in layout.json is
THUMBNAIL_CAP = 5 << 20   # the examples' 2400 x 1260 PNGs are 1 MB at most
PULL_FILES_CAP = 3000     # the most files GitHub lists for a pull request


def projects(root: Path) -> dict:
    folder = root / "projects"
    return {d.name: d for d in folder.iterdir()} if folder.is_dir() else {}


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def png_size(path: Path):
    head = path.read_bytes()[:24]
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def gh(*args: str):
    """`gh api`'s output, or None for a 404. Anything else fails the job."""
    run = subprocess.run(["gh", "api", *args], capture_output=True, text=True)
    if run.returncode and "HTTP 404" in run.stderr:
        return None
    if run.returncode:
        raise SystemExit(f"gh api {' '.join(args)}: {run.stderr.strip()}")
    return run.stdout


def user(path: str):
    found = gh(path)
    return found and json.loads(found)


def user_id(login: str):
    found = user(f"users/{login}")
    return found and found["id"]


def check(pr: Path, opener: str, opener_id: int, changed: list) -> list:
    """`changed` is the pull request's files as GitHub lists them, against the merge base: a
    branch behind main does not undo what main has gained since."""
    problems = []
    me = opener.lower()
    base, head = projects(Path(".")), projects(pr)
    names = set()
    for f in changed:
        parts = f.split("/")
        if parts[0] == "projects" and len(parts) > 2:
            names.add(parts[1])
        else:
            problems.append(f"{f}: a pull request changes only projects/<id>/")
    # By numeric id, which the index keeps: a renamed author's old login can be anyone's now.
    listed = {e["id"]: e["author"]["id"] for e in read(Path("index.json"))["projects"]}

    def author_id(name):
        return listed.get(name) or user_id(read(base[name] / "project.json")["author"])

    for name in sorted(names):
        where = f"projects/{name}"
        if name not in head:
            if author_id(name) != opener_id:
                old = read(base[name] / "project.json")["author"]
                problems.append(f"{where}: only its author, {old}, can remove it")
            continue
        folder = head[name]
        if folder.is_symlink() or not folder.is_dir():
            problems.append(f"{where}: is not a folder")
            continue
        run = subprocess.run(["sp", "pack", "--check", str(folder)], capture_output=True, text=True)
        if run.returncode:
            said = [line for line in (run.stdout + run.stderr).splitlines()
                    if line.startswith(("problem", "error"))]
            # A traceback or a usage error says neither, and still fails.
            problems += [f"{where}: {line}" for line in said or
                         [f"sp pack --check exited {run.returncode}: {run.stderr.strip()[-500:]}"]]
            continue
        # The folder is what `sp pack -o` wrote and nothing else: all it leaves out is the thumbnail.
        extra = [line.split(None, 2)[2] for line in run.stdout.splitlines()
                 if line.startswith("left out")]
        problems += [f"{where}/{e}: is not part of the package" for e in extra
                     if e != "thumbnail.png"]
        thumb = folder / "thumbnail.png"
        if (thumb.is_symlink() or not thumb.is_file() or thumb.stat().st_size > THUMBNAIL_CAP
                or png_size(thumb) != THUMBNAIL):
            problems.append(f"{where}/thumbnail.png: is not the {THUMBNAIL[0]} x {THUMBNAIL[1]} "
                            "PNG `sp pack -o` draws")
        pj = read(folder / "project.json")
        if pj["id"] != name:
            problems.append(f"{where}: the folder is not named for the project's id, {pj['id']}")
        for login in [pj["author"], *pj.get("contributors", [])]:
            if user_id(login) is None:
                problems.append(f"{where}: {login} is not a GitHub user")
        author = pj["author"].lower()
        people = {c.lower() for c in pj.get("contributors", [])}
        if name not in base:
            if author != me:
                problems.append(f"{where}: its author is {pj['author']}, and only they can add it")
            continue
        if author_id(name) == opener_id:
            continue  # its author, who can change anything, handing it over included
        old = read(base[name] / "project.json")["author"]
        if author != old.lower():
            problems.append(f"{where}: only {old} can change its author")
        if me not in people:
            problems.append(f"{where}: add {opener} to its contributors in project.json")
    return problems


def person(login: str, known: dict) -> dict:
    """{login, id}. A login can be renamed and the numeric id cannot, so a person the index
    already has is looked up by id, which corrects the login it shows. An account deleted since
    keeps the login it had and no id."""
    found = user(f"user/{known[login.lower()]}" if login.lower() in known else f"users/{login}")
    return {"login": found["login"], "id": found["id"]} if found else {"login": login, "id": None}


def device(folder: Path) -> str:
    """"iphone" when the first canvas's cover board is the phone artboard, else "web"."""
    canvases = [d for d in (folder / "canvases").iterdir() if d.is_dir() and any(d.glob("*.html"))]
    layout = lambda d: read(d / "layout.json") if (d / "layout.json").is_file() else {}
    canvases.sort(key=lambda d: (layout(d).get("order", 0), d.name))
    if not canvases:
        return "web"
    first = layout(canvases[0])
    names = sorted(f.stem for f in canvases[0].glob("*.html"))
    cover = first.get("cover") if first.get("cover") in names else next(
        (n for n in names if not n.startswith("00")), names[0])
    for row in first.get("rows") or []:
        for entry in row.get("files") or []:
            if isinstance(entry, dict) and entry.get("file") == cover and entry.get("w"):
                return "iphone" if (entry["w"], entry["h"]) == PHONE else "web"
    return "iphone"


def index():
    path = Path("index.json")
    old = read(path)["projects"] if path.exists() else []
    known = {}
    for entry in old:
        for p in [entry["author"], *entry["contributors"]]:
            if p["id"]:
                known[p["login"].lower()] = p["id"]
    out = []
    for name, folder in sorted(projects(Path(".")).items()):
        pj = read(folder / "project.json")
        icons = sorted(folder.glob("canvases/*/icon.png"))
        updated = subprocess.run(["git", "log", "-1", "--format=%cI", "--", str(folder)],
                                 capture_output=True, text=True, check=True).stdout.strip()
        out.append({
            "id": name,
            "name": pj.get("name") or name,
            "author": person(pj["author"], known),
            "contributors": [person(c, known) for c in pj.get("contributors", [])],
            "boards": len(list(folder.glob("canvases/*/*.html"))),
            "device": device(folder),
            "thumbnail": f"projects/{name}/thumbnail.png",
            "icon": icons[0].as_posix() if icons else None,
            "updated": updated,
        })
    out.sort(key=lambda e: datetime.fromisoformat(e["updated"]), reverse=True)
    path.write_text(json.dumps({"format": 1, "projects": out}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    if sys.argv[1] == "check":
        if int(os.environ["CHANGED_FILES"]) > PULL_FILES_CAP:
            sys.exit(f"::error::over the {PULL_FILES_CAP} files GitHub lists; split it up")
        # A rename lists its old path too, which is a change to the folder it left.
        changed = gh("--paginate", f"repos/{os.environ['GITHUB_REPOSITORY']}/pulls/"
                     f"{os.environ['PR']}/files", "--jq", ".[] | .filename, .previous_filename // empty")
        found = check(Path(sys.argv[2]), sys.argv[3], int(sys.argv[4]), changed.split())
        for p in found:
            print(f"::error::{p}")
        print(f"{len(found)} problem(s)" if found else "ok")
        sys.exit(1 if found else 0)
    index()
