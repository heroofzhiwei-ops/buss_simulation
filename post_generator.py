"""阶段 2-3: 主帖 + 回帖生成"""
import asyncio
import json
from typing import List, Callable

from config import DATA_OUTPUT, LLM_CONCURRENCY_POST, LLM_CONCURRENCY_REPLY
from llm_client import llm_call, parse_json_loose
from prompts import MAIN_POST_PROMPT, REPLY_PROMPT


# ============================================================
# 主帖
# ============================================================
def _format_main_post_prompt(persona: dict, signal_word: str,
                             signal_brief: str) -> str:
    return MAIN_POST_PROMPT.format(
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
        image_search_styles=persona.get('image_search_styles', []),
        inquiry_voice_samples=persona.get('inquiry_voice_samples', []),
        inquiry_concerns=persona.get('inquiry_concerns', {}),
        shop_voice_samples='\n'.join(persona.get('shop_voice_samples', [])[:8]),
        profile_summary_raw=persona.get('profile_summary_raw', '')[:800],
        signal_word=signal_word,
        signal_brief=signal_brief,
    )


async def _gen_one_post(persona: dict, signal_word: str, signal_brief: str,
                        sem: asyncio.Semaphore):
    async with sem:
        try:
            prompt = _format_main_post_prompt(persona, signal_word, signal_brief)
            resp = await llm_call(prompt, temperature=0.85)
            data = parse_json_loose(resp)
            if not data:
                return None
            data['buyer_id'] = persona['buyer_id']
            data['persona_brief'] = {
                'main_categories': persona.get('main_categories', []),
                'downstream_channels': persona.get('downstream_channels', []),
                'gmv_tier': persona.get('gmv_tier', ''),
                'exploration_status': persona.get('exploration_status', ''),
                'key_traits': persona.get('key_traits', []),
            }
            return data
        except Exception as e:
            print(f"[WARN] main post fail buyer={persona.get('buyer_id')}: {e}")
            return None


async def generate_main_posts(
    personas: List[dict],
    signal_word: str,
    signal_brief: str,
    progress_callback: Callable = None,
) -> List[dict]:
    sem = asyncio.Semaphore(LLM_CONCURRENCY_POST)
    completed = 0
    total = len(personas)

    async def _gen_with_progress(persona):
        nonlocal completed
        result = await _gen_one_post(persona, signal_word, signal_brief, sem)
        completed += 1
        if progress_callback:
            progress_callback(f"主帖生成: {completed}/{total}", completed, total)
        return result

    tasks = [_gen_with_progress(p) for p in personas]
    results = await asyncio.gather(*tasks)
    posts = [r for r in results if r]
    print(f"[POST] {len(posts)}/{len(personas)} 主帖生成成功")

    output_path = DATA_OUTPUT / 'posts.jsonl'
    with open(output_path, 'w', encoding='utf-8') as f:
        for post in posts:
            f.write(json.dumps(post, ensure_ascii=False) + '\n')
    return posts


# ============================================================
# 回帖
# ============================================================
def _format_other_posts(posts: List[dict], exclude_buyer_id: str) -> str:
    lines = []
    for post in posts:
        if post['buyer_id'] == exclude_buyer_id:
            continue
        brief = post.get('persona_brief', {})
        category = (brief.get('main_categories', [''])[0]
                    if brief.get('main_categories') else '')
        channel = (brief.get('downstream_channels', [''])[0]
                   if brief.get('downstream_channels') else '')
        lines.append(
            f"[buyer_id={post['buyer_id']}] "
            f"[{category}/{channel}/{brief.get('gmv_tier', '')}] "
            f"立场={post.get('stance', '')}\n"
            f"  正文: {post.get('voice', '')}\n"
            f"  落地: {post.get('concrete_translation', '')}\n"
            f"  衍生词: {post.get('derived_keywords', [])}"
        )
    return '\n\n'.join(lines)


async def _gen_one_reply(persona: dict, posts: List[dict],
                         signal_word: str, sem: asyncio.Semaphore):
    async with sem:
        try:
            other_posts_str = _format_other_posts(posts, persona['buyer_id'])
            prompt = REPLY_PROMPT.format(
                main_categories=persona.get('main_categories', []),
                downstream_channels=persona.get('downstream_channels', []),
                downstream_audience=persona.get('downstream_audience', ''),
                key_traits=persona.get('key_traits', []),
                signal_word=signal_word,
                other_posts_formatted=other_posts_str,
            )
            resp = await llm_call(prompt, temperature=0.85)
            data = parse_json_loose(resp)
            replies = data.get('replies', [])
            for reply in replies:
                reply['from_buyer_id'] = persona['buyer_id']
            return replies
        except Exception as e:
            print(f"[WARN] reply fail buyer={persona.get('buyer_id')}: {e}")
            return []


async def generate_replies(
    personas: List[dict],
    posts: List[dict],
    signal_word: str,
    progress_callback: Callable = None,
) -> List[dict]:
    sem = asyncio.Semaphore(LLM_CONCURRENCY_REPLY)
    completed = 0
    total = len(personas)

    async def _gen_with_progress(persona):
        nonlocal completed
        result = await _gen_one_reply(persona, posts, signal_word, sem)
        completed += 1
        if progress_callback:
            progress_callback(f"回帖生成: {completed}/{total}", completed, total)
        return result

    tasks = [_gen_with_progress(p) for p in personas]
    results = await asyncio.gather(*tasks)
    all_replies = [reply for replies in results for reply in replies]
    print(f"[REPLY] 生成 {len(all_replies)} 条回帖")

    output_path = DATA_OUTPUT / 'replies.jsonl'
    with open(output_path, 'w', encoding='utf-8') as f:
        for reply in all_replies:
            f.write(json.dumps(reply, ensure_ascii=False) + '\n')
    return all_replies
