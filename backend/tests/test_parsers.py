"""Parser tests against real saved Yahoo pages (tests/fixtures, private)."""

from datetime import datetime

from conftest import fixture, taken_pages

from app.importer import parsers as P
from app.importer.detect import detect
from app.importer.source import read_page


def load(name_part: str):
    path = fixture(name_part)
    page = read_page(path.read_bytes(), path.name, None)
    return page, detect(page.url)


# ---------------------------------------------------------------- helpers

def test_number_helpers():
    assert P.num("32.30") == 32.3
    assert P.num("83%") == 83.0
    assert P.num("-") is None
    assert P.minutes("31:40") == 31.67
    assert P.intnum("12") == 12


def test_detect_page_types():
    base = "https://basketball.fantasysports.yahoo.com/nba/70793"
    assert detect(base).page_type == "league_home"
    assert detect(base + "/settings").page_type == "settings"
    assert detect(base + "/matchup").page_type == "matchup"
    k = detect(base + "/5")
    assert (k.page_type, k.league_id, k.team_id) == ("team", 70793, 5)
    k = detect(base + "/players?status=T&stat1=S_AS_2026")
    assert k.page_type == "players" and k.params["status"] == "T"
    assert detect("https://example.com/nba/70793") is None
    assert detect(None) is None


def test_waiver_date_rolls_into_next_year():
    assert P._waiver_date("W (Jan 2)", datetime(2026, 12, 30)) == "2027-01-02"
    assert P._waiver_date("W (Nov 28)", datetime(2026, 11, 25)) == "2026-11-28"


# ---------------------------------------------------------------- real pages

def test_mhtml_source_reads_url_time_and_utf8():
    page, kind = load("Engineering Fantasy League _ Fantasy")
    assert page.url == "https://basketball.fantasysports.yahoo.com/nba/70793"
    assert page.saved_at == datetime(2026, 11, 25, 23, 53, 44)
    assert "Egor Dëmin" in page.html  # non-ASCII names decode correctly
    assert kind.page_type == "league_home"


def test_settings_page():
    page, kind = load("settings.html")
    assert kind.page_type == "settings" and page.saved_at is None  # HTML files carry no save time
    s = P.parse_settings(page.html)
    assert s.scoring == {"3PTM": 1.5, "PTS": 1.0, "REB": 1.2, "AST": 1.5, "ST": 3.0, "BLK": 3.0, "TO": -1.0}
    assert s.roster_positions == ["PG", "SG", "G", "SF", "PF", "F", "C", "C", "Util", "Util", "BN", "BN", "BN", "IL", "IL"]
    assert s.max_adds_per_week == 3
    assert s.playoff_weeks == [20, 21, 22]
    assert s.trade_end_date == "2027-03-04"


def test_league_home_standings_and_transactions():
    page, kind = load("Engineering Fantasy League _ Fantasy")
    soup = P.soup_of(page.html)
    assert P.league_name(soup) == "Engineering Fantasy League"
    assert P.my_team_id(soup, 70793) == 5
    home = P.parse_league_home(page.html, 70793)
    assert len(home.standings) == 12
    me = next(r for r in home.standings if r.team_id == 5)
    assert (me.name, me.rank, me.wins, me.losses, me.points_for) == ("PokemonPinoys", 5, 3, 2, 6890.3)
    assert home.transactions and home.transactions[0].team_name


def test_league_home_lists_all_matchups_of_the_week():
    page, _ = load("Engineering Fantasy League _ Fantasy")
    home = P.parse_league_home(page.html, 70793)
    assert len(home.matchups) == 6 and {m.week for m in home.matchups} == {6}
    mine = next(m for m in home.matchups if 5 in (m.team1, m.team2))
    assert (mine.team1, mine.team2, mine.score1, mine.score2) == (5, 3, 526.2, 300.5)
    assert sorted(t for m in home.matchups for t in (m.team1, m.team2)) == list(range(1, 13))


def test_schedule_tab_gives_one_teams_season():
    page, kind = load("League schedule 2ts.mhtml")
    assert kind.page_type == "league_home"  # same address as the League page; the Schedule tab is part of it
    home = P.parse_league_home(page.html, 70793)
    s = home.schedule
    assert s is not None and s.team_id == 1  # 2ts was the team selected when saved
    assert len(s.weeks) == 19 and s.weeks[1] == 3 and s.weeks[6] == 10
    assert len(home.matchups) == 6  # the schedule table's matchup links aren't mistaken for this week's box


