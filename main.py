"""命令行入口：persona 构建 → 商机画像 → 买家评估 → 交叉质询 → 机会地图"""
import asyncio
import json
import argparse
from pathlib import Path

from config import DATA_OUTPUT
from persona_builder import build_personas_pipeline
from post_generator import generate_buyer_assessments, generate_cross_examinations
from scoring import compute_resonance
from renderer import render_demo_html
from signal_analyzer import build_signal_profile, select_review_personas


def load_jsonl(path: Path) -> list:
    items = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


async def stage_personas(args):
    """阶段 1: 只跑 persona 构建"""
    await build_personas_pipeline(
        buyer_table=args.buyer_table,
        profile_table=args.profile_table,
        sample_limit=args.sample_limit,
    )


async def stage_demo(args):
    """阶段 2-5: 基于已有 personas_demo.jsonl 跑商机会诊 demo"""
    demo_path = DATA_OUTPUT / 'personas_demo.jsonl'
    if not demo_path.exists():
        raise FileNotFoundError(f"先跑 stage=personas 生成 {demo_path}")

    personas = load_jsonl(demo_path)
    print(f"[DEMO] 加载 {len(personas)} 个 demo persona")

    signal_profile = build_signal_profile(args.signal, args.signal_brief)
    reviewers = select_review_personas(personas, signal_profile)
    print(f"[DEMO] 选出 {len(reviewers)} 个买家评审视角")

    assessments = await generate_buyer_assessments(
        reviewers, args.signal, args.signal_brief, signal_profile,
    )
    if not assessments:
        print("[ERROR] 没有任何买家评估生成成功，退出")
        return

    challenges = await generate_cross_examinations(
        reviewers, assessments, args.signal,
    )
    resonance = await compute_resonance(reviewers, assessments, args.signal)
    output_html = render_demo_html(
        assessments, challenges, resonance,
        args.signal, args.signal_brief, signal_profile,
    )
    print(f"\n✅ Demo 完成: 浏览器打开 {output_html}")


async def stage_all(args):
    """端到端: persona + demo"""
    await stage_personas(args)
    await stage_demo(args)


def main():
    parser = argparse.ArgumentParser(
        description='1688 商机信号个性化反应模拟器 - 命令行入口')
    parser.add_argument('--stage', choices=['personas', 'demo', 'all'],
                        default='all')
    parser.add_argument('--buyer-table', default='buyer_features.tsv')
    parser.add_argument('--profile-table', default='buyer_profiles.tsv')
    parser.add_argument('--sample-limit', type=int, default=300,
                        help='persona 阶段只跑前 N 个 buyer')
    parser.add_argument('--signal', default='巴恩风',
                        help='商机信号词')
    parser.add_argument('--signal-brief',
                        default='美式复古休闲风，近期小红书话题热度环比+120%，'
                                '主打oversize衬衫和复古工装')
    args = parser.parse_args()

    if args.stage == 'personas':
        asyncio.run(stage_personas(args))
    elif args.stage == 'demo':
        asyncio.run(stage_demo(args))
    else:
        asyncio.run(stage_all(args))


if __name__ == '__main__':
    main()
