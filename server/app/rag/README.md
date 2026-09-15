"""RAG 核心模块占位。

MVP 阶段仅定义接口与流程说明，后续可依次实现：
- document_parser.py  :  PDF/DOCX/TXT/MD 多格式解析与文本提取
- text_chunker.py     :  智能分块（标题层级/语义分块/父子分块）
- embedding.py        :  Embedding 模型封装（BGE 中文/OpenAI/DashScope）
- vector_store.py     :  Chroma/Milvus 向量库封装（增删改查、相似度检索）
- retriever.py        :  混合检索 + RRF 融合 + 重排序
- llm_client.py       :  LLM 客户端封装（OpenAI 兼容接口、流式输出）
- prompt_templates.py :  Prompt 模板（问答/查询改写/总结）
- pipeline.py         :  端到端 RAG 管线串联
"""
