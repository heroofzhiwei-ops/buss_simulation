"""阶段 5: 把 posts + replies + resonance 渲染成 HTML

输出三层结构:
  L1 泛化信号全景 — 衍生词按类目/场景/立场分类
  L2 个性化反馈卡 — 每个 buyer 完整反应(不展示分数)
  L3 群体动态 — 高共识词 + 稀有视角 + 反对意见
"""
import json
import hashlib
from collections import Counter, defaultdict
from typing import List, Dict

from jinja2 import Environment, FileSystemLoader
from config import DATA_OUTPUT, TEMPLATE_DIR

STANCE_CLASS_MAP = {
    '积极拓展': 'positive',
    '观望试探': 'neutral',
    '无关跳过': 'negative',
}

REPLY_TYPE_EN_MAP = {
    '反对': ('DISAGREE', 'disagree'),
    '补充': ('ADD', 'add'),
    '质疑': ('QUESTION', 'question'),
}

# 衍生词分类规则（简易版，按关键词匹配）
CATEGORY_KEYWORDS = {
    '服装·男装': ['男', 'oversize', '工装', 'polo', '马甲', '夹克', '卫衣男',
                 '衬衫男', '外套男', '裤男', '短袖男'],
    '服装·女装': ['女', '连衣裙', '半身裙', '吊带', '甜辣', '碎花', '衬衫女',
                 '外套女', '针织女', '裙', '女装'],
    '服装·童装': ['童', '亲子', '宝宝', '学生', '儿童', '校服'],
    '配饰': ['帽', '包', '腰带', '袜', '丝巾', '围巾', '手套', '发带', '饰品'],
    '鞋类': ['鞋', '靴', '凉鞋', '运动鞋', '拖鞋', '板鞋'],
    '家居': ['抱枕', '相框', '收纳', '窗帘', '地毯', '摆件'],
}


def _classify_keyword(word: str) -> str:
    """根据预定义关键词规则对衍生词做类目分类"""
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in word for kw in keywords):
            return category
    return '其他'


def _avatar_color(buyer_id: str) -> str:
    hash_hex = hashlib.md5(buyer_id.encode()).hexdigest()
    return '#' + hash_hex[:6]


def _format_shop_label(brief: dict, buyer_id: str) -> str:
    """生成身份简称：主营·渠道·探索类型"""
    parts = []
    if brief.get('main_categories'):
        parts.append(brief['main_categories'][0])
    if brief.get('downstream_channels'):
        parts.append(brief['downstream_channels'][0])
    if brief.get('exploration_status'):
        parts.append(brief['exploration_status'] + '型')
    if not parts:
        return f"分销同行#{buyer_id[-4:]}"
    return ' · '.join(parts)


def _format_identity_line(brief: dict) -> str:
    """生成身份详情行：主营 / 下游 / 体量"""
    segments = []
    if brief.get('main_categories'):
        segments.append(f"主营: {'/'.join(brief['main_categories'][:2])}")
    if brief.get('downstream_channels'):
        segments.append(f"下游: {brief['downstream_channels'][0]}")
    if brief.get('gmv_tier') and brief['gmv_tier'] != '未知':
        segments.append(f"体量: {brief['gmv_tier']}")
    if brief.get('price_band') and brief['price_band'] != '未知':
        segments.append(f"价格带: {brief['price_band']}")
    return '   '.join(segments)


