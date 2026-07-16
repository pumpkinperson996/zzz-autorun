"""导航驱动 —— 执行方看画面决定点哪，harness 执行

分工严格:
    harness  截图 → analyze_screen 得到结构化 dump(OCR文本+坐标+画面匹配) → 执行动作
    执行方   只看 dump, 输出下一个动作。它不能自己动手, 也不能自称"我点了"

为什么不写死坐标: 迷失之地入口的 13 个导航节点是 LostVoidApp 内部的 @operation_node,
    无法按 op_id 单跑(见 tasks 2.1c)。写死坐标则游戏一改版就烂。让执行方看着 OCR 走,
    它每一步都基于当前真实画面。

每一步都落盘截图 —— 出问题时能看见停在哪一帧, 而不是只有一句"卡住了"。
"""
from __future__ import annotations

import os
import time

from . import executor

ACTION_SCHEMA = {
    'type': 'object',
    'properties': {
        'reasoning': {'type': 'string', 'description': '先说清当前在哪、离目标还差什么'},
        'action': {
            'type': 'string',
            'enum': ['click', 'wait', 'done', 'stuck'],
            'description': 'click=点一下; wait=等加载; done=已到目标画面; stuck=走不下去了',
        },
        'target_text': {'type': 'string', 'description': 'click 时: 要点的那个 OCR 文本原文'},
        'x': {'type': 'integer', 'description': 'click 时: 点击坐标 x'},
        'y': {'type': 'integer', 'description': 'click 时: 点击坐标 y'},
        'why': {'type': 'string', 'description': '为什么是这一步'},
    },
    'required': ['reasoning', 'action', 'target_text', 'x', 'y', 'why'],
}


def _dump(backend, ctx, out_dir: str, tag: str) -> tuple[str, str, list]:
    """截图 + 结构化分析, 返回 (截图路径, 给执行方看的文本 dump, OCR 条目)"""
    from one_dragon.utils import cv2_utils

    ctx.controller.init_game_win()
    if not ctx.controller.is_game_window_ready:
        raise RuntimeError('游戏窗口未就绪')
    img = ctx.controller.screenshot()[1]
    path = os.path.join(out_dir, f'{time.strftime("%H%M%S")}_{tag}.png')
    cv2_utils.save_image(img, path)

    r = backend.analyze(screenshot=path)
    if not r.success:
        return path, f'analyze 失败: {r.error}', []

    precise = [s.screen_name for s in r.screens if s.is_precise]
    lines = [
        f'精准命中画面: {precise or "无(该画面未定义)"}',
        f'候选画面: {[s.screen_name for s in r.screens[:5]]}',
        '可见文本(text @ 中心坐标):',
    ]
    for t in r.ocr_texts:
        cx = int(t.x + t.width / 2)
        cy = int(t.y + t.height / 2)
        lines.append(f'  {t.text!r} @ ({cx}, {cy})')
    return path, '\n'.join(lines), list(r.ocr_texts)


_CLICK_TOLERANCE = 40


def validate_action(act: dict, ocr_items: list) -> str | None:
    """机械校验执行方的动作。返回拒绝理由, None 表示放行。

    为什么不能只靠提示词: 实测执行方在没看懂画面时会**编造一个按钮去点**。事故当晚它把
    整段自言自语("The user provided a JSON-like string but it seems incomplete...")灌进
    target_text, 然后点了顶号弹窗的「确认」。提示词写着"要点的东西必须在可见文本里出现过",
    它照样点了。

    逐字符相等这一条顺带解决了字段污染: 一段 2000 字的胡话匹配不上任何 OCR 文本。
    """
    if act.get('action') != 'click':
        return None

    target = act.get('target_text', '')
    hits = [t for t in ocr_items if t.text == target]
    if not hits:
        return (f'target_text 不是 OCR 原文(逐字符相等), 拒绝点击。'
                f'收到 {target[:60]!r}{"…(共%d字)" % len(target) if len(target) > 60 else ""}')

    x, y = int(act.get('x', -1)), int(act.get('y', -1))
    for t in hits:
        cx, cy = int(t.x + t.width / 2), int(t.y + t.height / 2)
        if abs(x - cx) <= _CLICK_TOLERANCE and abs(y - cy) <= _CLICK_TOLERANCE:
            return None
    near = [(int(t.x + t.width / 2), int(t.y + t.height / 2)) for t in hits]
    return f'坐标 ({x},{y}) 与 {target!r} 的实际位置 {near} 相差超过 {_CLICK_TOLERANCE}px, 拒绝点击'


