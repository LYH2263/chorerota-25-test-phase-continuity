"""补相位跨周连续回归——场景夹具模块。

只负责“搭世界 + 执行动作”，不做断言：每组场景在隔离库上按顺序操作若干周，
记录周的顺序与 skip 状态。相位期望值全部由断言助手用 app.engines.phase
从游标 0 手算推出，避免场景与断言两边各写一份预期数字互相抄。

固定尺寸：3 个成员、2 个任务、7 天 → 每周推进 14 格，14 % 3 = 2，
跨周相位衔接可直接手算。
"""

from dataclasses import dataclass

from app.modules import skip_week

DAYS = 7
ADVANCE_PER_WEEK = 2 * DAYS  # 14


@dataclass
class ScenarioRun:
    name: str
    conn: object
    member_ids: list[int]
    task_ids: list[int]
    week_order: list[int]            # 相位链上的周顺序
    week_skipped: dict[int, bool]    # week_id -> 最终是否 skip
    error: str | None = None         # 期望非法场景捕获到的错误码

    def week_advance(self, week_id: int) -> int:
        return ADVANCE_PER_WEEK


def _active_clean_members(conn) -> list[int]:
    return [r["id"] for r in conn.execute(
        "SELECT id FROM members WHERE active=1 AND data_quality='clean' ORDER BY id")]


def build_two_consecutive_weeks(roster: dict) -> ScenarioRun:
    """场景一：两周连续生成，第二周起点必须接第一周终点。"""
    conn, mids, tids, w = roster["conn"], roster["member_ids"], roster["task_ids"], roster["weeks"]
    skip_week.generate_week(conn, w["w1"], mids, tids, DAYS)
    skip_week.generate_week(conn, w["w2"], mids, tids, DAYS)
    return ScenarioRun(
        name="两周连续生成", conn=conn, member_ids=mids, task_ids=tids,
        week_order=[w["w1"], w["w2"]], week_skipped={w["w1"]: False, w["w2"]: False})


def build_skip_week_between(roster: dict) -> ScenarioRun:
    """场景二：中间周 skip（不落格但推进相位），两侧生成周依旧首尾相接。"""
    conn, mids, tids, w = roster["conn"], roster["member_ids"], roster["task_ids"], roster["weeks"]
    skip_week.generate_week(conn, w["w1"], mids, tids, DAYS)
    skip_week.mark_skip(conn, w["w2"], tids, DAYS)
    skip_week.generate_week(conn, w["w3"], mids, tids, DAYS)
    return ScenarioRun(
        name="中间插入skip周再生成", conn=conn, member_ids=mids, task_ids=tids,
        week_order=[w["w1"], w["w2"], w["w3"]],
        week_skipped={w["w1"]: False, w["w2"]: True, w["w3"]: False})


def build_skip_then_unskip_regenerate(roster: dict) -> ScenarioRun:
    """场景三：skip 后取消 skip 并重生成——相位窗保留，后续周衔接不变。"""
    conn, mids, tids, w = roster["conn"], roster["member_ids"], roster["task_ids"], roster["weeks"]
    skip_week.generate_week(conn, w["w1"], mids, tids, DAYS)
    skip_week.mark_skip(conn, w["w2"], tids, DAYS)
    skip_week.unskip(conn, w["w2"])
    # 重生成已有相位窗的周：必须回填原窗口，游标不得二次推进。
    skip_week.generate_week(conn, w["w2"], mids, tids, DAYS)
    skip_week.generate_week(conn, w["w3"], mids, tids, DAYS)
    return ScenarioRun(
        name="skip后取消skip重生成", conn=conn, member_ids=mids, task_ids=tids,
        week_order=[w["w1"], w["w2"], w["w3"]],
        week_skipped={w["w1"]: False, w["w2"]: False, w["w3"]: False})


def build_empty_members(roster: dict) -> ScenarioRun:
    """场景四：非法——没有任何有效成员时生成必须被拒，相位不得被推进。"""
    conn, mids, tids, w = roster["conn"], roster["member_ids"], roster["task_ids"], roster["weeks"]
    conn.execute("UPDATE members SET active=0 WHERE id IN (%s)" %
                 ",".join("?" * len(mids)), mids)
    conn.commit()
    error = None
    try:
        skip_week.generate_week(conn, w["w1"], _active_clean_members(conn), tids, DAYS)
    except ValueError as exc:
        error = str(exc)
    return ScenarioRun(
        name="非法空成员生成", conn=conn, member_ids=mids, task_ids=tids,
        week_order=[w["w1"]], week_skipped={w["w1"]: False}, error=error)


SCENARIO_BUILDERS = [
    build_two_consecutive_weeks,
    build_skip_week_between,
    build_skip_then_unskip_regenerate,
    build_empty_members,
]
