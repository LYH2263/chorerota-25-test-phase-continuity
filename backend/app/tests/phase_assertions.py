"""补相位跨周连续回归——断言助手模块。

与场景夹具分离：只负责从数据库“两侧”读回相位并核对。

* 周行侧：weeks.phase_start / phase_end / advance（skipped 周也在）。
* 游标侧：phase_cursor.phase 单行游标。

期望值不手写数字，全部用 app.engines.phase 从游标 0 手算，保证
“两侧读回同钉、可手算衔接”。任何断言失败都会先打印场景名和两侧相位。
"""

from app.engines import phase as phase_eng


def read_week_row(conn, week_id: int) -> dict:
    row = conn.execute(
        "SELECT skipped, phase_start, phase_end, advance, status "
        "FROM weeks WHERE id=?", (week_id,)).fetchone()
    return dict(row) if row is not None else None


def read_assignment_members(conn, week_id: int) -> list[int]:
    """按周内格顺序（day, task_id）读回实际落格成员。"""
    rows = conn.execute(
        "SELECT member_id FROM assignments WHERE week_id=? "
        "ORDER BY day, task_id", (week_id,)).fetchall()
    return [r["member_id"] for r in rows]


def read_cursor_phase(conn) -> int:
    row = conn.execute("SELECT phase FROM phase_cursor WHERE id=1").fetchone()
    return None if row is None else row["phase"]


def _both_sides_snapshot(run) -> str:
    lines = [f"[场景] {run.name}", "  周行侧 (weeks):"]
    for wid in run.week_order:
        w = read_week_row(run.conn, wid)
        lines.append(
            f"    week {wid}: skipped={w['skipped']} "
            f"phase_start={w['phase_start']} phase_end={w['phase_end']} "
            f"advance={w['advance']} status={w['status']}")
    lines.append(f"  游标侧 (phase_cursor): phase={read_cursor_phase(run.conn)}")
    return "\n".join(lines)


def _fail(run, detail: str):
    snap = _both_sides_snapshot(run)
    print("\n相位断言失败\n" + snap + f"\n  不一致: {detail}")
    raise AssertionError(f"[{run.name}] {detail}\n{snap}")


def assert_empty_members_rejected(run) -> None:
    """非法空成员：报错码正确，且周行/游标两侧都不得被推进。"""
    if run.error != "empty_members":
        _fail(run, f"期望抛 empty_members，实际 error={run.error!r}")
    wid = run.week_order[0]
    w = read_week_row(run.conn, wid)
    if w["phase_start"] is not None or w["phase_end"] is not None:
        _fail(run, "非法生成竟在周行侧留下相位窗 "
                   f"start={w['phase_start']} end={w['phase_end']}")
    if read_assignment_members(run.conn, wid):
        _fail(run, "非法生成竟落下了 assignment 格")
    cursor = read_cursor_phase(run.conn)
    if cursor != 0:
        _fail(run, f"非法生成后游标侧被推进到 {cursor}，期望仍为 0")


def assert_phase_chain(run) -> None:
    """正常场景核心断言：周行/游标两侧同钉，相邻周首尾相接，可手算复核。"""
    if run.error is not None:
        _fail(run, f"不应出错却捕获到 {run.error!r}")

    conn = run.conn
    advances = [run.week_advance(wid) for wid in run.week_order]
    windows, final_cursor = phase_eng.chain_phases(advances, initial=0)

    prev_end = None
    for wid, (exp_start, exp_end) in zip(run.week_order, windows):
        w = read_week_row(conn, wid)
        skipped = bool(run.week_skipped[wid])

        # 周行侧必须与手算窗口同钉。
        if (w["phase_start"], w["phase_end"], w["advance"]) != (exp_start, exp_end, exp_end - exp_start):
            _fail(run, f"week {wid} 周行侧相位窗 "
                       f"({w['phase_start']},{w['phase_end']},{w['advance']}) "
                       f"!= 手算 ({exp_start},{exp_end},{exp_end - exp_start})")

        # 后一周起点接前一周终点（含 skip 周夹在中间的情况）。
        if prev_end is not None and w["phase_start"] != prev_end:
            _fail(run, f"week {wid} 起点相位 {w['phase_start']} "
                       f"未接前一周终点 {prev_end}")
        prev_end = w["phase_end"]

        members = read_assignment_members(conn, wid)
        if skipped:
            # skip 周不落格……
            if members:
                _fail(run, f"skip 周 {wid} 不应落格，却有 {len(members)} 个 assignment")
        else:
            # ……生成周的逐格成员必须等于从起点手算的轮值序列。
            expected_members = phase_eng.expected_members(run.member_ids, exp_start, exp_end - exp_start)
            if members != expected_members:
                _fail(run, f"week {wid} 落格成员 {members} != 手算 {expected_members}")
            # 首格也单独用单点相位函数复核一次。
            if phase_eng.member_at_phase(exp_start, run.member_ids) != members[0]:
                _fail(run, f"week {wid} 首格成员与相位 {exp_start} 手算不符")

    # 游标侧：必须钉在链尾，与最后一周（即使是 skip 周）的终点一致。
    cursor = read_cursor_phase(conn)
    if cursor != final_cursor:
        _fail(run, f"游标侧 phase={cursor} != 手算链尾 {final_cursor}")
    last_w = read_week_row(conn, run.week_order[-1])
    if last_w["phase_end"] != cursor:
        _fail(run, f"两侧不同钉：周行侧末周终点={last_w['phase_end']} "
                   f"但游标侧={cursor}")
