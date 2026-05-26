"""Buyer 个体环境包加载。

右侧入口的推演从一个 buyer_id 出发，先实时查询该 buyer 对应的同行、
相似经营体或竞对人群，再复用左侧的商机推演链路。
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from config import (BUYER_ENV_MAX_SIZE, BUYER_ENV_PERSONA_JSON_COLUMN,
                    BUYER_ENV_POSTGRES_DSN, BUYER_ENV_TABLE)

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - exercised only in uninstalled envs.
    psycopg = None
    dict_row = None


IDENTIFIER_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


class BuyerEnvironmentError(RuntimeError):
    """Raised when the buyer environment package cannot be loaded."""


def _quote_identifier(identifier: str) -> str:
    parts = identifier.split('.')
    if not parts or any(not IDENTIFIER_RE.match(part) for part in parts):
        raise BuyerEnvironmentError(
            f'非法 BUYER_ENV_TABLE 配置: {identifier!r}'
        )
    return '.'.join(f'"{part}"' for part in parts)


def _coerce_json(value: Any):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    return None


def _coerce_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    parsed = _coerce_json(value)
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    if isinstance(value, str):
        parts = re.split(r'[|,，/、]+', value)
        return [part.strip() for part in parts if part.strip()]
    return [str(value).strip()] if str(value).strip() else []


def _coerce_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    parsed = _coerce_json(value)
    return parsed if isinstance(parsed, dict) else {}


def _row_to_persona(row: Dict[str, Any]) -> dict:
    persona_json = row.get(BUYER_ENV_PERSONA_JSON_COLUMN)
    persona = _coerce_json(persona_json)
    if isinstance(persona, dict):
        persona = dict(persona)
    else:
        persona = {}

    related_id = (
        row.get('related_buyer_id')
        or row.get('peer_buyer_id')
        or row.get('competitor_buyer_id')
        or row.get('target_buyer_id')
        or persona.get('buyer_id')
    )
    if not related_id:
        raise BuyerEnvironmentError(
            '个体环境包查询结果缺少 related_buyer_id / persona.buyer_id'
        )

    persona.setdefault('buyer_id', str(related_id))
    persona.setdefault('main_categories', _coerce_list(row.get('main_categories')))
    persona.setdefault('downstream_channels', _coerce_list(row.get('downstream_channels')))
    persona.setdefault('downstream_audience', row.get('downstream_audience') or '')
    persona.setdefault('gmv_tier', row.get('gmv_tier') or '未知')
    persona.setdefault('price_band', row.get('price_band') or '未知')
    persona.setdefault('supply_mode', row.get('supply_mode') or '未知')
    persona.setdefault('exploration_status', row.get('exploration_status') or '未知')
    persona.setdefault('style_tags', _coerce_list(row.get('style_tags')))
    persona.setdefault('key_traits', _coerce_list(row.get('key_traits')))
    persona.setdefault('shop_voice_samples', _coerce_list(row.get('shop_voice_samples')))
    persona.setdefault('recent_search_top10', _coerce_list(row.get('recent_search_top10')))
    persona.setdefault('image_search_styles', _coerce_list(row.get('image_search_styles')))
    persona.setdefault('image_search_brands', _coerce_list(row.get('image_search_brands')))
    persona.setdefault('inquiry_concerns', _coerce_dict(row.get('inquiry_concerns')))
    persona.setdefault('inquiry_voice_samples', _coerce_list(row.get('inquiry_voice_samples')))
    persona.setdefault('inquiry_distribution', _coerce_dict(row.get('inquiry_distribution')))
    persona.setdefault('profile_summary_raw', row.get('profile_summary_raw') or '')

    persona['environment_context'] = {
        'root_buyer_id': str(row.get('buyer_id') or ''),
        'relation_type': row.get('relation_type') or row.get('relation') or 'related',
        'relation_score': row.get('relation_score') or row.get('score'),
        'relation_reason': row.get('relation_reason') or '',
    }
    return persona


def load_buyer_environment_personas(buyer_id: str, limit: int = None) -> List[dict]:
    """Load buyer_id-centered persona pool from PostgreSQL.

    Expected default table shape:
      buyer_id, related_buyer_id, relation_type, relation_score, persona_json

    `persona_json` should contain the same persona fields produced by
    persona_builder.py. If persona_json is absent or partial, this loader also
    accepts persona fields as individual columns.
    """
    if not BUYER_ENV_POSTGRES_DSN:
        raise BuyerEnvironmentError(
            '未配置 BUYER_ENV_POSTGRES_DSN / POSTGRES_DSN / DATABASE_URL，'
            '无法加载 buyer 个体环境包'
        )
    if psycopg is None:
        raise BuyerEnvironmentError(
            '缺少 psycopg 依赖，请先安装 requirements.txt'
        )

    safe_table = _quote_identifier(BUYER_ENV_TABLE)
    query_limit = max(1, min(int(limit or BUYER_ENV_MAX_SIZE), BUYER_ENV_MAX_SIZE))
    sql = f"""
        SELECT *
        FROM {safe_table}
        WHERE buyer_id = %s
        ORDER BY relation_score DESC NULLS LAST, related_buyer_id
        LIMIT %s
    """

    try:
        with psycopg.connect(BUYER_ENV_POSTGRES_DSN, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (buyer_id, query_limit))
                rows = cur.fetchall()
    except Exception as exc:
        raise BuyerEnvironmentError(
            f'查询 buyer 个体环境包失败 buyer_id={buyer_id}: {exc}'
        ) from exc

    if not rows:
        raise BuyerEnvironmentError(
            f'没有找到 buyer_id={buyer_id} 对应的个体环境包数据'
        )

    personas = [_row_to_persona(row) for row in rows]
    return personas
