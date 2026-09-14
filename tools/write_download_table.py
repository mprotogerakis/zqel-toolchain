#!/usr/bin/env python3
"""Die Tabelle aller oeffentlichen Downloads - erzeugt, nicht getippt.

WARUM ERZEUGT:
Die Adressen unter dl.zqel.org entstehen an neun Stellen: drei Pins, fuenf
Workflows und der Cache-Fueller. Eine von Hand gepflegte Uebersicht ist am Tag
nach dem naechsten Pin falsch, ohne dass es jemandem auffaellt - und eine
Tabelle, die Vollstaendigkeit behauptet, die niemand prueft, ist genau das
Muster, das uns diese Woche sechsmal Arbeit gemacht hat.

Deshalb: die Adressen werden aus den Pins ABGELEITET und dann ANONYM
NACHGEMESSEN - von aussen, mit HEAD, ohne Anmeldung, so wie ein Fremder sie
holt. Was nicht antwortet, steht als fehlend in der Tabelle. Ein Eintrag, den
wir versprechen und nicht liefern, soll sichtbar sein, nicht stillschweigend
verschwinden.

WAS R2 NICHT KANN:
Cloudflare R2 liefert keine Verzeichnislisten. Es gibt also keinen Weg, den
Bucket zu FRAGEN, was drinliegt - die Liste muss aus unseren Manifesten
kommen. Wo ein Manifest fehlt (die zqel-Pakete kommen aus dem LoLa-Repo),
steht die Erwartung hier ausdruecklich im Quelltext.

    python3 tools/write_download_table.py            # nur anzeigen
    python3 tools/write_download_table.py --schreiben # in README.md einsetzen
    python3 tools/write_download_table.py --pruefen   # CI: weicht die README ab?
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
BASIS = "https://dl.zqel.org"
#: Eine inhaltsadressierte Flake-Adresse: der Hash IST der Name.
#:
#: Erkannt wird die FORM, nicht der aktuelle Wert. Der erste Versuch schloss
#: die Adresse aus, die `latest.json` gerade nennt - und meldete daraufhin den
#: AELTEREN Hash in der README als Ueberschuss (gemessen: forgejo 3212). Eine
#: Ausnahme, die den Wert kennt statt die Form, verfehlt genau den Fall, fuer
#: den sie da ist.
INHALTSADRESSIERT = re.compile(
    r"^https://dl\.zqel\.org/(?:zqel/)?flake/[0-9a-f]{64}\.tar\.gz$")

ANFANG = "<!-- downloads:anfang -->"
ENDE = "<!-- downloads:ende -->"
ZEIT = 60

# Der archivierte Z3-Stand, unter dem die Wheels liegen. Bewegt sich nur,
# wenn LoLas z3-pin.json sich bewegt - und dann faellt es hier sofort auf.
Z3_STAND = "z3-nightly-0d4a2db"

# Mit eigenem User-Agent. Gemessen am 2026-09-14: Cloudflare weist den
# Vorgabe-Agenten von urllib mit 403 ab - was wie "gibt es nicht" aussieht.
KOPF = {"User-Agent": "zqel-download-index"}


def _kopfabfrage(url: str) -> tuple[str, int, int]:
    req = urllib.request.Request(url, method="HEAD", headers=KOPF)
    try:
        with urllib.request.urlopen(req, timeout=ZEIT) as a:
            return url, a.status, int(a.headers.get("Content-Length") or -1)
    except urllib.error.HTTPError as e:
        return url, e.code, -1
    except OSError:
        # Ein Netzfehler ist NICHT "nicht vorhanden". Das unterscheidet -1
        # vom sauberen 404 weiter unten.
        return url, -1, -1


def _hole(url: str) -> bytes | None:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=KOPF),
                                    timeout=ZEIT) as a:
            return a.read()
    except (urllib.error.HTTPError, OSError):
        return None


def _heute() -> str:
    return dt.date.today().isoformat()


def _groesse(n: int) -> str:
    if n < 0:
        return "—"
    if n >= 1048576:
        return f"{n / 1048576:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


def eintraege() -> list[dict]:
    """Jede Adresse, die wir oeffentlich anbieten - aus den Manifesten."""
    e: list[dict] = []

    def dazu(gruppe, name, pfad, plattform, herkunft, fluechtig=False):
        # `fluechtig`: eine inhaltsadressierte Adresse. Sie ist richtig, aber
        # sie BEWEGT SICH, sobald sich das Eingangsmaterial bewegt - der Hash
        # IST der Name. Solche Zeilen werden gemessen und angezeigt, aber aus
        # dem Soll-Ist-Vergleich herausgehalten: sonst wuerde jede Aenderung
        # im Schwesterrepositorium diese CI roeten, ohne dass etwas kaputt
        # ist, und das schult alle darauf, sie zu ignorieren.
        e.append({"gruppe": gruppe, "name": name, "url": f"{BASIS}/{pfad}",
                  "plattform": plattform, "herkunft": herkunft,
                  "fluechtig": fluechtig})

    # 1./2. Werkzeuge - gespiegelte wie selbst gebaute.
    #
    # Die Ableitung steht in tools/toolchain_adressen.py, weil sie auch der
    # Lock braucht. Zwei Stellen, die dasselbe rechnen, driften - und genau
    # das war hier schon zweimal der Fund.
    from toolchain_adressen import alle

    for name, w in alle().items():
        art = "mirrored" if w["herkunft"] == "gespiegelt" else "our build"
        gruppe = f"{name} {w['version']} ({art})"
        for datei in w["namen"]:
            if datei.endswith((".notice.txt", "LICENSE.txt")):
                plattform = "—"
            elif w["herkunft"] == "selbst gebaut" and "win_amd64" not in datei:
                plattform = "source"
            else:
                plattform = _plattform_aus(datei)
            dazu(gruppe, datei, f"{w['praefix']}/{datei}", plattform,
                 "mirror-pin.json" if w["herkunft"] == "gespiegelt"
                 else f"{name}-pin.json")

    # 3. Die Flake als Tarball. Der Hash IST der Name; latest.json ist
    #    Navigation und darf in keinem Verdikt stehen.
    roh = _hole(f"{BASIS}/flake/latest.json")
    if roh:
        d = json.loads(roh)
        dazu("toolchain flake", f"{d['sha256'][:12]}….tar.gz",
             f"flake/{d['sha256']}.tar.gz", "Linux, macOS", "flake/latest.json",
             fluechtig=True)
    dazu("toolchain flake", "latest.json", "flake/latest.json",
         "—", "published by CI")
    dazu("toolchain flake", "probe_public_toolchain.py",
         "flake/probe_public_toolchain.py", "—", "published by CI")

    # 4. Der signierte Binaercache. Sein Inhalt ist inhaltsadressiert und
    #    NICHT auflistbar - nix fragt je Pfad an. Aufgefuehrt wird deshalb
    #    der Einstiegspunkt, nicht der Inhalt.
    dazu("nix binary cache", "nix-cache-info", "nix/nix-cache-info",
         "Linux, macOS", "publish_nix_cache.py")

    # 5. Die zqel-Seite. Diese Adressen fuellt das LoLa-Repository, nicht
    #    dieses hier - es gibt also kein Manifest, gegen das wir ableiten
    #    koennten. Die Erwartung steht deshalb hier, und die Messung sagt,
    #    ob sie stimmt.
    roh = _hole(f"{BASIS}/zqel/flake/latest.json")
    if roh:
        d = json.loads(roh)
        dazu("zqel devShell flake", f"{d['sha256'][:12]}….tar.gz",
             f"zqel/flake/{d['sha256']}.tar.gz", "Linux, macOS",
             "zqel/flake/latest.json", fluechtig=True)
    dazu("zqel devShell flake", "latest.json", "zqel/flake/latest.json",
         "—", "published by LoLa CI")

    for name, plattform in (("zqel-latest-linux-x86_64.tar.gz", "Linux x86_64"),
                            ("zqel-latest-windows-amd64.zip", "Windows x86_64"),
                            ("zqel-latest-macos-arm64.tar.gz", "macOS arm64")):
        for n in (name, f"{name}.sha256"):
            dazu("zqel (latest)", n, f"zqel/latest/{n}", plattform,
                 "published by LoLa CI")

    # Die Distributionspakete. Sie lagen bis zum 2026-09-14 NUR unter
    # zqel/nightly/<datum>/ und trugen die Version im Dateinamen - ohne
    # Verzeichnislisten musste man beides raten. Seit mprotogerakis/LoLa#350
    # gibt es feste Namen; geliefert sind sie erst, wenn ein Nightly
    # durchlaeuft (LoLa#348). Bis dahin stehen sie hier als fehlend, und
    # genau dafuer ist diese Spalte da.
    for n, plattform in (("zqel-latest-amd64.deb", "Linux x86_64"),
                         ("zqel-latest-x86_64.rpm", "Linux x86_64")):
        dazu("zqel (packages)", n, f"zqel/latest/{n}", plattform,
             "published by LoLa CI")

    # 6. Der gepinnte Z3. Der Pin IST die Beweisidentitaet.
    #
    # Das Verzeichnis traegt den Namen des archivierten Standes; der steht
    # unten als Konstante, weil er sich selten und sichtbar bewegt. Die
    # LISTE der Artefakte wird NICHT hier wiederholt, sondern aus dem
    # oeffentlich danebenliegenden Manifest geholt. Stimmt die Konstante
    # nicht mehr, antwortet das Manifest mit 404 - und die Tabelle zeigt
    # genau eine fehlende Zeile statt still einen ganzen Abschnitt zu
    # verlieren.
    dazu(f"Z3 pin ({Z3_STAND})", "z3-pin.json",
         f"zqel/z3/{Z3_STAND}/z3-pin.json", "—", "z3-pin.json")
    roh = _hole(f"{BASIS}/zqel/z3/{Z3_STAND}/z3-pin.json")
    if roh:
        pin = json.loads(roh)
        for name in sorted(pin["artifacts"]):
            dazu(f"Z3 pin ({Z3_STAND})", name, f"zqel/z3/{Z3_STAND}/{name}",
                 _plattform_aus(name), "z3-pin.json")
    return e


def _plattform_aus(name: str) -> str:
    """Plattform aus dem Dateinamen - mit Wortgrenze fuer Windows.

    GEMESSEN am 2026-09-14, erster Entwurf dieser Datei:
    `kani-0.67.0-aarch64-apple-darwin.tar.gz` kam als "Windows macOS arm64"
    heraus, weil `"win" in "darwin"` wahr ist. Genau die Sorte selbst
    erfundener Pruefung, die hier diese Woche schon dreimal danebenlag -
    deshalb fuer Windows ein Muster mit Trennzeichen statt einer Teilkette.

    Die Architekturen bleiben Teilketten: `x86_64`, `aarch64`, `amd64` und
    `arm64` kommen in keinem anderen Wort vor.
    """
    n = name.lower()
    treffer = []
    if re.search(r"(?:^|[-_.])win(?:32|64|dows)?(?:[-_.]|$)", n) \
            or n.endswith((".msi", ".exe")):
        treffer.append("Windows")
    if re.search(r"(?:^|[-_.])(?:darwin|macosx?|osx)(?:[-_.]|$)", n):
        treffer.append("macOS")
    if re.search(r"(?:^|[-_.])(?:many)?linux(?:[-_.]|$)", n):
        treffer.append("Linux")
    if "aarch64" in n or "arm64" in n:
        treffer.append("arm64")
    if "x86_64" in n or "amd64" in n:
        treffer.append("x86_64")
    return " ".join(treffer) if treffer else "—"


def tabelle(eintr: list[dict], stand: dict) -> str:
    z = [
        f"| Group | File | Platform | Size (measured {_heute()}) |",
        "| --- | --- | --- | --- |",
    ]
    vorher = None
    fehlend = 0
    for e in eintr:
        st, gr = stand[e["url"]]
        g = e["gruppe"] if e["gruppe"] != vorher else ""
        vorher = e["gruppe"]
        if st == 200:
            groesse = _groesse(gr) + (" ·moves" if e.get("fluechtig") else "")
            name = f"[{e['name']}]({e['url']})"
        elif st == -1:
            groesse = "not reached"
            name = f"[{e['name']}]({e['url']})"
        else:
            groesse = f"**missing ({st})**"
            name = e["name"]
            fehlend += 1
        z.append(f"| {g} | {name} | {e['plattform']} | {groesse} |")
    return "\n".join(z), fehlend


def rumpf(eintr, stand) -> str:
    tab, fehlend = tabelle(eintr, stand)
    da = sum(1 for e in eintr if stand[e["url"]][0] == 200)
    bytes_ = sum(stand[e["url"]][1] for e in eintr if stand[e["url"]][0] == 200)
    teile = [
        ANFANG,
        "",
        "## Everything we publish on `dl.zqel.org`",
        "",
        "Generated by `tools/write_download_table.py`, which derives every",
        "address from the pins and then **measures it anonymously** — one",
        "unauthenticated `HEAD` per row, the way an outsider fetches it. A row",
        "marked `missing` is something this project promises and does not",
        "currently deliver; that is deliberate, so the gap is visible here",
        "rather than in someone's terminal.",
        "",
        f"{da} of {len(eintr)} addresses answered, {_groesse(bytes_)} in total.",
        "",
        "The `missing` rows are all zqel packages, and they have two causes,",
        "both tracked in [the zqel repository](https://github.com/mprotogerakis/LoLa/issues):",
        "the Linux build does not currently produce a startable binary, and",
        "the macOS build has no runner registered against that repository.",
        "The toolchain itself is complete.",
        "",
        tab,
        "",
        "**Dated nightly builds are not listed.** Every nightly run also",
        "writes `zqel/nightly/<YYYY-MM-DD>/`, which grows without a manifest",
        "and cannot be enumerated — R2 serves no listings. The rows above are",
        "the addresses that stay put.",
        "",
        "A size marked `·moves` belongs to a content-addressed name: the hash",
        "**is** the address, so it changes whenever its input does. Those rows",
        "are measured and shown but deliberately left out of the CI check —",
        "otherwise a commit in the sibling repository would redden this one",
        "for nothing.",
        "",
        "**`latest` is navigation, never proof identity.** The `latest.json`",
        "files and the `zqel/latest/` names move. A verdict that cites this",
        "toolchain must name the content-addressed SHA-256 URL, which does not.",
        "",
        "**The binary cache has no listing.** R2 serves no directory indexes,",
        "and a nix substituter is queried per store path, not per closure —",
        "so `nix/nix-cache-info` is the entry point, and what lives behind it",
        "is whatever `publish_nix_cache.py` has filled. `tools/verify_nix_cache.py`",
        "checks it from the outside.",
        "",
        ENDE,
    ]
    return "\n".join(teile), fehlend


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--schreiben", action="store_true",
                    help="Abschnitt in README.md einsetzen")
    ap.add_argument("--pruefen", action="store_true",
                    help="Exit 1, wenn die README abweicht")
    ap.add_argument("--readme", default=str(ROOT / "README.md"))
    args = ap.parse_args(argv)

    eintr = eintraege()
    with cf.ThreadPoolExecutor(8) as p:
        gemessen = list(p.map(_kopfabfrage, [e["url"] for e in eintr]))
    stand = {u: (s, g) for u, s, g in gemessen}

    text, fehlend = rumpf(eintr, stand)
    readme = pathlib.Path(args.readme)

    if not (args.schreiben or args.pruefen):
        print(text)
        return 0

    alt = readme.read_text(encoding="utf-8")
    if ANFANG in alt and ENDE in alt:
        vor = alt.split(ANFANG)[0]
        nach = alt.split(ENDE, 1)[1]
        neu = vor + text + nach
    else:
        # Ans Ende, aber vor nichts anderes - der Abschnitt SOLL unten stehen.
        neu = alt.rstrip("\n") + "\n\n---\n\n" + text + "\n"

    if args.pruefen:
        # ABSICHTLICH nicht Text gegen Text.
        #
        # Groessen und Erreichbarkeit aendern sich rechtmaessig - ein neues
        # Nightly, ein gefuellter Cache. Ein Byte-Vergleich machte daraus eine
        # rote CI, die nichts Kaputtes meldet, und das schult jeden darauf,
        # sie zu ignorieren. Geprueft wird, was driften kann, ohne dass es
        # jemand merkt: die Menge der zugesagten Adressen.
        #
        # NUR IM ABSCHNITT. Der erste Entwurf durchsuchte die ganze Datei -
        # und liess eine geloeschte Tabellenzeile durchgehen, weil dieselbe
        # Adresse weiter oben in der Werkzeugmatrix noch einmal stand
        # (gemessen: Zeile entfernt, Exit 0). Eine Pruefung, die ihren eigenen
        # Gegenstand nicht eingrenzt, stimmt einem immer zu.
        if ANFANG not in alt or ENDE not in alt:
            print("  Der Abschnitt fehlt in der README.")
            return 1
        abschnitt = alt.split(ANFANG, 1)[1].split(ENDE, 1)[0]
        ausserhalb = alt.replace(abschnitt, "")

        ohne_link = {e["url"] for e in eintr
                     if stand[e["url"]][0] not in (200, -1)}
        soll = {e["url"] for e in eintr if not INHALTSADRESSIERT.match(e["url"])}
        ist = {u for u in re.findall(
            r"\((https://dl\.zqel\.org/[^)\s]+)\)", abschnitt)
            if not INHALTSADRESSIERT.match(u)}

        fehlt = (soll - ohne_link) - ist
        zuviel = ist - soll
        for u in sorted(fehlt):
            print(f"  fehlt in der Tabelle:   {u}")
        for u in sorted(zuviel):
            print(f"  steht zu viel darin:    {u}")

        # Und die Gegenrichtung, die die Quell-Tarballs gefunden hat: ein
        # Verweis anderswo in der README auf etwas, das aus keinem Pin folgt.
        alle = {e["url"] for e in eintr}
        fremd = {u for u in re.findall(
            r"\((https://dl\.zqel\.org/[^)\s]+)\)", ausserhalb)
            if u not in alle and not INHALTSADRESSIERT.match(u)
            and not u.rstrip("/").endswith("dl.zqel.org")}
        for u in sorted(fremd):
            print(f"  verwiesen, aber aus keinem Pin abgeleitet: {u}")

        if fehlt or zuviel or fremd:
            print("  -> python3 tools/write_download_table.py --schreiben")
            return 1
        print(f"  Die Tabelle nennt alle {len(soll)} zugesagten Adressen "
              f"({fehlend} davon derzeit nicht ausgeliefert).")
        return 0

    readme.write_text(neu, encoding="utf-8")
    print(f"  {len(eintr)} Adressen gemessen, {fehlend} fehlend -> {readme}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