def navigate_to(backend, ctx, goal: str, out_dir: str, max_steps: int = 12) -> dict:
    """让执行方把游戏导航到 goal 描述的画面

    Args:
        goal: 目标画面的自然语言描述, 含判断到达的标志
        out_dir: 每步截图落盘目录
        max_steps: 步数上限 —— 走不到就停, 不许无限点下去

    Returns:
        {'reached': bool, 'steps': [...], 'last_shot': path}
    """
    os.makedirs(out_dir, exist_ok=True)
    steps: list[dict] = []
    last_shot = ''
    rejects = 0

    from .oracle import Abort, check_abort

    for i in range(max_steps):
        # 每一步之前先过必停检查 —— 执行方无权决定要不要点顶号弹窗
        try:
            check_abort(backend)
        except Abort as e:
            return {'reached': False, 'steps': steps, 'last_shot': last_shot,
                    'reason': str(e), 'abort': True}
        last_shot, dump, ocr_items = _dump(backend, ctx, out_dir, f'nav{i:02d}')

        prompt = f"""你在驱动《绝区零》的游戏界面导航。harness 已经截图并做了 OCR，你只负责决定下一步点哪。

## 目标
{goal}

## 当前画面（harness 刚截的，OCR 结果与坐标如下）
{dump}

## 规矩
1. 只能依据上面的 dump 判断。看不到的元素就是不在画面上，**不要猜坐标**。
2. 要点的东西必须在「可见文本」里出现过，直接用它给出的中心坐标。
3. 画面像在加载(文本很少/没有可点的目标) → action=wait。
4. 已经到达目标画面 → action=done。
5. 目标不在画面上且不知道下一步 → action=stuck，别乱点。
6. 你只输出动作，harness 执行。**不要自称已经点过了。**

## 已走过的步骤
{[f"{s['action']} {s.get('target_text', '')}" for s in steps] or '(这是第一步)'}
"""
        act, _ = executor.ask(prompt, ACTION_SCHEMA, max_tokens=4000)
        act['_step'] = i
        steps.append(act)
        print(f"  [{i}] {act['action']} {str(act.get('target_text', ''))[:30]!r} "
              f"@({act.get('x')},{act.get('y')}) — {str(act['why'])[:60]}")

        if act['action'] == 'done':
            return {'reached': True, 'steps': steps, 'last_shot': last_shot}
        if act['action'] == 'stuck':
            return {'reached': False, 'steps': steps, 'last_shot': last_shot,
                    'reason': act['why']}
        if act['action'] == 'wait':
            time.sleep(2)
            continue

        # 机械校验 —— 拒绝就不点, 不给它第二次机会乱点同一帧
        reject = validate_action(act, ocr_items)
        if reject:
            print(f'       ✗ 动作被拒: {reject}')
            act['_rejected'] = reject
            rejects += 1
            if rejects >= 3:
                return {'reached': False, 'steps': steps, 'last_shot': last_shot,
                        'reason': f'连续被拒 {rejects} 次(执行方在编造点击目标): {reject}'}
            continue

        from one_dragon.base.geometry.point import Point
        ctx.controller.click(Point(int(act['x']), int(act['y'])))
        time.sleep(2)
        rejects = 0

    return {'reached': False, 'steps': steps, 'last_shot': last_shot,
            'reason': f'步数用尽({max_steps}步)'}
