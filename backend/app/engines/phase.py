"""跨周轮转的相位（phase）游标算术。

相位是一个从 0 开始、不回绕的全局槽位计数器：
周内第 k 个格的轮值成员为 ``member_ids[(phase_start + k) % len(member_ids)]``。
一周占据连续 ``advance`` 个槽位，因此下一周的起点相位必然等于本周的
终点相位（``phase_start + advance``）。skip 周不落任何格，但仍按整周长度
推进相位。这里的全部函数都是纯函数，周行存储与独立游标表两侧的读回值
都能用这些函数手工推算衔接。
"""


def slots_per_week(task_count: int, days: int = 7) -> int:
    """一周名义槽位数 = 任务数 × 天数（skip 周也推进这么多）。"""
    return task_count * days


def end_phase(phase_start: int, advance: int) -> int:
    """本周终点相位 = 下周起点相位。"""
    return phase_start + advance


def member_at_phase(phase: int, member_ids: list[int]) -> int:
    """某个全局相位落在哪个成员上（可手算：phase % 成员数）。"""
    return member_ids[phase % len(member_ids)]


def expected_members(member_ids: list[int], phase_start: int, advance: int) -> list[int]:
    """手算：从 phase_start 起连续 advance 个格的期望成员序列。"""
    n = len(member_ids)
    return [member_ids[(phase_start + k) % n] for k in range(advance)]


def chain_phases(advances: list[int], initial: int = 0) -> tuple[list[tuple[int, int]], int]:
    """手算整条周链：给定每周推进量，返回每周 (起点, 终点) 与最终游标相位。"""
    windows = []
    cursor = initial
    for advance in advances:
        windows.append((cursor, cursor + advance))
        cursor += advance
    return windows, cursor
