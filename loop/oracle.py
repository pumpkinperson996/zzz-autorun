"""实机成功率判据 —— 唯一不可贿赂的那个

design.md D1: 修复是否成立只由「同场景重复 N 次的实机成功率」判定。
不用测试全绿(测试是代码, 在执行方的可改范围内, 前一版闸门被六种方式打穿)。
不用单次成功(无法与运气区分)。

迷失之地模式不消耗任何游戏资源, 故采样次数不受预算限制 —— 这是本判据成立的前提。
"""
from __future__ import annotations

import asyncio
import os
import time

_SNAP_ROOT = r'C:\ZZZ-OD\.debug\temp\lost_void_film'

# 见到这些即刻停, 绝不点击、绝不重试(design.md 安全锁 #4 / tasks 4.4)
# 与 plugins/unattended_guardian 的 kicked_keywords 同源, 但此处独立成表:
# 两个插件各自独立安装, 不做跨插件 import。
#
# 这条锁是补写的 —— 2026-07-15 循环首次真跑时账号被顶号(异地登录), 而循环
# 代码里一处检查都没有, 执行方顺手把弹窗点掉并重新登录, 会把在别处登录的人顶下线。
# 设计里这条锁一直在, 只是没实现就把循环放出去跑了。
ABORT_KEYWORDS = (
    '其他地方登录', '账号在其他地方', '您的账号在其他', '异地登录', '被迫下线',
    '服务器连接超时', '是否继续尝试连接', '登录游戏服务器中', '点击进入游戏',
    '游戏维护', '停机维护', '版本更新',
)


class Abort(RuntimeError):
    """撞上必须立即停止的界面 —— 不重试, 上报"""


def check_abort(backend) -> None:
    """任何驱动游戏的动作之前都要过这道 —— 撞上就抛, 不给执行方决定的机会

    为什么不交给执行方判断: 它已经证明会在没看懂画面时编造一个按钮去点
    (实测: 把整段自言自语灌进 target_text, 然后点了顶号弹窗的「确认」)。
    这类判断必须机械, 和 guard.py 同理。
    """
    r = backend.analyze()
    if not r.success:
        return
    txt = ''.join(t.text for t in r.ocr_texts)
    for kw in ABORT_KEYWORDS:
        if kw in txt:
            raise Abort(f'撞上必停界面(关键词「{kw}」) —— 已停止, 不重试。OCR: {txt[:120]}')


def _picker_open(backend) -> bool:
    r = backend.analyze()
    if not r.success:
        return False
    return '快捷编队' in ''.join(t.text for t in r.ocr_texts)


def _at_deploy(backend) -> bool:
    r = backend.analyze()
    if not r.success:
        return False
    txt = ''.join(t.text for t in r.ocr_texts)
    return '出战' in txt and '预备编队' in txt


def _in_open_world(backend) -> bool:
    r = backend.analyze()
    return r.success and any(s.screen_name == '大世界-普通' for s in r.screens if s.is_precise)


