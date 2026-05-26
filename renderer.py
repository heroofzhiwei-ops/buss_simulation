"""阶段 5: 把商机推演结果渲染成 HTML。

输出结构：
  L1 商机画像与推演概览
  L2 个性化商机延伸地图
  L3 买家推演卡 + 视角碰撞（适配 buyer）
  L4 共识、视角碰撞与延伸边界
  L5 不适配 buyer 反馈（单独底部区域）
"""
import hashlib
from datetime import datetime
from collections import Counter, defaultdict
from typing import Dict, List

from jinja2 import Environment, FileSystemLoader
from config import DATA_OUTPUT, TEMPLATE_DIR

FIT_CLASS_MAP = {
    '高适配': 'positive',
    '可试探': 'neutral',
    '低适配': 'negative',
    '不适配': 'negative',
}

CHALLENGE_TYPE_EN_MAP = {
    '边界挑战': ('BOUNDARY', 'disagree'),
    '迁移补充': ('MIGRATE', 'add'),
    '风险追问': ('RISK', 'question'),
}

CATEGORY_KEYWORDS = {
    '服装·男装': ['男', 'oversize', '工装', 'polo', '马甲', '夹克', '卫衣男',
                 '衬衫男', '外套男', '裤男', '短袖男'],
    '服装·女装': ['女', '连衣裙', '半身裙', '吊带', '甜辣', '碎花', '衬衫女',
                 '外套女', '针织女', '裙', '女装', '通勤'],
    '服装·童装': ['童', '亲子', '宝宝', '学生', '儿童', '校服'],
    '配饰': ['帽', '包', '腰带', '袜', '丝巾', '围巾', '手套', '发带', '饰品'],
    '鞋类': ['鞋', '靴', '凉鞋', '运动鞋', '拖鞋', '板鞋'],
    '家居': ['抱枕', '相框', '收纳', '窗帘', '地毯', '摆件', '桌布', '藤编'],
}


def _classify_keyword(word: str) -> str:
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in word for kw in keywords):
            return category
    return '其他机会'


def _avatar_color(buyer_id: str) -> str:
    hash_hex = hashlib.md5(str(buyer_id).encode()).hexdigest()
    return '#' + hash_hex[:6]


def _format_shop_label(brief: dict, buyer_id: str) -> str:
    parts = []
    if brief.get('main_categories'):
        parts.append(brief['main_categories'][0])
    if brief.get('downstream_channels'):
        parts.append(brief['downstream_channels'][0])
    if brief.get('exploration_status'):
        parts.append(brief['exploration_status'] + '型')
    if not parts:
        return f"分销买家#{str(buyer_id)[-4:]}"
    return ' · '.join(parts)


def _format_identity_line(brief: dict) -> str:
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


def _as_list(value) -> list:
    if not value:
        return []
    if isinstance(value, list):
        return value
    return [value]


# ============================================================
# 机会地图
# ============================================================
def build_opportunity_map(assessments: List[dict]) -> dict:
    keyword_info = {}
    for assessment in assessments:
        brief = assessment.get('persona_brief', {})
        source_label = _format_shop_label(brief, assessment.get('buyer_id', ''))
        fit_level = assessment.get('fit_level', '')
        # 用 buyer 的主营类目作为衍生词归类依据
        buyer_categories = brief.get('main_categories') or []
        buyer_category = buyer_categories[0] if buyer_categories else '其他'

        all_words = []
        for word in _as_list(assessment.get('derived_keywords')):
            all_words.append((word, False))
        unique_word = assessment.get('unique_angle_keyword') or assessment.get('personal_twist_keyword')
        if unique_word:
            all_words.append((unique_word, True))

        for word, is_unique in all_words:
            if not word:
                continue
            info = keyword_info.setdefault(word, {
                'word': word,
                'category': buyer_category,
                'sources': [],
                'is_unique': False,
                'fit_levels': [],
                'reason': assessment.get('opportunity_translation', ''),
            })
            info['sources'].append(source_label)
            info['is_unique'] = info['is_unique'] or is_unique
            info['fit_levels'].append(assessment.get('fit_level', ''))

    clusters = defaultdict(list)
    for info in keyword_info.values():
        info['count'] = len(info['sources'])
        info['source_preview'] = info['sources'][0] if info['sources'] else ''
        info['fit_preview'] = next((x for x in info['fit_levels'] if x), '')
        clusters[info['category']].append(info)

    sorted_clusters = []
    for category, items in sorted(clusters.items(), key=lambda x: -len(x[1])):
        items.sort(key=lambda x: (-x['count'], not x['is_unique'], x['word']))
        sorted_clusters.append({'category': category, 'words': items})
    return {
        'clusters': sorted_clusters,
        'total_words': len(keyword_info),
        'unique_angle_count': sum(1 for item in keyword_info.values() if item['is_unique']),
    }


