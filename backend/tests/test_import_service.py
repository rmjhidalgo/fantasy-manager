"""Import service: storing pages, duplicates, and the freshness rule."""

from datetime import datetime

from conftest import FIXTURES, fixture
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.db.models import Ownership, Player, RosterSlot
from app.importer.service import import_bytes, import_path
from app.importer.source import read_page


def import_all():
    results = [import_path(p, source="upload") for p in sorted(FIXTURES.glob("*")) if p.is_file()]
    assert all(r.status in ("imported", "partial") for r in results), [(r.filename, r.status, r.summary) for r in results]
    return results


def test_import_everything_and_overview(fresh_db):
    fixture("PokemonPinoys")  # skip if fixtures missing
    import_all()
    from app.main import app

    with TestClient(app) as client:
        ov = client.get("/api/overview").json()
        leagues = client.get("/api/leagues").json()["leagues"]
    assert leagues == [{"id": 70793, "name": "Engineering Fantasy League", "my_team_id": 5, "my_team_name": "PokemonPinoys", "active": True}]
    assert ov["league"]["my_team_name"] == "PokemonPinoys"
    assert len(ov["standings"]) == 12 and ov["standings"][4]["is_me"]
    assert len(ov["my_roster"]) == 15
    assert ov["matchup"]["week"] == 6 and ov["matchup"]["opp_name"] == "ThorAlmighty"
    # The schedule fixture is a League page saved ~4 hours later: its fresher score wins
    assert ov["matchup"]["my_score"] == 757.3
    assert ov["players"]["rostered_known"] >= 177
    assert ov["players"]["free_agents_known"] + ov["players"]["waivers_known"] == 25
    assert ov["settings"]["max_adds_per_week"] == 3
    for key in ("settings", "standings", "my_roster", "matchup", "players", "stats"):
        assert ov["freshness"][key], key
    # Full names win over the matchup page's abbreviations ("J. McCain")
    mc = next(p for p in ov["my_roster"] if p["player_id"] == 10276)
    assert mc["name"] == "Jared McCain" and mc["fpts"] is not None


def test_same_file_twice_is_a_duplicate(fresh_db):
    path = fixture("PokemonPinoys")
    assert import_path(path).status == "imported"
    assert import_path(path).status == "duplicate"


def test_unsupported_files(fresh_db):
    r = import_bytes(b"hello", "notes.txt")
    assert r.status == "unsupported"
    r = import_bytes(b"<html><body>hi</body></html>", "random.html", fallback_saved_at=datetime(2026, 11, 1))
    assert r.status == "unsupported"


def _with_date(data: bytes, new_date: str) -> bytes:
    """Same page, different save time (MHTML 'Date:' header)."""
    old = b"Date: Wed, 25 Nov 2026 23:53:14 +0000"
    if old not in data:
        old = b"Date: Wed, 25 Nov 2026 23:53:14 GMT"
    assert old in data
    return data.replace(old, b"Date: " + new_date.encode(), 1)


def test_older_page_never_overwrites_newer(fresh_db):
    path = fixture("PokemonPinoys")
    data = path.read_bytes()
    assert import_bytes(data, path.name).status == "imported"

    with SessionLocal() as db:
        # Simulate a later change: Okoro was dropped (newer data than the page).
        db.query(RosterSlot).filter_by(player_id=6397).delete()
        db.query(Ownership).filter_by(player_id=6397).delete()
        db.commit()

    older = import_bytes(_with_date(data, "Tue, 24 Nov 2026 10:00:00 GMT"), path.name)
    assert older.status == "partial"
    assert "older" in older.warnings[0]
    with SessionLocal() as db:
        assert db.query(RosterSlot).filter_by(player_id=6397).count() == 0  # old page didn't bring him back

    newer = import_bytes(_with_date(data, "Fri, 27 Nov 2026 10:00:00 GMT"), path.name)
    assert newer.status == "imported"
    with SessionLocal() as db:
        assert db.query(RosterSlot).filter_by(player_id=6397).count() == 1


def test_dropped_player_loses_team_ownership(fresh_db):
    path = fixture("PokemonPinoys")
    data = path.read_bytes()
    import_bytes(data, path.name)
    # A newer roster page (saved as plain HTML) without Isaac Okoro
    page = read_page(data, path.name, None)
    assert "/nba/players/6397" in page.html
    html = page.html.replace("/nba/players/6397", "/nba/not-a-player/6397")
    newer = f"<!-- saved from url=(0052){page.url} -->\n{html}".encode()
    res = import_bytes(newer, "team.html", fallback_saved_at=datetime(2026, 11, 27, 10))
    assert res.status == "imported", res
    with SessionLocal() as db:
        assert db.get(Ownership, (70793, 6397)) is None
        assert db.query(RosterSlot).filter_by(team_id=5).count() == 14
        assert db.get(Player, 6397) is not None  # the player is still known


def test_upload_endpoint(fresh_db):
    path = fixture("PokemonPinoys")
    from app.main import app

    with TestClient(app) as client:
        r = client.post(
            "/api/import",
            files=[("files", (path.name, path.read_bytes(), "application/octet-stream"))],
            data={"last_modified": "0"},
        )
        assert r.status_code == 200
        res = r.json()["results"][0]
        assert res["status"] == "imported" and res["page_label"] == "Team roster"
        hist = client.get("/api/imports").json()["imports"]
        assert hist[0]["status"] == "imported"
