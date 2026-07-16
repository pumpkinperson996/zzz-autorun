# ruff: noqa: E402, E702 —— 自检脚本, 分段追加式书写
"""自检: 必停锁真的拦得住吗 —— 用当时那个顶号画面的 OCR 原文"""
import io
import sys

sys.path.insert(0, r'C:\ZZZ-OD\ZZZ-autorun')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from loop.oracle import Abort, check_abort


class FakeText:
    def __init__(self, t): self.text = t
class FakeResult:
    def __init__(self, texts): self.success, self.ocr_texts = True, [FakeText(t) for t in texts]
class FakeBackend:
    def __init__(self, texts): self._t = texts
    def analyze(self, screenshot=None): return FakeResult(self._t)

# 事故当晚执行方真实点掉的那些画面
CASES = {
    '顶号弹窗':     ['您的账号在其他地方登录', '确认'],
    '连接超时':     ['服务器连接超时', '是否继续尝试连接', '确认'],
    '登录中':       ['登录游戏服务器中,请等待'],
    '进游戏':       ['点击进入游戏'],
    '维护公告':     ['游戏维护', '公告'],
}
for name, texts in CASES.items():
    try:
        check_abort(FakeBackend(texts))
        print(f'  ✗ {name:10} 没拦住！'); sys.exit(1)
    except Abort:
        print(f'  ✓ {name:10} 已拦截')

# 正常画面必须放行
try:
    check_abort(FakeBackend(['出战', '预备编队', '等级60', '战斗设置']))
    print('  ✓ 出战画面   正常放行')
except Abort:
    print('  ✗ 出战画面被误拦！'); sys.exit(1)
print('\n[OK] 必停锁自检通过')


# ---- 动作校验: 用事故当晚执行方真实输出的那段污染文本做断言 ----
from loop.navigate import validate_action


class T:
    def __init__(self, text, x, y, w=40, h=20):
        self.text, self.x, self.y, self.width, self.height = text, x, y, w, h

OCR = [T('确认', 957, 616), T('零号空洞', 192, 260), T('出战', 1699, 1007)]

POLLUTED = ('确认 The user provided a JSON-like string but it seems incomplete or malformed. '
            'Let me look at what they are trying to do. Wait, looking at the context, this appears '
            'to be a continuation of the game navigation task...')

_cases = [
    ('污染的 target_text', {'action':'click','target_text':POLLUTED,'x':977,'y':626}, True),
    ('编造不存在的按钮',   {'action':'click','target_text':'开始探索','x':640,'y':640}, True),
    ('坐标离目标太远',     {'action':'click','target_text':'确认','x':1500,'y':100}, True),
    ('正常点击',           {'action':'click','target_text':'确认','x':957,'y':616}, False),
    ('容差内的坐标',       {'action':'click','target_text':'出战','x':1710,'y':1020}, False),
    ('wait 不校验',        {'action':'wait','target_text':'','x':0,'y':0}, False),
]
for name, act, should_reject in _cases:
    r = validate_action(act, OCR)
    ok = (r is not None) == should_reject
    print(f"  {'✓' if ok else '✗'} {name:18} {'已拒绝' if r else '放行'}")
    assert ok, f'{name} 校验行为不符预期: {r}'
print('\n[OK] 动作校验自检通过 —— 编造的点击目标进不来')
