"""实机实验闭环 · 执行方客户端 (Fireworks / GLM-5.2)

分工: 决策方(强模型)提假设定方向, 执行方(本模块)干重活 —— 写探针、读产物报观察、改代码。

为什么只用标准库:
    不能给 ZZZ-OD 加依赖。pyproject.toml 被 ZZZ-OD 的 git 跟踪, 而启动器自动更新会跑
    git reset --hard, 任何新增依赖都会被上游版本抹掉。openai 库装不得, requests 是未声明
    的传递依赖也不可靠。一个 POST 而已, urllib 够了。

为什么住在 ZZZ-autorun 而不是 plugins/lost_void_film:
    闭环不能住在它自己有权修改的目录里 —— 否则模型可以改闭环本身, 白名单就是废纸。

设计依据见 openspec/changes/add-live-experiment-loop/design.md D8。
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), '.env')

_TIMEOUT = 180
_MAX_TOKENS = 3000

# 必须显式设 UA: urllib 默认的 Python-urllib/3.x 被 Fireworks 的 Cloudflare 单独封禁
# (HTTP 403 + error code 1010 "banned based on browser signature")。任何其他 UA 均放行,
# 故此处用本项目的真实标识, 不伪装。
_USER_AGENT = 'zzz-od-experiment-loop/1.0'


class ExecutorError(RuntimeError):
    """执行方调用失败 (重试耗尽 / 输出不合 schema)"""


def _env() -> dict[str, str]:
    """读 .env。密钥只从这里来, 绝不落入任何将进入 git 的文件"""
    if not os.path.exists(_ENV_PATH):
        raise ExecutorError(f'缺少 .env: {_ENV_PATH}')
    out: dict[str, str] = {}
    with open(_ENV_PATH, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            out[k.strip()] = v.strip()
    if 'FIREWORKS_API_KEY' not in out:
        raise ExecutorError('.env 缺少 FIREWORKS_API_KEY')
    return out


def _post(url: str, key: str, body: dict) -> dict:
    # 必须显式 UTF-8: Windows 下默认编码会写成 GBK, Fireworks 直接返回 body 解析错误
    data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        url, data=data, method='POST',
        headers={
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json; charset=utf-8',
            'User-Agent': _USER_AGENT,
        },
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode('utf-8'))


def ask(
        prompt: str,
        schema: dict,
        *,
        image_path: str | None = None,
        max_tokens: int = _MAX_TOKENS,
        retries: int = 3,
) -> tuple[dict, dict]:
    """让执行方按 schema 作答, 返回 (结果对象, token 用量)

    Args:
        prompt: 任务描述
        schema: JSON Schema。**required 首位必须是 reasoning 字段** —— 见下方硬校验
        image_path: 传图则自动路由到视觉模型 (GLM-5.2 不支持图片输入)
        max_tokens: 需 >=3000, 实测一次观察约用 1350
        retries: 网络/格式失败的重试次数

    Raises:
        ExecutorError: schema 不合规、重试耗尽、或输出不是合法 JSON
    """
    _require_reasoning_first(schema)

    env = _env()
    base = env.get('FIREWORKS_BASE_URL', 'https://api.fireworks.ai/inference/v1')
    if image_path:
        model = env.get('FIREWORKS_VISION_MODEL')
        if not model:
            raise ExecutorError('.env 缺少 FIREWORKS_VISION_MODEL, 无法处理图片')
        content = _image_content(prompt, image_path)
    else:
        model = env.get('FIREWORKS_EXECUTOR_MODEL')
        if not model:
            raise ExecutorError('.env 缺少 FIREWORKS_EXECUTOR_MODEL')
        content = prompt

    body = {
        'model': model,
        'max_tokens': max_tokens,
        'temperature': 0,
        'response_format': {
            'type': 'json_schema',
            'json_schema': {'name': 'result', 'schema': schema},
        },
        'messages': [{'role': 'user', 'content': content}],
    }

    last = ''
    for attempt in range(retries):
        try:
            resp = _post(f'{base}/chat/completions', env['FIREWORKS_API_KEY'], body)
            if 'error' in resp:
                last = str(resp['error'])[:200]
                continue
            choice = resp['choices'][0]
            if choice.get('finish_reason') == 'length':
                # 推理没写完就被截断 结果不可信 —— 加额度重来
                last = f'输出被 max_tokens={max_tokens} 截断'
                body['max_tokens'] = int(body['max_tokens'] * 1.5)
                continue
            return json.loads(choice['message']['content']), resp.get('usage', {})
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as e:
            last = f'{type(e).__name__}: {e}'
        if attempt < retries - 1:
            time.sleep(2 ** attempt)

    raise ExecutorError(f'执行方调用失败(重试{retries}次): {last}')


def _require_reasoning_first(schema: dict) -> None:
    """硬校验: schema 必须让模型先想再答

    实测(design.md D8, 同一案例): 裸上 json_schema 会把推理空间挤掉, 三个假设的判定
    全部塌成 undetermined; 加一个 reasoning 字段后判定质量回到自由输出水平且可机读。
    这条以机制强制, 不靠提示词自觉。
    """
    req = schema.get('required') or []
    if not req or req[0] != 'reasoning':
        raise ExecutorError(
            "schema 的 required 首位必须是 'reasoning' 字段 —— 不给它先想的地方, "
            '判定质量会塌成全 undetermined (见 design.md D8 实测表)'
        )
    if schema.get('properties', {}).get('reasoning', {}).get('type') != 'string':
        raise ExecutorError("schema 的 reasoning 字段必须是 string")


def _image_content(prompt: str, image_path: str) -> list[dict]:
    """图片走 data URI —— 视觉模型是兜底路径, 仅当文本产物不足以区分假设时才用"""
    import base64
    with open(image_path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode('ascii')
    return [
        {'type': 'text', 'text': prompt},
        {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{b64}'}},
    ]


if __name__ == '__main__':
    # 自检: 打通一次真实调用, 并验证 schema 硬校验生效
    schema_ok = {
        'type': 'object',
        'properties': {
            'reasoning': {'type': 'string'},
            'answer': {'type': 'string'},
        },
        'required': ['reasoning', 'answer'],
    }
    try:
        ask('回答 1+1', {'type': 'object', 'properties': {'answer': {'type': 'string'}},
                        'required': ['answer']})
        raise AssertionError('缺 reasoning 的 schema 应当被拒绝')
    except ExecutorError as e:
        assert 'reasoning' in str(e)
        print('[OK] schema 硬校验生效')

    result, usage = ask('用中文回答: 1+1 等于几?', schema_ok)
    assert result['answer'], '执行方无应答'
    print(f"[OK] 执行方连通 answer={result['answer'][:40]!r} tokens={usage.get('total_tokens')}")
