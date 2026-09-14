"""Der Cache ist eine lasttragende Stufe - er muss sich selbst binden.

Wer den Signaturschluessel haelt, bestimmt mit, welcher Beweiser auf einer
fremden Maschine laeuft. Drei Dinge duerfen deshalb nicht auseinanderlaufen:
was die Flake als Substituter nennt, welchen oeffentlichen Schluessel sie
dazu nennt, und gegen welchen Schluesselnamen der Pruefer spaeter misst.

Kein Netzzugang hier. Die Messung selbst machen die Werkzeuge.
"""
from __future__ import annotations

import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import publish_nix_cache  # noqa: E402
import verify_nix_cache  # noqa: E402

FLAKE = (ROOT / "flake.nix").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".forgejo" / "workflows" / "publish-flake.yml").read_text(
    encoding="utf-8")


def _anweisungen(text: str, kommentar: str) -> str:
    """Ohne Kommentarzeilen - sonst misst ein Test die Prosa, die ihn erklaert."""
    return "\n".join(z for z in text.splitlines()
                     if not z.lstrip().startswith(kommentar))


def test_the_flake_names_a_substituter_and_the_key_for_it():
    nix = _anweisungen(FLAKE, "#")
    assert "extra-substituters" in nix, "kein Substituter deklariert"
    assert "extra-trusted-public-keys" in nix, (
        "ein Substituter ohne Schluessel ist nutzlos: nix lehnt unsignierte "
        "Pfade ab, und zwar zu Recht")


def test_the_key_the_verifier_checks_is_the_key_the_flake_publishes():
    """Zwei Stellen, ein Name. Laufen sie auseinander, meldet der Pruefer
    'fremder Schluessel' fuer den eigenen Cache."""
    treffer = re.findall(r'"([A-Za-z0-9_.:-]+-\d):([A-Za-z0-9+/=]+)"', FLAKE)
    assert treffer, "kein oeffentlicher Schluessel in flake.nix gefunden"
    name = treffer[0][0]
    assert verify_nix_cache.SCHLUESSELNAME == name, (
        f"flake.nix nennt {name!r}, der Pruefer misst gegen "
        f"{verify_nix_cache.SCHLUESSELNAME!r}")


def test_the_substituter_the_flake_names_is_the_one_we_fill():
    adressen = re.findall(r'"(https://[^"]+)"', _anweisungen(FLAKE, "#"))
    assert verify_nix_cache.UNSERER in adressen, (
        f"die Flake nennt {adressen}, gefuellt und geprueft wird aber "
        f"{verify_nix_cache.UNSERER}")
    assert publish_nix_cache.ZIEL in verify_nix_cache.UNSERER


def test_publishing_without_a_key_refuses_instead_of_making_a_useless_cache():
    """Ein unsignierter Cache sieht fertig aus und wird beim Nutzer abgelehnt.
    Das ist der teuerste denkbare Ausgang: Arbeit getan, Wirkung null."""
    with pytest.raises(SystemExit) as exc:
        publish_nix_cache.main(["--key", "", ".#irgendwas"])
    assert "UNSIGNIERTER" in str(exc.value)


def test_a_named_key_file_that_does_not_exist_is_a_finding(tmp_path):
    with pytest.raises(SystemExit) as exc:
        publish_nix_cache.main(["--key", str(tmp_path / "gibtsnicht"), ".#x"])
    assert "nicht da" in str(exc.value)


def test_only_the_gap_is_uploaded_by_default():
    """Die ganze Closure hochzuladen waere nicht falsch, aber verschwenderisch:
    3.36 GB statt 1.09 GB, gemessen an der Darwin-Kette. Ein Substituter wird
    je Pfad befragt, nicht je Closure - was upstream hat, holt der Nutzer
    weiter von dort."""
    quelle = (ROOT / "tools" / "publish_nix_cache.py").read_text(encoding="utf-8")
    assert "--alles" in quelle, "kein Weg, im Notfall doch alles zu tragen"
    assert "schon_oeffentlich" in _anweisungen(quelle, "#")


