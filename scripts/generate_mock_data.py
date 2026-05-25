"""
生成模拟测试数据，用于验证全流程跑通。
真实数据请从 ODPS 导出替换。

用法: python scripts/generate_mock_data.py
"""
import csv
import json
import random
import sys
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent / 'data' / 'input'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# 模拟 buyer 元数据
# ============================================================
MOCK_BUYERS = [
    {
        'id': 'B100001',
        'categories': ['女装', '连衣裙'],
        'channels': ['抖音小店', '拼多多'],
        'audience': '18-30岁年轻女性，追求性价比和时尚感',
        'gmv': '中体量',
        'price': '39-128元',
        'supply': '一件代发',
        'status': '稳定经营',
        'style': ['韩系', '甜美', '通勤'],
        'traits': ['抖音直播间日销200+', '主打39-79元连衣裙', '换季清仓节奏快'],
        'searches': ['碎花连衣裙', '韩版女装', 'A字裙', '雪纺衫', '通勤套装', '吊带裙', '法式连衣裙', '显瘦女装', '小个子穿搭', '甜美风裙子'],
    },
    {
        'id': 'B100002',
        'categories': ['男装', 'T恤'],
        'channels': ['淘宝', '私域微商'],
        'audience': '25-40岁男性，注重品质基础款',
        'gmv': '大体量',
        'price': '59-199元',
        'supply': '自仓',
        'status': '试水扩品',
        'style': ['美式休闲', '商务休闲', '重磅'],
        'traits': ['淘宝月销10万+', '重磅T恤复购率高', '开始试水工装裤'],
        'searches': ['重磅T恤男', '纯棉polo衫', '美式工装裤', '男士衬衫', '宽松短袖', '复古T恤', '260g纯棉T恤', '基础款男装', '商务休闲裤', 'oversize男装'],
    },
    {
        'id': 'B100003',
        'categories': ['家居', '收纳'],
        'channels': ['拼多多', '小红书'],
        'audience': '25-45岁家庭主妇，注重实用和颜值',
        'gmv': '小体量',
        'price': '9.9-49元',
        'supply': '一件代发',
        'status': '谨慎试探',
        'style': ['日系简约', '北欧', '奶油风'],
        'traits': ['小红书种草带货', '9.9包邮引流款', '家居小物毛利高'],
        'searches': ['亚克力收纳盒', '桌面整理', '冰箱收纳', '日式收纳篮', '化妆品收纳', '厨房置物架', '衣柜收纳', '奶油风花瓶', '极简摆件', '墙面装饰'],
    },
    {
        'id': 'B100004',
        'categories': ['运动户外', '瑜伽服'],
        'channels': ['抖音小店', '小红书'],
        'audience': '22-35岁运动爱好者女性，追求穿搭与功能兼得',
        'gmv': '中体量',
        'price': '49-168元',
        'supply': '混合',
        'status': '激进扩张',
        'style': ['运动辣妹', 'athleisure', '瑜伽'],
        'traits': ['抖音瑜伽服日销500+', '正在拓展户外露营线', '注重面料科技感'],
        'searches': ['瑜伽裤女', '运动内衣', '速干T恤', '健身套装', '鲨鱼裤', '户外防晒衣', '跑步短裤', '露营穿搭', '瑜伽垫', '运动水壶'],
    },
    {
        'id': 'B100005',
        'categories': ['箱包', '斜挎包'],
        'channels': ['淘宝', '线下批发'],
        'audience': '批发档口客户+淘宝中小卖家',
        'gmv': '超大体量',
        'price': '15-89元',
        'supply': '自仓',
        'status': '稳定经营',
        'style': ['平替', '百搭', '通勤'],
        'traits': ['广州白马档口供货', '月出货2万个包', '快速翻单能力强'],
        'searches': ['斜挎包女', '帆布包', '托特包', '通勤包', '小众设计包', '单肩包', '水桶包', '链条包', '复古邮差包', '大容量女包'],
    },
    {
        'id': 'B100006',
        'categories': ['母婴', '儿童服装'],
        'channels': ['拼多多', '社区团购'],
        'audience': '宝妈群体，注重安全和性价比',
        'gmv': '中体量',
        'price': '19-79元',
        'supply': '一件代发',
        'status': '转型中',
        'style': ['可爱', '亲子', '国潮'],
        'traits': ['社区团购起家', '正从母婴转向儿童潮服', '客单价在提升'],
        'searches': ['儿童T恤', '童装夏季', '亲子装', '儿童防晒衣', '小女孩裙子', '男童短裤', '婴儿连体衣', '国潮童装', '儿童汉服', '学生校服'],
    },
    {
        'id': 'B100007',
        'categories': ['配饰', '发饰'],
        'channels': ['小红书', '抖音小店'],
        'audience': '16-28岁少女，追求小众精致',
        'gmv': '小体量',
        'price': '3.9-29元',
        'supply': '一件代发',
        'status': '试水扩品',
        'style': ['小众', '法式', 'INS风'],
        'traits': ['小红书笔记引流', '客单低但复购高', '正在拓展耳饰品类'],
        'searches': ['发夹', '珍珠发饰', '法式发箍', '鲨鱼夹', '蝴蝶结发绳', '耳钉', '项链女', 'INS风戒指', '手链', '小众耳环'],
    },
]


