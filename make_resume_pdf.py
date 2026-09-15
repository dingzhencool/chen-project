# -*- coding: utf-8 -*-
"""生成精简版项目描述 PDF (中文，如实版)。"""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# ---------- 字体注册 ----------
FONT_DIR = r"C:\Windows\Fonts"
pdfmetrics.registerFont(TTFont("MSYH", os.path.join(FONT_DIR, "msyh.ttc")))
pdfmetrics.registerFont(TTFont("MSYHBD", os.path.join(FONT_DIR, "msyhbd.ttc")))
registerFontFamily("MSYH", normal="MSYH", bold="MSYHBD")

# ---------- 颜色 ----------
PRIMARY = colors.HexColor("#1F4E79")   # 深蓝
ACCENT = colors.HexColor("#2E74B5")    # 中蓝
GRAY = colors.HexColor("#595959")
LIGHT = colors.HexColor("#F2F6FA")
BORDER = colors.HexColor("#D9E2EC")

# ---------- 样式 ----------
def P(font="MSYH", size=10, leading=15, color=colors.black, **kw):
    return ParagraphStyle("s", fontName=font, fontSize=size, leading=leading,
                          textColor=color, wordWrap="CJK", **kw)

title_style = P("MSYHBD", 17, 22, PRIMARY, alignment=TA_CENTER)
sub_style = P("MSYH", 10.5, 15, GRAY, alignment=TA_CENTER)
h1_style = P("MSYHBD", 12, 16, PRIMARY, spaceBefore=10, spaceAfter=4)
body_style = P("MSYH", 10, 16)
bullet_style = P("MSYH", 10, 16, leftIndent=12, firstLineIndent=-12)
tag_style = P("MSYH", 9.5, 14, colors.HexColor("#1F4E79"))
note_style = P("MSYH", 9, 14, colors.HexColor("#8a8a8a"))

def kv_table(rows):
    data = []
    for k, v in rows:
        data.append([Paragraph(k, P("MSYHBD", 10, 15, colors.black)),
                     Paragraph(v, P("MSYH", 10, 15))])
    t = Table(data, colWidths=[38*mm, 128*mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("TOPPADDING", (0,0), (-1,-1), 2),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
        ("LEFTPADDING", (0,0), (-1,-1), 0),
    ]))
    return t

def section_heading(text):
    return Paragraph(text, h1_style)

# ---------- 内容 ----------
doc = SimpleDocTemplate(
    r"E:\Tare project\mianshi1\项目简历-精简版.pdf",
    pagesize=A4, topMargin=18*mm, bottomMargin=18*mm,
    leftMargin=20*mm, rightMargin=20*mm,
)

story = []
story.append(Paragraph("企业级 RAG 智能知识库系统", title_style))
story.append(Spacer(1, 3))
story.append(Paragraph("前后端分离 · 独立开发", sub_style))
story.append(Spacer(1, 6))
story.append(HRFlowable(width="100%", thickness=1, color=ACCENT))
story.append(Spacer(1, 2))

# 技术栈
story.append(section_heading("技术栈"))
story.append(Paragraph(
    "FastAPI · Vue 3 · Element Plus · Pinia · MySQL · Redis · Chroma (向量库) · Docker / Docker Compose",
    body_style))
story.append(Spacer(1, 4))

# 项目简介
story.append(section_heading("项目简介"))
story.append(Paragraph(
    "基于 FastAPI + Vue 3 自研的智能知识库系统，实现文档从解析、分块、向量化到检索、"
    "大模型流式生成的端到端 RAG 闭环；借鉴 RAGFlow / FastGPT 等成熟架构，前后端物理隔离，"
    "支持容器化分层部署。", body_style))
story.append(Spacer(1, 4))

# 核心职责与成果
story.append(section_heading("核心职责与成果"))
bullets = [
    "后端基于 FastAPI 采用 接口层→业务层→数据层 三层架构，前后端物理隔离，便于容器化分层部署；设计 JWT 无状态鉴权与统一响应/异常处理。",
    "前端基于 Vue 3 + Element Plus + Pinia 实现，支持 SSE 流式打字机呈现的多会话问答与引用来源展示；Vue Router 鉴权守卫控制访问。",
    "实现 RAG 端到端管线：多格式文档解析 → 智能分块 → BGE 中文 Embedding → Chroma 向量存储 → 混合检索 → LLM 流式生成 → 多轮上下文管理。",
    "使用 SQLAlchemy 管理 MySQL（用户/知识库/文档/对话），基于统一 CRUDBase + 领域 CRUD 实现数据访问收口；Chroma 按 kb_id 隔离 collection。",
    "设计多级「引用来源过滤保险」（分数过滤 + 去重 + 孤魂向量剔除），并启动时幂等重放文档向量，保证查询质量与数据一致性。",
    "编写 Docker Compose 一键编排 MySQL/Redis/前后端四容器，含健康检查与依赖启动；敏感信息全部走环境变量，零硬编码。",
]
for b in bullets:
    story.append(Paragraph(f"•  {b}", bullet_style))
story.append(Spacer(1, 4))

# 难点与亮点
story.append(section_heading("难点与亮点"))
highlights = [
    "SSE 流式问答：异步生成器流式输出 token，前端 ReadableStream 分块解析，实现打字机效果。",
    "向量库一致性：删除文档时 Chroma 清理失败导致“孤魂向量”，通过多级过滤 + 启动重放保证 DB 与向量数据一致。",
    "来源可靠性：RAG 引用来源经三道过滤（正分过滤、去重、DB 反查文档名兜底），确保引用真实可追溯。",
    "权限边界：会话级与消息级双重知识库越权校验，防止关联/切换他人知识库。",
]
for h in highlights:
    story.append(Paragraph(f"•  {h}", bullet_style))

doc.build(story)
print("PDF generated OK")