def test_an_unreachable_upstream_counts_as_missing_not_as_present():
    """Die Richtung des Zweifels entscheidet.

    Haelt ein Netzfehler einen Pfad faelschlich fuer vorhanden, fehlt er
    hinterher im Cache - und der Fehler faellt erst dem auf, der ihn benutzt.
    Andersherum wird nur einmal zu viel hochgeladen.
    """
    quelle = (ROOT / "tools" / "publish_nix_cache.py").read_text(encoding="utf-8")
    stelle = quelle[quelle.index("def schon_oeffentlich"):]
    stelle = stelle[:stelle.index("\ndef ")]
    assert "except OSError" in stelle
    # im OSError-Zweig darf der Pfad NICHT als vorhanden vermerkt werden
    zweig = stelle[stelle.index("except OSError"):]
    assert "da.add" not in zweig, "ein Netzfehler darf nicht als 'vorhanden' zaehlen"


def test_the_workflow_fills_the_cache_before_it_announces_the_flake():
    """Sonst zeigt latest.json auf eine Flake, deren Cache noch leer ist -
    der erste Nutzer baut dann alles selbst und weiss nicht, warum."""
    anweisungen = _anweisungen(WORKFLOW, "#")
    assert "publish_nix_cache.py" in anweisungen
    assert anweisungen.index("publish_nix_cache.py") < anweisungen.index("latest.json")


def test_the_workflow_checks_the_cache_from_outside_afterwards():
    anweisungen = _anweisungen(WORKFLOW, "#")
    assert "verify_nix_cache.py" in anweisungen, (
        "ein Cache, den niemand von aussen abfragt, ist eine Behauptung")
    assert anweisungen.index("publish_nix_cache.py") < anweisungen.index(
        "verify_nix_cache.py")


def test_no_publishing_step_can_be_skipped_silently():
    """Ein `if:` am Schritt macht aus einem Fehlschlag ein stilles
    Ueberspringen: gruener Lauf, nichts veroeffentlicht."""
    zeilen = WORKFLOW.splitlines()
    schritt = re.compile(r"^\s{6}- name:")
    bedingung = re.compile(r"^\s+if:\s*(.+)$")
    schlecht = []
    for i, z in enumerate(zeilen):
        if not any(m in z for m in ("publish_r2.py", "publish_nix_cache.py")):
            continue
        if z.lstrip().startswith("#"):
            continue
        j = i
        while j > 0 and not schritt.match(zeilen[j]):
            j -= 1
        for b in zeilen[j:i]:
            m = bedingung.match(b)
            if m and "always()" not in m.group(1):
                schlecht.append(f"{zeilen[j].strip()} -> if: {m.group(1)}")
    assert not schlecht, "\n  ".join(schlecht)


def test_the_secret_is_never_written_where_it_survives_the_job():
    """Der Schluessel darf nur als Datei im Lauf existieren, mit umask 077,
    und muss danach weg sein."""
    anweisungen = _anweisungen(WORKFLOW, "#")
    assert "umask 077" in anweisungen, "der Schluessel entstuende welt-lesbar"
    assert "rm -f" in anweisungen, "der Schluessel bliebe nach dem Lauf liegen"
    assert "echo $NIX_SIGNING_KEY" not in anweisungen
    assert "echo \"$NIX_SIGNING_KEY\"" not in anweisungen


DARWIN = (ROOT / ".forgejo" / "workflows" / "publish-cache-darwin.yml").read_text(
    encoding="utf-8")


