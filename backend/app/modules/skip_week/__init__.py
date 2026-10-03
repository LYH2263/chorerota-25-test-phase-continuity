"""skip_week：跨周相位游标的落格、跳周与重生成。

相位持久化两侧同钉（两种实现取舍都保留，读回必须一致）：

* 周行侧：``weeks`` 表新增 ``phase_start / phase_end / advance``，钉住每一周
  占据的相位窗；skipped 周的窗口照常落库，只是没有任何 assignment 格。
* 游标侧：独立的 ``phase_cursor`` 单行表，记录“下一个新周将从哪一个相位
  开始”。

不变量：生成/跳周完成后，``phase_cursor.phase`` 等于全部已占位周中最大的
``phase_end``；周链上相邻两周满足 ``后一周.phase_start == 前一周.phase_end``。
skip 周不落 assignment 格，但仍推进整整一周的相位（``任务数*天数``）。
对已经有相位窗的周做重生成（含取消 skip 后重生成）只重落格、回填原窗口，
不重复推进游标。
"""

from app.engines.rota import build_week_slots

_ADDED_COLUMNS = ("skipped", "phase_start", "phase_end", "advance")


def ensure_schema(c) -> None:
    """给老库补列并建立独立游标表（幂等）。"""
    existing = {r["name"] for r in c.execute("PRAGMA table_info(weeks)")}
    if "skipped" not in existing:
        c.execute("ALTER TABLE weeks ADD COLUMN skipped INT NOT NULL DEFAULT 0")
    if "phase_start" not in existing:
        c.execute("ALTER TABLE weeks ADD COLUMN phase_start INT")
    if "phase_end" not in existing:
        c.execute("ALTER TABLE weeks ADD COLUMN phase_end INT")
    if "advance" not in existing:
        c.execute("ALTER TABLE weeks ADD COLUMN advance INT")
    c.execute(
        "CREATE TABLE IF NOT EXISTS phase_cursor("
        "id INTEGER PRIMARY KEY CHECK(id=1), phase INT NOT NULL DEFAULT 0)"
    )
    c.execute(
        "INSERT OR IGNORE INTO phase_cursor(id, phase) VALUES (1, 0)"
    )
    c.commit()


def read_cursor(c) -> int:
    row = c.execute("SELECT phase FROM phase_cursor WHERE id=1").fetchone()
    return 0 if row is None else row["phase"]


def _set_cursor_forward(c, phase_end: int) -> None:
    """游标只进不退：重生成历史周不能回卷后续周已经占走的相位。"""
    c.execute(
        "UPDATE phase_cursor SET phase=? WHERE id=1 AND phase<?",
        (phase_end, phase_end),
    )


def _get_week(c, week_id: int):
    week = c.execute("SELECT * FROM weeks WHERE id=?", (week_id,)).fetchone()
    if week is None:
        raise LookupError("week_not_found")
    return week


def generate_week(c, week_id: int, member_ids: list[int], task_ids: list[int],
                  days: int = 7, commit: bool = True) -> dict:
    """为某一周落格。空成员抛 ValueError('empty_members')；skip 周需先 unskip。"""
    week = _get_week(c, week_id)
    if week["skipped"]:
        raise ValueError("week_skipped")
    if not member_ids:
        raise ValueError("empty_members")

    advance = len(task_ids) * days
    phase_start = week["phase_start"]
    claimed_now = phase_start is None
    if claimed_now:
        phase_start = read_cursor(c)
    phase_end = phase_start + advance

    # 先算出全部格再动库，空成员等非法输入不会留下半截状态。
    slots = build_week_slots(member_ids, task_ids, days=days, phase=phase_start)

    c.execute("DELETE FROM assignments WHERE week_id=?", (week_id,))
    for s in slots:
        c.execute(
            "INSERT INTO assignments(week_id,day,task_id,member_id) VALUES (?,?,?,?)",
            (week_id, s["day"], s["task_id"], s["member_id"]),
        )
    c.execute(
        "UPDATE weeks SET skipped=0, phase_start=?, phase_end=?, advance=?, status='ready' WHERE id=?",
        (phase_start, phase_end, advance, week_id),
    )
    if claimed_now:
        _set_cursor_forward(c, phase_end)
    if commit:
        c.commit()
    return {
        "week_id": week_id,
        "skipped": False,
        "phase_start": phase_start,
        "phase_end": phase_end,
        "advance": advance,
        "slots": slots,
    }


def mark_skip(c, week_id: int, task_ids: list[int], days: int = 7,
              commit: bool = True) -> dict:
    """把一周标为 skip：清空格、相位窗照常推进。"""
    week = _get_week(c, week_id)
    advance = len(task_ids) * days
    phase_start = week["phase_start"]
    claimed_now = phase_start is None
    if claimed_now:
        phase_start = read_cursor(c)
    phase_end = phase_start + advance

    c.execute("DELETE FROM assignments WHERE week_id=?", (week_id,))
    c.execute(
        "UPDATE weeks SET skipped=1, phase_start=?, phase_end=?, advance=?, status='skipped' WHERE id=?",
        (phase_start, phase_end, advance, week_id),
    )
    if claimed_now:
        _set_cursor_forward(c, phase_end)
    if commit:
        c.commit()
    return {
        "week_id": week_id,
        "skipped": True,
        "phase_start": phase_start,
        "phase_end": phase_end,
        "advance": advance,
        "slots": [],
    }


def unskip(c, week_id: int, commit: bool = True) -> None:
    """取消 skip：保留已预留的相位窗，只把周交回可生成状态。"""
    _get_week(c, week_id)
    c.execute("UPDATE weeks SET skipped=0, status='draft' WHERE id=?", (week_id,))
    if commit:
        c.commit()
