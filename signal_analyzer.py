"""商机画像拆解与买家匹配。

这一层把外部商机词从自由文本变成可路由的结构化信号，并在调用 LLM
之前先给 buyer 做粗匹配，避免完全不相关的经营体被迫参与评估。
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List


CATEGORY_RULES = {
    '服装·女装': ['女装', '女', '裙', '衬衫', '针织', '通勤', '穿搭', '多巴胺', '巴恩'],
    '服装·男装': ['男装', '男', '工装', '夹克', 'polo', '马甲', '户外', '巴恩'],
    '服装·童装': ['童装', '儿童', '亲子', '宝宝', '学生'],
    '配饰': ['帽', '包', '腰带', '袜', '丝巾', '饰品', '配饰', '巴恩'],
    '鞋类': ['鞋', '靴', '凉鞋', '运动鞋', '拖鞋'],
    '家居': ['家居', '抱枕', '桌布', '收纳', '摆件', '藤编', '复古'],
    '美妆个护': ['美妆', '护肤', '香氛', '彩妆', '口红'],
    '宠物': ['宠物', '猫', '狗', '养宠'],
}

STYLE_RULES = {
    '美式复古': ['巴恩', '美式', '复古', 'barn', '工装'],
    '户外通勤': ['户外', '露营', '通勤', '松弛'],
    '内容平台风格': ['小红书', '多巴胺', '美学', '穿搭', '风'],
    '传统文化': ['宋代', '新中式', '国风', '茶', '香道'],
    '科技未来': ['赛博', '朋克', '未来', '机能'],
    '情绪消费': ['宠物', '情绪', '疗愈', '陪伴'],
}

CHANNEL_RULES = {
    '小红书': ['小红书', '美学', '穿搭', '种草', '风'],
    '抖音/直播': ['抖音', '直播', '短视频', '爆款'],
    '淘宝/天猫': ['淘宝', '天猫', '搜索', '款式'],
    '拼多多': ['拼多多', '低价', '拼团', '性价比'],
    '线下/批发': ['线下', '批发', '档口'],
    '私域/社区团购': ['私域', '社区', '团购', '拼团'],
}


def _contains_any(text: str, words: Iterable[str]) -> bool:
    text = text.lower()
    return any(str(word).lower() in text for word in words)


def _unique(items: Iterable[str], fallback: List[str] = None) -> List[str]:
    seen = set()
    values = []
    for item in items:
        if not item:
            continue
        item = str(item).strip()
        if item and item not in seen:
            seen.add(item)
            values.append(item)
    return values or list(fallback or [])


def build_signal_profile(signal_word: str, signal_brief: str = '') -> Dict[str, object]:
    """用规则先生成一个稳定的商机画像。

    后续可以把这一层替换/增强成 LLM 结构化，但规则版本可以在无 env 的
    脱敏环境里工作，也能作为批量商机路由的兜底。
    """
    text = f'{signal_word} {signal_brief}'
    categories = [
        category for category, words in CATEGORY_RULES.items()
        if _contains_any(text, words)
    ]
    styles = [
        style for style, words in STYLE_RULES.items()
        if _contains_any(text, words)
    ]
    channels = [
        channel for channel, words in CHANNEL_RULES.items()
        if _contains_any(text, words)
    ]

    audiences = []
    if _contains_any(text, ['小红书', '穿搭', '通勤', '美学']):
        audiences.extend(['内容平台用户', '年轻女性', '城市通勤人群'])
    if _contains_any(text, ['宠物', '养宠']):
        audiences.extend(['养宠人群', '年轻家庭'])
    if _contains_any(text, ['社区', '拼团', '低价']):
        audiences.extend(['价格敏感用户', '社区团购用户'])
    if _contains_any(text, ['儿童', '亲子', '学生']):
        audiences.extend(['学生/亲子人群'])

    supply_requirements = ['可小批量试单', '多 SKU 快速上新']
    if _contains_any(text, ['直播', '抖音', '爆款']):
        supply_requirements.append('现货稳定供应')
    if _contains_any(text, ['小红书', '美学', '穿搭', '风']):
        supply_requirements.append('图片素材和内容表达能力')
    if _contains_any(text, ['低价', '拼团', '社区']):
        supply_requirements.append('低价带和履约稳定性')

    price_band_hint = '中低到中高价格带'
    if _contains_any(text, ['低价', '拼团', '社区']):
        price_band_hint = '低客单价'
    elif _contains_any(text, ['美学', '小红书', '通勤', '复古']):
        price_band_hint = '中客单价到中高客单价'

    return {
        'signal_word': signal_word,
        'signal_brief': signal_brief,
        'category_candidates': _unique(categories, ['服装·女装', '服装·男装', '配饰']),
        'style_tags': _unique(styles, ['趋势风格']),
        'audience_hints': _unique(audiences, ['趋势敏感人群']),
        'channel_hints': _unique(channels, ['内容平台', '搜索电商']),
        'price_band_hint': price_band_hint,
        'supply_requirements': _unique(supply_requirements),
        'interpretation': (
            f'把“{signal_word}”先拆成可匹配的类目、渠道、人群和供应链要求，'
            '再分配给高适配、相邻迁移和边界视角的买家评审。'
        ),
    }


def _list_text(value) -> str:
    if isinstance(value, list):
        return ' '.join(str(x) for x in value)
    return str(value or '')


def _extract_signal_keywords(signal_word: str, signal_brief: str) -> List[str]:
    """从信号词和简介中提取用于匹配的关键字（2字以上的有意义片段）。"""
    text = f'{signal_word} {signal_brief}'
    # 去掉停用词/虚词，按中文分词取有意义的片段
    stop_words = {'的', '了', '是', '在', '和', '与', '或', '等', '及', '为', '有'}
    # 简单切分：先按标点空格切，再取 2-4 字的子串
    segments = re.split(r'[，。、；：！？\s·/+]+', text)
    keywords = set()
    for seg in segments:
        seg = seg.strip()
        if len(seg) >= 2 and seg not in stop_words:
            keywords.add(seg)
            # 对长词也切出 2-3 字子串
            if len(seg) >= 4:
                for i in range(len(seg) - 1):
                    sub = seg[i:i+2]
                    if sub not in stop_words:
                        keywords.add(sub)
                    if i + 3 <= len(seg):
                        sub3 = seg[i:i+3]
                        keywords.add(sub3)
    return list(keywords)


def score_persona_match(signal_profile: Dict[str, object], persona: dict) -> Dict[str, object]:
    """给商机与 buyer 做可解释匹配。"""
    reasons = []
    score = 0.0

    signal_word = signal_profile.get('signal_word', '')
    signal_brief = signal_profile.get('signal_brief', '')

    # --- 维度 1: 信号词直接匹配 persona 搜索词/文案/商品 ---
    signal_keywords = _extract_signal_keywords(signal_word, signal_brief)
    persona_text = ' '.join([
        _list_text(persona.get('recent_search_top10')),
        _list_text(persona.get('shop_voice_samples')),
        _list_text(persona.get('image_search_styles')),
        _list_text(persona.get('style_tags')),
        _list_text(persona.get('inquiry_concerns')),
        _list_text(persona.get('main_categories')),
    ]).lower()

    # 用信号词的关键字命中 persona 文本
    hit_keywords = [kw for kw in signal_keywords if kw.lower() in persona_text]
    if len(hit_keywords) >= 3:
        score += 0.45
        reasons.append(f"信号词高度关联: {'/'.join(hit_keywords[:4])}")
    elif len(hit_keywords) >= 2:
        score += 0.32
        reasons.append(f"信号词较相关: {'/'.join(hit_keywords[:3])}")
    elif len(hit_keywords) >= 1:
        score += 0.18
        reasons.append(f"信号词部分命中: {'/'.join(hit_keywords[:2])}")

    # --- 维度 2: 类目关键词匹配（用 CATEGORY_RULES 的关键词去匹配 persona 类目） ---
    categories = signal_profile.get('category_candidates', [])
    persona_categories_text = _list_text(persona.get('main_categories', []))
    category_matched = False
    for cat in categories:
        # 取这个大类对应的关键词列表
        cat_keywords = CATEGORY_RULES.get(cat, [])
        if cat_keywords and _contains_any(persona_categories_text, cat_keywords):
            score += 0.25
            reasons.append(f'类目相关: {cat}')
            category_matched = True
            break
    if not category_matched and categories:
        # 退而求其次：用大类目名的子串匹配
        for cat in categories:
            cat_parts = re.split(r'[·/ ]+', cat)
            if _contains_any(persona_categories_text, cat_parts):
                score += 0.15
                reasons.append(f'类目部分相关: {cat}')
                break

    # --- 维度 3: 渠道匹配 ---
    channels = signal_profile.get('channel_hints', [])
    persona_channels = persona.get('downstream_channels', [])
    if _contains_any(_list_text(persona_channels), channels):
        score += 0.15
        reasons.append('下游渠道匹配')

    # --- 维度 4: 风格标签匹配 ---
    style_text = ' '.join([
        _list_text(persona.get('style_tags')),
        _list_text(persona.get('image_search_styles')),
    ])
    style_hits = [
        tag for tag in signal_profile.get('style_tags', [])
        if tag != '趋势风格' and _contains_any(style_text, re.split(r'[·/ ]+', tag) or [tag])
    ]
    if style_hits:
        score += 0.12
        reasons.append(f"风格相关: {'/'.join(style_hits[:2])}")

    # --- 维度 5: 经营状态加分（小幅） ---
    exploration_status = persona.get('exploration_status', '')
    if exploration_status in ('试水扩品', '激进扩张', '转型中', '积极拓展'):
        score += 0.06
        reasons.append('经营状态适合试新')
    elif exploration_status in ('谨慎试探', '稳定经营'):
        score += 0.03

    score = min(round(score, 3), 1.0)
    if score >= 0.55:
        tier = '高适配'
        role = '核心视角'
    elif score >= 0.30:
        tier = '可迁移'
        role = '相邻迁移'
    elif score >= 0.15:
        tier = '边界观察'
        role = '边界视角'
    else:
        tier = '低适配'
        role = '低关联'

    return {
        'match_score': score,
        'match_tier': tier,
        'review_role': role,
        'match_reasons': reasons or ['未命中经营标签'],
    }


def select_review_personas(
    personas: List[dict],
    signal_profile: Dict[str, object],
    max_reviewers: int = 12,
    min_score: float = 0.20,
) -> List[dict]:
    """选择高适配 + 相邻迁移视角，不再强制纳入低适配/边界 buyer。"""
    scored = []
    for persona in personas:
        match = score_persona_match(signal_profile, persona)
        scored.append({**persona, 'signal_match': match})

    # 只保留达到最低分数门槛的 persona
    qualified = [
        p for p in scored
        if p['signal_match']['match_score'] >= min_score
    ]
    qualified.sort(key=lambda p: -p['signal_match']['match_score'])

    # 从 qualified 中按梯队选取
    groups = {
        'core': [p for p in qualified if p['signal_match']['match_tier'] == '高适配'],
        'adjacent': [p for p in qualified if p['signal_match']['match_tier'] == '可迁移'],
        'boundary': [p for p in qualified if p['signal_match']['match_tier'] == '边界观察'],
    }

    selected = []
    # 优先选核心适配，再补相邻迁移，最后少量边界（但不选低适配）
    quota = [('core', 8), ('adjacent', 4), ('boundary', 0)]
    for group_name, group_quota in quota:
        for persona in groups.get(group_name, [])[:group_quota]:
            if len(selected) < max_reviewers:
                selected.append(persona)

    # 如果 core+adjacent 仍不够，从 qualified 中按分数补齐（绝不低于 min_score）
    if len(selected) < max_reviewers:
        selected_ids = {p.get('buyer_id') for p in selected}
        for persona in qualified:
            if len(selected) >= max_reviewers:
                break
            if persona.get('buyer_id') not in selected_ids:
                selected.append(persona)
                selected_ids.add(persona.get('buyer_id'))

    return selected[:max_reviewers]
