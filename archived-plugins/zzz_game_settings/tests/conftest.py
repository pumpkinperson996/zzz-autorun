"""插件测试的路径配置: 保证可以 import src 与 plugins"""
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
for _p in (_ROOT, os.path.join(_ROOT, 'src')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
