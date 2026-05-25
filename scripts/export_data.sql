-- ============================================================
-- 1688 商机信号模拟器 - ODPS 数据导出 SQL
-- ============================================================
-- 使用方法：
--   1. 在 ODPS 控制台执行以下 SQL
--   2. 将结果导出为 TSV 文件
--   3. 分别保存为 data/input/buyer_features.tsv 和 data/input/buyer_profiles.tsv

-- ============================================================
-- 表 1: buyer_features.tsv (动线行为数据)
-- 来源: cbu_data_algo_dev.buss_bizword_user_profile_data
-- ============================================================
SELECT
    buyer_id,
    inquiry_cnt,
    inquiry_contents,
    image_search_cnt,
    image_search_contents,
    search_cnt,
    search_keywords,
    product_view_cnt,
    viewed_products,
    cart_cnt,
    carted_products,
    recommend_click_cnt,
    recommended_products,
    video_play_cnt,
    video_products,
    shop_view_cnt,
    shop_viewed_products
FROM cbu_data_algo_dev.buss_bizword_user_profile_data
;

-- ============================================================
-- 表 2: buyer_profiles.tsv (画像 summary)
-- 来源: cbuads.ads_cn_dap_bizworld_scene_node_merge_profile_d
-- 说明: profile 字段为 JSON，从中提取 summary 字段作为 profile_text
-- ============================================================
SELECT
    node_id AS buyer_id,
    get_json_object(profile, '$.summary') AS profile_text
FROM cbuads.ads_cn_dap_bizworld_scene_node_merge_profile_d
WHERE ds = '20260522'
  AND scene_code = 'fx'
  AND node_type = 'buyer'
  AND get_json_object(profile, '$.summary') IS NOT NULL
  AND length(get_json_object(profile, '$.summary')) >= 100
;
