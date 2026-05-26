"""阶段 4: 机会评估可参考度评分"""
import asyncio
import json
from typing import Callable, Dict, List
from collections import defaultdict

from config import DATA_OUTPUT, LLM_CONCURRENCY_SCORE
from llm_client import llm_call, parse_json_loose
from prompts import RESONANCE_PROMPT


def _format_assessments_for_scoring(assessments: List[dict]) -> str:
    lines = []
    for item in assessments:
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


async def _score_one(persona: dict, assessments: List[dict],
                     signal_word: str, sem: asyncio.Semaphore):
    async with sem:
        try:
            assessments_str = _format_assessments_for_scoring(assessments)
            prompt = RESONANCE_PROMPT.format(
                main_categories=persona.get('main_categories', []),
                downstream_channels=persona.get('downstream_channels', []),
                downstream_audience=persona.get('downstream_audience', ''),
                key_traits=persona.get('key_traits', []),
                signal_word=signal_word,
                assessments_formatted=assessments_str,
            )
            resp = await llm_call(prompt, temperature=0.25)
            data = parse_json_loose(resp)
            return persona['buyer_id'], data.get('scores', [])
        except Exception as e:
            print(f"[WARN] score fail buyer={persona.get('buyer_id')}: {e}")
            return persona['buyer_id'], []


async def compute_resonance(
    personas: List[dict],
    assessments: List[dict],
    signal_word: str,
    progress_callback: Callable = None,
) -> Dict[str, dict]:
    """返回每个推演结果在买家视角池中的可参考度汇总。"""
    sem = asyncio.Semaphore(LLM_CONCURRENCY_SCORE)
    completed = 0
    total = len(personas)

    async def _score_with_progress(persona):
        nonlocal completed
        result = await _score_one(persona, assessments, signal_word, sem)
        completed += 1
        if progress_callback:
            progress_callback(f"机会可参考度评分: {completed}/{total}", completed, total)
        return result

    tasks = [_score_with_progress(p) for p in personas]
    results = await asyncio.gather(*tasks)

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
    assessment_by_id = {item.get('buyer_id'): item for item in assessments}
    for target_id, item in assessment_by_id.items():
        values = score_accumulator.get(target_id, [])
        avg = sum(values) / len(values) if values else 0
        summary[target_id] = {
            'avg_score': round(avg, 3),
            'voter_count': len(values),
            'like_count': int(round(avg * 30)),
            'resonance_score': round(avg * 100),
            'fit_level': item.get('fit_level', ''),
        }

    output_path = DATA_OUTPUT / 'resonance.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[SCORE] 落盘: {output_path}")
    return summary