# ============================================================
# 买家评审与质询增强
# ============================================================
def enrich_assessments(
    assessments: List[dict],
    challenges_by_target: Dict[str, list],
    resonance: Dict[str, dict],
) -> List[dict]:
    enriched = []
    for item in assessments:
        buyer_id = item.get('buyer_id', '')
        brief = item.get('persona_brief', {})
        shop_label = _format_shop_label(brief, buyer_id)
        fit_level = item.get('fit_level') or item.get('stance', '可试探')
        fit_class = FIT_CLASS_MAP.get(fit_level, 'neutral')
        match = item.get('signal_match', {})
        enriched.append({
            **item,
            'shop_label': shop_label,
            'avatar_initial': shop_label[0] if shop_label else '?',
            'identity_line': _format_identity_line(brief),
            'avatar_color': _avatar_color(buyer_id),
            'fit_level': fit_level,
            'fit_class': fit_class,
            'fit_score': match.get('match_score'),
            'review_role': match.get('review_role', '评审'),
            'match_reasons': match.get('match_reasons', []),
            'recommended_actions': _as_list(item.get('recommended_actions')),
            'risks': _as_list(item.get('risks') or item.get('concerns')),
            'evidence': _as_list(item.get('evidence')),
            'unique_angle_keyword': item.get('unique_angle_keyword') or item.get('personal_twist_keyword', ''),
            'resonance': resonance.get(buyer_id, {}),
            'challenges': challenges_by_target.get(buyer_id, []),
        })
    return sorted(
        enriched,
        key=lambda x: (
            {'高适配': 0, '可试探': 1, '低适配': 2, '不适配': 3}.get(x['fit_level'], 1),
            -(x.get('resonance', {}).get('avg_score', 0) or 0),
        )
    )


def enrich_challenges(challenges: List[dict]) -> Dict[str, list]:
    by_target = defaultdict(list)
    for item in challenges:
        from_id = item.get('from_buyer_id', '')
        from_brief = item.get('from_persona_brief', {})
        author_label = _format_shop_label(from_brief, from_id) if from_brief else f"买家#{str(from_id)[-4:]}"
        type_zh = item.get('challenge_type') or item.get('reply_type', '迁移补充')
        type_en, type_class = CHALLENGE_TYPE_EN_MAP.get(type_zh, ('NOTE', 'add'))
        enriched = {
            **item,
            'author': author_label,
            'avatar_initial': author_label[0] if author_label else '?',
            'avatar_color': _avatar_color(from_id) if from_id else '#6b7280',
            'type_en': type_en,
            'type_class': type_class,
            'challenge_type': type_zh,
            'challenge': item.get('challenge') or item.get('voice', ''),
        }
        by_target[item.get('target_buyer_id') or item.get('reply_to_buyer_id')].append(enriched)
    return by_target


# ============================================================
# 总览/洞察
# ============================================================
def build_review_overview(signal_profile: dict, assessments: List[dict], opportunity_map: dict) -> dict:
    fit_distribution = Counter(a.get('fit_level', '可试探') for a in assessments)
    return {
        'reviewer_count': len(assessments),
        'total_words': opportunity_map['total_words'],
        'cluster_count': len(opportunity_map['clusters']),
        'high_fit_count': fit_distribution.get('高适配', 0),
        'boundary_count': fit_distribution.get('低适配', 0) + fit_distribution.get('不适配', 0),
        'fit_distribution': dict(fit_distribution),
        'signal_profile': signal_profile,
    }