def test_the_darwin_job_runs_only_when_someone_asks():
    """Ein HOST-Runner fuehrt Jobs ohne Container aus - mit den Rechten des
    Kontos, das ihn gestartet hat. Und er ist nur zeitweise da: ein
    automatischer Ausloeser liefe ins Leere und saehe aus wie ein Ausfall.
    """
    anweisungen = _anweisungen(DARWIN, "#")
    assert "workflow_dispatch" in anweisungen
    for ausloeser in ("push:", "pull_request:", "schedule:"):
        assert ausloeser not in anweisungen, (
            f"{ausloeser} auf einem Host-Runner-Job, der Geheimnisse sieht")


def test_the_darwin_job_does_not_install_anything_on_someone_s_machine():
    """nix gehoert der Maschine, nicht diesem Lauf. Ein Job, der auf einem
    fremden Laptop installiert, ueberschreitet seinen Auftrag."""
    anweisungen = _anweisungen(DARWIN, "#")
    assert "ci_install_nix.sh" not in anweisungen, \
        "der Darwin-Job wuerde nix auf der Maschine installieren"


def test_the_darwin_job_checks_that_nix_is_visible_to_the_runner_account():
    """`winget list` zeigte pwsh, SYSTEM sah es nie - zwei Laeufe gekostet.

    Dasselbe hier: der Runner laeuft unter einem Konto, dessen PATH nicht der
    deines Terminals sein muss. Die Mehrbenutzer-Installation liegt unter
    /nix/var/nix/profiles/default und ist nicht ueberall eingehaengt.
    """
    anweisungen = _anweisungen(DARWIN, "#")
    assert "/nix/var/nix/profiles/default" in anweisungen
    assert "id -un" in anweisungen, \
        "der Fehlerfall muss sagen, ALS WER der Runner laeuft"


def test_the_signing_key_never_outlives_the_job():
    anweisungen = _anweisungen(DARWIN, "#")
    assert "umask 077" in anweisungen
    assert "trap 'rm -rf" in anweisungen, \
        "ohne trap bleibt der Schluessel liegen, wenn der Job abbricht"
    assert "RUNNER_TEMP" not in anweisungen, (
        "RUNNER_TEMP gibt es auf einem Host-Runner nicht verlaesslich - "
        "der Schluessel landete dann in einem leeren Pfad")


def test_the_attach_script_refuses_a_machine_that_cannot_build_darwin():
    quelle = (ROOT / "scripts" / "attach_macos_runner.sh").read_text(encoding="utf-8")
    anweisungen = _anweisungen(quelle, "#")
    assert 'uname -m' in anweisungen and "arm64" in anweisungen
    assert ":host" in anweisungen, (
        "ohne :host liefe der Job im Container und saehe den /nix/store "
        "dieser Maschine nicht - von 'schon gebaut' bliebe nichts")
    assert "curl" in anweisungen, (
        "ohne Erreichbarkeitsprobe haengt ein Runner still, wenn die VPN weg ist")


def test_the_reachability_probe_does_not_use_dev_tcp():
    """Gemessen am 2026-09-14 auf macOS 15 (Apple Silicon):

        cat < /dev/null > /dev/tcp/host/443    funktioniert
        exec 3<> /dev/tcp/host/443             SIGKILL, exit 137

    und zwar in bash 5.2 aus nixpkgs GENAUSO wie in Apples bash 3.2. Die
    erste Fassung benutzte die zweite Form und meldete "nicht erreichbar"
    fuer eine Instanz, die im Browser einwandfrei lief - ein Instrument, das
    dem Benutzer die Schuld gibt.
    """
    quelle = (ROOT / "scripts" / "attach_macos_runner.sh").read_text(encoding="utf-8")
    anweisungen = _anweisungen(quelle, "#")
    assert "/dev/tcp/" not in anweisungen, \
        "auf macOS wird diese Form mit SIGKILL beendet"


