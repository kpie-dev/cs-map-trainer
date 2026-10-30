import polars as pl
import pytest

from cs_map_trainer.analysis import RoundRow
from cs_map_trainer.match_statistics import match_statistics

PLAYER = 76561198000000001
ALLY = 76561198000000002
ENEMY = 76561198000000003
OTHER = 76561198000000004
T, CT = "terrorist", "counter-terrorist"


def kill(tick=100, attacker=PLAYER, victim=ENEMY, **kwargs):
    return {
        "tick": tick,
        "attacker_steamid": attacker,
        "victim_steamid": victim,
        "attacker_side": T,
        "victim_side": CT,
        "headshot": False,
        "assister_steamid": None,
        "assister_side": None,
        "assist_flash": False,
        **kwargs,
    }


def damage(tick=90, attacker=PLAYER, victim=ENEMY, hp=40, pre=100, **kwargs):
    return {
        "tick": tick,
        "attacker_steamid": attacker,
        "victim_steamid": victim,
        "attacker_side": T,
        "victim_side": CT,
        "dmg_health": hp,
        "health_pre": pre,
        **kwargs,
    }


def round_row(number=1, start=0, **kwargs):
    return RoundRow(
        round_num=number,
        start_tick=start,
        freeze_end_tick=start + 10,
        end_tick=start + 900,
        is_knife_round=False,
        **kwargs,
    )


def compute(kills=None, damages=None, rounds=None, snapshots=None, tickrate=64):
    rounds = rounds if rounds is not None else [round_row()]
    if snapshots is None:
        snapshots = [
            {"tick": row.freeze_end_tick, "steamid": PLAYER, "health": 100, "side": T}
            for row in rounds
        ]
    return match_statistics(
        str(PLAYER),
        rounds,
        pl.DataFrame(kills) if kills else pl.DataFrame([kill()]).clear(),
        pl.DataFrame(damages) if damages else pl.DataFrame([damage()]).clear(),
        pl.DataFrame(snapshots),
        tickrate=tickrate,
    )


def test_scoreboard_uses_all_weapons_and_hp_without_overkill_or_friendly_damage():
    result = compute(
        kills=[
            kill(headshot=True, weapon="hegrenade"),
            kill(200, attacker=ALLY, victim=PLAYER, victim_side=T),
            kill(300, attacker=PLAYER, victim=ALLY, victim_side=T),
            kill(400, attacker=PLAYER, victim=PLAYER, victim_side=T),
            kill(500, attacker=None, victim=PLAYER, attacker_side=None, victim_side=T),
        ],
        damages=[
            damage(hp=400, pre=30),
            damage(attacker=PLAYER, victim=ALLY, victim_side=T),
            damage(attacker=PLAYER, victim=PLAYER, victim_side=T),
        ],
    )
    assert (result.kills, result.deaths, result.assists) == (1, 3, 0)
    assert result.damage_hp == 30
    assert result.adr == 30
    assert result.hs_percent == 100


def test_formula_components_and_no_presentation_rounding():
    result = compute(kills=[kill(headshot=True)], damages=[damage(hp=100)])
    assert result.kpr == 1
    assert result.dpr == 0
    assert result.apr == 0
    assert result.kast == 100
    assert result.impact == pytest.approx(2.13 - 0.41)
    assert result.estimated_rating_2 == pytest.approx(
        0.0073 * 100 + 0.3591 + 0.2372 * (2.13 - 0.41) + 0.0032 * 100 + 0.1587
    )
    assert result.unavailable == {}


@pytest.mark.parametrize(
    "hp,flash,expected", [(39, False, 0), (40, False, 1), (0, True, 1), (40, True, 1)]
)
def test_rating_assists_use_40_hp_or_flash_once_per_kill(hp, flash, expected):
    result = compute(
        kills=[kill(attacker=ALLY, assister_steamid=PLAYER, assister_side=T, assist_flash=flash)],
        damages=[damage(hp=hp)],
    )
    assert result.assists == 1
    assert result.rating_assists == expected


def test_assist_damage_is_round_scoped_and_excludes_killer():
    result = compute(
        rounds=[round_row(), round_row(2, 1000)],
        kills=[kill(1100, attacker=ALLY), kill(1200)],
        damages=[damage(hp=60)],
    )
    assert result.rating_assists == 0


@pytest.mark.parametrize("delta,expected", [(319, 100), (320, 100), (321, 0)])
def test_kast_five_second_trade_inclusive_boundary(delta, expected):
    result = compute(
        kills=[
            kill(100, attacker=ENEMY, victim=PLAYER, attacker_side=CT, victim_side=T),
            kill(100 + delta, attacker=ALLY, victim=ENEMY),
        ]
    )
    assert result.kast == expected


