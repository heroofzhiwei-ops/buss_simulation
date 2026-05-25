"""阶段 5: 把 posts + replies + resonance 渲染成 HTML"""
import json
import hashlib
from collections import Counter
from typing import List, Dict

from jinja2 import Environment, FileSystemLoader
from config import DATA_OUTPUT, TEMPLATE_DIR

STANCE_CLASS_MAP = {
    '积极拓展': 'positive',
    '观望试探': 'neutral',
    '无关跳过': 'negative',
}


def _build_persona_tags(persona_brief: dict) -> str:
    parts = []
    if persona_brief.get('main_categories'):
        parts.append(persona_brief['main_categories'][0])
    if persona_brief.get('downstream_channels'):
        parts.append(persona_brief['downstream_channels'][0])
    if persona_brief.get('gmv_tier'):
        parts.append(persona_brief['gmv_tier'].split('(')[0])
    if persona_brief.get('exploration_status'):
        parts.append(persona_brief['exploration_status'])
    return ' · '.join(parts)


def _avatar_color(buyer_id: str) -> str:
    hash_hex = hashlib.md5(buyer_id.encode()).hexdigest()
    return '#' + hash_hex[:6]


def _shop_name_proxy(persona_brief: dict, buyer_id: str) -> str:
    """没有真实店铺名时，用主营+渠道造一个显示名"""
    category = (persona_brief.get('main_categories', [''])[0]
                if persona_brief.get('main_categories') else '')
    channel = (persona_brief.get('downstream_channels', [''])[0]
               if persona_brief.get('downstream_channels') else '')
    buyer_id_tail = buyer_id[-4:] if len(buyer_id) >= 4 else buyer_id
    if category and channel:
        return f"{category}·{channel}店主#{buyer_id_tail}"
    return f"分销同行#{buyer_id_tail}"


def _enrich_post(post: dict, replies_by_target: Dict[str, list],
                 resonance: Dict[str, dict]) -> dict:
    buyer_id = post['buyer_id']
    brief = post.get('persona_brief', {})
    shop_name = _shop_name_proxy(brief, buyer_id)
    resonance_data = resonance.get(buyer_id, {})
    post_replies = replies_by_target.get(buyer_id, [])

    enriched_replies = []
    for reply in post_replies:
        from_id = reply.get('from_buyer_id', '')
        author_name = f"同行#{from_id[-4:]}" if from_id else '同行'
        enriched_replies.append({
            'author': author_name,
            'type': reply.get('reply_type', '补充'),
            'voice': reply.get('voice', ''),
        })

    return {
        **post,
        'shop_name': shop_name,
        'persona_tags': _build_persona_tags(brief),
        'avatar_initial': shop_name[0] if shop_name else '?',
        'avatar_color': _avatar_color(buyer_id),
        'stance_class': STANCE_CLASS_MAP.get(post.get('stance', ''), 'neutral'),
        'like_count': resonance_data.get('like_count', 0),
        'resonance_score': resonance_data.get('resonance_score', 0),
        'replies': enriched_replies,
    }


def _aggregate_keywords(posts: List[dict],
                        resonance: Dict[str, dict]) -> list:
    """衍生词汇总，按出现次数 + 共鸣度加权排序"""
    keyword_count = Counter()
    keyword_weight = {}

    for post in posts:
        buyer_id = post['buyer_id']
        weight = resonance.get(buyer_id, {}).get('avg_score', 0.5)
        all_keywords = list(post.get('derived_keywords', []))
        if post.get('personal_twist_keyword'):
            all_keywords.append(post['personal_twist_keyword'])
        for keyword in all_keywords:
            keyword_count[keyword] += 1
            keyword_weight[keyword] = keyword_weight.get(keyword, 0) + weight

    items = [
        {'word': kw, 'count': cnt, 'weight': round(keyword_weight[kw], 2)}
        for kw, cnt in keyword_count.items()
    ]
    items.sort(key=lambda x: (-x['count'], -x['weight']))
    return items[:30]


def _compute_stats(posts: List[dict]) -> dict:
    stances = Counter([p.get('stance', '') for p in posts])
    keyword_total = sum(len(p.get('derived_keywords', [])) for p in posts)
    return {
        'positive': stances.get('积极拓展', 0),
        'neutral': stances.get('观望试探', 0),
        'negative': stances.get('无关跳过', 0),
        'kw_count': keyword_total,
    }


def _aggregate_twist_keywords(posts: List[dict],
                              resonance: Dict[str, dict]) -> list:
    """专门收集每个 agent 的 personal_twist_keyword，带角色信息"""
    items = []
    for post in posts:
        twist = post.get('personal_twist_keyword')
        if not twist:
            continue
        buyer_id = post['buyer_id']
        brief = post.get('persona_brief', {})
        category = (brief.get('main_categories', [''])[0]
                    if brief.get('main_categories') else '')
        channel = (brief.get('downstream_channels', [''])[0]
                   if brief.get('downstream_channels') else '')
        items.append({
            'word': twist,
            'from_persona': f"{category} · {channel}",
            'stance': post.get('stance', ''),
            'resonance': resonance.get(buyer_id, {}).get('resonance_score', 0),
        })
    items.sort(key=lambda x: -x['resonance'])
    return items


def render_demo_html(posts: List[dict], replies: List[dict],
                     resonance: Dict[str, dict],
                     signal_word: str, signal_brief: str) -> str:
    # 按目标聚合 replies
    replies_by_target = {}
    for reply in replies:
        target_id = reply.get('reply_to_buyer_id')
        if target_id:
            replies_by_target.setdefault(target_id, []).append(reply)

    # 按共鸣度排序主帖
    posts_sorted = sorted(
        posts,
        key=lambda p: -resonance.get(p['buyer_id'], {}).get('avg_score', 0)
    )
    enriched = [_enrich_post(p, replies_by_target, resonance)
                for p in posts_sorted]

    context = {
        'signal_word': signal_word,
        'signal_brief': signal_brief,
        'posts': enriched,
        'stats': _compute_stats(posts),
        'aggregated_keywords': _aggregate_keywords(posts, resonance),
        'twist_keywords': _aggregate_twist_keywords(posts, resonance),
    }

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)
    template = env.get_template('feed.html')
    html = template.render(**context)

    output_path = DATA_OUTPUT / 'demo.html'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"[RENDER] 输出: {output_path}")
    return str(output_path)
