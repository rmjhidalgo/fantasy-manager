"""Parsers for each Yahoo Fantasy Basketball page type.

Each parser takes the page HTML and returns plain dataclasses; nothing here touches
the database. Parsers look for stable markers (table ids, link patterns, header
names) rather than column positions where possible, so small layout changes on
Yahoo's side don't silently shift data into the wrong fields.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime

from bs4 import BeautifulSoup, Tag


class ParseError(ValueError):
    pass


# ---------------------------------------------------------------- shared helpers

def soup_of(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


_ICON_CHARS = re.compile(r"[-]")  # Yahoo's icon font (sort arrows etc.)


def _text(node: Tag | None) -> str:
    if not node:
        return ""
    s = node.get_text(" ", strip=True).replace("\xa0", " ")
    return re.sub(r"\s+", " ", _ICON_CHARS.sub("", s)).strip()


def num(s: str | None) -> float | None:
    """'32.30' -> 32.3, '83%' -> 83.0, '-' / '' -> None."""
    if s is None:
        return None
    s = s.strip().replace(",", "").rstrip("%")
    if s in ("", "-", "—", "–"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def intnum(s: str | None) -> int | None:
    v = num(s)
    return int(v) if v is not None else None


def minutes(s: str | None) -> float | None:
    """'31:40' -> 31.67 minutes."""
    if not s or ":" not in s:
        return num(s)
    m, _, sec = s.strip().partition(":")
    try:
        return round(int(m) + int(sec) / 60, 2)
    except ValueError:
        return None


_LEAGUE_NAME = re.compile(r"Viewing Info for League:\s*(.+?)\s*\(ID#\s*(\d+)\)")


def league_name(soup: BeautifulSoup) -> str | None:
    m = _LEAGUE_NAME.search(soup.get_text(" ", strip=True)[:20000])
    return m.group(1) if m else None


def my_team_id(soup: BeautifulSoup, league_id: int) -> int | None:
    """The signed-in user's team, from the 'My Team' link in Yahoo's navigation."""
    pat = re.compile(rf"/nba/{league_id}/(\d+)/?$")
    for a in soup.find_all("a", href=pat):
        if a.get_text(strip=True) == "My Team":
            return int(pat.search(a["href"]).group(1))
    return None


def _team_id_from_href(href: str | None, league_id: int) -> int | None:
    if not href:
        return None
    m = re.search(rf"/nba/{league_id}/(\d+)/?(?:[?#]|$)", href)
    return int(m.group(1)) if m else None


@dataclass
class PlayerRef:
    id: int
    name: str
    nba_team: str | None
    positions: str | None  # "PG,SG"
    status: str | None  # O, Q, GTD, ... (None = healthy / not shown)


_TEAM_POS = re.compile(r"^([A-Z]{2,4})\s+-\s+([A-Z,]+)$")


def player_cell(td: Tag) -> PlayerRef | None:
    """Player cell used on team pages and players lists."""
    a = td.find("a", href=re.compile(r"/nba/players/\d+$"))
    if not a:
        return None
    pid = int(re.search(r"/(\d+)$", a["href"]).group(1))
    name = a.get("title") or a.get_text(strip=True)
    status_el = td.find(class_="F-injury")
    status = _text(status_el) or None
    nba_team = positions = None
    for span in td.find_all("span"):
        m = _TEAM_POS.match(span.get_text(strip=True))
        if m:
            nba_team, positions = m.group(1), m.group(2)
            break
    return PlayerRef(pid, name, nba_team, positions, status)


# ---------------------------------------------------------------- settings

@dataclass
class SettingsPage:
    league_name: str | None
    raw: dict[str, str]
    scoring: dict[str, float]  # stat abbreviation -> points, e.g. {"PTS": 1.0, "TO": -1.0}
    roster_positions: list[str]
    max_adds_per_week: int | None
    playoff_weeks: list[int]
    trade_end_date: str | None


def parse_settings(html: str) -> SettingsPage:
    soup = soup_of(html)
    raw: dict[str, str] = {}
    scoring: dict[str, float] = {}
    table = soup.find("table", id="settings-table")
    if not table:
        raise ParseError("Settings table not found")
    for tbl in [table, *table.find_all_next("table")]:
        for tr in tbl.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) != 2:
                continue
            key = _text(cells[0]).rstrip(":").strip()
            val = _text(cells[1])
            m = re.search(r"\(([A-Z0-9%]+)\)$", key)
            if m and num(val) is not None:
                scoring[m.group(1)] = num(val)
            elif key:
                raw[key] = val
    positions = [p.strip() for p in raw.get("Roster Positions", "").split(",") if p.strip()]
    playoffs = raw.get("Playoffs", "")
    weeks_part = playoffs.split("Week", 1)[1].split("(")[0] if "Week" in playoffs else ""
    playoff_weeks = [int(w) for w in re.findall(r"\d+", weeks_part)]
    trade_end = None
    if raw.get("Trade End Date"):
        try:
            trade_end = datetime.strptime(raw["Trade End Date"], "%B %d, %Y").date().isoformat()
        except ValueError:
            trade_end = raw["Trade End Date"]
    return SettingsPage(
        league_name=raw.get("League Name"),
        raw=raw,
        scoring=scoring,
        roster_positions=positions,
        max_adds_per_week=intnum(raw.get("Max Acquisitions per Week")),
        playoff_weeks=playoff_weeks,
        trade_end_date=trade_end,
    )


# ---------------------------------------------------------------- standings + transactions

@dataclass
class StandingRow:
    team_id: int
    name: str
    rank: int | None
    wins: int | None
    losses: int | None
    ties: int | None
    points_for: float | None
    waiver_priority: int | None
    moves: int | None


@dataclass
class TransactionRow:
    team_name: str | None
    when_text: str | None
    description: str


@dataclass
class WeekMatchup:
    week: int
    team1: int
    team2: int
    score1: float | None
    score2: float | None


@dataclass
class LeagueHomePage:
    standings: list[StandingRow]
    transactions: list[TransactionRow]
    matchups: list[WeekMatchup] = field(default_factory=list)


def _league_matchups(soup: BeautifulSoup, league_id: int) -> list[WeekMatchup]:
    """This week's matchups box: 'View Matchup' links (week, mid1, mid2) with both teams' scores next to them.

    Each row reads like "PokemonPinoys 3-2-0 | 5th 526.20 1327.21 vs 300.50 1305.94 ThorAlmighty ...":
    current score then Yahoo's projection, for each side.
    """
    out: list[WeekMatchup] = []
    seen: set[tuple[int, int, int]] = set()
    for a in soup.find_all("a", href=re.compile(r"matchup\?.*week=\d+.*mid1=\d+.*mid2=\d+")):
        q = dict(re.findall(r"(week|mid1|mid2)=(\d+)", a["href"]))
        week, t1, t2 = int(q["week"]), int(q["mid1"]), int(q["mid2"])
        if (week, t1, t2) in seen:
            continue
        # Smallest ancestor that holds links to both teams = this matchup's row
        box = a.parent
        while box is not None:
            ids = {_team_id_from_href(x["href"], league_id) for x in box.find_all("a", href=True)}
            if t1 in ids and t2 in ids:
                break
            box = box.parent
        if box is None:
            continue
        text = _text(box)
        left, _, right = text.partition(" vs ")
        s1 = re.findall(r"\d+\.\d{2}", left)
        s2 = re.findall(r"\d+\.\d{2}", right)
        seen.add((week, t1, t2))
        out.append(WeekMatchup(week, t1, t2, float(s1[0]) if s1 else None, float(s2[0]) if s2 else None))
    return out


def parse_league_home(html: str, league_id: int) -> LeagueHomePage:
    soup = soup_of(html)
    table = soup.find("table", id="standingstable")
    if not table:
        raise ParseError("Standings table not found")
    header = [_text(th) for th in table.find("tr").find_all(["th", "td"])]
    col = {h: i for i, h in enumerate(header)}
    rows: list[StandingRow] = []
    for tr in table.find_all("tr")[1:]:
        tds = tr.find_all("td")
        if len(tds) < len(header):
            continue
        # The cell has a logo link and a name link to the same team; use the one with text.
        links = [a for a in tds[col["Team"]].find_all("a", href=True) if _text(a)]
        team_link = links[0] if links else None
        team_id = _team_id_from_href(team_link and team_link["href"], league_id)
        if team_id is None:
            continue
        w = l = t = None
        wlt = _text(tds[col["W-L-T"]]) if "W-L-T" in col else ""
        if re.fullmatch(r"\d+-\d+-\d+", wlt):
            w, l, t = (int(x) for x in wlt.split("-"))

        def cell(name: str) -> str | None:
            return _text(tds[col[name]]) if name in col else None

        rows.append(
            StandingRow(
                team_id=team_id,
                name=_text(team_link),
                rank=intnum(cell("Rank")),
                wins=w,
                losses=l,
                ties=t,
                points_for=num(cell("Pts")),
                waiver_priority=intnum(cell("Waiver")),
                moves=intnum(cell("Moves")),
            )
        )
    if not rows:
        raise ParseError("No teams found in the standings table")

    txs: list[TransactionRow] = []
    tx_section = soup.find(id="transactions")
    if tx_section:
        for tr in tx_section.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue
            desc = _text(tds[1])
            who = tds[2]
            team_a = who.find("a")
            team_name = _text(team_a) or None
            when = _text(who).replace(team_name or "", "", 1).strip() or None
            if desc:
                txs.append(TransactionRow(team_name, when, desc))
    return LeagueHomePage(rows, txs, _league_matchups(soup, league_id))


# ---------------------------------------------------------------- team roster

@dataclass
class RosterEntry:
    slot: str
    player: PlayerRef


@dataclass
class TeamPage:
    team_id: int
    team_name: str | None
    roster: list[RosterEntry]


def parse_team(html: str, team_id: int) -> TeamPage:
    soup = soup_of(html)
    table = soup.find("table", id="statTable0")
    if not table:
        raise ParseError("Roster table not found")
    roster: list[RosterEntry] = []
    for tr in table.find_all("tr"):
        pos_td = tr.find("td", class_="pos")
        player_td = tr.find("td", class_="player")
        if not pos_td or not player_td:
            continue
        ref = player_cell(player_td)
        if ref is None:  # "(Empty)" slot
            continue
        roster.append(RosterEntry(slot=_text(pos_td), player=ref))
    if not roster:
        raise ParseError("No players found on the roster")
    team_name = None
    title = soup.title.get_text(strip=True) if soup.title else ""
    m = re.match(r"(.+?) - (.+?) \| Fantasy Basketball", title)
    if m:
        team_name = m.group(2)
    return TeamPage(team_id, team_name, roster)


# ---------------------------------------------------------------- matchup

@dataclass
class MatchupSide:
    team_id: int
    team_name: str
    score: float | None
    roster: list[RosterEntry]


@dataclass
class MatchupPage:
    week: int | None
    start_date: str | None
    end_date: str | None
    left: MatchupSide
    right: MatchupSide


_MATCHUP_TEAM_POS = re.compile(r"^([A-Z]{2,4})\s+-\s+([A-Z,]+)$")


def _matchup_player(td: Tag) -> PlayerRef | None:
    note = td.find("a", id=re.compile(r"^playernote-\d+$"))
    name_a = td.find("a")
    if not note or not name_a:
        return None
    pid = int(note["id"].split("-")[1])
    nba_team = positions = None
    for span in td.find_all("span"):
        m = _MATCHUP_TEAM_POS.match(span.get_text(strip=True))
        if m:
            nba_team, positions = m.group(1), m.group(2)
            break
    # Names here are abbreviated ("J. McCain"); status isn't marked reliably.
    return PlayerRef(pid, name_a.get_text(strip=True), nba_team, positions, None)


def parse_matchup(html: str, league_id: int) -> MatchupPage:
    soup = soup_of(html)
    week = None
    nav = soup.find(id="matchup_selectlist_nav")
    if nav and nav.get("title"):
        m = re.search(r"Week\s+(\d+)", nav["title"])
        week = int(m.group(1)) if m else None
    dates = sorted(
        set(re.findall(r"date=(\d{4}-\d{2}-\d{2})", " ".join(a["href"] for a in soup.find_all("a", href=True) if "/matchup" in a["href"])))
    )

    # Header: the two big team links, and the two scores between them.
    team_links = [
        a for a in soup.find_all("a", href=re.compile(rf"/nba/{league_id}/\d+/?$"))
        if "Fz(26px)" in (a.get("class") or [])
    ]
    if len(team_links) < 2:
        raise ParseError("Matchup teams not found")
    left_a, right_a = team_links[0], team_links[1]
    container = left_a
    while container is not None and right_a not in container.find_all("a"):
        container = container.parent
    scores = [
        float(s) for s in re.findall(r"(?<![\d.])(\d+\.\d{2})(?![\d.])", container.get_text(" ", strip=True))
    ] if container else []

    # Rosters: rows of the big table with a slot in the middle column.
    left_roster: list[RosterEntry] = []
    right_roster: list[RosterEntry] = []
    table = None
    for t in soup.find_all("table"):
        heads = [_text(th) for th in t.find_all("th")]
        if heads.count("Player") == 2 and "Pos" in heads:
            table = t
            break
    if table is None:
        raise ParseError("Matchup roster table not found")
    for tr in table.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 3:
            continue
        mid = len(tds) // 2
        slot = _text(tds[mid])
        if not slot or slot == "TOTAL":
            continue
        lp, rp = _matchup_player(tds[0]), _matchup_player(tds[mid + 1])
        if lp:
            left_roster.append(RosterEntry(slot, lp))
        if rp:
            right_roster.append(RosterEntry(slot, rp))

    def side(a: Tag, score: float | None, roster: list[RosterEntry]) -> MatchupSide:
        return MatchupSide(_team_id_from_href(a["href"], league_id), _text(a), score, roster)

    return MatchupPage(
        week=week,
        start_date=dates[0] if dates else None,
        end_date=dates[-1] if dates else None,
        left=side(left_a, scores[0] if len(scores) > 0 else None, left_roster),
        right=side(right_a, scores[1] if len(scores) > 1 else None, right_roster),
    )


# ---------------------------------------------------------------- players list

@dataclass
class PlayerListRow:
    player: PlayerRef
    owner_kind: str  # "team" | "FA" | "W"
    owner_team_id: int | None
    waiver_until: str | None  # ISO date
    gp: int | None
    fpts: float | None
    rank_preseason: int | None
    rank_current: int | None
    pct_rostered: float | None
    mpg: float | None
    tpm: float | None
    pts: float | None
    reb: float | None
    ast: float | None
    stl: float | None
    blk: float | None
    tov: float | None


@dataclass
class PlayersPage:
    status_filter: str | None  # A (available), T (taken), ALL, FA, W ...
    window: str | None  # stat1, e.g. S_AS_2026
    rows: list[PlayerListRow]


_WAIVER = re.compile(r"^W\s*\((\w{3})\s+(\d{1,2})\)$")


def _waiver_date(text: str, saved_at: datetime | None) -> str | None:
    m = _WAIVER.match(text)
    if not m:
        return None
    ref = (saved_at or datetime.now()).date()
    try:
        d = datetime.strptime(f"{m.group(1)} {m.group(2)} {ref.year}", "%b %d %Y").date()
    except ValueError:
        return None
    if d < ref.replace(day=1) and ref.month == 12:  # e.g. "Jan 2" seen in late December
        d = d.replace(year=ref.year + 1)
    return d.isoformat()


def parse_players(html: str, league_id: int, params: dict[str, str], saved_at: datetime | None) -> PlayersPage:
    soup = soup_of(html)
    table = None
    header: list[str] = []
    for t in soup.find_all("table"):
        for tr in t.find_all("tr")[:3]:
            cells = [_text(c) for c in tr.find_all(["th", "td"])]
            if "Players" in cells and "Roster Status" in cells:
                table, header = t, cells
                break
        if table:
            break
    if table is None:
        raise ParseError("Players table not found")
    col = {h.rstrip("*").strip(): i for i, h in enumerate(header) if h}

    def cell(tds: list[Tag], name: str) -> str | None:
        i = col.get(name)
        return _text(tds[i]) if i is not None and i < len(tds) else None

    rows: list[PlayerListRow] = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        player_td = tr.find("td", class_="player")
        if not player_td or len(tds) < len(col):
            continue
        ref = player_cell(player_td)
        if ref is None:
            continue
        status_td = tds[col["Roster Status"]]
        status_text = _text(status_td)
        team_a = status_td.find("a", href=True)
        owner_team = _team_id_from_href(team_a and team_a["href"], league_id)
        if owner_team is not None:
            kind, waiver = "team", None
        elif status_text.startswith("W"):
            kind, waiver = "W", _waiver_date(status_text, saved_at)
        elif status_text == "FA":
            kind, waiver = "FA", None
        else:
            continue  # unknown status: don't guess
        rows.append(
            PlayerListRow(
                player=ref,
                owner_kind=kind,
                owner_team_id=owner_team,
                waiver_until=waiver,
                gp=intnum(cell(tds, "GP")),
                fpts=num(cell(tds, "Fan Pts")),
                rank_preseason=intnum(cell(tds, "Pre-Season")),
                rank_current=intnum(cell(tds, "Current")),
                pct_rostered=num(cell(tds, "% Ros")),
                mpg=minutes(cell(tds, "MPG")),
                tpm=num(cell(tds, "3PTM")),
                pts=num(cell(tds, "PTS")),
                reb=num(cell(tds, "REB")),
                ast=num(cell(tds, "AST")),
                stl=num(cell(tds, "ST")),
                blk=num(cell(tds, "BLK")),
                tov=num(cell(tds, "TO")),
            )
        )

    window = params.get("stat1")
    if not window:
        m = re.search(r"stat1=([A-Za-z0-9_]+)", html)
        window = m.group(1) if m else None
    return PlayersPage(
        status_filter=(params.get("status") or "A").upper(),
        window=window.upper() if window else None,
        rows=rows,
    )