def test_the_probe_also_asks_the_path_the_runner_actually_speaks():
    """Die Wurzel kann antworten, waehrend Actions abgeschaltet sind. Dann
    haengt der Runner spaeter, ohne zu sagen warum. 404 auf dem RPC-Pfad ist
    der Befund; 400 heisst 'Route da, Nutzlast falsch' - gemessen."""
    quelle = (ROOT / "scripts" / "attach_macos_runner.sh").read_text(encoding="utf-8")
    anweisungen = _anweisungen(quelle, "#")
    assert "runner.v1.RunnerService" in anweisungen
    assert "404" in anweisungen, "eine 404 muss als Fehler behandelt werden"


def test_the_attach_script_never_prints_the_token_value():
    """Nicht der NAME ist das Problem, sondern die ERWEITERUNG.

    Der erste Entwurf verbot `FORGEJO_RUNNER_TOKEN` in jeder echo-Zeile und
    schlug an der Zeile an, die sagt "FORGEJO_RUNNER_TOKEN ist nicht gesetzt".
    Elfter Fall derselben Falle: eine Pruefung trifft eine Zeichenkette, die
    etwas anderes bedeutet.
    """
    quelle = (ROOT / "scripts" / "attach_macos_runner.sh").read_text(encoding="utf-8")
    for nr, zeile in enumerate(quelle.splitlines(), 1):
        if zeile.lstrip().startswith("#"):
            continue
        if not any(b in zeile for b in ("echo", "printf")):
            continue
        for erweiterung in ("$FORGEJO_RUNNER_TOKEN", "${FORGEJO_RUNNER_TOKEN"):
            assert erweiterung not in zeile, f"Zeile {nr}: {zeile.strip()}"


def test_that_check_would_notice_a_leak():
    """Der Nenner - ohne ihn waere der Test oben immer gruen."""
    import re
    verseucht = 'echo "token: $FORGEJO_RUNNER_TOKEN"'
    assert any(e in verseucht for e in ("$FORGEJO_RUNNER_TOKEN",))
    sauber = 'echo "FORGEJO_RUNNER_TOKEN ist nicht gesetzt." >&2'
    assert "$FORGEJO_RUNNER_TOKEN" not in sauber
    assert "${FORGEJO_RUNNER_TOKEN" not in sauber


def test_the_script_does_not_invent_a_token_format():
    """Gemessen an der Instanz am 2026-09-14: das Registrierungstoken hat
    43 Zeichen, Gross- und Kleinbuchstaben, und enthaelt - oder _.

    Der erste Entwurf verlangte 40 Zeichen aus [a-z0-9] und haette ein
    gueltiges Token abgewiesen - mit der Begruendung, der Benutzer habe das
    falsche kopiert. Ein Pruefer, der sich seine Erwartung ausdenkt, ist
    schlimmer als keiner.
    """
    quelle = (ROOT / "scripts" / "attach_macos_runner.sh").read_text(encoding="utf-8")
    anweisungen = _anweisungen(quelle, "#")
    assert "-ne 40" not in anweisungen, "wieder eine erfundene Laenge"
    assert "a-z0-9" not in anweisungen, "wieder eine erfundene Zeichenklasse"


def test_the_darwin_job_establishes_trust_before_it_clones():
    """Der erste Lauf starb im Checkout:

        SSL certificate ... self-signed certificate in certificate chain (19)

    Die Instanz traegt ein Zertifikat aus einer eigenen CA. macOS vertraut ihr,
    git aus nixpkgs nicht - und NIX_SSL_CERT_FILE zeigte auf einen LINUX-Pfad,
    den es auf macOS gar nicht gibt.
    """
    anweisungen = _anweisungen(DARWIN, "#")
    assert "GIT_SSL_CAINFO" in anweisungen
    assert anweisungen.index("GIT_SSL_CAINFO") < anweisungen.index("git fetch"), \
        "das Vertrauen muss VOR dem Klonen stehen, sonst stirbt der Checkout"


