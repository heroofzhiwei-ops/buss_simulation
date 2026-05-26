"""阶段 2-3: 买家商机推演 + 视角碰撞"""
import asyncio
import json
from typing import Callable, Dict, List

from config import DATA_OUTPUT, LLM_CONCURRENCY_POST, LLM_CONCURRENCY_REPLY
from llm_client import llm_call, parse_json_loose
from prompts import BUYER_ASSESSMENT_PROMPT, CROSS_EXAM_PROMPT


# ============================================================
# 买家商机评估
# ============================================================
def _format_buyer_assessment_prompt(
    persona: dict,
    signal_word: str,
    signal_brief: str,
    signal_profile: Dict[str, object],
) -> str:
    all_searches = persona.get('recent_search_top10', [])
    granular_refs = [s for s in all_searches if len(str(s)) >= 4][:3] or all_searches[:3]
    match = persona.get('signal_match', {})

    return BUYER_ASSESSMENT_PROMPT.format(
        main_categories=persona.get('main_categories', []),
        gmv_tier=persona.get('gmv_tier', '未知'),
        price_band=persona.get('price_band', '未知'),
        downstream_channels=persona.get('downstream_channels', []),
        downstream_audience=persona.get('downstream_audience', ''),
        supply_mode=persona.get('supply_mode', '未知'),
        exploration_status=persona.get('exploration_status', '未知'),
        style_tags=persona.get('style_tags', []),
        key_traits=persona.get('key_traits', []),
        recent_search_top10=persona.get('recent_search_top10', []),
        search_granularity_reference='、'.join(granular_refs) or '(无)',
        image_search_styles=persona.get('image_search_styles', []),
        inquiry_voice_samples=persona.get('inquiry_voice_samples', []),
        inquiry_concerns=persona.get('inquiry_concerns', {}),
        shop_voice_samples='\n'.join(persona.get('shop_voice_samples', [])[:8]),
        profile_summary_raw=persona.get('profile_summary_raw', '')[:800],
        signal_word=signal_word,
        signal_brief=signal_brief,
        signal_categories=signal_profile.get('category_candidates', []),
        signal_styles=signal_profile.get('style_tags', []),
        signal_audiences=signal_profile.get('audience_hints', []),
        signal_channels=signal_profile.get('channel_hints', []),
        signal_price_band=signal_profile.get('price_band_hint', ''),
        signal_supply=signal_profile.get('supply_requirements', []),
        match_score=match.get('match_score', 0),
        review_role=match.get('review_role', '推演视角'),
        match_reasons=match.get('match_reasons', []),
    )


def _persona_brief(persona: dict) -> dict:
    return {
        'main_categories': persona.get('main_categories', []),
        'downstream_channels': persona.get('downstream_channels', []),
        'gmv_tier': persona.get('gmv_tier', ''),
        'price_band': persona.get('price_band', ''),
        'exploration_status': persona.get('exploration_status', ''),
        'key_traits': persona.get('key_traits', []),
    }


async def _gen_one_assessment(
    persona: dict,
    signal_word: str,
    signal_brief: str,
    signal_profile: Dict[str, object],
    sem: asyncio.Semaphore,
):
    async with sem:
        try:
            prompt = _format_buyer_assessment_prompt(
                persona, signal_word, signal_brief, signal_profile,
            )
            resp = await llm_call(prompt, temperature=0.72)
            data = parse_json_loose(resp)
            if not data:
                return None
            data['buyer_id'] = persona['buyer_id']
            data['persona_brief'] = _persona_brief(persona)
            data['signal_match'] = persona.get('signal_match', {})
            return data
        except Exception as e:
            print(f"[WARN] assessment fail buyer={persona.get('buyer_id')}: {e}")
            return None


async def generate_buyer_assessments(
    personas: List[dict],
    signal_word: str,
    signal_brief: str,
    signal_profile: Dict[str, object],
    progress_callback: Callable = None,
) -> List[dict]:
    sem = asyncio.Semaphore(LLM_CONCURRENCY_POST)
    completed = 0
    total = len(personas)

    async def _gen_with_progress(persona):
        nonlocal completed
        result = await _gen_one_assessment(
            persona, signal_word, signal_brief, signal_profile, sem,
        )
        completed += 1
        if progress_callback:
            progress_callback(f"买家推演: {completed}/{total}", completed, total)
        return result

    tasks = [_gen_with_progress(p) for p in personas]
    results = await asyncio.gather(*tasks)
    assessments = [r for r in results if r]
    print(f"[ASSESS] {len(assessments)}/{len(personas)} 买家推演生成成功")

    output_path = DATA_OUTPUT / 'assessments.jsonl'
    with open(output_path, 'w', encoding='utf-8') as f:
        for assessment in assessments:
            f.write(json.dumps(assessment, ensure_ascii=False) + '\n')
    return assessments


