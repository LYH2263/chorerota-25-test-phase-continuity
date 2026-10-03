"""skip_week：周跳过与跨周相位游标。

相位（phase）钉在 ``weeks`` 行上：``start_phase`` / ``end_phase`` 记录该周
在全局轮转游标上的起止位置。普通周与 skip 周都推进同样的网格长度
（``days * 任务数``），区别只在 skip 周不写任何 assignment。

取消 skip 时清空该周相位并回退为 draft，随后按周序重新生成即可与前后周
重新衔接——因为跳过与正常生成推进的格数相同，两侧相位始终可手算核对。
"""
from app.engines.rota import build_phase_week, grid_size

SKIP_REQUIRED_COLUMNS = ("start_phase", "end_phase", "skipped")


def migrate(c) -> None:
    """Idempotently add phase/skip columns to a pre-existing weeks table."""
    existing = {r["name"] for r in c.execute("PRAGMA table_info(weeks)")}
    for col in SKIP_REQUIRED_COLUMNS:
        if col not in existing:
            default = "0" if col == "skipped" else "NULL"
            c.execute(f"ALTER TABLE weeks ADD COLUMN {col} INTEGER DEFAULT {default}")


def _cursor_phase(c, week_id: int) -> int:
    """Phase at which week ``week_id`` starts: prior weeks' end_phase, else 0."""
    row = c.execute(
        "SELECT MAX(end_phase) AS p FROM weeks WHERE id < ? AND end_phase IS NOT NULL",
        (week_id,),
    ).fetchone()
    return row["p"] if row and row["p"] is not None else 0


def regenerate_week(c, week_id: int, member_ids: list[int], task_ids: list[int],
                    days: int = 7) -> dict:
    """Generate (or regenerate) one normal week, resuming the persisted cursor.

    空成员名册抛 ``ValueError("empty_members")`` 且不写任何数据。
    """
    week = c.execute("SELECT * FROM weeks WHERE id=?", (week_id,)).fetchone()
    if week is None:
        raise LookupError("week_not_found")
    start = _cursor_phase(c, week_id)
    result = build_phase_week(member_ids, task_ids, start, days=days)
    c.execute("DELETE FROM assignments WHERE week_id=?", (week_id,))
    for s in result["slots"]:
        c.execute(
            "INSERT INTO assignments(week_id,day,task_id,member_id) VALUES (?,?,?,?)",
            (week_id, s["day"], s["task_id"], s["member_id"]),
        )
    c.execute(
        "UPDATE weeks SET status='ready', skipped=0, start_phase=?, end_phase=? WHERE id=?",
        (result["start_phase"], result["end_phase"], week_id),
    )
    return result


def mark_skipped(c, week_id: int, member_ids: list[int], task_ids: list[int],
                 days: int = 7) -> dict:
    """Mark a week skipped: advance the phase but write no assignments."""
    week = c.execute("SELECT * FROM weeks WHERE id=?", (week_id,)).fetchone()
    if week is None:
        raise LookupError("week_not_found")
    start = _cursor_phase(c, week_id)
    end = start + grid_size(member_ids, task_ids, days)  # raises on empty members
    c.execute("DELETE FROM assignments WHERE week_id=?", (week_id,))
    c.execute(
        "UPDATE weeks SET status='skipped', skipped=1, start_phase=?, end_phase=? WHERE id=?",
        (start, end, week_id),
    )
    return {"start_phase": start, "end_phase": end, "slots": []}


def unmark_skipped(c, week_id: int) -> None:
    """Cancel a skip: clear phased footprint so the week can be regenerated."""
    week = c.execute("SELECT * FROM weeks WHERE id=?", (week_id,)).fetchone()
    if week is None:
        raise LookupError("week_not_found")
    c.execute("DELETE FROM assignments WHERE week_id=?", (week_id,))
    c.execute(
        "UPDATE weeks SET status='draft', skipped=0, start_phase=NULL, end_phase=NULL WHERE id=?",
        (week_id,),
    )
