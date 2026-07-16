"""自检: 必停锁真的拦得住吗 —— 用当时那个顶号画面的 OCR 原文"""
import io, sys
sys.path.insert(0, r'C:\ZZZ-OD\ZZZ-autorun')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from loop.oracle import ABORT_KEYWORDS, Abort, check_abort

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
    except Abort as e:
        print(f'  ✓ {name:10} 已拦截')

# 正常画面必须放行
try:
    check_abort(FakeBackend(['出战', '预备编队', '等级60', '战斗设置']))
    print('  ✓ 出战画面   正常放行')
except Abort:
    print('  ✗ 出战画面被误拦！'); sys.exit(1)
print('\n[OK] 必停锁自检通过')