# ============================================================
# 视角碰撞
# ============================================================
def _format_other_assessments(assessments: List[dict], exclude_buyer_id: str) -> str:
    lines = []
    for item in assessments:
        if item['buyer_id'] == exclude_buyer_id:
            continue
        brief = item.get('persona_brief', {})
        category = (brief.get('main_categories', [''])[0]
                    if brief.get('main_categories') else '')
        channel = (brief.get('downstream_channels', [''])[0]
                   if brief.get('downstream_channels') else '')
        lines.append(
            f"[buyer_id={item['buyer_id']}] "
            f"[{category}/{channel}/{brief.get('gmv_tier', '')}] "
            f"适配={item.get('fit_level', '')}\n"
            f"  评估: {item.get('assessment', '')}\n"
            f"  翻译: {item.get('opportunity_translation', '')}\n"
            f"  衍生词: {item.get('derived_keywords', [])}\n"
            f"  风险: {item.get('risks', [])}"
        )
    return '\n\n'.join(lines)


async def _gen_one_cross_exam(
    persona: dict,
    assessments: List[dict],
    signal_word: str,
    sem: asyncio.Semaphore,
):
    async with sem:
        try:
            other_assessments_str = _format_other_assessments(
                assessments, persona['buyer_id'],
            )
            prompt = CROSS_EXAM_PROMPT.format(
                main_categories=persona.get('main_categories', []),
                downstream_channels=persona.get('downstream_channels', []),
                downstream_audience=persona.get('downstream_audience', ''),
                key_traits=persona.get('key_traits', []),
                review_role=persona.get('signal_match', {}).get('review_role', '推演视角'),
                signal_word=signal_word,
                other_assessments_formatted=other_assessments_str,
            )
            resp = await llm_call(prompt, temperature=0.76)
            data = parse_json_loose(resp)
            challenges = data.get('challenges', [])
            for challenge in challenges:
                challenge['from_buyer_id'] = persona['buyer_id']
                challenge['from_persona_brief'] = _persona_brief(persona)
            return challenges
        except Exception as e:
            print(f"[WARN] cross exam fail buyer={persona.get('buyer_id')}: {e}")
            return []


async def generate_cross_examinations(
    personas: List[dict],
    assessments: List[dict],
    signal_word: str,
    progress_callback: Callable = None,
) -> List[dict]:
    sem = asyncio.Semaphore(LLM_CONCURRENCY_REPLY)
    completed = 0
    total = len(personas)

    async def _gen_with_progress(persona):
        nonlocal completed
        result = await _gen_one_cross_exam(persona, assessments, signal_word, sem)
        completed += 1
        if progress_callback:
            progress_callback(f"视角碰撞: {completed}/{total}", completed, total)
        return result

    tasks = [_gen_with_progress(p) for p in personas]
    results = await asyncio.gather(*tasks)
    all_challenges = [challenge for challenges in results for challenge in challenges]
    print(f"[CROSS] 生成 {len(all_challenges)} 条视角碰撞")

    output_path = DATA_OUTPUT / 'cross_examinations.jsonl'
    with open(output_path, 'w', encoding='utf-8') as f:
        for challenge in all_challenges:
            f.write(json.dumps(challenge, ensure_ascii=False) + '\n')
    return all_challenges


# 兼容旧函数名。
async def generate_main_posts(personas, signal_word, signal_brief, progress_callback=None):
    from signal_analyzer import build_signal_profile

    signal_profile = build_signal_profile(signal_word, signal_brief)
    return await generate_buyer_assessments(
        personas, signal_word, signal_brief, signal_profile, progress_callback,
    )


async def generate_replies(personas, posts, signal_word, progress_callback=None):
    return await generate_cross_examinations(
        personas, posts, signal_word, progress_callback,
    )