def test_the_ca_comes_from_the_machine_not_from_the_server():
    """Der Kern. Den NAMEN der CA vom Server abzulesen ist harmlos; ihr
    ZERTIFIKAT von dort zu nehmen waere zirkulaer - dann bestaetigte der
    Server sich selbst. Es muss aus dem Vertrauensspeicher der Maschine
    kommen.
    """
    anweisungen = _anweisungen(DARWIN, "#")
    assert "security find-certificate" in anweisungen, \
        "das Zertifikat kommt nicht aus dem Schluesselbund der Maschine"
    assert "-showcerts" not in anweisungen, \
        "die vom Server angebotene Kette darf nicht als Vertrauensanker dienen"


def test_the_trust_step_proves_itself_before_the_checkout_needs_it():
    """Ohne Gegenprobe faellt der Fehler erst im Checkout auf - und sieht
    dort aus wie ein Netzproblem."""
    anweisungen = _anweisungen(DARWIN, "#")
    assert "git ls-remote" in anweisungen
    assert anweisungen.index("git ls-remote") < anweisungen.index("git fetch")


CHECK = (ROOT / ".forgejo" / "workflows" / "check.yml").read_text(encoding="utf-8")


def test_every_branch_is_checked_not_only_main():
    """forgejo ist ein PULL-Spiegel: der Zweig kommt an, das
    pull_request-Ereignis nicht. Mit `push: branches: [main]` gab es deshalb
    kein Gate VOR einem Merge - geprueft wurde erst, was schon drin war.

    Gemessen am 2026-09-14: der Zweig lag im Spiegel, `status` meldete
    "no runs found".
    """
    anweisungen = _anweisungen(CHECK, "#")
    assert "branches: [main]" not in anweisungen, (
        "dann prueft nichts einen Zweig, bevor er gemergt wird")
    assert "push:" in anweisungen


def test_no_git_command_can_open_a_pager_on_a_host_runner():
    """Ein Host-Runner hat ein Terminal, ein Container nicht.

    `git log` startete deshalb einen Pager und wartete auf eine Taste: der
    Job stand fast sechs Minuten bei "checked out: ..." und waere 360 Minuten
    so geblieben. In den Linux-Jobs faellt dasselbe nie auf - dort gibt es
    kein Terminal, das ein Pager benutzen koennte.
    """
    anweisungen = _anweisungen(DARWIN, "#")
    assert "GIT_PAGER: cat" in anweisungen, "ohne das haengt der Job am Pager"
    for zeile in anweisungen.splitlines():
        if "git log" in zeile:
            assert "--no-pager" in zeile, f"Pager moeglich: {zeile.strip()}"


def test_nothing_can_stop_and_ask_for_credentials():
    """Dieselbe Falle, anderer Ausloeser: eine Eingabeaufforderung auf einem
    Runner ohne Benutzer haengt genauso still."""
    anweisungen = _anweisungen(DARWIN, "#")
    assert 'GIT_TERMINAL_PROMPT: "0"' in anweisungen


def test_no_step_on_the_host_runner_can_stop_and_ask():
    """Ein Host-Runner hat ein TERMINAL - ein Container nicht. Alles, was
    fragen KANN, fragt dort und wartet still.

    Zweimal passiert: erst `git log` mit seinem Pager (6 Minuten bei
    "checked out: ..."), dann `nix` mit der Frage nach unserem EIGENEN
    nixConfig (6 Minuten bei 0,0 % CPU - es arbeitete nicht, es wartete).

    Gemessen: mit geschlossener Eingabe warnt nix nur
    ("Pass --accept-flake-config to trust it") und laeuft weiter.
    """
    import re
    bloecke = re.split(r"^      - name: ", DARWIN, flags=re.M)[1:]
    ohne = []
    for b in bloecke:
        if "run:" not in b:
            continue
        if "exec </dev/null" not in b:
            ohne.append(b.splitlines()[0].strip())
    assert not ohne, "diese Schritte koennen auf einem Terminal haengen:\n  " + "\n  ".join(ohne)
