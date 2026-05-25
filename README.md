# 1688 商机信号个性化反应模拟器

输入一个外部商机词（如"巴恩风"），系统从真实买家画像中抽取差异化角色，模拟他们在分销同行群中对这个信号的个性化反应，输出一个信息流页面。

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

## 使用方式

### Web 界面（推荐）

启动 Flask 后访问 `http://localhost:5000`，在页面上：

1. 输入商机信号词和简介
2. 选择运行模式（端到端 / 仅 Demo / 仅 Persona）
3. 点击"开始模拟"，实时查看进度
4. 完成后点击链接查看结果页面

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
├── post_generator.py       # 主帖 + 回帖生成
├── scoring.py              # 共鸣度评分
├── renderer.py             # HTML 渲染
├── templates/
│   ├── index.html          # Web 首页
│   └── feed.html           # 结果展示模板
└── data/
    ├── input/              # 输入数据
    └── output/             # 输出结果
```
