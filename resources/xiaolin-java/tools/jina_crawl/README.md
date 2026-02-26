# Jina Reader 网页爬取工具

使用 [Jina Reader API](https://r.jina.ai/) 将指定网页爬取为 Markdown 并保存到本地。

## 运行环境

- Python 3.8+
- Conda 环境：`alphafrog`（建议）

```bash
conda activate alphafrog
pip install -r requirements.txt
```

## 配置

1. 在项目根或 `jina_crawl/` 下创建 `.env`，填入 Jina API Key：

   ```
   JINA_API_KEY=your_jina_api_key
   ```

2. 编辑 `configs/example.yml`（或复制为 `configs/your_config.yml`）：
   - `urls`: 待爬取的 URL 列表
   - `output_dir`: Markdown 输出目录

## 使用

```bash
# 使用默认配置 configs/example.yml
python jina_crawl.py

# 指定配置
python jina_crawl.py -c configs/your_config.yml

# 覆盖输出目录
python jina_crawl.py -o ./my_output
```

## API 规范

脚本按 [r.jina.ai/docs](https://r.jina.ai/docs) 规范请求：

- 请求 `GET https://r.jina.ai/{url}`（url 已编码）
- Header `X-Respond-With: markdown`
- Header `Authorization: Bearer {JINA_API_KEY}`（从 .env 读取）