def _build_inquiry_contents(buyer):
    """生成模拟询盘内容"""
    categories = buyer['categories']
    templates = [
        f'售前-商品参数:这个{categories[0]}的尺码表有吗',
        f'售前-议价:拿50件什么价格',
        f'售中-物流:什么时候发货啊催一下',
        f'售后-退货:颜色和图片差太多要退货',
        f'售前-商品对比:这款和你家另一款有什么区别',
        f'售中-催促发货:三天了还没揽收',
        f'售前-议价:长期合作能给个底价吗',
        f'售后-质量:收到有线头客户投诉了',
    ]
    count = random.randint(4, 8)
    return '||'.join(random.sample(templates, min(count, len(templates))))


def _build_image_search(buyer):
    """生成模拟图搜内容"""
    styles = buyer['style']
    items = []
    for style in styles:
        items.append(f"{buyer['categories'][0]}:{style}")
    return '|'.join(items)


def _build_products(buyer, count):
    """生成模拟商品标题"""
    category = buyer['categories'][0]
    style_options = buyer['style']
    titles = []
    for i in range(count):
        style = random.choice(style_options)
        price = random.randint(10, 200)
        titles.append(f"2026新款{style}{category}春夏季{buyer['categories'][-1]}女装时尚百搭{price}元包邮")
    return '|'.join(titles)


def generate_buyer_features():
    """生成 buyer_features.tsv"""
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

    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(columns)

        for buyer in MOCK_BUYERS:
            inquiry_cnt = random.randint(5, 30)
            inquiry_contents = _build_inquiry_contents(buyer)
            image_search_cnt = random.randint(3, 20)
            image_search_contents = _build_image_search(buyer)
            search_cnt = len(buyer['searches'])
            search_keywords = '|'.join(buyer['searches'])
            product_view_cnt = random.randint(20, 100)
            viewed_products = _build_products(buyer, min(product_view_cnt, 15))
            cart_cnt = random.randint(5, 30)
            carted_products = _build_products(buyer, min(cart_cnt, 8))
            recommend_click_cnt = random.randint(3, 20)
            recommended_products = _build_products(buyer, min(recommend_click_cnt, 6))
            video_play_cnt = random.randint(2, 15)
            video_products = _build_products(buyer, min(video_play_cnt, 5))
            shop_view_cnt = random.randint(3, 15)
            shop_viewed_products = _build_products(buyer, min(shop_view_cnt, 5))

            writer.writerow([
                buyer['id'], inquiry_cnt, inquiry_contents,
                image_search_cnt, image_search_contents,
                search_cnt, search_keywords,
                product_view_cnt, viewed_products,
                cart_cnt, carted_products,
                recommend_click_cnt, recommended_products,
                video_play_cnt, video_products,
                shop_view_cnt, shop_viewed_products,
            ])

    print(f"✅ 生成 {output_path} ({len(MOCK_BUYERS)} 条)")


def generate_buyer_profiles():
    """生成 buyer_profiles.tsv"""
    output_path = OUTPUT_DIR / 'buyer_profiles.tsv'

    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(['buyer_id', 'profile_text'])

        for buyer in MOCK_BUYERS:
            profile = (
                f"这是一个深度聚焦{'/'.join(buyer['channels'])}平台的分销卖家，"
                f"主营{'/'.join(buyer['categories'])}品类，"
                f"经营体量属于{buyer['gmv']}级别，"
                f"主力价格带在{buyer['price']}区间。"
                f"供应链模式为{buyer['supply']}，"
                f"当前经营状态为{buyer['status']}。"
                f"下游受众画像：{buyer['audience']}。"
                f"风格定位偏{'/'.join(buyer['style'])}，"
                f"核心经营特征包括：{'、'.join(buyer['traits'])}。"
                f"近期高频搜索词集中在{'、'.join(buyer['searches'][:5])}等方向，"
                f"体现出对{buyer['categories'][0]}细分市场的深度耕耘。"
                f"该卖家在选品上注重{'快速翻单和应季款' if buyer['supply'] == '自仓' else '低库存风险和测款'}，"
                f"对供应商的核心诉求是{'稳定供货和品质管控' if buyer['gmv'] in ('大体量', '超大体量') else '一件代发和快速响应'}。"
            )
            writer.writerow([buyer['id'], profile])

    print(f"✅ 生成 {output_path} ({len(MOCK_BUYERS)} 条)")


if __name__ == '__main__':
    generate_buyer_features()
    generate_buyer_profiles()
    print("\n🎉 模拟数据生成完成！")
