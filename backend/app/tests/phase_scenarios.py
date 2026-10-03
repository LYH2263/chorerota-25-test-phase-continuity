"""补相位跨周回归——场景夹具模块。

只负责在内存 sqlite 上搭世界、跑操作、读回结果（:class:`ScenarioRun`），
不做任何断言。断言与手算期望值全部在 :mod:`app.tests.phase_assertions`。

四组场景：
1. two_consecutive_weeks   两周连续生成
2. skip_week_between       中间插入 skip 周再生成
3. unskip_then_regenerate  skip 后再取消 skip 重生成
4. empty_members_rejected  非法空成员生成
"""
import sqlite3
from dataclasses import dataclass, field

from app.seed import create_schema
from app.modules import skip_week


@dataclass
class WeekState:
    week_id: int
    label: str
    status: str
    skipped: int
    start_phase: int | None
    end_phase: int | None
    assignments: list[dict] = field(default_factory=list)


@dataclass
class ScenarioRun:
    name: str
    kind: str  # "continuity" | "invalid"
    member_ids: list[int]
    task_ids: list[int]
    days: int
    weeks: dict[int, WeekState]
    order: list[int]
    captured_errors: list[tuple[str, str]] = field(default_factory=list)
    invalid_attempt: WeekState | None = None  # 非法调用后该周的即时快照（仅非法场景）


class PhaseWorld:
    """内存库上的排班世界。相位钉在 weeks 行（start_phase/end_phase）。"""

    def __init__(self, name: str, kind: str, members: int = 3, tasks: int = 2, days: int = 7):
        self.name = name
        self.kind = kind
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        create_schema(self.conn)
        self.member_ids = list(range(1, members + 1))
        for mid in self.member_ids:
            self.conn.execute(
                "INSERT INTO members(id,name,active,data_quality) VALUES (?,?,1,'clean')",
                (mid, f"成员{mid}"),
            )
        self.task_ids = [10 * (i + 1) for i in range(tasks)]  # 刻意非连续自增，防 id/下标混用
        for tid in self.task_ids:
            self.conn.execute(
                "INSERT INTO tasks(id,title,weight,data_quality) VALUES (?,?,1,'clean')",
                (tid, f"任务{tid}"),
            )
        self.days = days
        self.order: list[int] = []
        self.captured_errors: list[tuple[str, str]] = []

    def add_week(self, label: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO weeks(label,status,skipped) VALUES (?,'draft',0)", (label,)
        )
        wid = cur.lastrowid
        self.order.append(wid)
        return wid

    def _ids(self, override: list[int] | None):
        mids = self.member_ids if override is None else override
        return mids, list(self.task_ids)

    def generate(self, week_id: int, members: list[int] | None = None):
        mids, tids = self._ids(members)
        try:
            skip_week.regenerate_week(self.conn, week_id, mids, tids, days=self.days)
        except ValueError as e:
            self.captured_errors.append((type(e).__name__, str(e)))

    def skip(self, week_id: int, members: list[int] | None = None):
        mids, tids = self._ids(members)
        try:
            skip_week.mark_skipped(self.conn, week_id, mids, tids, days=self.days)
        except ValueError as e:
            self.captured_errors.append((type(e).__name__, str(e)))

    def unskip(self, week_id: int):
        skip_week.unmark_skipped(self.conn, week_id)

    def snapshot_week(self, week_id: int) -> WeekState:
        row = self.conn.execute("SELECT * FROM weeks WHERE id=?", (week_id,)).fetchone()
        assigns = [
            dict(r)
            for r in self.conn.execute(
                "SELECT day,task_id,member_id FROM assignments "
                "WHERE week_id=? ORDER BY day,task_id",
                (week_id,),
            )
        ]
        return WeekState(
            week_id=week_id,
            label=row["label"],
            status=row["status"],
            skipped=row["skipped"],
            start_phase=row["start_phase"],
            end_phase=row["end_phase"],
            assignments=assigns,
        )

    def readback(self, invalid_attempt: WeekState | None = None) -> ScenarioRun:
        weeks = {wid: self.snapshot_week(wid) for wid in self.order}
        run = ScenarioRun(
            name=self.name,
            kind=self.kind,
            member_ids=list(self.member_ids),
            task_ids=list(self.task_ids),
            days=self.days,
            weeks=weeks,
            order=list(self.order),
            captured_errors=list(self.captured_errors),
            invalid_attempt=invalid_attempt,
        )
        self.conn.close()
        return run


def _two_consecutive_weeks() -> ScenarioRun:
    w = PhaseWorld("两周连续生成", "continuity")
    w1, w2 = w.add_week("第1周"), w.add_week("第2周")
    w.generate(w1)
    w.generate(w2)
    return w.readback()


def _skip_week_between() -> ScenarioRun:
    w = PhaseWorld("中间插入skip周再生成", "continuity")
    w1, w2, w3 = w.add_week("第1周"), w.add_week("第2周(skip)"), w.add_week("第3周")
    w.generate(w1)
    w.skip(w2)          # 不落格，但推进相位
    w.generate(w3)
    return w.readback()


def _unskip_then_regenerate() -> ScenarioRun:
    w = PhaseWorld("skip后取消skip重生成", "continuity")
    w1, w2, w3 = w.add_week("第1周"), w.add_week("第2周(skip)"), w.add_week("第3周")
    w.generate(w1)
    w.skip(w2)
    w.generate(w3)
    w.unskip(w2)        # 取消 skip：清空相位脚印
    w.generate(w2)      # 重新生成，须与前后周重新钉在同一游标上
    return w.readback()


def _empty_members_rejected() -> ScenarioRun:
    w = PhaseWorld("非法空成员生成", "invalid")
    w1, w2 = w.add_week("第1周"), w.add_week("第2周")
    w.generate(w1)
    w.generate(w2, members=[])      # 非法：必须拒绝且不写格、不留相位
    attempt = w.snapshot_week(w2)   # 非法调用后的即时状态
    w.generate(w2)                  # 恢复名册后重生，衔接仍连续
    return w.readback(invalid_attempt=attempt)


def build_scenarios() -> list[ScenarioRun]:
    return [
        _two_consecutive_weeks(),
        _skip_week_between(),
        _unskip_then_regenerate(),
        _empty_members_rejected(),
    ]