def ensure_deploy_screen(backend, ctx, out_dir: str) -> bool:
    """把游戏恢复到出战画面这个已知状态

    每一轮采样前必须做。实测教训: 游戏状态会在多次运行间漂移(选人器留着没关、
    退到副本选择页、断线重登回大世界), 而 ChooseTrialTeamOp 要求已在出战画面。

    分工原则(实测得来, 别再违反):
      有确定性 op 的地方就用 op; 只在没有 op 的地方才让执行方看画面开车。
      · 选人器返回键: 图标无文字, 执行方在 OCR 里看不见 -> 用已知常量点
      · 大世界 -> 迷失之地入口: 用 TransportByCompendium(17s 直达, 已验证)。
        **不要交给执行方盲点** —— 大世界 OCR 里的「零号空洞」是任务追踪器的文字标签
        不是按钮, 实测执行方对着它连点 8 次纹丝不动。模型开车只在有文字按钮的
        菜单画面有效, 在 3D 大世界无效。
      · 迷失之地入口 -> 出战画面: 13 个导航节点是 LostVoidApp 内部的 @operation_node,
        无法按 op_id 单跑 -> 这一段交给执行方(已验证 5 步走通)
    """
    from lost_void_film.trial_team_select import PICKER_BACK

    check_abort(backend)
    if _at_deploy(backend):
        return True

    if _picker_open(backend):
        ctx.controller.click(PICKER_BACK)
        time.sleep(2)
        check_abort(backend)
        if _at_deploy(backend):
            return True

    if _in_open_world(backend):
        from zzz_od.operation.compendium.tp_by_compendium import TransportByCompendium
        print('    在大世界 -> TransportByCompendium 直达迷失之地入口')
        ok, future = backend.start_run(
            'oracle', lambda c: TransportByCompendium(c, '作战', '零号空洞', '迷失之地'),
            display_name='TransportByCompendium')
        if not ok:
            return False
        try:
            future.result(300)
        except Exception as e:
            print(f'    传送失败: {e}')
            return False
        time.sleep(3)
        check_abort(backend)

    from . import navigate
    goal = ('把游戏开到迷失之地的【出战画面】。到达标志: 底部同时出现「出战」和「预备编队」，'
            '上方有3个角色卡与「等级」字样。现在应该在迷失之地入口或副本选择页: '
            '右上角有「周期/常规」切换, 我们要「常规」下的副本(战线肃清 / 特遣调查)。'
            '点副本条目或「前往挑战」推进; 路上可能要选调查战略、周期增益, 再点「下一步」。')
    r = navigate.navigate_to(backend, ctx, goal, out_dir, max_steps=12)
    if r.get('abort'):
        raise Abort(r['reason'])
    return r.get('reached', False)


async def sample_success_rate(
        backend, ctx, targets: list[str], n: int, out_dir: str,
) -> dict:
    """跑 n 次, 统计每个目标被选中的次数

    Returns:
        {'n': n, 'runs': [...], 'per_agent': {name: hits}, 'rate': 平均成功率, 'aborted': str|None}
    """
    from lost_void_film.trial_team_select import ChooseTrialTeamOp

    runs: list[dict] = []
    per_agent: dict[str, int] = dict.fromkeys(targets, 0)
    aborted = None

    for i in range(n):
        try:
            if not ensure_deploy_screen(backend, ctx, out_dir):
                aborted = f'第{i + 1}次采样: 无法恢复到出战画面'
                break
            check_abort(backend)
        except Abort as e:
            aborted = f'第{i + 1}次采样前: {e}'
            break

        op = ChooseTrialTeamOp(ctx, list(targets))
        # 默认参数绑定当前 op: 闭包按引用捕获循环变量, 工厂若非立即调用会拿到下一轮的 op
        ok, future = backend.start_run('oracle', lambda c, _op=op: _op,
                                       display_name='ChooseTrialTeamOp')
        if not ok:
            aborted = f'第{i + 1}次采样: 单跑道被占'
            break
        t0 = time.time()
        try:
            await asyncio.get_running_loop().run_in_executor(None, future.result, 480)
        except Exception as e:
            runs.append({'i': i, 'error': str(e)[:200]})
            continue
        for a in op.selected:
            if a in per_agent:
                per_agent[a] += 1
        runs.append({'i': i, 'selected': list(op.selected), 'failed': list(op.failed),
                     'seconds': round(time.time() - t0)})
        print(f'    [{i + 1}/{n}] 成功={op.selected} 失败={op.failed} ({time.time() - t0:.0f}s)')

    done = [r for r in runs if 'selected' in r]
    rate = (sum(len(r['selected']) for r in done) / (len(done) * len(targets))) if done else 0.0
    return {'n': n, 'runs': runs, 'per_agent': per_agent, 'rate': rate, 'aborted': aborted}


def snapshot_dirs() -> set[str]:
    """当前的快照目录(排除保留区)"""
    if not os.path.isdir(_SNAP_ROOT):
        return set()
    return {d for d in os.listdir(_SNAP_ROOT)
            if os.path.isdir(os.path.join(_SNAP_ROOT, d)) and not d.startswith('_keep')}
