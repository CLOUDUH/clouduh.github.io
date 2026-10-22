#!/usr/bin/env python3
"""Build the Chinese CV in editable DOCX and fixed-layout PDF formats."""

from __future__ import annotations

import argparse
from pathlib import Path
from xml.sax.saxutils import escape

from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.enum.table import WD_ALIGN_VERTICAL, WD_CELL_VERTICAL_ALIGNMENT, WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Mm, Pt, RGBColor


ROOT = Path("/Users/cloudu/Documents/document/05_Note/clouduh.github.io")
TMP = Path("/private/tmp/cv_zh_work")
IMG = TMP / "extract" / "images"
DOCX_OUT = ROOT / "output" / "docx" / "杜云浩_中文简历.docx"
PDF_OUT = ROOT / "output" / "pdf" / "杜云浩_中文简历.pdf"

PHOTO = IMG / "p1_0_Im0.png"
PROJECT_IMAGES = [
    IMG / "p2_3_Im3.png",  # Formula Student
    IMG / "p2_2_Im2.png",  # Distributed energy supply
    IMG / "p2_1_Im1.png",  # Battery test platform
    IMG / "p2_0_Im0.png",  # DRL hardware platform
]

NAVY = "112D4E"
BLUE = "3F72AF"
BLACK = "000000"
GRAY = "666666"
# This macOS system font is visible to the bundled headless renderer and closely
# matches the source resume's PingFang typography.
CN_FONT = "Source Han Sans CN"
# LibreOffice applies the high-ANSI face to some CJK runs, so the default Latin
# face must also contain Chinese glyphs. The QA renderer is supplied with this
# font locally; publication PDF typography is handled separately with Arial.
LATIN_FONT = "Source Han Sans CN"


def set_repeat_table_layout(table, widths_pt):
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.autofit = False
    tbl_pr = table._tbl.tblPr
    tbl_layout = tbl_pr.find(qn("w:tblLayout"))
    if tbl_layout is None:
        tbl_layout = OxmlElement("w:tblLayout")
        tbl_pr.append(tbl_layout)
    tbl_layout.set(qn("w:type"), "fixed")
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(int(sum(widths_pt) * 20)))
    tbl_w.set(qn("w:type"), "dxa")
    for row in table.rows:
        for cell, width in zip(row.cells, widths_pt):
            cell.width = Pt(width)
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:w"), str(int(width * 20)))
            tc_w.set(qn("w:type"), "dxa")
            set_cell_margins(cell, 0, 0, 0, 0)
    set_table_borders_none(table)


def set_table_borders_none(table):
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.find(qn("w:tblBorders"))
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = borders.find(qn(f"w:{edge}"))
        if tag is None:
            tag = OxmlElement(f"w:{edge}")
            borders.append(tag)
        tag.set(qn("w:val"), "nil")


def set_cell_margins(cell, top=0, start=0, bottom=0, end=0):
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for key, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{key}"))
        if node is None:
            node = OxmlElement(f"w:{key}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_repeat_cant_split(row):
    tr_pr = row._tr.get_or_add_trPr()
    cant = OxmlElement("w:cantSplit")
    tr_pr.append(cant)


def set_para_border_bottom(paragraph, color=BLUE, size_eighths=56, space=1):
    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = p_pr.find(qn("w:pBdr"))
    if p_bdr is None:
        p_bdr = OxmlElement("w:pBdr")
        p_pr.append(p_bdr)
    bottom = p_bdr.find(qn("w:bottom"))
    if bottom is None:
        bottom = OxmlElement("w:bottom")
        p_bdr.append(bottom)
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size_eighths))
    bottom.set(qn("w:space"), str(space))
    bottom.set(qn("w:color"), color)


def set_run_font(
    run,
    size=10,
    bold=False,
    italic=False,
    color=BLACK,
    underline=False,
    latin=LATIN_FONT,
    east_asia=CN_FONT,
):
    run.font.name = latin
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.underline = underline
    run.font.color.rgb = RGBColor.from_string(color)
    r_pr = run._element.get_or_add_rPr()
    r_fonts = r_pr.rFonts
    if r_fonts is None:
        r_fonts = OxmlElement("w:rFonts")
        r_pr.insert(0, r_fonts)
    r_fonts.set(qn("w:ascii"), latin)
    r_fonts.set(qn("w:hAnsi"), latin)
    r_fonts.set(qn("w:eastAsia"), east_asia)
    r_fonts.set(qn("w:cs"), latin)
    return run


def set_paragraph(
    p,
    *,
    align=WD_ALIGN_PARAGRAPH.LEFT,
    before=0,
    after=0,
    leading=None,
    keep_next=False,
    keep_together=False,
    left=0,
    first=0,
):
    f = p.paragraph_format
    p.alignment = align
    f.space_before = Pt(before)
    f.space_after = Pt(after)
    f.left_indent = Pt(left)
    f.first_line_indent = Pt(first)
    f.keep_with_next = keep_next
    f.keep_together = keep_together
    if leading is not None:
        f.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        f.line_spacing = Pt(leading)
    else:
        # Clear an exact line height inherited from a normalized table cell;
        # inline pictures otherwise render as a narrow cropped strip.
        spacing = p._p.get_or_add_pPr().find(qn("w:spacing"))
        if spacing is not None:
            for attr in (qn("w:line"), qn("w:lineRule")):
                if attr in spacing.attrib:
                    del spacing.attrib[attr]
    return p