# ============================================================
# L1 泛化信号全景
# ============================================================
def build_overview_panel(posts: List[dict]) -> dict:
    """生成 L1 泛化信号全景数据"""
    all_keywords = []
    for post in posts:
        brief = post.get('persona_brief', {})
        channel = (brief.get('downstream_channels', [''])[0]
                   if brief.get('downstream_channels') else '未知')
        stance = post.get('stance', '')

        for kw in post.get('derived_keywords', []):
            all_keywords.append({
                'word': kw,
                'channel': channel,
                'stance': stance,
                'is_twist': False,
            })
        if post.get('personal_twist_keyword'):
            all_keywords.append({
                'word': post['personal_twist_keyword'],
                'channel': channel,
                'stance': stance,
                'is_twist': True,
            })

    # 按类目分组
    by_category = defaultdict(list)
    for item in all_keywords:
        category = _classify_keyword(item['word'])
        by_category[category].append(item)
    by_category_sorted = dict(
        sorted(by_category.items(), key=lambda x: -len(x[1]))
    )

    # 按下游场景分组
    by_channel = defaultdict(list)
    for item in all_keywords:
        by_channel[item['channel']].append(item)
    by_channel_sorted = dict(
        sorted(by_channel.items(), key=lambda x: -len(x[1]))
    )

    # 按立场分组
    by_stance = defaultdict(list)
    for item in all_keywords:
        by_stance[item['stance']].append(item)

    # 立场分布统计
    stance_distribution = Counter(p.get('stance', '') for p in posts)

    return {
        'total_kws': len(all_keywords),
        'unique_kws': len(set(item['word'] for item in all_keywords)),
        'category_count': len(by_category_sorted),
        'channel_count': len(by_channel_sorted),
        'twist_count': sum(1 for k in all_keywords if k['is_twist']),
        'stance_distribution': dict(stance_distribution),
        'by_category': by_category_sorted,
        'by_channel': by_channel_sorted,
        'by_stance': dict(by_stance),
    }


# ============================================================
# L2 个性化反馈卡
# ============================================================
def enrich_post_v2(post: dict, replies_by_target: Dict[str, list]) -> dict:
    """增强主帖数据用于 L2 个性化反馈卡（不含分数）"""
    buyer_id = post['buyer_id']
    brief = post.get('persona_brief', {})
    post_replies = replies_by_target.get(buyer_id, [])

    enriched_replies = []
    for reply in post_replies:
        from_id = reply.get('from_buyer_id', '')
        from_brief = reply.get('from_persona_brief', {})
        if from_brief:
            author_label = _format_shop_label(from_brief, from_id)
        else:
            author_label = f"同行#{from_id[-4:]}" if from_id else '同行'
        type_zh = reply.get('reply_type', '补充')
        type_en, type_class = REPLY_TYPE_EN_MAP.get(type_zh, ('NOTE', 'add'))
        enriched_replies.append({
            'author': author_label,
            'avatar_initial': author_label[0] if author_label else '?',
            'avatar_color': _avatar_color(from_id) if from_id else '#6b7280',
            'type': type_zh,
            'type_en': type_en,
            'type_class': type_class,
            'voice': reply.get('voice', ''),
            'time_label': 'just now',
        })

    shop_label = _format_shop_label(brief, buyer_id)
    return {
        **post,
        'shop_label': shop_label,
        'avatar_initial': shop_label[0] if shop_label else '?',
        'identity_line': _format_identity_line(brief),
        'avatar_color': _avatar_color(buyer_id),
        'stance_class': STANCE_CLASS_MAP.get(post.get('stance', ''), 'neutral'),
        'replies': enriched_replies,
    }


# ============================================================
# L3 群体动态
# ============================================================
def build_crowd_dynamics(posts: List[dict]) -> dict:
    """生成 L3 群体动态数据"""
    # 统计所有衍生词出现次数
    keyword_counter = Counter()
    for post in posts:
        for kw in post.get('derived_keywords', []):
            keyword_counter[kw] += 1
        if post.get('personal_twist_keyword'):
            keyword_counter[post['personal_twist_keyword']] += 1

    # 高共识词（≥2 人都提到）
    high_consensus = [
        {'word': kw, 'count': count}
        for kw, count in keyword_counter.most_common()
        if count >= 2
    ][:8]

    # 稀有视角（twist 词且仅 1 人提出）
    rare_views = []
    for post in posts:
        twist = post.get('personal_twist_keyword')
        if twist and keyword_counter.get(twist, 0) <= 1:
            brief = post.get('persona_brief', {})
            rare_views.append({
                'word': twist,
                'from_label': _format_shop_label(brief, post['buyer_id']),
            })

    # 反对/观望的代表性观点
    objections = []
    for post in posts:
        if post.get('stance') in ('无关跳过', '观望试探'):
            brief = post.get('persona_brief', {})
            reason = post.get('concerns', '') or post.get('voice', '')[:120]
            objections.append({
                'stance': post.get('stance', ''),
                'from_label': _format_shop_label(brief, post['buyer_id']),
                'reason': reason,
            })

    return {
        'high_consensus': high_consensus,
        'rare_views': rare_views,
        'objections': objections,
    }


