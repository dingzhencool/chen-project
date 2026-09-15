"""Prompt 模板集合。"""

RAG_QA_SYSTEM_PROMPT = """你是一个专业的企业知识库助手，严格基于用户提供的参考资料（文档片段）回答用户问题。

规则：
1. 仅基于参考资料作答：如果参考资料不包含问题答案，或资料不足以准确回答，请明确说「根据现有资料暂无法回答该问题」，不要编造信息。
2. 引用标注：每条参考资料都标注了它所属的「文档序号」（形如 文档 [1]）。回答中涉及资料结论的地方，在对应句子末尾用 [序号] 标注来源，例如「企业年营收为 1 亿元 [1]」。
   - 序号是「文档」的编号，不是资料片段的编号：同一篇文档的所有片段共用同一个序号；
   - 一句话同时参考多篇文档时可并列标注多个序号，如 [1][2]；
   - 只能使用参考资料中实际出现过的文档序号，禁止编造。
3. 结构清晰：用换行和「1. 2. 3.」或「- 」序号分点阐述，让层次清楚。
   输出必须是纯文本，禁止使用任何 Markdown 排版符号：不要用 ** 加粗、不要用 * 或 _ 斜体、不要用 # 标题、不要用反引号；需要强调时直接陈述即可。
   唯一允许的标记是引用标注 [序号]。
4. 语言风格：正式、客观、简洁；若用户使用英文则以英文回答，否则使用中文。
"""

RAG_QA_USER_TEMPLATE = """## 用户问题
{query}

## 参考资料（按相关性从高到低排列）
{sources_text}

---
请根据上述参考资料回答用户问题，回答前请先思考再作答。"""


def build_rag_prompt(query: str, context_hits: list) -> tuple[str, str]:
    """根据检索命中拼接 RAG Prompt。返回 (system_prompt, user_prompt)。"""
    if not context_hits:
        sys_prompt = (
            "你是一个企业知识库助手。当前会话没有关联任何知识库，或暂未检索到相关资料。"
            "请以通用、谨慎的口吻与用户交流，明确说明当前没有可用的知识库内容，并提示用户先上传文档。不要编造答案。"
        )
        user_msg = (
            f"用户问题：{query}\n\n"
            f"（当前没有检索到任何相关文档资料，请以通用助手口吻礼貌回应，并说明若上传相关文档可获得更准确回答。）"
        )
        return sys_prompt, user_msg

    blocks = []
    # 文档序号按「文档首次出现顺序」分配（context_hits 已按相关度降序）：
    # 同一文档的所有片段共用同一个序号，回答里的 [1]/[2] 与前端引用卡片编号一一对应。
    doc_no_map: dict = {}
    for h in context_hits:
        did = getattr(h, "doc_id", 0)
        if did not in doc_no_map:
            doc_no_map[did] = len(doc_no_map) + 1
    for i, h in enumerate(context_hits):
        doc_id = getattr(h, "doc_id", 0)
        chunk_idx = getattr(h, "chunk_index", i)
        score = getattr(h, "score", 0.0)
        text = getattr(h, "text", str(h))
        doc_no = doc_no_map.get(doc_id, i + 1)
        blocks.append(
            f"### 资料 {i + 1}（文档 [{doc_no}]，相关度 {score:.2f}，chunk={chunk_idx}）\n{text.strip()}"
        )
    sources_text = "\n\n".join(blocks)
    return RAG_QA_SYSTEM_PROMPT, RAG_QA_USER_TEMPLATE.format(query=query, sources_text=sources_text)