def add_runs(p, fragments, default_size=10):
    for frag in fragments:
        if isinstance(frag, str):
            frag = {"text": frag}
        run = p.add_run(frag["text"])
        set_run_font(
            run,
            size=frag.get("size", default_size),
            bold=frag.get("bold", False),
            italic=frag.get("italic", False),
            color=frag.get("color", BLACK),
            underline=frag.get("underline", False),
            latin=frag.get("latin", LATIN_FONT),
            east_asia=frag.get("east_asia", CN_FONT),
        )
    return p


def section_heading(doc, text, before=0, after=7):
    p = doc.add_paragraph(style="Heading 1")
    set_paragraph(p, before=before, after=after, leading=21, keep_next=True)
    add_runs(p, [{"text": text, "size": 14, "bold": True, "color": NAVY}])
    set_para_border_bottom(p)
    return p


def compact_table(doc, rows, widths, before=0, after=0):
    if before:
        spacer = doc.add_paragraph()
        set_paragraph(spacer, before=0, after=0, leading=before)
    table = doc.add_table(rows=rows, cols=len(widths))
    set_repeat_table_layout(table, widths)
    for row in table.rows:
        set_repeat_cant_split(row)
    # Word inserts a paragraph in every cell; normalize it.
    for row in table.rows:
        for cell in row.cells:
            for p in cell.paragraphs:
                set_paragraph(p, after=0, leading=14)
    if after:
        table._after_spacing_pt = after
    return table


def add_bullet(container, fragments, *, size=10, leading=17, after=0, light=False):
    p = container.add_paragraph() if hasattr(container, "add_paragraph") else container
    set_paragraph(p, after=after, leading=leading, left=11, first=-1, keep_together=True)
    add_runs(p, [{"text": "• ", "size": size}])
    if light:
        fragments = [({"text": f} if isinstance(f, str) else dict(f)) for f in fragments]
        for f in fragments:
            f.setdefault("color", BLACK)
    add_runs(p, fragments, default_size=size)
    return p


def add_education_entry(doc, school, date, degree, place, bullets, before=0):
    if before:
        p = doc.add_paragraph()
        set_paragraph(p, leading=before)
    table = compact_table(doc, 2, [421, 116])
    left, right = table.rows[0].cells
    set_paragraph(left.paragraphs[0], leading=15, keep_next=True)
    add_runs(left.paragraphs[0], [{"text": school, "size": 10.2, "bold": True}])
    set_paragraph(right.paragraphs[0], align=WD_ALIGN_PARAGRAPH.RIGHT, leading=15, keep_next=True)
    add_runs(right.paragraphs[0], [{"text": date, "size": 9.8, "color": BLACK}])
    left, right = table.rows[1].cells
    set_paragraph(left.paragraphs[0], leading=15, keep_next=True)
    add_runs(left.paragraphs[0], [{"text": degree, "size": 9.8, "italic": True}])
    set_paragraph(right.paragraphs[0], align=WD_ALIGN_PARAGRAPH.RIGHT, leading=15, keep_next=True)
    add_runs(right.paragraphs[0], [{"text": place, "size": 9.8, "italic": True}])
    for bullet in bullets:
        add_bullet(doc, bullet, size=9.8, leading=17)


def add_publication(doc, number, authors_prefix, title, venue, tail, keywords, *, status=None):
    p = doc.add_paragraph()
    set_paragraph(p, leading=16, left=14, first=-14, keep_together=True)
    add_runs(p, [{"text": f"[{number}] ", "size": 9.5}])
    # Underline every occurrence of the owner's published name while preserving author spelling.
    remaining = authors_prefix
    needle = "Yunhao Du"
    while needle in remaining:
        pre, remaining = remaining.split(needle, 1)
        if pre:
            add_runs(p, [{"text": pre, "size": 9.5}])
        add_runs(p, [{"text": needle, "size": 9.5, "underline": True}])
    if remaining:
        add_runs(p, [{"text": remaining, "size": 9.5}])
    add_runs(p, [{"text": title, "size": 9.5, "bold": True}])
    if venue:
        add_runs(p, [{"text": venue, "size": 9.5, "italic": True}])
    if tail:
        add_runs(p, [{"text": tail, "size": 9.5}])
    if status:
        add_runs(p, [{"text": status, "size": 9.5, "bold": True}])

    k = doc.add_paragraph()
    set_paragraph(k, leading=16, left=11, first=-1, keep_together=True)
    add_runs(k, [{"text": "• ", "size": 9.3}, {"text": "关键词：", "size": 9.3, "italic": True}])
    add_runs(k, [{"text": keywords, "size": 9.3, "italic": True, "color": GRAY}])


def add_project(doc, title, date, image_path, bullets, *, gap_after=4):
    head = compact_table(doc, 1, [420, 117])
    left, right = head.rows[0].cells
    set_paragraph(left.paragraphs[0], leading=17, keep_next=True)
    left.paragraphs[0].style = doc.styles["Heading 2"]
    add_runs(left.paragraphs[0], [{"text": title, "size": 11, "bold": True, "color": NAVY}])
    set_paragraph(right.paragraphs[0], align=WD_ALIGN_PARAGRAPH.RIGHT, leading=17, keep_next=True)
    add_runs(right.paragraphs[0], [{"text": date, "size": 9.6}])

    body = compact_table(doc, 1, [172, 365])
    set_repeat_cant_split(body.rows[0])
    image_cell, text_cell = body.rows[0].cells
    image_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
    text_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
    ip = image_cell.paragraphs[0]
    set_paragraph(ip)
    ip.add_run().add_picture(str(image_path), width=Pt(172), height=Pt(132))
    # Remove the default empty paragraph in the text cell by reusing it for the first bullet.
    for idx, bullet in enumerate(bullets):
        p = text_cell.paragraphs[0] if idx == 0 else text_cell.add_paragraph()
        set_paragraph(p, leading=15.8, left=12, first=-6, keep_together=True)
        add_runs(p, [{"text": "• ", "size": 9.4}])
        add_runs(p, bullet, default_size=9.4)
    # Minimum height matches the 132 pt source-image block without risking clipped text.
    body.rows[0].height = Pt(132)
    body.rows[0].height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
    if gap_after:
        spacer = doc.add_paragraph()
        set_paragraph(spacer, leading=gap_after)


