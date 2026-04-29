# ChunkFlow

面向 RAG 场景的文档解析与智能切片服务。一键将 PDF / 表格 / 文本类文件转换为带父子结构、适合向量化与检索的 chunk 包，并附带完整的执行链路与质量诊断。

## 核心能力

### 1. 多解析器自动降级

| 解析器 | 适用场景 | 特点 |
| --- | --- | --- |
| **Docling** | 结构化 PDF | 保留标题层级、表格、图片、阅读顺序，效果最好（需额外安装） |
| **MinerU** | 表格密集 / 复杂版式 PDF | 在线 API 调用，表格还原能力强（需额外安装/配置） |
| **pypdf** | 兜底 | 纯文本提取，无外部依赖，永远可用 |
| **table_file** | CSV / TSV / XLSX | 结构化转 block |
| **text_file** | TXT / MD | 标题感知的纯文本切分 |

按 `CHUNKFLOW_PARSER_PRIORITY`（默认 `docling,mineru,pypdf`）依次尝试，前一个失败或不可用时自动降级到下一个，并在结果的 `parser_fallback_chain` 中记录实际链路。

### 2. 文档类型识别 + 9 套模板切片器

通过关键词、表格/图片占比等信号自动识别文档类型，并路由到对应模板：

- `contract_terms`（合同/保险条款）— 按条款标号切分
- `paper`（学术论文）— 摘要 / 章节 / 参考文献分离
- `book`（书籍）— 按目录、章节切分
- `laws`（法律法规）— 按"第 X 条"切分
- `manual`（说明书/手册）— 按操作步骤、警告块切分
- `table_data`（表格数据）— 行/段聚合
- `picture_pdf`（图片型 PDF）— 以图为中心，附加邻域上下文
- `qa`（问答 / FAQ）— 一问一答聚合
- `generic_structured`（通用结构化）— 兜底，按标题树 + 段落聚合

也可以通过 `template` 参数手动指定。

### 3. 父子切片结构（Parent-Child）

输出包含两层 chunk：

- **ParentChunk**：章节 / 节级粗粒度切片，用于 LLM 阶段补充上下文
- **ChildChunk**：细粒度切片，带 `token_count`、`bbox_refs`、`heading_path`，是向量库的写入单位

通过 `parent_id ↔ child_chunk_ids` 双向链接，召回 child 后可零成本回溯 parent，实现 small-to-big 检索。

### 4. 完整后处理流水线

`parse → 噪声清理 → 章节树构建 → 类型识别 → 模板切片 → 媒体上下文附加 → 边界修复 → 小切片合并 → 超长切片切分 → 校验 → 质量指标`

每一步都会把 warning 写回结果，方便排查。

### 5. 质量监控面板

每次解析返回 `quality_monitor` 字段，包含：

- `execution_chain`：每个阶段的状态、用时、降级链
- `health_checks`：parser / blocks / sections / sources / tokens / relations 6 项体检
- `metrics`：平均/最大/最小 token 数、超长切片数、孤儿 child 数、表格上下文覆盖率等
- `distributions`：block_type / child_type / heading_level 分布
- `warning_groups`：按来源分组的告警
- `risk_samples`：自动挑选最值得人工 review 的切片样本
- `suggested_checks`：基于指标给出下一步排查建议

## 快速开始

### 安装

```bash
pip install -r requirements.txt

# 可选：开启结构化解析
pip install docling sentence-transformers
```

### 启动

**Windows 一键脚本**

```powershell
./start_chunkflow.ps1
```

脚本会自动结束占用 8900 端口的旧进程，并设置 `CHUNKFLOW_PARSER_PRIORITY=docling,mineru,pypdf`。

**或手动启动**

```bash
python -m chunkflow.app
# 等价于
uvicorn chunkflow.app:app --host 0.0.0.0 --port 8900
```

### 使用

打开 http://localhost:8900 ，在 Web 界面：

1. 选择解析器（auto / docling / mineru / pypdf / table_file / text_file）
2. 选择切片模板（auto 或手动指定）
3. 调整 `child_max_tokens`、`parent_granularity`、`table/image_context_blocks` 等参数
4. 上传文件 → 查看 chunk 列表 / 质量诊断 / 导出 JSON