# ============================================================
# 汇总视图：衍生信号总罗列
# ============================================================
def build_keyword_roster(posts: List[dict]) -> list:
    """生成去重的衍生词总表，标注来源数量和是否为 twist"""
    keyword_info = {}
    for post in posts:
        brief = post.get('persona_brief', {})
        source_label = _format_shop_label(brief, post['buyer_id'])
        for kw in post.get('derived_keywords', []):
            if kw not in keyword_info:
                keyword_info[kw] = {'word': kw, 'sources': [], 'is_twist': False}
            keyword_info[kw]['sources'].append(source_label)
        twist = post.get('personal_twist_keyword')
        if twist:
            if twist not in keyword_info:
                keyword_info[twist] = {'word': twist, 'sources': [], 'is_twist': True}
            else:
                keyword_info[twist]['is_twist'] = True
            keyword_info[twist]['sources'].append(source_label)

    roster = sorted(keyword_info.values(), key=lambda x: (-len(x['sources']), x['word']))
    for item in roster:
        item['count'] = len(item['sources'])
        item['source_preview'] = item['sources'][0] if item['sources'] else ''
    return roster


# ============================================================
# 汇总视图：个性化反馈速览
# ============================================================
def build_buyer_summaries(posts: List[dict]) -> list:
    """每个 buyer 的一句话总结"""
    summaries = []
    for post in posts:
        brief = post.get('persona_brief', {})
        voice = post.get('voice', '')
        voice_short = voice[:60] + '...' if len(voice) > 60 else voice
        summaries.append({
            'shop_label': _format_shop_label(brief, post['buyer_id']),
            'stance': post.get('stance', ''),
            'stance_class': STANCE_CLASS_MAP.get(post.get('stance', ''), 'neutral'),
            'twist': post.get('personal_twist_keyword', ''),
            'kw_count': len(post.get('derived_keywords', [])),
            'voice_short': voice_short,
        })
    return summaries


# ============================================================
# 主渲染入口
# ============================================================
def render_demo_html(posts: List[dict], replies: List[dict],
                     resonance: Dict[str, dict],
                     signal_word: str, signal_brief: str) -> str:
    # 按目标聚合 replies
    replies_by_target = {}
    for reply in replies:
        target_id = reply.get('reply_to_buyer_id')
        if target_id:
            replies_by_target.setdefault(target_id, []).append(reply)

    # 按共鸣度排序主帖（内部排序信号，不对外展示分数）
    posts_sorted = sorted(
        posts,
        key=lambda p: -resonance.get(p['buyer_id'], {}).get('avg_score', 0)
    )

    # 构建三层数据
    overview = build_overview_panel(posts_sorted)
    enriched_posts = [enrich_post_v2(p, replies_by_target) for p in posts_sorted]
    crowd_dynamics = build_crowd_dynamics(posts_sorted)

    # 汇总视图数据
    all_derived_words = build_keyword_roster(posts_sorted)
    buyer_summaries = build_buyer_summaries(posts_sorted)

    context = {
        'signal_word': signal_word,
        'signal_brief': signal_brief,
        'overview': overview,
        'posts': enriched_posts,
        'crowd_dynamics': crowd_dynamics,
        'all_derived_words': all_derived_words,
        'buyer_summaries': buyer_summaries,
    }

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)
    template = env.get_template('feed.html')
    html = template.render(**context)

    output_path = DATA_OUTPUT / 'demo.html'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"[RENDER] 输出: {output_path}")
    return str(output_path)