def configure_styles(doc):
    normal = doc.styles["Normal"]
    normal.font.name = LATIN_FONT
    normal.font.size = Pt(10)
    normal.font.color.rgb = RGBColor(0, 0, 0)
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), CN_FONT)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)

    title = doc.styles["Title"]
    title.font.name = LATIN_FONT
    title.font.size = Pt(20)
    title.font.bold = True
    title.font.color.rgb = RGBColor(0, 0, 0)
    title._element.rPr.rFonts.set(qn("w:eastAsia"), CN_FONT)
    title.paragraph_format.space_before = Pt(0)
    title.paragraph_format.space_after = Pt(0)
    if title._element.pPr is not None:
        p_bdr = title._element.pPr.find(qn("w:pBdr"))
        if p_bdr is not None:
            title._element.pPr.remove(p_bdr)

    for style_name, size in (("Heading 1", 14), ("Heading 2", 11)):
        style = doc.styles[style_name]
        style.font.name = LATIN_FONT
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(NAVY)
        style._element.rPr.rFonts.set(qn("w:eastAsia"), CN_FONT)
        style.paragraph_format.space_before = Pt(0)
        style.paragraph_format.space_after = Pt(0)


def build_docx():
    DOCX_OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    configure_styles(doc)
    section = doc.sections[0]
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.top_margin = Pt(28)
    section.bottom_margin = Pt(25)
    section.left_margin = Pt(29)
    section.right_margin = Pt(29)
    section.header_distance = Pt(0)
    section.footer_distance = Pt(0)

    # Page 1 header: 460 pt centered information area + 77 pt photo area.
    header = compact_table(doc, 1, [460, 77])
    info, portrait = header.rows[0].cells
    info.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
    portrait.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP

    name = info.paragraphs[0]
    name.style = doc.styles["Title"]
    set_paragraph(name, align=WD_ALIGN_PARAGRAPH.CENTER, after=3, leading=24)
    add_runs(name, [{"text": "杜云浩", "size": 20, "bold": True}])
    for fragments in [
        [{"text": "天津市智能无人集群技术与系统重点实验室", "size": 10}],
        [{"text": "天津大学电气自动化与信息工程学院", "size": 10}],
        [{"text": "地址：", "size": 10, "bold": True}, {"text": "天津市南开区卫津路 92 号", "size": 10}],
        [
            {"text": "邮箱：", "size": 10, "bold": True},
            {"text": "clouduh@tju.edu.cn", "size": 10},
            {"text": "  |  ", "size": 10},
            {"text": "电话：", "size": 10, "bold": True},
            {"text": "(+86) 13954349756", "size": 10},
        ],
    ]:
        p = info.add_paragraph()
        set_paragraph(p, align=WD_ALIGN_PARAGRAPH.CENTER, leading=14)
        add_runs(p, fragments)

    pp = portrait.paragraphs[0]
    set_paragraph(pp, align=WD_ALIGN_PARAGRAPH.RIGHT, before=2)
    pp.add_run().add_picture(str(PHOTO), width=Pt(65), height=Pt(83.6))

    section_heading(doc, "研究方向", before=10, after=7)
    p = doc.add_paragraph()
    set_paragraph(p, after=1, leading=17, keep_next=True)
    add_runs(p, [{"text": "临近空间太阳能无人机储能管理", "size": 10.2, "bold": True}])
    research = [
        "储能电池建模与状态估计。",
        "健康感知的电池充放电策略优化。",
        "面向能源管理的深度强化学习。",
        "基于专家示范的模仿学习。",
    ]
    for idx, item in enumerate(research):
        add_bullet(doc, [{"text": item, "size": 10, "italic": True}], size=10, leading=17, after=0)

    section_heading(doc, "教育经历与荣誉", before=14, after=7)
    add_education_entry(
        doc,
        "天津大学 电气自动化与信息工程学院",
        "2021.08 - 至今",
        "控制科学与工程专业博士研究生（硕博连读）",
        "天津",
        [
            [{"text": "导师：", "bold": True}, {"text": "左志强教授", "bold": True, "underline": True}, {"text": "，天津市智能无人集群技术与系统重点实验室主任"}],
            [{"text": "学生工作：", "bold": True}, {"text": "班长；中国自动化学会天津大学学生分会执行委员会委员"}],
            [{"text": "荣誉奖励：", "bold": True}, {"text": "三好学生；中国自动化学会博士生学术论坛优秀论文奖；一等奖学金"}],
        ],
    )
    add_education_entry(
        doc,
        "燕山大学 车辆与能源学院",
        "2017.08 - 2021.06",
        "车辆工程专业工学学士（卓越工程师培养计划）",
        "河北",
        [
            [{"text": "成绩：", "bold": True}, {"text": "GPA 3.6/4.0，综合测评排名 1/59"}],
            [{"text": "学生工作：", "bold": True}, {"text": "班长；学生会主席；燕翔车队队长"}],
            [{"text": "荣誉奖励：", "bold": True}, {"text": "国家奖学金；国家励志奖学金；省级三好学生；优秀毕业生；一等奖学金"}],
            [{"text": "获推荐免试攻读硕士研究生资格"}],
        ],
        before=3,
    )

    section_heading(doc, "论文成果", before=12, after=4)
    add_publication(
        doc,
        1,
        "Yunhao Du, Zhicheng Zhang, Zhiqiang Zuo, Yijing Wang, ",
        "Lithium Battery Charging Optimization via Multi-Stage Combined Charging Strategy in Solar-Powered Vehicles",
        ", Journal of Energy Storage",
        ", 83: 110716, 2024.",
        "多目标充电优化；电池耦合模型；所构建的充电焦虑指标。",
    )
    add_publication(
        doc,
        2,
        "Yunhao Du, Zhiqiang Zuo, Zhicheng Zhang, Peng Li, Yijing Wang, Rui Zhao, Zheng Li, ",
        "Task-Oriented Energy Storage Management for Solar-Powered UAVs: An Enhanced Multi-Objective Deep Reinforcement Learning Approach",
        ", 64th IEEE Conference on Decision and Control (CDC)",
        ", 2025. ",
        "三维电池模型；多目标能源管理；深度强化学习。",
        status="[已录用]",
    )
    add_publication(
        doc,
        3,
        "Zhiqiang Zuo, Yunhao Du, Yijing Wang, Zhicheng Zhang, Peng Li, ",
        "State-of-Charge Balancing Control for Battery Energy Storage Systems of Near-Space Vehicles with an Electric-Thermal-Aging Coupling Model",
        ", 2023 42nd Chinese Control Conference (CCC)",
        ", 2023: 1853-1858.",
        "荷电状态均衡；电池耦合模型；滚动时域控制。",
    )
    add_publication(
        doc,
        4,
        "Yunhao Du, Zhiqiang Zuo, Zhicheng Zhang, Peng Li, ",
        "Health- and Dynamics-Constrained Energy Management for Solar-Powered UAVs based on Enhanced TD3 from Demonstrations",
        "",
        ". ",
        "exponential-dilated multi-step TD3；基于示范的强化学习；高度势能利用。",
        status="[审稿中]",
    )

    # Page 2 is intentionally fixed as a separate page, matching the source.
    pb = doc.add_paragraph()
    pb.add_run().add_break(WD_BREAK.PAGE)
    section_heading(doc, "项目经历", before=0, after=5)

    projects = [
        (
            "电动方程式赛车设计、制造与控制",
            "2017.12 - 2020.11",
            PROJECT_IMAGES[0],
            [
                [{"text": "中国大学生电动方程式大赛（FSEC），燕翔车队，"}, {"text": "队长", "bold": True}],
                [{"text": "2018、2019 年 FSEC 全国三等奖；2019 年“挑战杯”大学生课外学术科技作品竞赛全国三等奖"}],
                [{"text": "带领学生团队完成电动方程式赛车设计、制造与参赛。"}],
                [{"text": "负责整车电气系统架构与设计，包括传感器与控制线束、电池包及高压动力部件。"}],
                [
                    {"text": "开发", "color": BLACK},
                    {"text": "电池管理策略", "color": BLUE},
                    {"text": "和", "color": BLACK},
                    {"text": "牵引力控制算法", "color": BLUE},
                    {"text": "，分析遥测数据，为机械调校与性能验证提供支持。", "color": BLACK},
                ],
            ],
        ),
        (
            "分布式自主供能系统协同调度",
            "2020.11 - 2023.04",
            PROJECT_IMAGES[1],
            [
                [{"text": "“十三五”装备预研项目，"}, {"text": "项目骨干", "bold": True}],
                [{"text": "设计系统通信架构，包括 CAN、NI-VISA、TCP/IP 协议及网络拓扑。"}],
                [
                    {"text": "基于 ", "color": BLACK},
                    {"text": "PyQt", "color": BLUE},
                    {"text": " 构建 MVC 架构上位机，用于系统监控、数据采集、设备控制及自定义算法部署。", "color": BLACK},
                ],
                [
                    {"text": "开发", "color": BLACK},
                    {"text": "自适应能量调度算法", "color": BLUE},
                    {"text": "，按节点能量状态确定优先级，满足实时需求并均衡负载；快速隔离故障节点，保障系统稳定性与可用性。", "color": BLACK},
                ],
            ],
        ),
        (
            "临近空间无人机储能调度与协同控制",
            "2021.08 - 2024.12",
            PROJECT_IMAGES[2],
            [
                [{"text": "国家自然科学基金重点项目，"}, {"text": "项目骨干", "bold": True}],
                [
                    {"text": "搭建实验室电池测试平台，完成不同工况下的 HPPC 和循环充放电测试，建立", "color": BLACK},
                    {"text": "三维耦合电池模型", "color": BLUE},
                    {"text": "。", "color": BLACK},
                ],
                [
                    {"text": "提出光伏约束下的", "color": BLACK},
                    {"text": "组合充电策略", "color": BLUE},
                    {"text": "，在提高充电效率的同时降低电池老化速率。", "color": BLACK},
                ],
                [
                    {"text": "开发健康感知的", "color": BLACK},
                    {"text": "多节点能量均衡算法", "color": BLUE},
                    {"text": "，兼顾荷电状态均衡速率与电池老化速率。", "color": BLACK},
                ],
            ],
        ),
        (
            "基于深度强化学习的能量流调度与硬件实现",
            "2022.10 - 2025.03",
            PROJECT_IMAGES[3],
            [
                [{"text": "国家部委科研项目，"}, {"text": "项目负责人", "bold": True}],
                [
                    {"text": "将", "color": BLACK},
                    {"text": "临近空间无人机飞行环境仿真", "color": BLUE},
                    {"text": "集成至硬件平台，用于模拟太阳辐照度和推进负载。", "color": BLACK},
                ],
                [
                    {"text": "基于 PyTorch 和 Stable-Baselines3，将深度强化学习算法部署于华为 Atlas 模块（性能与 NVIDIA Jetson Nano 相当），实现", "color": BLACK},
                    {"text": "昼夜连续储能管理", "color": BLUE},
                    {"text": "。", "color": BLACK},
                ],
                [{"text": "开展超过一个月的不间断仿真测试，验证算法可行性与鲁棒性。"}],
            ],
        ),
    ]
    for idx, args in enumerate(projects):
        add_project(doc, *args, gap_after=3 if idx < 3 else 2)

    p = doc.add_paragraph()
    set_paragraph(p, before=3, after=4, leading=16, keep_next=True)
    add_runs(p, [{"text": "参与多项企业项目及国家自然科学基金项目申请工作。", "size": 11, "bold": True}])

    section_heading(doc, "技能与经历", before=0, after=3)
    skill_lines = [
        [
            {"text": "英语：", "bold": True}, {"text": "CET-4 475 | CET-6 530    "},
            {"text": "编程与软件：", "bold": True}, {"text": "NCRE 二级 | Python | MATLAB | Simscape | Qt | PyTorch"},
        ],
        [
            {"text": "兴趣爱好：", "bold": True}, {"text": "运动 | 摄影 | HomeLab    "},
            {"text": "硬件与平台：", "bold": True}, {"text": "STM32 | DSP | RapidECU | NVIDIA Jetson | ESXi Server"},
        ],
        [
            {"text": "社会任职与实习：", "bold": True},
            {"text": "中国自动化学会天津大学学生分会成员 | 山东省博士生协会副部长 | 中电十八所实习生"},
        ],
        [
            {"text": "组织运营经历：", "bold": True}, {"text": "组织多场大型学术活动 | 负责团队宣传及社交媒体账号运营"},
        ],
    ]
    for frags in skill_lines:
        p = doc.add_paragraph()
        set_paragraph(p, leading=17, keep_together=True)
        for frag in frags:
            frag.setdefault("size", 9.2)
        add_runs(p, frags, default_size=9.2)

    # Remove document metadata inherited from python-docx defaults.
    props = doc.core_properties
    props.title = "杜云浩中文简历"
    props.subject = "中文个人简历"
    props.author = "杜云浩"
    props.keywords = "简历, 无人机, 储能管理, 强化学习"
    props.comments = ""
    doc.save(DOCX_OUT)
    print(DOCX_OUT)


