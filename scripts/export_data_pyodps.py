"""
ODPS 数据导出脚本 (PyODPS 版本)

使用前需安装: pip install pyodps
并配置 ODPS 访问凭证。

用法:
    python scripts/export_data_pyodps.py

导出结果:
    data/input/buyer_features.tsv
    data/input/buyer_profiles.tsv
"""
import os
import sys
from pathlib import Path

try:
    from odps import ODPS
except ImportError:
    print("请先安装 pyodps: pip install pyodps")
    sys.exit(1)

# ODPS 连接配置 - 请根据实际情况修改
ODPS_ACCESS_ID = os.getenv('ODPS_ACCESS_ID', '')
ODPS_ACCESS_KEY = os.getenv('ODPS_ACCESS_KEY', '')
ODPS_PROJECT = os.getenv('ODPS_PROJECT', 'cbu_data_algo_dev')
ODPS_ENDPOINT = os.getenv('ODPS_ENDPOINT', 'http://service.odps.aliyun.com/api')

OUTPUT_DIR = Path(__file__).parent.parent / 'data' / 'input'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def export_buyer_features():
    """导出动线行为数据"""
    print("[1/2] 导出 buyer_features ...")

    odps = ODPS(ODPS_ACCESS_ID, ODPS_ACCESS_KEY, ODPS_PROJECT, ODPS_ENDPOINT)

    sql = """
    SELECT
        buyer_id,
        inquiry_cnt, inquiry_contents,
        image_search_cnt, image_search_contents,
        search_cnt, search_keywords,
        product_view_cnt, viewed_products,
        cart_cnt, carted_products,
        recommend_click_cnt, recommended_products,
        video_play_cnt, video_products,
        shop_view_cnt, shop_viewed_products
    FROM cbu_data_algo_dev.buss_bizword_user_profile_data
    """

    output_path = OUTPUT_DIR / 'buyer_features.tsv'
    columns = [
        'buyer_id', 'inquiry_cnt', 'inquiry_contents',
        'image_search_cnt', 'image_search_contents',
        'search_cnt', 'search_keywords',
        'product_view_cnt', 'viewed_products',
        'cart_cnt', 'carted_products',
        'recommend_click_cnt', 'recommended_products',
        'video_play_cnt', 'video_products',
        'shop_view_cnt', 'shop_viewed_products',
    ]

    with odps.execute_sql(sql).open_reader() as reader:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\t'.join(columns) + '\n')
            count = 0
            for record in reader:
                values = [str(record[col]) if record[col] is not None else '\\N'
                          for col in columns]
                f.write('\t'.join(values) + '\n')
                count += 1
                if count % 1000 == 0:
                    print(f"  已导出 {count} 行 ...")

    print(f"  完成: {output_path} ({count} 行)")


def export_buyer_profiles():
    """导出画像 summary 数据"""
    print("[2/2] 导出 buyer_profiles ...")

    odps = ODPS(ODPS_ACCESS_ID, ODPS_ACCESS_KEY,
                'cbuads', ODPS_ENDPOINT)

    sql = """
    SELECT
        node_id AS buyer_id,
        get_json_object(profile, '$.summary') AS profile_text
    FROM cbuads.ads_cn_dap_bizworld_scene_node_merge_profile_d
    WHERE ds = '20260522'
      AND scene_code = 'fx'
      AND node_type = 'buyer'
      AND get_json_object(profile, '$.summary') IS NOT NULL
      AND length(get_json_object(profile, '$.summary')) >= 100
    """

    output_path = OUTPUT_DIR / 'buyer_profiles.tsv'

    with odps.execute_sql(sql).open_reader() as reader:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('buyer_id\tprofile_text\n')
            count = 0
            for record in reader:
                buyer_id = str(record['buyer_id']) if record['buyer_id'] else ''
                profile_text = str(record['profile_text']) if record['profile_text'] else ''
                # 去除 profile_text 中的制表符和换行符，防止 TSV 格式错乱
                profile_text = profile_text.replace('\t', ' ').replace('\n', ' ').replace('\r', '')
                if buyer_id and len(profile_text) >= 100:
                    f.write(f'{buyer_id}\t{profile_text}\n')
                    count += 1
                    if count % 1000 == 0:
                        print(f"  已导出 {count} 行 ...")

    print(f"  完成: {output_path} ({count} 行)")


if __name__ == '__main__':
    if not ODPS_ACCESS_ID:
        print("请设置环境变量 ODPS_ACCESS_ID 和 ODPS_ACCESS_KEY")
        print("  export ODPS_ACCESS_ID=your_access_id")
        print("  export ODPS_ACCESS_KEY=your_access_key")
        print("\n或者直接在 ODPS 控制台执行 scripts/export_data.sql 中的 SQL，")
        print("手动导出 TSV 文件到 data/input/ 目录。")
        sys.exit(1)

    export_buyer_features()
    export_buyer_profiles()
    print("\n✅ 数据导出完成！可以运行 python app.py 启动应用。")
