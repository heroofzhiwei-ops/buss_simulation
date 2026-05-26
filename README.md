# 1688 商机信号个性化反应模拟器

输入一个外部商机词（如"巴恩风"），系统从真实买家画像中抽取差异化角色，组织差异化买家视角进行商机拆解、个性化推演、视角碰撞，并输出个性化衍生商机词延伸地图。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 LLM API Key
cp .env.example .env
# 编辑 .env 填入 LLM_API_KEY

# 3. 放入数据
# 将 buyer_features.tsv 和 buyer_profiles.tsv 放到 data/input/

# 4. 启动 Flask 应用
python app.py

# 5. 浏览器打开 http://localhost:5000
```

## 数据文件

- `data/input/buyer_features.tsv` — 买家行为特征表（17 列 TSV）
- `data/input/buyer_profiles.tsv` — 买家画像文本表（buyer_id + profile_text）

## Buyer 个体环境包

右侧「买家个体环境泛化推演」会根据 `buyer_id` 实时查询 PostgreSQL 中预先
计算好的同行、相似经营体或竞对人群，然后复用左侧同一套推演链路。

环境变量：

```bash
BUYER_ENV_POSTGRES_DSN=postgresql://user:password@host:5432/dbname
BUYER_ENV_TABLE=buyer_environment_personas
BUYER_ENV_PERSONA_JSON_COLUMN=persona_json
BUYER_ENV_MAX_SIZE=80
```

默认表结构建议：

```sql
CREATE TABLE buyer_environment_personas (
  buyer_id text NOT NULL,
  related_buyer_id text NOT NULL,
  relation_type text,
  relation_score double precision,
  relation_reason text,
  persona_json jsonb NOT NULL
);
```

`persona_json` 使用 `persona_builder.py` 输出的 persona 字段即可；如果不存
JSON，也可以把 `main_categories`、`downstream_channels`、`recent_search_top10`
等字段拆成独立列，加载器会自动兼容。

## 使用方式

### Web 界面（推荐）

启动 Flask 后访问 `http://localhost:5000`，在页面上：

1. 输入商机信号词和简介
2. 选择生意视角或买家视角入口
3. 选择运行模式（端到端 / 仅推演 / 仅 Persona）
4. 点击"启动推演"，实时查看进度
5. 完成后点击链接查看结果页面

### 命令行

```bash
# 端到端一键跑
python main.py --stage all --sample-limit 300 --signal "巴恩风" \
    --signal-brief "美式复古休闲风，近期小红书话题热度环比+120%"

# 只跑 persona
python main.py --stage personas --sample-limit 300

# 只跑 demo（需已有 persona）
python main.py --stage demo --signal "巴恩风"
```

## 项目结构

```
├── app.py                  # Flask Web 应用入口
├── main.py                 # 命令行入口
├── config.py               # 全局配置
├── llm_client.py           # LLM 异步客户端封装
├── prompts.py              # Prompt 模板
├── persona_builder.py      # 画像构建
├── buyer_environment.py    # buyer_id 个体环境包 Postgres 加载
├── signal_analyzer.py      # 商机画像拆解 + buyer 匹配
├── post_generator.py       # 买家推演 + 视角碰撞生成
├── scoring.py              # 机会可参考度评分
├── renderer.py             # HTML 渲染
├── templates/
│   ├── index.html          # Web 首页
│   └── feed.html           # 推演结果展示模板
└── data/
    ├── input/              # 输入数据
    └── output/             # 输出结果
```