def build_buyer_summaries(assessments: List[dict]) -> list:
    summaries = []
    for item in assessments:
        brief = item.get('persona_brief', {})
        assessment = item.get('assessment') or item.get('voice', '')
        assessment_short = assessment[:70] + '...' if len(assessment) > 70 else assessment
        summaries.append({
            'shop_label': _format_shop_label(brief, item.get('buyer_id', '')),
            'fit_level': item.get('fit_level', '可试探'),
            'fit_class': FIT_CLASS_MAP.get(item.get('fit_level', ''), 'neutral'),
            'unique_angle': item.get('unique_angle_keyword') or item.get('personal_twist_keyword', ''),
            'assessment_short': assessment_short,
        })
    return summaries


def build_council_insights(assessments: List[dict], challenges: List[dict]) -> dict:
    all_keywords = []
    for item in assessments:
        all_keywords.extend(_as_list(item.get('derived_keywords')))
        if item.get('unique_angle_keyword'):
            all_keywords.append(item['unique_angle_keyword'])
    keyword_counter = Counter(all_keywords)
    consensus_keywords = [
        {'word': word, 'count': count}
        for word, count in keyword_counter.most_common(8)
        if count >= 2
    ]

    consensus = []
    if consensus_keywords:
        consensus.append('多个买家重复提及相同细粒度词，说明存在可聚合的货盘方向。')
    if any(a.get('fit_level') == '高适配' for a in assessments):
        consensus.append('高适配买家集中在类目/渠道与信号语境接近的经营体。')
    if any(a.get('recommended_actions') for a in assessments):
        consensus.append('多数建议先小批量测款，用具体场景词替代原始趋势大词。')

    tensions = []
    for challenge in challenges[:6]:
        text = challenge.get('challenge') or challenge.get('voice') or ''
        if text:
            tensions.append({
                'type': challenge.get('challenge_type') or challenge.get('reply_type', '质询'),
                'text': text,
            })

    boundaries = []
    for item in assessments:
        if item.get('fit_level') in ('低适配', '不适配'):
            brief = item.get('persona_brief', {})
            boundaries.append({
                'from_label': _format_shop_label(brief, item.get('buyer_id', '')),
                'reason': (item.get('risks') or [item.get('assessment', '')])[0],
                'fit_level': item.get('fit_level'),
            })

    return {
        'consensus': consensus or ['当前评审结果较分散，需要扩大样本或补充更明确的商机简介。'],
        'consensus_keywords': consensus_keywords,
        'tensions': tensions,
        'boundaries': boundaries,
    }


# ============================================================
# 主渲染入口
# ============================================================
def render_demo_html(
    assessments: List[dict],
    challenges: List[dict],
    resonance: Dict[str, dict],
    signal_word: str,
    signal_brief: str,
    signal_profile: Dict[str, object] = None,
) -> str:
    if signal_profile is None:
        from signal_analyzer import build_signal_profile
        signal_profile = build_signal_profile(signal_word, signal_brief)

    challenges_by_target = enrich_challenges(challenges)
    enriched_assessments = enrich_assessments(assessments, challenges_by_target, resonance)
    opportunity_map = build_opportunity_map(enriched_assessments)
    overview = build_review_overview(signal_profile, enriched_assessments, opportunity_map)
    buyer_summaries = build_buyer_summaries(enriched_assessments)
    council_insights = build_council_insights(enriched_assessments, challenges)

    # 分组：适配 vs 不适配
    fit_assessments = [a for a in enriched_assessments if a.get('fit_level') != '不适配']
    unfit_assessments = [a for a in enriched_assessments if a.get('fit_level') == '不适配']

    context = {
        'signal_word': signal_word,
        'signal_brief': signal_brief,
        'signal_profile': signal_profile,
        'overview': overview,
        'opportunity_map': opportunity_map,
        'assessments': fit_assessments,
        'unfit_assessments': unfit_assessments,
        'buyer_summaries': buyer_summaries,
        'council_insights': council_insights,
    }

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)
    template = env.get_template('feed.html')
    html = template.render(**context)

    # 唯一文件名：signal_word + 时间戳
    timestamp = datetime.now().strftime('%m%d_%H%M%S')
    safe_name = signal_word[:10].replace('/', '_').replace(' ', '_')
    filename = f'{safe_name}_{timestamp}.html'
    output_path = DATA_OUTPUT / filename
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"[RENDER] 输出: {output_path}")
    return filename
