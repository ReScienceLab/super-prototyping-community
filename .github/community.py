"""The repo's two jobs, run by its workflows.

    python .github/community.py check <pr-checkout> <login>
        A pull request's projects, against the base branch checked out here. Reads the pull
        request's files and runs `sp pack --check` on them; runs nothing of theirs.

    python .github/community.py index
        Rewrites index.json from projects/, after a push to main.

Standard library only, beside `sp` and `gh` on PATH.
"""

import filecmp, json, re, subprocess, sys
from pathlib import Path

THUMBNAIL = (1600, 1000)  # what `sp pack -o` draws
PHONE = (478, 980)        # the artboard a board with no size in layout.json is


def projects(root: Path) -> dict:
    folder = root / "projects"
    return {d.name: d for d in folder.iterdir()} if folder.is_dir() else {}


def same(a: Path, b: Path) -> bool:
    """Whether two project folders hold the same files, byte for byte."""
    files = lambda d: sorted(p.relative_to(d) for p in d.rglob("*") if not p.is_dir())
    if a.is_symlink() or b.is_symlink() or not (a.is_dir() and b.is_dir()):
        return False
    if files(a) != files(b):
        return False
    return all(filecmp.cmp(a / f, b / f, shallow=False) for f in files(a))


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def png_size(path: Path):
    head = path.read_bytes()[:24]
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def check(pr: Path, opener: str) -> list:
    problems = []
    me = opener.lower()
    base, head = projects(Path(".")), projects(pr)
    for name in sorted(base.keys() | head.keys()):
        if name in base and name in head and same(base[name], head[name]):
            continue
        where = f"projects/{name}"
        if name not in head:
            old = read(base[name] / "project.json")
            if old.get("author", "").lower() != me:
                problems.append(f"{where}: only its author, {old.get('author')}, can remove it")
            continue
        folder = head[name]
        if folder.is_symlink() or not folder.is_dir():
            problems.append(f"{where}: is not a folder")
            continue
        run = subprocess.run(["sp", "pack", "--check", str(folder)], capture_output=True, text=True)
        if run.returncode:
            problems += [f"{where}: {line}" for line in (run.stdout + run.stderr).splitlines()
                         if line.startswith(("problem", "error"))]
            continue
        # The folder is what `sp pack -o` wrote and nothing else: all it leaves out is the thumbnail.
        extra = [line.split(None, 2)[2] for line in run.stdout.splitlines()
                 if line.startswith("left out")]
        if extra != ["thumbnail.png"]:
            problems += [f"{where}/{e}: is not part of the package" for e in extra
                         if e != "thumbnail.png"]
        thumb = folder / "thumbnail.png"
        if thumb.is_symlink() or not thumb.is_file() or png_size(thumb) != THUMBNAIL:
            problems.append(f"{where}/thumbnail.png: is not the {THUMBNAIL[0]} x {THUMBNAIL[1]} "
                            "PNG `sp pack -o` draws")
        pj = read(folder / "project.json")
        if pj["id"] != name:
            problems.append(f"{where}: the folder is not named for the project's id, {pj['id']}")
        author = pj["author"].lower()
        people = {c.lower() for c in pj.get("contributors", [])}
        if name not in base:
            if author != me:
                problems.append(f"{where}: its author is {pj['author']}, and only they can add it")
            continue
        old = read(base[name] / "project.json")
        if author != old["author"].lower() and me != old["author"].lower():
            problems.append(f"{where}: only {old['author']} can change its author")
        if me not in people | {author}:
            problems.append(f"{where}: add {opener} to its contributors in project.json")
    return problems


def gh(path: str) -> dict:
    return json.loads(subprocess.run(["gh", "api", path], capture_output=True, text=True,
                                     check=True).stdout)


def person(login: str, known: dict) -> dict:
    """{login, id}. A login can be renamed and the numeric id cannot, so a person the index
    already has is looked up by id, which corrects the login it shows."""
    if login.lower() in known:
        user = gh(f"user/{known[login.lower()]}")
    else:
        user = gh(f"users/{login}")
    return {"login": user["login"], "id": user["id"]}


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
    out.sort(key=lambda e: e["updated"], reverse=True)
    path.write_text(json.dumps({"format": 1, "projects": out}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    if sys.argv[1] == "check":
        found = check(Path(sys.argv[2]), sys.argv[3])
        for p in found:
            print(f"::error::{p}")
        print(f"{len(found)} problem(s)" if found else "ok")
        sys.exit(1 if found else 0)
    index()