# -------------------------- fixed-layout PDF --------------------------


def register_pdf_fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    candidates = {
        "CNLight": [
            ("/System/Library/Fonts/STHeiti Light.ttc", 0),
            ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0),
            ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", 0),
        ],
        "CNMedium": [
            ("/System/Library/Fonts/STHeiti Medium.ttc", 0),
            ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0),
            ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", 0),
        ],
        "Arial": [("/System/Library/Fonts/Supplemental/Arial.ttf", 0)],
        "ArialBold": [("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0)],
        "ArialItalic": [("/System/Library/Fonts/Supplemental/Arial Italic.ttf", 0)],
        "ArialBoldItalic": [("/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf", 0)],
    }
    for name, options in candidates.items():
        last_error = None
        for path, index in options:
            try:
                pdfmetrics.registerFont(TTFont(name, path, subfontIndex=index))
                break
            except Exception as exc:  # pragma: no cover - fallback depends on host fonts
                last_error = exc
        else:
            raise RuntimeError(f"Unable to register PDF font {name}: {last_error}")


def draw_text_top(c, text, x, top, *, font="CNLight", size=10, color=BLACK, align="left", underline=False):
    from reportlab.lib.colors import HexColor
    from reportlab.pdfbase import pdfmetrics

    c.setFont(font, size)
    hex_color = color if color.startswith("#") else f"#{color}"
    c.setFillColor(HexColor(hex_color))
    baseline = 842 - top - size * 0.82
    width = pdfmetrics.stringWidth(text, font, size)
    if align == "center":
        x = x - width / 2
    elif align == "right":
        x = x - width
    c.drawString(x, baseline, text)
    if underline:
        c.setStrokeColor(HexColor(hex_color))
        c.setLineWidth(0.55)
        c.line(x, baseline - 1.2, x + width, baseline - 1.2)
    return x + width


def draw_rich_top(c, fragments, x, top, *, default_size=10):
    cur = x
    for frag in fragments:
        if isinstance(frag, str):
            frag = {"text": frag}
        cur = draw_text_top(
            c,
            frag["text"],
            cur,
            top,
            font=frag.get("font", "CNLight"),
            size=frag.get("size", default_size),
            color=frag.get("color", BLACK),
            underline=frag.get("underline", False),
        )
    return cur


def draw_section(c, text, top):
    from reportlab.lib.colors import HexColor

    draw_text_top(c, text, 30, top, font="CNMedium", size=14, color=NAVY)
    c.setFillColor(HexColor(f"#{BLUE}"))
    c.rect(29, 842 - (top + 21.2), 537, 7, stroke=0, fill=1)


def pdf_pub_line(c, number, top, fragments):
    x = 30
    if number is not None:
        x = draw_text_top(c, f"[{number}] ", x, top, font="Arial", size=10)
    draw_rich_top(c, fragments, x, top, default_size=10)


def pdf_keyword(c, top, fragments):
    draw_text_top(c, "•", 40, top, font="CNLight", size=10)
    draw_rich_top(c, fragments, 50, top, default_size=9.7)


def draw_project_lines(c, top, lines):
    for idx, (is_bullet, fragments) in enumerate(lines):
        line_top = top + idx * 16
        if is_bullet:
            draw_text_top(c, "•", 205.5, line_top, font="CNLight", size=9.8)
        draw_rich_top(c, fragments, 215, line_top, default_size=9.8)


def build_pdf():
    from reportlab.lib.colors import HexColor
    from reportlab.pdfgen import canvas

    PDF_OUT.parent.mkdir(parents=True, exist_ok=True)
    register_pdf_fonts()
    c = canvas.Canvas(str(PDF_OUT), pagesize=(595, 842), pageCompression=1)
    c.setTitle("杜云浩中文简历")
    c.setAuthor("杜云浩")
    c.setSubject("中文个人简历")

    # Page 1 header
    c.drawImage(str(PHOTO), 489.778, 842 - 32.214 - 83.571, width=65, height=83.571, mask="auto")
    draw_text_top(c, "杜云浩", 297.5, 35.2, font="CNMedium", size=20, align="center")
    draw_text_top(c, "天津市智能无人集群技术与系统重点实验室", 297.5, 61.0, font="CNLight", size=10, align="center")
    draw_text_top(c, "天津大学电气自动化与信息工程学院", 297.5, 75.0, font="CNLight", size=10, align="center")
    # Contact information is slightly left of page center to clear the photograph.
    line = [
        {"text": "地址：", "font": "CNMedium", "size": 10},
        {"text": "天津市南开区卫津路 92 号", "font": "CNLight", "size": 10},
    ]
    from reportlab.pdfbase import pdfmetrics
    total = sum(pdfmetrics.stringWidth(f["text"], f["font"], f["size"]) for f in line)
    draw_rich_top(c, line, 297.5 - total / 2, 89.0)
    line = [
        {"text": "邮箱：", "font": "CNMedium", "size": 10},
        {"text": "clouduh@tju.edu.cn", "font": "Arial", "size": 10},
        {"text": "  |  ", "font": "Arial", "size": 10},
        {"text": "电话：", "font": "CNMedium", "size": 10},
        {"text": "(+86) 13954349756", "font": "Arial", "size": 10},
    ]
    total = sum(pdfmetrics.stringWidth(f["text"], f["font"], f["size"]) for f in line)
    draw_rich_top(c, line, 297.5 - total / 2, 103.0)

    draw_section(c, "研究方向", 130.4)
    draw_text_top(c, "临近空间太阳能无人机储能管理", 30, 158.3, font="CNMedium", size=10.2)
    for top, text in zip((175.3, 192.3, 209.3, 226.3), (
        "储能电池建模与状态估计。",
        "健康感知的电池充放电策略优化。",
        "面向能源管理的深度强化学习。",
        "基于专家示范的模仿学习。",
    )):
        draw_text_top(c, "•", 40.5, top, font="CNLight", size=10)
        draw_text_top(c, text, 50, top, font="CNLight", size=10)

    draw_section(c, "教育经历与荣誉", 255.4)
    # Tianjin University
    draw_text_top(c, "天津大学 电气自动化与信息工程学院", 30, 283.3, font="CNMedium", size=10.2)
    draw_text_top(c, "2021.08 - 至今", 565, 283.3, font="CNLight", size=10, align="right")
    draw_text_top(c, "控制科学与工程专业博士研究生（硕博连读）", 30, 300.3, font="CNLight", size=10)
    draw_text_top(c, "天津", 565, 300.3, font="CNLight", size=10, align="right")
    edu1 = [
        [
            {"text": "导师：", "font": "CNMedium"},
            {"text": "左志强教授", "font": "CNMedium", "underline": True},
            {"text": "，天津市智能无人集群技术与系统重点实验室主任", "font": "CNLight"},
        ],
        [
            {"text": "学生工作：", "font": "CNMedium"},
            {"text": "班长；中国自动化学会天津大学学生分会执行委员会委员", "font": "CNLight"},
        ],
        [
            {"text": "荣誉奖励：", "font": "CNMedium"},
            {"text": "三好学生；中国自动化学会博士生学术论坛优秀论文奖；一等奖学金", "font": "CNLight"},
        ],
    ]
    for top, frags in zip((317.3, 334.3, 351.3), edu1):
        draw_text_top(c, "•", 40.5, top, font="CNLight", size=10)
        draw_rich_top(c, frags, 50, top, default_size=10)

    draw_text_top(c, "燕山大学 车辆与能源学院", 30, 378.3, font="CNMedium", size=10.2)
    draw_text_top(c, "2017.08 - 2021.06", 565, 378.3, font="CNLight", size=10, align="right")
    draw_text_top(c, "车辆工程专业工学学士（卓越工程师培养计划）", 30, 395.3, font="CNLight", size=10)
    draw_text_top(c, "河北", 565, 395.3, font="CNLight", size=10, align="right")
    edu2 = [
        [
            {"text": "成绩：", "font": "CNMedium"}, {"text": "GPA 3.6/4.0，综合测评排名 1/59", "font": "CNLight"},
        ],
        [
            {"text": "学生工作：", "font": "CNMedium"}, {"text": "班长；学生会主席；燕翔车队队长", "font": "CNLight"},
        ],
        [
            {"text": "荣誉奖励：", "font": "CNMedium"}, {"text": "国家奖学金；国家励志奖学金；省级三好学生；优秀毕业生；一等奖学金", "font": "CNLight"},
        ],
        [{"text": "获推荐免试攻读硕士研究生资格", "font": "CNLight"}],
    ]
    for top, frags in zip((412.3, 429.3, 446.3, 463.3), edu2):
        draw_text_top(c, "•", 40.5, top, font="CNLight", size=10)
        draw_rich_top(c, frags, 50, top, default_size=10)

    draw_section(c, "论文成果", 515.4)
    # Entries preserve official published titles and author spelling.
    pdf_pub_line(c, 1, 541.3, [
        {"text": "Yunhao Du", "font": "Arial", "underline": True},
        {"text": ", Zhicheng Zhang, Zhiqiang Zuo, Yijing Wang, ", "font": "Arial"},
        {"text": "Lithium Battery Charging Optimization via Multi-Stage", "font": "ArialBold"},
    ])
    pdf_pub_line(c, None, 559.3, [
        {"text": "Combined Charging Strategy in Solar-Powered Vehicles", "font": "ArialBold"},
        {"text": ", ", "font": "Arial"},
        {"text": "Journal of Energy Storage", "font": "ArialItalic"},
        {"text": ", 83: 110716, 2024.", "font": "Arial"},
    ])
    pdf_keyword(c, 577.3, [
        {"text": "关键词：", "font": "CNLight"},
        {"text": "多目标充电优化；电池耦合模型；所构建的充电焦虑指标。", "font": "CNLight", "color": GRAY},
    ])

    pdf_pub_line(c, 2, 595.3, [
        {"text": "Yunhao Du", "font": "Arial", "underline": True},
        {"text": ", Zhiqiang Zuo, Zhicheng Zhang, Peng Li, Yijing Wang, Rui Zhao, Zheng Li, ", "font": "Arial"},
        {"text": "Task-Oriented Energy", "font": "ArialBold"},
    ])
    pdf_pub_line(c, None, 613.3, [
        {"text": "Storage Management for Solar-Powered UAVs: An Enhanced Multi-Objective Deep Reinforcement Learning", "font": "ArialBold"},
    ])
    pdf_pub_line(c, None, 631.3, [
        {"text": "Approach", "font": "ArialBold"},
        {"text": ", ", "font": "Arial"},
        {"text": "64th IEEE Conference on Decision and Control (CDC)", "font": "ArialItalic"},
        {"text": ", 2025. ", "font": "Arial"},
        {"text": "[已录用]", "font": "CNMedium"},
    ])
    pdf_keyword(c, 649.3, [
        {"text": "关键词：三维电池模型；多目标能源管理；深度强化学习。", "font": "CNLight", "color": GRAY},
    ])

    pdf_pub_line(c, 3, 667.3, [
        {"text": "Zhiqiang Zuo, ", "font": "Arial"},
        {"text": "Yunhao Du", "font": "Arial", "underline": True},
        {"text": ", Yijing Wang, Zhicheng Zhang, Peng Li, ", "font": "Arial"},
        {"text": "State-of-Charge Balancing Control for", "font": "ArialBold"},
    ])
    pdf_pub_line(c, None, 685.3, [
        {"text": "Battery Energy Storage Systems of Near-Space Vehicles with an Electric-Thermal-Aging Coupling Model", "font": "ArialBold"},
        {"text": ",", "font": "Arial"},
    ])
    pdf_pub_line(c, None, 703.3, [
        {"text": "2023 42nd Chinese Control Conference (CCC)", "font": "ArialItalic"},
        {"text": ", 2023: 1853-1858.", "font": "Arial"},
    ])
    pdf_keyword(c, 721.3, [
        {"text": "关键词：荷电状态均衡；电池耦合模型；滚动时域控制。", "font": "CNLight", "color": GRAY},
    ])

    pdf_pub_line(c, 4, 739.3, [
        {"text": "Yunhao Du", "font": "Arial", "underline": True},
        {"text": ", Zhiqiang Zuo, Zhicheng Zhang, Peng Li, ", "font": "Arial"},
        {"text": "Health- and Dynamics-Constrained Energy Management", "font": "ArialBold"},
    ])
    pdf_pub_line(c, None, 757.3, [
        {"text": "for Solar-Powered UAVs based on Enhanced TD3 from Demonstrations", "font": "ArialBold"},
        {"text": ". ", "font": "Arial"},
        {"text": "[审稿中]", "font": "CNMedium"},
    ])
    pdf_keyword(c, 775.3, [
        {"text": "关键词：exponential-dilated multi-step TD3；基于示范的强化学习；高度势能利用。", "font": "CNLight", "color": GRAY},
    ])
    c.showPage()

    # Page 2
    draw_section(c, "项目经历", 35.4)
    project_data = [
        (
            "电动方程式赛车设计、制造与控制", "2017.12 - 2020.11", PROJECT_IMAGES[0],
            [
                (True, [{"text": "中国大学生电动方程式大赛（FSEC），燕翔车队，"}, {"text": "队长", "font": "CNMedium"}]),
                (True, [{"text": "2018、2019 年 FSEC 全国三等奖；2019 年“挑战杯”大学生", "font": "CNLight"}]),
                (False, [{"text": "课外学术科技作品竞赛全国三等奖", "font": "CNLight"}]),
                (True, [{"text": "带领学生团队完成电动方程式赛车设计、制造与参赛。"}]),
                (True, [{"text": "负责整车电气系统架构与设计，包括传感器与控制线束、"}]),
                (False, [{"text": "电池包及高压动力部件。"}]),
                (True, [{"text": "开发", "font": "CNLight"}, {"text": "电池管理策略与牵引力控制算法", "font": "CNLight", "color": BLUE}, {"text": "，分析遥测数据，"}]),
                (False, [{"text": "为机械调校与性能验证提供支持。"}]),
            ],
        ),
        (
            "分布式自主供能系统协同调度", "2020.11 - 2023.04", PROJECT_IMAGES[1],
            [
                (True, [{"text": "“十三五”装备预研项目，"}, {"text": "项目骨干", "font": "CNMedium"}]),
                (True, [{"text": "设计系统通信架构，包括 CAN、NI-VISA、TCP/IP 协议及"}]),
                (False, [{"text": "网络拓扑。"}]),
                (True, [{"text": "基于 ", "font": "CNLight"}, {"text": "PyQt", "font": "Arial", "color": BLUE}, {"text": " 构建 MVC 架构上位机，用于系统监控、数据采集、"}]),
                (False, [{"text": "设备控制及自定义算法部署。"}]),
                (True, [{"text": "开发", "font": "CNLight"}, {"text": "自适应能量调度算法", "font": "CNLight", "color": BLUE}, {"text": "，按节点能量状态确定优先级，"}]),
                (False, [{"text": "满足实时需求并均衡负载；快速隔离故障节点，保障系统"}]),
                (False, [{"text": "稳定性与可用性。"}]),
            ],
        ),
        (
            "临近空间无人机储能调度与协同控制", "2021.08 - 2024.12", PROJECT_IMAGES[2],
            [
                (True, [{"text": "国家自然科学基金重点项目，"}, {"text": "项目骨干", "font": "CNMedium"}]),
                (True, [{"text": "搭建实验室电池测试平台，完成不同工况下的 HPPC 和循环"}]),
                (False, [{"text": "充放电测试，建立", "font": "CNLight"}, {"text": "三维耦合电池模型", "font": "CNLight", "color": BLUE}, {"text": "。"}]),
                (True, [{"text": "提出光伏约束下的", "font": "CNLight"}, {"text": "组合充电策略", "font": "CNLight", "color": BLUE}, {"text": "，在提高充电效率的同时"}]),
                (False, [{"text": "降低电池老化速率。"}]),
                (True, [{"text": "开发健康感知的", "font": "CNLight"}, {"text": "多节点能量均衡算法", "font": "CNLight", "color": BLUE}, {"text": "，兼顾荷电状态"}]),
                (False, [{"text": "均衡速率与电池老化速率。"}]),
            ],
        ),
        (
            "基于深度强化学习的能量流调度与硬件实现", "2022.10 - 2025.03", PROJECT_IMAGES[3],
            [
                (True, [{"text": "国家部委科研项目，"}, {"text": "项目负责人", "font": "CNMedium"}]),
                (True, [{"text": "将", "font": "CNLight"}, {"text": "临近空间无人机飞行环境仿真", "font": "CNLight", "color": BLUE}, {"text": "集成至硬件平台，用于"}]),
                (False, [{"text": "模拟太阳辐照度和推进负载。"}]),
                (True, [{"text": "基于 PyTorch 和 Stable-Baselines3，将深度强化学习算法"}]),
                (False, [{"text": "部署于华为 Atlas 模块（性能与 NVIDIA Jetson Nano 相当），"}]),
                (False, [{"text": "实现", "font": "CNLight"}, {"text": "昼夜连续储能管理", "font": "CNLight", "color": BLUE}, {"text": "。"}]),
                (True, [{"text": "开展超过一个月的不间断仿真测试，验证算法可行性与"}]),
                (False, [{"text": "鲁棒性。"}]),
            ],
        ),
    ]
    for idx, (title, date, image_path, lines) in enumerate(project_data):
        title_top = 62.5 + idx * 155
        image_top = 80 + idx * 155
        draw_text_top(c, title, 30, title_top, font="CNMedium", size=11, color=NAVY)
        draw_text_top(c, date, 565, title_top, font="CNLight", size=10, color=BLACK, align="right")
        c.drawImage(str(image_path), 30, 842 - image_top - 132, width=172, height=132, mask="auto")
        draw_project_lines(c, image_top + 2.5, lines)

    draw_text_top(c, "参与多项企业项目及国家自然科学基金项目申请工作。", 30, 687.5, font="CNMedium", size=11)
    draw_section(c, "技能与经历", 710.4)
    skill_lines = [
        [
            {"text": "英语：", "font": "CNMedium"}, {"text": "CET-4 475 | CET-6 530    ", "font": "Arial"},
            {"text": "编程与软件：", "font": "CNMedium"}, {"text": "NCRE 二级 | Python | MATLAB | Simscape | Qt | PyTorch", "font": "CNLight"},
        ],
        [
            {"text": "兴趣爱好：", "font": "CNMedium"}, {"text": "运动 | 摄影 | HomeLab    ", "font": "CNLight"},
            {"text": "硬件与平台：", "font": "CNMedium"}, {"text": "STM32 | DSP | RapidECU | NVIDIA Jetson | ESXi Server", "font": "CNLight"},
        ],
        [
            {"text": "社会任职与实习：", "font": "CNMedium"}, {"text": "中国自动化学会天津大学学生分会成员 | 山东省博士生协会副部长 | 中电十八所实习生", "font": "CNLight"},
        ],
        [
            {"text": "组织运营经历：", "font": "CNMedium"}, {"text": "组织多场大型学术活动 | 负责团队宣传及社交媒体账号运营", "font": "CNLight"},
        ],
    ]
    for top, frags in zip((734.3, 751.3, 768.3, 785.3), skill_lines):
        for frag in frags:
            frag.setdefault("size", 9.15)
        draw_rich_top(c, frags, 30, top, default_size=9.15)

    c.showPage()
    c.save()
    print(PDF_OUT)


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--docx", action="store_true")
    group.add_argument("--pdf", action="store_true")
    args = parser.parse_args()
    for path in [PHOTO, *PROJECT_IMAGES]:
        if not path.exists():
            raise FileNotFoundError(path)
    if args.docx:
        build_docx()
    else:
        build_pdf()


if __name__ == "__main__":
    main()
