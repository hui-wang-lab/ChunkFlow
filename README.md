# ChunkFlow

文档解析与智能切片服务。从 PDF 文件中提取文本并生成结构化的 chunks，支持 Docling 结构化解析和 pypdf 滑动窗口两种模式。

## 功能

- **Docling 解析**（优先）：基于文档结构的智能切片，保留标题层级、章节、页码等元数据
- **pypdf 回退**：当 Docling 不可用时，使用滑动窗口算法进行切片
- **Web 界面**：上传 PDF，可视化查看所有 chunks，支持搜索和 JSON 导出
- **参数可调**：max_tokens、chunk_size、overlap 均可在页面上自定义

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 可选：安装 Docling 以启用结构化解析
# pip install docling sentence-transformers

# 启动服务
python -m chunkflow.app
```

浏览器打开 http://localhost:8900 即可使用。

## 项目结构

```
ChunkFlow/
├── chunkflow/
│   ├── app.py            # FastAPI 服务入口
│   ├── chunking.py       # 统一切片管道
│   ├── docling_parser.py # Docling 结构化解析器
│   ├── pdf_parser.py     # pypdf 回退解析器
│   ├── schema.py         # 数据模型
│   └── tokenizer.py      # 分词器
├── static/
│   ├── index.html        # Web 页面
│   ├── style.css         # 样式
│   └── app.js            # 前端逻辑
├── requirements.txt
└── README.md
```

## API

### `GET /api/status`

返回服务状态和当前使用的解析器。

### `POST /api/parse`

上传 PDF 文件并解析为 chunks。

参数（query string）：
- `max_tokens` - Docling 模式下每个 chunk 的最大 token 数（默认 400）
- `chunk_size_tokens` - pypdf 模式下滑动窗口大小（默认 400）
- `overlap_tokens` - pypdf 模式下重叠 token 数（默认 100）
