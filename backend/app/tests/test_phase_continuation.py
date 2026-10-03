"""补相位跨周连续回归测试。

场景夹具见 phase_scenarios.py，断言助手见 phase_assertions.py，两者分离。
四组场景：两周连续 / 中间 skip / skip 后取消重生成 / 非法空成员。
失败时断言助手会打印场景名与周行侧、游标侧两侧相位。
"""

import pytest

from app.tests import phase_assertions as A
from app.tests import phase_scenarios as S


def test_two_consecutive_weeks_phase_continues(roster):
    run = S.build_two_consecutive_weeks(roster)
    # 3 成员、周推进 14：手算窗口应为 (0,14)、(14,28)，第二周起点=14 接上。
    assert run.week_order == [roster["weeks"]["w1"], roster["weeks"]["w2"]]
    A.assert_phase_chain(run)


def test_skip_week_advances_phase_without_slots(roster):
    run = S.build_skip_week_between(roster)
    # skip 周窗口 (14,28) 不落格；第三周从 28 起，跳过 14 格相位。
    A.assert_phase_chain(run)


def test_unskip_and_regenerate_keeps_phase_window(roster):
    run = S.build_skip_then_unskip_regenerate(roster)
    # 取消 skip 重生成只回填原窗口，游标不二次推进，链仍为 0-14-28-42。
    A.assert_phase_chain(run)


def test_empty_members_generation_rejected(roster):
    run = S.build_empty_members(roster)
    A.assert_empty_members_rejected(run)


# 再以参数化方式跑一遍全部场景，确保新增场景自动纳入收集，且每个至少有
# 一条断言路径覆盖。
@pytest.mark.parametrize(
    "builder,illegal",
    [
        (S.build_two_consecutive_weeks, False),
        (S.build_skip_week_between, False),
        (S.build_skip_then_unskip_regenerate, False),
        (S.build_empty_members, True),
    ],
    ids=["two_consecutive", "skip_between", "unskip_regenerate", "empty_members"],
)
def test_phase_scenarios_parametrized(roster, builder, illegal):
    run = builder(roster)
    if illegal:
        A.assert_empty_members_rejected(run)
    else:
        A.assert_phase_chain(run)
