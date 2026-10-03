"""Round-robin weekly chore assignments + swap legality.

跨周相位（phase）语义：每周网格按 ``days * len(task_ids)`` 个槽位推进一个
连续游标。上一周的终点相位必须等于下一周的起点相位；skip 周不落任何格，
但仍按同样的网格大小推进相位，因此取消 skip 后重新生成能与前后周无缝衔接。
"""


def build_week_slots(member_ids: list[int], task_ids: list[int], days: int = 7) -> list[dict]:
    """Assign each (day, task) to members in round-robin by task then day."""
    if not member_ids or not task_ids:
        return []
    slots = []
    idx = 0
    for day in range(days):
        for tid in task_ids:
            mid = member_ids[idx % len(member_ids)]
            slots.append({"day": day, "task_id": tid, "member_id": mid})
            idx += 1
    return slots


def grid_size(member_ids: list[int], task_ids: list[int], days: int = 7) -> int:
    """Number of slots one week (or one skipped week) advances the phase by."""
    if not member_ids:
        raise ValueError("empty_members")
    return days * len(task_ids)


def advance_phase(phase: int, member_ids: list[int], task_ids: list[int], days: int = 7) -> int:
    """Advance the cursor by a full week grid without emitting any slots (skip 周)."""
    return phase + grid_size(member_ids, task_ids, days)


def build_phase_week(member_ids: list[int], task_ids: list[int], start_phase: int,
                     days: int = 7) -> dict:
    """Build one week whose first slot resumes the round-robin at ``start_phase``.

    返回 ``{"slots", "start_phase", "end_phase"}``；空成员名册是非法输入，
    抛 ``ValueError("empty_members")``，且不产生任何部分结果。
    """
    if not member_ids:
        raise ValueError("empty_members")
    n = len(member_ids)
    phase = start_phase
    slots = []
    for day in range(days):
        for tid in task_ids:
            slots.append({"day": day, "task_id": tid, "member_id": member_ids[phase % n]})
            phase += 1
    return {"slots": slots, "start_phase": start_phase, "end_phase": phase}


def swap_legal(slots: list[dict], a_day: int, a_task: int, b_day: int, b_task: int) -> dict:
    """Two slots may swap only if both exist, different assignees, same week grid."""
    def find(day, task):
        for s in slots:
            if s["day"] == day and s["task_id"] == task:
                return s
        return None
    sa, sb = find(a_day, a_task), find(b_day, b_task)
    if sa is None or sb is None:
        return {"ok": False, "reason": "slot_missing"}
    if sa["member_id"] == sb["member_id"]:
        return {"ok": False, "reason": "same_assignee"}
    if a_day == b_day and a_task == b_task:
        return {"ok": False, "reason": "same_slot"}
    return {
        "ok": True,
        "reason": "",
        "a_member": sa["member_id"],
        "b_member": sb["member_id"],
    }


def apply_swap(slots: list[dict], a_day: int, a_task: int, b_day: int, b_task: int) -> list[dict]:
    check = swap_legal(slots, a_day, a_task, b_day, b_task)
    if not check["ok"]:
        raise ValueError(check["reason"])
    out = [dict(s) for s in slots]
    ia = next(i for i, s in enumerate(out) if s["day"] == a_day and s["task_id"] == a_task)
    ib = next(i for i, s in enumerate(out) if s["day"] == b_day and s["task_id"] == b_task)
    out[ia]["member_id"], out[ib]["member_id"] = out[ib]["member_id"], out[ia]["member_id"]
    return out
