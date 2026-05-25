"""阶段 1: 从原始 buyer 数据 + 画像表 构建 persona"""
import re
import json
import asyncio
from collections import Counter, defaultdict
from typing import List, Dict, Callable

import pandas as pd

from config import (DATA_INPUT, DATA_OUTPUT,
                    FILTER_MIN_ACTIVE_DIMS, FILTER_MIN_TOTAL_ACTIONS,
                    FILTER_MIN_UNIQUE_TITLES, FILTER_MIN_PROFILE_LEN,
                    PROFILE_LLM_INPUT_MAX, PROFILE_RAW_KEEP_LEN,
                    PERSONA_VOICE_SAMPLES, LLM_CONCURRENCY_PROFILE,
                    DEMO_PERSONA_COUNT)
from llm_client import llm_call, parse_json_loose
from prompts import PROFILE_EXTRACT_PROMPT

BEHAVIOR_COLS = [
    'inquiry_cnt', 'image_search_cnt', 'search_cnt',
    'product_view_cnt', 'cart_cnt', 'recommend_click_cnt',
    'video_play_cnt', 'shop_view_cnt',
]


# ============================================================
# 筛选
# ============================================================
def filter_quality_buyers(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in BEHAVIOR_COLS:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

    df['active_dims'] = (df[BEHAVIOR_COLS] > 0).sum(axis=1)
    df['total_actions'] = df[BEHAVIOR_COLS].sum(axis=1)

    def count_unique_titles(row):
        titles = set()
        for field in ['viewed_products', 'carted_products', 'recommended_products',
                      'video_products', 'shop_viewed_products']:
            value = row.get(field)
            if isinstance(value, str) and value != '\\N':
                for title in value.split('|'):
                    title = title.strip()
                    if len(title) >= 8:
                        titles.add(title[:30])
        return len(titles)

    df['unique_titles'] = df.apply(count_unique_titles, axis=1)

    mask = (
        (df['active_dims'] >= FILTER_MIN_ACTIVE_DIMS)
        & (df['total_actions'] >= FILTER_MIN_TOTAL_ACTIONS)
        & (df['unique_titles'] >= FILTER_MIN_UNIQUE_TITLES)
        & (df['search_cnt'] > 0)
    )
    return df[mask].reset_index(drop=True)


# ============================================================
# 字段解析
# ============================================================
def parse_inquiry(text: str) -> dict:
    if not isinstance(text, str) or text == '\\N':
        return {}

    items = [x for x in text.split('||') if x.strip()]
    pre = mid = after = 0
    concerns = defaultdict(int)
    raw_asks = []

    for item in items:
        if ':' not in item:
            continue
        tag, content = item.split(':', 1)
        content = content.strip()
        if 5 <= len(content) <= 60:
            raw_asks.append(content)

        if tag.startswith('售前'):
            pre += 1
        elif tag.startswith('售中'):
            mid += 1
        elif tag.startswith('售后'):
            after += 1

        rules = [
            (('议价', '价格'), '议价/压价'),
            (('催促发货', '物流', '快递', '配送', '揽收'), '物流时效'),
            (('退货', '退款'), '退货退款'),
            (('补发',), '少件漏发/补发'),
            (('商品对比', '商品参数'), '商品研究'),
            (('改价',), '频繁改价(代发特征)'),
            (('密文', '面单'), '密文/抖音单(代发特征)'),
            (('破损', '质量'), '品控敏感'),
        ]
        for keywords, label in rules:
            if any(keyword in tag for keyword in keywords):
                concerns[label] += 1

    total = pre + mid + after
    seen, unique_asks = set(), []
    for ask in raw_asks:
        key = ask[:20]
        if key in seen:
            continue
        seen.add(key)
        unique_asks.append(ask)

    return {
        'inquiry_distribution': {
            '售前比例': round(pre / total, 2) if total else 0,
            '售中比例': round(mid / total, 2) if total else 0,
            '售后比例': round(after / total, 2) if total else 0,
            '总询盘数': total,
        },
        'inquiry_concerns': dict(sorted(concerns.items(), key=lambda x: -x[1])[:5]),
        'inquiry_voice_samples': unique_asks[:5],
    }


def parse_image_search(text: str) -> dict:
    if not isinstance(text, str) or text == '\\N':
        return {}

    items = [x for x in text.split('|') if x.strip()]
    styles, brands, prices = [], [], []

    for item in items:
        if ':' not in item:
            continue
        _, attrs = item.split(':', 1)
        for attr in attrs.split('|'):
            attr = attr.strip()
            if not attr:
                continue
            brand_match = re.search(r'品牌为([^,，]+)', attr)
            if brand_match:
                brands.append(brand_match.group(1).strip())
                continue
            price_match = re.search(r'(\d+)\s*元', attr)
            if price_match:
                prices.append(int(price_match.group(1)))
                continue
            if 2 <= len(attr) <= 8 and not any(c in attr for c in '元品牌'):
                styles.append(attr)

    style_top = [style for style, _ in Counter(styles).most_common(15)]
    return {
        'image_search_styles': style_top,
        'image_search_brands': list(dict.fromkeys(brands))[:10],
        'image_search_price_range': (
            f"¥{min(prices)}-{max(prices)}" if prices else None
        ),
    }


def parse_search_keywords(text: str, top_k: int = 12) -> list:
    if not isinstance(text, str) or text == '\\N':
        return []
    keywords = [kw.strip() for kw in text.split('|') if kw.strip()]
    return list(dict.fromkeys(keywords))[:top_k]


def collect_product_titles(row: dict) -> list:
    titles = []
    for field in ['viewed_products', 'carted_products', 'recommended_products',
                  'video_products', 'shop_viewed_products']:
        value = row.get(field)
        if isinstance(value, str) and value != '\\N':
            titles.extend(t.strip() for t in value.split('|') if t.strip())

    seen, unique_titles = set(), []
    for title in titles:
        if len(title) < 8:
            continue
        key = title[:25]
        if key in seen:
            continue
        seen.add(key)
        unique_titles.append(title)
    return unique_titles


def diversify_voice_samples(titles: list, n: int = PERSONA_VOICE_SAMPLES) -> list:
    if len(titles) <= n:
        return titles
    step = max(1, len(titles) // n)
    return [titles[i] for i in range(0, len(titles), step)][:n]


# ============================================================
# 画像 LLM 结构化（异步并发）
# ============================================================
async def _extract_one_profile(buyer_id: str, profile_text: str,
                               sem: asyncio.Semaphore):
    async with sem:
        try:
            prompt = PROFILE_EXTRACT_PROMPT.format(
                profile_text=profile_text[:PROFILE_LLM_INPUT_MAX]
            )
            resp = await llm_call(prompt, temperature=0.2)
            return buyer_id, parse_json_loose(resp)
        except Exception as e:
            print(f"[WARN] profile extract fail buyer={buyer_id}: {e}")
            return buyer_id, {}


async def llm_extract_profile_batch(
    profile_pairs: List[tuple],
    progress_callback: Callable = None,
) -> Dict[str, dict]:
    sem = asyncio.Semaphore(LLM_CONCURRENCY_PROFILE)
    completed = 0
    total = len(profile_pairs)

    async def _extract_with_progress(buyer_id, profile_text):
        nonlocal completed
        result = await _extract_one_profile(buyer_id, profile_text, sem)
        completed += 1
        if progress_callback:
            progress_callback(f"画像结构化: {completed}/{total}", completed, total)
        return result

    tasks = [_extract_with_progress(bid, txt) for bid, txt in profile_pairs]
    results = await asyncio.gather(*tasks)
    return dict(results)


# ============================================================
# Persona 组装
# ============================================================
def build_persona(row: dict, profile_struct: dict, profile_raw: str) -> dict:
    inquiry_data = parse_inquiry(row.get('inquiry_contents'))
    image_data = parse_image_search(row.get('image_search_contents'))
    search_keywords = parse_search_keywords(row.get('search_keywords'))
    titles = collect_product_titles(row)
    voice_samples = diversify_voice_samples(titles)

    return {
        'buyer_id': str(row['buyer_id']),
        # 画像层
        'main_categories': profile_struct.get('main_categories', []),
        'downstream_channels': profile_struct.get('downstream_channels', []),
        'downstream_audience': profile_struct.get('downstream_audience', ''),
        'gmv_tier': profile_struct.get('gmv_tier', '未知'),
        'price_band': profile_struct.get('price_band', '未知'),
        'supply_mode': profile_struct.get('supply_mode', '未知'),
        'exploration_status': profile_struct.get('exploration_status', '未知'),
        'style_tags': profile_struct.get('style_tags', []),
        'key_traits': profile_struct.get('key_traits', []),
        # 行为层
        'shop_voice_samples': voice_samples,
        'recent_search_top10': search_keywords[:10],
        'image_search_styles': image_data.get('image_search_styles', [])[:8],
        'image_search_brands': image_data.get('image_search_brands', [])[:5],
        'inquiry_concerns': inquiry_data.get('inquiry_concerns', {}),
        'inquiry_voice_samples': inquiry_data.get('inquiry_voice_samples', []),
        'inquiry_distribution': inquiry_data.get('inquiry_distribution', {}),
        # 画像原文（prompt 兜底用）
        'profile_summary_raw': profile_raw[:PROFILE_RAW_KEEP_LEN],
    }


# ============================================================
# Demo 多样性抽样
# ============================================================
def select_demo_personas(personas: List[dict],
                         n: int = DEMO_PERSONA_COUNT) -> List[dict]:
    """按 (主营 × 下游 × 体量 × 探索状态) 分层，每个 cell 取 1"""
    buckets = defaultdict(list)
    for persona in personas:
        key = (
            persona['main_categories'][0] if persona['main_categories'] else '未知',
            persona['downstream_channels'][0] if persona['downstream_channels'] else '未知',
            persona['gmv_tier'],
            persona['exploration_status'],
        )
        buckets[key].append(persona)

    selected = []
    for _, persona_list in buckets.items():
        persona_list.sort(key=lambda x: -len(x['shop_voice_samples']))
        selected.append(persona_list[0])
        if len(selected) >= n:
            break
    return selected[:n]


# ============================================================
# 主流程
# ============================================================
async def build_personas_pipeline(
    buyer_table: str,
    profile_table: str,
    sample_limit: int = None,
    progress_callback: Callable = None,
):
    """
    sample_limit: None=全量；给整数则只跑前 N 个（开发期建议 200）
    progress_callback: 可选回调 (message, current, total) 用于 Web 端进度推送
    """
    def _progress(msg, current=0, total=0):
        if progress_callback:
            progress_callback(msg, current, total)
        print(f"  {msg}")

    # 1. 加载
    buyer_df = pd.read_csv(DATA_INPUT / buyer_table, sep='\t',
                           dtype={'buyer_id': str})
    profile_df = pd.read_csv(DATA_INPUT / profile_table, sep='\t',
                             dtype={'buyer_id': str})[['buyer_id', 'profile_text']]
    _progress(f"加载完成: buyer={len(buyer_df)}, profile={len(profile_df)}")

    # 2. 筛选
    qualified = filter_quality_buyers(buyer_df)
    _progress(f"行为筛选: {len(buyer_df)} → {len(qualified)}")

    # 3. join 画像 + 画像长度过滤
    qualified = qualified.merge(profile_df, on='buyer_id', how='left')
    qualified = qualified[
        qualified['profile_text'].notna()
        & (qualified['profile_text'].str.len() >= FILTER_MIN_PROFILE_LEN)
    ].reset_index(drop=True)
    _progress(f"有画像后: {len(qualified)}")

    if sample_limit:
        qualified = qualified.head(sample_limit).copy()
        _progress(f"限制 sample_limit={sample_limit}")

    # 4. 画像 LLM 结构化
    pairs = list(zip(qualified['buyer_id'], qualified['profile_text']))
    _progress(f"开始画像 LLM 结构化（{len(pairs)} 个）")

    struct_map = await llm_extract_profile_batch(pairs, progress_callback)
    success_count = sum(1 for v in struct_map.values() if v)
    _progress(f"画像结构化完成: 成功 {success_count}/{len(pairs)}")

    # 5. 组装 persona
    personas = []
    for _, row in qualified.iterrows():
        buyer_id = row['buyer_id']
        if not struct_map.get(buyer_id):
            continue
        personas.append(build_persona(
            row.to_dict(), struct_map[buyer_id], row['profile_text']
        ))

    # 6. 输出全量
    output_full = DATA_OUTPUT / 'personas.jsonl'
    with open(output_full, 'w', encoding='utf-8') as f:
        for persona in personas:
            f.write(json.dumps(persona, ensure_ascii=False) + '\n')
    _progress(f"全量 persona 落盘: {len(personas)} 条")

    # 7. demo 抽样
    demo_set = select_demo_personas(personas)
    output_demo = DATA_OUTPUT / 'personas_demo.jsonl'
    with open(output_demo, 'w', encoding='utf-8') as f:
        for persona in demo_set:
            f.write(json.dumps(persona, ensure_ascii=False) + '\n')
    _progress(f"Demo 样本落盘: {len(demo_set)} 条")

    return personas, demo_set
