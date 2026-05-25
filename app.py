"""1688 商机信号个性化反应模拟器 - Flask Web 应用"""
import asyncio
import json
import threading
import queue
from datetime import datetime
from pathlib import Path

from flask import (Flask, render_template, request, Response,
                   jsonify, send_from_directory)

from config import DATA_INPUT, DATA_OUTPUT

app = Flask(__name__)

# ============================================================
# 全局：历史记录
# ============================================================
_history_file = DATA_OUTPUT / 'history.json'


def _load_history() -> list:
    if _history_file.exists():
        with open(_history_file, encoding='utf-8') as f:
            return json.load(f)
    return []


def _save_history(items: list):
    with open(_history_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


# ============================================================
# 路由
# ============================================================
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/result/<path:filename>')
def serve_result(filename):
    """提供 data/output 中的静态文件（如 demo.html）"""
    return send_from_directory(DATA_OUTPUT, filename)


@app.route('/api/data-status')
def data_status():
    """返回数据文件状态"""
    buyer_path = DATA_INPUT / 'buyer_features.tsv'
    profile_path = DATA_INPUT / 'buyer_profiles.tsv'
    demo_path = DATA_OUTPUT / 'personas_demo.jsonl'

    result = {
        'buyer_features': buyer_path.exists(),
        'buyer_count': 0,
        'buyer_profiles': profile_path.exists(),
        'profile_count': 0,
        'personas_demo': demo_path.exists(),
        'demo_count': 0,
    }

    if buyer_path.exists():
        with open(buyer_path, encoding='utf-8') as f:
            result['buyer_count'] = sum(1 for _ in f) - 1

    if profile_path.exists():
        with open(profile_path, encoding='utf-8') as f:
            result['profile_count'] = sum(1 for _ in f) - 1

    if demo_path.exists():
        with open(demo_path, encoding='utf-8') as f:
            result['demo_count'] = sum(1 for line in f if line.strip())

    return jsonify(result)


@app.route('/api/history')
def history_api():
    """返回历史运行记录"""
    items = _load_history()
    return jsonify({'items': items[-20:]})


@app.route('/api/run')
def run_pipeline():
    """SSE 端点：启动流水线并实时推送进度"""
    signal_word = request.args.get('signal', '').strip()
    signal_brief = request.args.get('signal_brief', '').strip()
    sample_limit = int(request.args.get('sample_limit', 300))
    stage = request.args.get('stage', 'all')

    if not signal_word:
        def error_stream():
            yield _sse_event('error_msg', {'message': '商机信号词不能为空'})
        return Response(error_stream(), mimetype='text/event-stream')

    message_queue = queue.Queue()

    def progress_callback(message, current=0, total=0):
        percent = int(current / total * 100) if total > 0 else 0
        message_queue.put(('progress', {
            'message': message,
            'current': current,
            'total': total,
            'percent': percent,
        }))

    def run_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                _execute_pipeline(
                    signal_word, signal_brief, sample_limit, stage,
                    progress_callback, message_queue,
                )
            )
        except Exception as exc:
            message_queue.put(('error_msg', {'message': str(exc)}))
        finally:
            loop.close()

    worker_thread = threading.Thread(target=run_in_thread, daemon=True)
    worker_thread.start()

    def event_stream():
        while True:
            try:
                event_type, data = message_queue.get(timeout=120)
                yield _sse_event(event_type, data)
                if event_type in ('done', 'error_msg'):
                    break
            except queue.Empty:
                # 心跳，保持连接
                yield _sse_event('progress', {'message': '等待中...', 'percent': 0})

    return Response(event_stream(), mimetype='text/event-stream',
                    headers={
                        'Cache-Control': 'no-cache',
                        'X-Accel-Buffering': 'no',
                    })


# ============================================================
# 核心流水线执行
# ============================================================
async def _execute_pipeline(signal_word, signal_brief, sample_limit,
                            stage, progress_callback, message_queue):
    """在子线程的事件循环中执行整个流水线"""
    from persona_builder import build_personas_pipeline
    from post_generator import generate_main_posts, generate_replies
    from scoring import compute_resonance
    from renderer import render_demo_html

    def send_stage(stage_name):
        message_queue.put(('stage', {'stage': stage_name}))

    # 阶段 1: Persona 构建
    if stage in ('all', 'personas'):
        send_stage('阶段 1/5: Persona 画像构建')
        buyer_file = 'buyer_features.tsv'
        profile_file = 'buyer_profiles.tsv'

        if not (DATA_INPUT / buyer_file).exists():
            message_queue.put(('error_msg', {
                'message': f'缺少数据文件 data/input/{buyer_file}'
            }))
            return
        if not (DATA_INPUT / profile_file).exists():
            message_queue.put(('error_msg', {
                'message': f'缺少数据文件 data/input/{profile_file}'
            }))
            return

        await build_personas_pipeline(
            buyer_table=buyer_file,
            profile_table=profile_file,
            sample_limit=sample_limit,
            progress_callback=progress_callback,
        )

    if stage == 'personas':
        message_queue.put(('done', {
            'message': 'Persona 构建完成',
            'result_url': None,
        }))
        return

    # 检查 demo persona 是否存在
    demo_path = DATA_OUTPUT / 'personas_demo.jsonl'
    if not demo_path.exists():
        message_queue.put(('error_msg', {
            'message': '没有找到 personas_demo.jsonl，请先运行 Persona 构建阶段'
        }))
        return

    personas = _load_jsonl(demo_path)
    progress_callback(f'加载 {len(personas)} 个 demo persona', 1, 1)

    # 阶段 2: 主帖生成
    send_stage('阶段 2/5: 主帖生成')
    posts = await generate_main_posts(
        personas, signal_word, signal_brief,
        progress_callback=progress_callback,
    )
    if not posts:
        message_queue.put(('error_msg',
                           {'message': '没有任何主帖生成成功，请检查 LLM 配置'}))
        return

    # 阶段 3: 回帖生成
    send_stage('阶段 3/5: 回帖生成')
    replies = await generate_replies(
        personas, posts, signal_word,
        progress_callback=progress_callback,
    )

    # 阶段 4: 共鸣度评分
    send_stage('阶段 4/5: 共鸣度评分')
    resonance = await compute_resonance(
        personas, posts, signal_word,
        progress_callback=progress_callback,
    )

    # 阶段 5: HTML 渲染
    send_stage('阶段 5/5: HTML 渲染')
    render_demo_html(posts, replies, resonance, signal_word, signal_brief)
    progress_callback('HTML 渲染完成', 1, 1)

    # 记录历史
    history = _load_history()
    history.append({
        'signal_word': signal_word,
        'signal_brief': signal_brief,
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'post_count': len(posts),
        'reply_count': len(replies),
        'url': '/result/demo.html',
    })
    _save_history(history)

    message_queue.put(('done', {
        'message': '全部完成！',
        'result_url': '/result/demo.html',
    }))


# ============================================================
# 工具函数
# ============================================================
def _load_jsonl(path: Path) -> list:
    items = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def _sse_event(event_type: str, data: dict) -> str:
    """格式化 SSE 事件"""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ============================================================
# 启动
# ============================================================
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)