## API

### `GET /api/status`

返回服务状态、可用解析器、当前优先级、可用模板。

### `GET /api/templates`

返回模板列表。

### `POST /api/parse`

multipart 上传文件，query 参数：

| 参数 | 说明 | 默认 |
| --- | --- | --- |
| `parser` | `auto` / `docling` / `mineru` / `pypdf` / `table_file` / `text_file` | `auto` |
| `template` | `auto` 或 9 个模板名 | `auto` |
| `child_max_tokens` | 子切片最大 token | `450` |
| `child_min_tokens` | 子切片最小 token（小于则尝试合并） | `80` |
| `parent_granularity` | `chapter` / `section` | `chapter` |
| `table_context_blocks` | 表格前后各取几个邻居 block 作为 context | `2` |
| `image_context_blocks` | 图片前后各取几个邻居 block 作为 context | `2` |
| `max_tokens` | Docling 切片器内部 token 上限 | `400` |
| `chunk_size_tokens` | pypdf 滑动窗口大小 | `400` |
| `overlap_tokens` | pypdf 窗口重叠 | `100` |
| `min_chunk_tokens` | 解析阶段最小 token | `50` |
| `include_blocks` | 返回原始 blocks | `true` |
| `debug` | 返回 debug payload | `false` |

支持的文件后缀：`.pdf .csv .tsv .xlsx .xlsm .txt .md .markdown`

### 返回结构（精简）

```json
{
  "document_id": "...",
  "document_type": "paper",
  "parser_used": "docling",
  "chunker_used": "PaperChunker",
  "parent_chunk_count": 8,
  "child_chunk_count": 53,
  "parent_chunks": [...],
  "child_chunks": [...],
  "blocks": [...],
  "parse_report": { "page_count": 12, "block_count": 280, ... },
  "warnings": [...],
  "metadata": { "parser_fallback_chain": ["docling"], ... },
  "quality_monitor": { "execution_chain": [...], "health_checks": [...], ... }
}
```

## 配置项

通过环境变量调整：

- `CHUNKFLOW_PARSER_PRIORITY` — 解析器优先级，逗号分隔，默认 `docling,mineru,pypdf`

## 项目结构

```
ChunkFlow/
├── chunkflow/
│   ├── app.py                  # FastAPI 入口
│   ├── core/
│   │   ├── pipeline.py         # 总流水线
│   │   ├── document_type.py    # 文档类型识别
│   │   ├── debug.py            # 调试 payload
│   │   ├── snapshot.py         # 阶段快照
│   │   └── ids.py              # ID 生成
│   ├── ir/                     # 中间表示（Block / Section / Chunk）
│   │   ├── models.py
│   │   ├── normalize.py
│   │   ├── section_tree.py
│   │   ├── layout_noise.py
│   │   └── validators.py
│   ├── parsers/                # 解析器适配层
│   │   ├── docling_pdf.py
│   │   ├── mineru_pdf.py
│   │   ├── pypdf_fallback.py
│   │   ├── table_file.py
│   │   └── text_file.py
│   ├── chunkers/               # 9 套模板切片器
│   │   ├── registry.py
│   │   ├── contract_terms.py / paper.py / book.py / manual.py
│   │   ├── laws.py / qa.py / table_data.py / picture_pdf.py
│   │   └── generic_structured.py
│   └── postprocess/            # 后处理
│       ├── boundary_repair.py
│       ├── small_chunk_merge.py
│       ├── overlong_split.py
│       ├── media_context.py
│       └── quality.py
├── static/                     # Web UI
├── docs/                       # 架构文档与各阶段实现说明
├── test/                       # 各阶段测试
├── start_chunkflow.ps1         # Windows 启动脚本
└── requirements.txt
```

## 设计文档

详细架构与各阶段实现见 `docs/`：

- `document_understanding_chunking_architecture.md` — 总体架构
- `phase_1_implementation_summary.md` ~ `phase_5_implementation_summary.md` — 分阶段实现说明