def test_kast_rejects_teamkill_trade_and_previous_same_tick_event():
    for rows in (
        [
            kill(100, attacker=ENEMY, victim=PLAYER, attacker_side=CT, victim_side=T),
            kill(150, attacker=OTHER, victim=ENEMY, attacker_side=CT),
        ],
        [
            kill(100, attacker=ALLY, victim=ENEMY),
            kill(100, attacker=ENEMY, victim=PLAYER, attacker_side=CT, victim_side=T),
        ],
    ):
        assert compute(kills=rows).kast == 0


def test_kast_counts_round_only_once_and_survival():
    result = compute(kills=[kill(), kill(200, victim=OTHER)])
    assert result.kast == 100
    assert compute().kast == 100


def test_knife_warmup_excluded_overtime_and_side_switch_included():
    rounds = [
        round_row(),
        round_row(2, 1000),
        round_row(25, 2000),
        round_row(26, 3000, is_warmup=True),
    ]
    rounds[1].is_knife_round = True
    result = compute(
        rounds=rounds,
        kills=[kill(100), kill(1100), kill(2100, attacker_side=CT, victim_side=T), kill(3100)],
        damages=[damage(2100, attacker_side=CT, victim_side=T)],
    )
    assert result.rounds_played == 2
    assert result.kills == 2
    assert result.adr == 20


def test_participation_denominator_not_total_round_count():
    rounds = [round_row(), round_row(2, 1000)]
    result = compute(
        rounds=rounds,
        kills=[kill()],
        snapshots=[
            {"tick": 10, "steamid": PLAYER, "health": 100, "side": T},
            {"tick": 1010, "steamid": PLAYER, "health": 0, "side": T},
        ],
    )
    assert result.rounds_played == 1
    assert result.kpr == 1


def test_no_participation_and_no_kills_are_explicitly_unavailable():
    result = compute(snapshots=[])
    assert result.adr is None and result.estimated_rating_2 is None
    assert result.unavailable["adr"] == "no_participating_live_rounds"
    result = compute()
    assert result.hs_percent is None
    assert result.unavailable["hs_percent"] == "no_enemy_kills"


@pytest.mark.parametrize(
    "column,metric",
    [
        ("dmg_health", "adr"),
        ("health_pre", "adr"),
        ("attacker_side", "adr"),
    ],
)
def test_missing_damage_fields_do_not_produce_zero_or_partial_rating(column, metric):
    frame = pl.DataFrame([damage()]).drop(column)
    result = match_statistics(
        str(PLAYER),
        [round_row()],
        pl.DataFrame([kill()]),
        frame,
        pl.DataFrame([{"tick": 10, "steamid": PLAYER, "health": 100, "side": T}]),
        tickrate=64,
    )
    assert getattr(result, metric) is None
    assert result.estimated_rating_2 is None
    assert metric in result.unavailable


@pytest.mark.parametrize(
    "column,metric",
    [
        ("headshot", "hs_percent"),
        ("assister_steamid", "assists"),
        ("assist_flash", "rating_assists"),
        ("victim_side", "kills"),
    ],
)
def test_missing_native_kill_fields_are_explicit(column, metric):
    result = match_statistics(
        str(PLAYER),
        [round_row()],
        pl.DataFrame([kill()]).drop(column),
        pl.DataFrame([damage()]),
        pl.DataFrame([{"tick": 10, "steamid": PLAYER, "health": 100, "side": T}]),
        tickrate=64,
    )
    assert getattr(result, metric) is None
    assert metric in result.unavailable


def test_missing_tickrate_or_participation_snapshot_prevents_rating():
    result = compute(tickrate=None)
    assert result.kast is None and result.estimated_rating_2 is None
    result = compute(
        kills=[kill(1100)],
        rounds=[round_row(), round_row(2, 1000)],
        snapshots=[{"tick": 10, "steamid": PLAYER, "health": 100, "side": T}],
    )
    assert result.kills == 1
    assert result.kpr is None and result.estimated_rating_2 is None
    assert result.unavailable["kpr"] == "events_without_round_participation_snapshot"


def test_serialized_statistics_require_explicit_reasons_and_finite_values():
    from pydantic import ValidationError

    from cs_map_trainer.match_statistics import MatchStatistics

    payload = compute().model_dump()
    payload["unavailable"] = {}
    with pytest.raises(ValidationError, match="requires an explicit reason"):
        MatchStatistics.model_validate(payload)
    payload = compute(kills=[kill()]).model_dump()
    payload["estimated_rating_2"] = float("nan")
    with pytest.raises(ValidationError):
        MatchStatistics.model_validate(payload)
