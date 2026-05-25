"""
ODPS 数据导出脚本 (PyODPS Tunnel 直读版本)

使用 TableTunnel 直读分区数据，避免跨项目 SQL Instance 问题。

用法:
    python scripts/export_data_pyodps.py
    python scripts/export_data_pyodps.py --dry-run   # 仅探测，不写文件
    python scripts/export_data_pyodps.py --limit 100  # 只导前 100 条

导出结果:
    data/input/buyer_features.tsv
    data/input/buyer_profiles.tsv
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / '.env')

try:
    from odps import ODPS
    from odps.tunnel import TableTunnel
except ImportError:
    print("请先安装 pyodps: pip install pyodps")
    sys.exit(1)

ODPS_ACCESS_ID = os.getenv('ODPS_ACCESS_ID', '')
ODPS_ACCESS_KEY = os.getenv('ODPS_ACCESS_KEY', '')
ODPS_PROJECT = os.getenv('ODPS_PROJECT', 'cbuads_dev')
ODPS_ENDPOINT = os.getenv('ODPS_ENDPOINT', 'http://service-corp.odps.aliyun-inc.com/api')

OUTPUT_DIR = Path(__file__).parent.parent / 'data' / 'input'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 动线数据表 (无分区)
FEATURES_TABLE = 'buss_bizword_user_profile_data'
FEATURES_PROJECT = 'cbu_data_algo_dev'

# 画像表 (分区表)
PROFILE_TABLE = 'ads_cn_dap_bizworld_scene_node_merge_profile_d'
PROFILE_PROJECT = 'cbuads'
PROFILE_DS = '20260522'
PROFILE_PARTITION = f'ds={PROFILE_DS},scene_code=fx'

FEATURES_COLUMNS = [
    'buyer_id', 'inquiry_cnt', 'inquiry_contents',
    'image_search_cnt', 'image_search_contents',
    'search_cnt', 'search_keywords',
    'product_view_cnt', 'viewed_products',
    'cart_cnt', 'carted_products',
    'recommend_click_cnt', 'recommended_products',
    'video_play_cnt', 'video_products',
    'shop_view_cnt', 'shop_viewed_products',
]


def to_str(value):
    """将值转为字符串，None 转为 \\N，去除 tab/换行防止 TSV 错乱"""
    if value is None:
        return '\\N'
    text = str(value)
    text = text.replace('\t', ' ').replace('\n', ' ').replace('\r', '')
    return text


def get_odps_client(project=None):
    return ODPS(
        ODPS_ACCESS_ID, ODPS_ACCESS_KEY,
        project=project or ODPS_PROJECT,
        endpoint=ODPS_ENDPOINT
    )


def export_buyer_features_tunnel(limit=None, dry_run=False):
    """通过 Tunnel 直读动线行为数据"""
    print(f"[1/2] 导出 buyer_features (Tunnel 直读) ...")

    odps = get_odps_client(FEATURES_PROJECT)
    tunnel = TableTunnel(odps, project=FEATURES_PROJECT)

    session = tunnel.create_download_session(FEATURES_TABLE)
    total = session.count
    print(f"  表总行数: {total}")

    if dry_run:
        print("  [dry-run] 读取前 3 行样本:")
        with session.open_record_reader(0, min(3, total)) as reader:
            for record in reader:
                sample = {col: to_str(record[col]) for col in FEATURES_COLUMNS[:5]}
                print(f"    {sample}")
        return

    target = min(limit, total) if limit else total
    output_path = OUTPUT_DIR / 'buyer_features.tsv'

    start_time = time.time()
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\t'.join(FEATURES_COLUMNS) + '\n')
        count = 0
        with session.open_record_reader(0, target) as reader:
            for record in reader:
                values = []
                for col in FEATURES_COLUMNS:
                    values.append(to_str(record[col]))
                f.write('\t'.join(values) + '\n')
                count += 1
                if count % 1000 == 0:
                    elapsed = time.time() - start_time
                    rate = count / elapsed if elapsed > 0 else 0
                    eta = (target - count) / rate if rate > 0 else 0
                    print(f"  已导出 {count}/{target} ({100*count/target:.1f}%) "
                          f"速率 {rate:.0f} 行/s  ETA {eta:.0f}s")

    elapsed = time.time() - start_time
    print(f"  完成: {output_path} ({count} 行, {elapsed:.1f}s)")


def export_buyer_profiles_tunnel(limit=None, dry_run=False):
    """通过 Tunnel 直读画像 summary 数据"""
    print(f"[2/2] 导出 buyer_profiles (Tunnel 直读) ...")

    odps = get_odps_client(PROFILE_PROJECT)
    tunnel = TableTunnel(odps, project=PROFILE_PROJECT)

    session = tunnel.create_download_session(
        PROFILE_TABLE, partition_spec=PROFILE_PARTITION
    )
    total = session.count
    print(f"  分区 {PROFILE_PARTITION} 总行数: {total}")

    if dry_run:
        print("  [dry-run] 读取前 3 行样本:")
        with session.open_record_reader(0, min(3, total)) as reader:
            for record in reader:
                node_id = to_str(record['node_id'])
                node_type = to_str(record['node_type'])
                profile_str = to_str(record['profile'])
                profile = {}
                try:
                    profile = json.loads(profile_str) if profile_str != '\\N' else {}
                except (json.JSONDecodeError, TypeError):
                    pass
                summary = profile.get('summary', '')[:80]
                print(f"    node_id={node_id}, type={node_type}, summary={summary}...")
        return

    target = min(limit, total) if limit else total
    output_path = OUTPUT_DIR / 'buyer_profiles.tsv'

    start_time = time.time()
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('buyer_id\tprofile_text\n')
        count = 0
        skipped = 0
        with session.open_record_reader(0, target) as reader:
            for record in reader:
                node_type = to_str(record['node_type'])
                if node_type != 'buyer':
                    skipped += 1
                    continue

                node_id = to_str(record['node_id'])
                profile_str = to_str(record['profile'])

                profile_text = ''
                try:
                    if profile_str and profile_str != '\\N':
                        profile_data = json.loads(profile_str)
                        if isinstance(profile_data, dict):
                            profile_text = profile_data.get('summary', '')
                except (json.JSONDecodeError, TypeError):
                    pass

                if not profile_text or len(profile_text) < 100:
                    skipped += 1
                    continue

                profile_text = (profile_text
                                .replace('\t', ' ')
                                .replace('\n', ' ')
                                .replace('\r', ''))

                f.write(f'{node_id}\t{profile_text}\n')
                count += 1

                if count % 1000 == 0:
                    elapsed = time.time() - start_time
                    rate = count / elapsed if elapsed > 0 else 0
                    print(f"  已导出 {count} 条 buyer (跳过 {skipped} 条) "
                          f"速率 {rate:.0f} 行/s")

    elapsed = time.time() - start_time
    print(f"  完成: {output_path} ({count} 条 buyer, 跳过 {skipped} 条, {elapsed:.1f}s)")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='从 ODPS 导出 buyer 数据')
    parser.add_argument('--dry-run', action='store_true',
                        help='仅探测连接和样本，不写文件')
    parser.add_argument('--limit', type=int, default=None,
                        help='每张表只导前 N 行')
    parser.add_argument('--skip-features', action='store_true',
                        help='跳过动线数据导出')
    parser.add_argument('--skip-profiles', action='store_true',
                        help='跳过画像数据导出')
    args = parser.parse_args()

    if not ODPS_ACCESS_ID:
        print("请在 .env 中设置 ODPS_ACCESS_ID 和 ODPS_ACCESS_KEY")
        sys.exit(1)

    print(f"ODPS 配置:")
    print(f"  endpoint = {ODPS_ENDPOINT}")
    print(f"  features = {FEATURES_PROJECT}.{FEATURES_TABLE}")
    print(f"  profiles = {PROFILE_PROJECT}.{PROFILE_TABLE} ({PROFILE_PARTITION})")
    print()

    if not args.skip_features:
        export_buyer_features_tunnel(limit=args.limit, dry_run=args.dry_run)

    if not args.skip_profiles:
        export_buyer_profiles_tunnel(limit=args.limit, dry_run=args.dry_run)

    if not args.dry_run:
        print("\n✅ 数据导出完成！可以运行 python app.py 启动应用。")
