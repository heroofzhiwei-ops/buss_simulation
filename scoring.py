"""阶段 4: 共鸣度评分"""
import asyncio
import json
from typing import List, Dict, Callable
from collections import defaultdict

from config import DATA_OUTPUT, LLM_CONCURRENCY_SCORE
from llm_client import llm_call, parse_json_loose
from prompts import RESONANCE_PROMPT


def _format_posts_for_scoring(posts: List[dict]) -> str:
    lines = []
    for post in posts:
        brief = post.get('persona_brief', {})
        category = (brief.get('main_categories', [''])[0]
                    if brief.get('main_categories') else '')
        channel = (brief.get('downstream_channels', [''])[0]
                   if brief.get('downstream_channels') else '')
        lines.append(
            f"[buyer_id={post['buyer_id']}] "
            f"[{category}/{channel}/{brief.get('gmv_tier', '')}]\n"
            f"  正文: {post.get('voice', '')}\n"
            f"  落地: {post.get('concrete_translation', '')}"
        )
    return '\n\n'.join(lines)


async def _score_one(persona: dict, posts: List[dict],
                     signal_word: str, sem: asyncio.Semaphore):
    async with sem:
        try:
            posts_str = _format_posts_for_scoring(posts)
            prompt = RESONANCE_PROMPT.format(
                main_categories=persona.get('main_categories', []),
                downstream_channels=persona.get('downstream_channels', []),
                downstream_audience=persona.get('downstream_audience', ''),
                key_traits=persona.get('key_traits', []),
                signal_word=signal_word,
                posts_formatted=posts_str,
            )
            resp = await llm_call(prompt, temperature=0.3)
            data = parse_json_loose(resp)
            return persona['buyer_id'], data.get('scores', [])
        except Exception as e:
            print(f"[WARN] score fail buyer={persona.get('buyer_id')}: {e}")
            return persona['buyer_id'], []


async def compute_resonance(
    personas: List[dict],
    posts: List[dict],
    signal_word: str,
    progress_callback: Callable = None,
) -> Dict[str, dict]:
    """
    返回:
    {
      target_buyer_id: {
        "avg_score": 0.x,
        "voter_count": N,
        "like_count": M,
        "resonance_score": 0-100
      }
    }
    """
    sem = asyncio.Semaphore(LLM_CONCURRENCY_SCORE)
    completed = 0
    total = len(personas)

    async def _score_with_progress(persona):
        nonlocal completed
        result = await _score_one(persona, posts, signal_word, sem)
        completed += 1
        if progress_callback:
            progress_callback(f"共鸣度评分: {completed}/{total}", completed, total)
        return result

    tasks = [_score_with_progress(p) for p in personas]
    results = await asyncio.gather(*tasks)

    # 聚合：对每个被打分的 buyer 取平均
    score_accumulator = defaultdict(list)
    for voter_id, scores in results:
        for score_item in scores:
            target_id = score_item.get('buyer_id')
            try:
                value = float(score_item.get('score', 0))
            except (TypeError, ValueError):
                continue
            if target_id and target_id != voter_id:
                score_accumulator[target_id].append(value)

    summary = {}
    for target_id, values in score_accumulator.items():
        avg = sum(values) / len(values) if values else 0
        summary[target_id] = {
            'avg_score': round(avg, 3),
            'voter_count': len(values),
            'like_count': int(round(avg * 30)),
            'resonance_score': round(avg * 100),
        }

    output_path = DATA_OUTPUT / 'resonance.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[SCORE] 落盘: {output_path}")
    return summary
