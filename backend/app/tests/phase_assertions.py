"""补相位跨周回归——断言助手模块。

期望值全部手算：网格 G = days * 任务数，第 i 周（0 起）起点相位 = i*G，
终点 = (i+1)*G；槽位 j（day*任务数 + 任务序内下标）的当值成员
= members[(start+j) % 成员数]。

两侧相位都从同一份读回（weeks 行上的 start_phase/end_phase）取，保证
"周行存相位还是独立游标表" 的实现取舍对断言透明。任一断言失败都会抛出
带场景名与两侧相位的 AssertionError，并打印到 stdout。
"""
from .phase_scenarios import ScenarioRun, WeekState


def _fail(run: ScenarioRun, msg: str, prev: WeekState | None = None,
          nxt: WeekState | None = None) -> None:
    head = f"[场景失败] {run.name}: {msg}"
    if prev is not None and nxt is not None:
        head += (
            f" | 前一周<{prev.label} week_id={prev.week_id}> 终点相位={prev.end_phase}"
            f" 后一周<{nxt.label} week_id={nxt.week_id}> 起点相位={nxt.start_phase}"
        )
    print(head)
    raise AssertionError(head)


def expected_grid(run: ScenarioRun) -> int:
    return run.days * len(run.task_ids)


def _slot_index(run: ScenarioRun, assignment: dict) -> int:
    return assignment["day"] * len(run.task_ids) + run.task_ids.index(assignment["task_id"])


def assert_adjacent_phases_link(run: ScenarioRun) -> None:
    """后一周起点相位必须正好接上前一周终点相位（skip 周也算一站）。"""
    weeks = [run.weeks[wid] for wid in run.order]
    for prev, nxt in zip(weeks, weeks[1:]):
        if prev.end_phase is None or nxt.start_phase is None or prev.end_phase != nxt.start_phase:
            _fail(run, "相邻周相位断链", prev, nxt)


def assert_phases_hand_computable(run: ScenarioRun) -> None:
    """逐周手算核对：第 i 周 start=i*G、end=(i+1)*G，不依赖实现内部状态。"""
    g = expected_grid(run)
    for i, wid in enumerate(run.order):
        wk = run.weeks[wid]
        want_start, want_end = i * g, (i + 1) * g
        if (wk.start_phase, wk.end_phase) != (want_start, want_end):
            print(f"[场景失败] {run.name}: 周<{wk.label}> 相位手算不符 "
                  f"| 读回起点={wk.start_phase} 终点={wk.end_phase} "
                  f"手算起点={want_start} 终点={want_end}")
            raise AssertionError(f"{run.name}: 周 {wk.label} 相位手算不符")


def assert_week_slots(run: ScenarioRun, wk: WeekState) -> None:
    """正常周：落 G 个格，每格当值成员 = members[(start+槽位) % n]。"""
    g = expected_grid(run)
    n = len(run.member_ids)
    if wk.skipped or wk.status != "ready":
        _fail(run, f"正常周<{wk.label}> 状态异常 status={wk.status} skipped={wk.skipped}")
    if len(wk.assignments) != g:
        _fail(run, f"正常周<{wk.label}> 落格数={len(wk.assignments)} != 网格={g}")
    for a in wk.assignments:
        j = _slot_index(run, a)
        want_member = run.member_ids[(wk.start_phase + j) % n]
        if a["member_id"] != want_member:
            print(f"[场景失败] {run.name}: 周<{wk.label}> day={a['day']} "
                  f"task={a['task_id']} 当值成员读回={a['member_id']} "
                  f"手算={want_member}（起点相位={wk.start_phase} 槽位={j}）")
            raise AssertionError(f"{run.name}: 周 {wk.label} 槽位 {j} 当值成员不符")
    if wk.end_phase != wk.start_phase + len(wk.assignments):
        _fail(run, f"正常周<{wk.label}> 终点未等于起点+落格数")


def assert_skipped_week(run: ScenarioRun, wk: WeekState) -> None:
    """skip 周：不落格，但相位照常推进整整一个网格。"""
    g = expected_grid(run)
    if wk.assignments:
        _fail(run, f"skip 周<{wk.label}> 不应落格，实际 {len(wk.assignments)} 格")
    if not wk.skipped or wk.status != "skipped":
        _fail(run, f"周<{wk.label}> 应标记 skip，实际 status={wk.status} skipped={wk.skipped}")
    if wk.start_phase is None or wk.end_phase != wk.start_phase + g:
        print(f"[场景失败] {run.name}: skip 周<{wk.label}> 相位未按网格推进 "
              f"| 起点相位={wk.start_phase} 终点相位={wk.end_phase} 网格={g}")
        raise AssertionError(f"{run.name}: skip 周 {wk.label} 相位未推进")


def assert_continuity_scenario(run: ScenarioRun) -> None:
    assert_adjacent_phases_link(run)
    assert_phases_hand_computable(run)
    for wid in run.order:
        wk = run.weeks[wid]
        if wk.skipped:
            assert_skipped_week(run, wk)
        else:
            assert_week_slots(run, wk)


def assert_invalid_scenario(run: ScenarioRun) -> None:
    """非法空成员：抛 empty_members、不留任何格/相位，恢复名册后衔接连续。"""
    errors = run.captured_errors
    if not errors or not any(msg == "empty_members" for _, msg in errors):
        _fail(run, f"空成员生成应拒绝(empty_members)，实际捕获={errors}")
    attempt = run.invalid_attempt
    if attempt is None:
        _fail(run, "缺少非法调用后的即时快照")
    if attempt.assignments or attempt.start_phase is not None or attempt.end_phase is not None:
        print(f"[场景失败] {run.name}: 空成员被拒后仍留下脏数据 "
              f"| 起点相位={attempt.start_phase} 终点相位={attempt.end_phase} "
              f"落格数={len(attempt.assignments)}")
        raise AssertionError(f"{run.name}: 空成员被拒后留下脏数据")
    # 恢复名册重生成后，两侧仍须同钉衔接
    assert_adjacent_phases_link(run)
    assert_phases_hand_computable(run)
    for wid in run.order:
        assert_week_slots(run, run.weeks[wid])


def assert_scenario(run: ScenarioRun) -> None:
    if run.kind == "invalid":
        assert_invalid_scenario(run)
    else:
        assert_continuity_scenario(run)