def test_team_page_roster():
    page, kind = load("PokemonPinoys")
    assert (kind.page_type, kind.team_id) == ("team", 5)
    team = P.parse_team(page.html, 5)
    assert team.team_name == "PokemonPinoys"
    assert len(team.roster) == 15
    first = team.roster[0]
    assert (first.slot, first.player.id, first.player.name, first.player.nba_team, first.player.positions) == (
        "PG", 10276, "Jared McCain", "OKC", "PG,SG")
    il = [e for e in team.roster if e.slot == "IL"]
    assert {e.player.name for e in il} == {"Jalen Smith", "Chet Holmgren"}
    assert all(e.player.status == "O" for e in il)


def test_matchup_page():
    page, kind = load("Fantasy Basketball _ Yahoo! Sports.mhtml")
    m = P.parse_matchup(page.html, 70793)
    assert (m.week, m.start_date, m.end_date) == (6, "2026-11-23", "2026-11-29")
    assert (m.left.team_id, m.left.team_name, m.left.score) == (5, "PokemonPinoys", 526.2)
    assert (m.right.team_id, m.right.team_name, m.right.score) == (3, "ThorAlmighty", 300.5)
    assert len(m.left.roster) == 15 and len(m.right.roster) == 15
    assert m.left.roster[0].player.id == 10276


def test_matchup_page_totals_tab():
    """The same page opened on its "Totals" tab (Yahoo's default when no games are live) has another layout."""
    page, kind = load("Matchup totals tab.mhtml")
    assert kind.page_type == "matchup"
    m = P.parse_matchup(page.html, 70793)
    assert (m.week, m.start_date, m.end_date) == (6, "2026-11-23", "2026-11-29")
    assert (m.left.team_id, m.left.score, m.right.team_id, m.right.score) == (5, 806.0, 3, 546.0)
    assert len(m.left.roster) == 15 and len(m.right.roster) == 15
    assert (m.left.roster[0].slot, m.left.roster[0].player.id) == ("PG", 10276)
    assert [e.slot for e in m.left.roster].count("IL") == 2
    # A player dropped earlier in the week is listed with slot "--": he's no longer on the roster
    assert "Isaiah Joe" not in {e.player.name for e in m.left.roster}


def test_available_players_page():
    page, kind = load("Player List _ Fantasy")
    p = P.parse_players(page.html, 70793, kind.params, page.saved_at)
    assert p.status_filter == "A" and p.window == "S_AS_2026"
    assert len(p.rows) == 25
    assert {r.owner_kind for r in p.rows} <= {"FA", "W"}
    jw = next(r for r in p.rows if r.player.name == "Jalen Williams")
    assert (jw.fpts, jw.gp, jw.player.status, jw.mpg) == (30.49, 3, "O", 31.67)
    ga = next(r for r in p.rows if r.player.name == "Grayson Allen")
    assert (ga.owner_kind, ga.waiver_until) == ("W", "2026-11-28")


def test_fantasy_points_match_league_scoring():
    """Yahoo's Fan Pts equal the league's scoring weights applied to the per-game stats."""
    page, kind = load("Player List _ Fantasy")
    weights = {"tpm": 1.5, "pts": 1.0, "reb": 1.2, "ast": 1.5, "stl": 3.0, "blk": 3.0, "tov": -1.0}
    for r in P.parse_players(page.html, 70793, kind.params, page.saved_at).rows:
        calc = sum(getattr(r, k) * w for k, w in weights.items())
        assert abs(calc - r.fpts) < 0.06, r.player.name


def test_taken_pages_cover_all_rosters():
    ids, teams = set(), set()
    for path in taken_pages():
        page = read_page(path.read_bytes(), path.name, None)
        kind = detect(page.url)
        p = P.parse_players(page.html, 70793, kind.params, page.saved_at)
        assert p.status_filter == "T"
        assert all(r.owner_kind == "team" and r.owner_team_id for r in p.rows)
        ids |= {r.player.id for r in p.rows}
        teams |= {r.owner_team_id for r in p.rows}
    assert len(ids) == 177
    assert teams == set(range(1, 13))
