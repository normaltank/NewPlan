"""Offline evidence checks for Issue #25; never requests a URL or calls a model."""
import argparse
from bisect import bisect_right
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata

from bs4 import BeautifulSoup

LIVE = Path(__file__).resolve().parents[1] / "mission-c-live-20261027"
sys.path.insert(0, str(LIVE))
from compare import OUT, SAMPLES

# These short checkpoints were read against the saved official HTML, not inferred
# from the Fetch response. A hit is a spot check, never a full-content score.
CHECKS = {
    "suda": {
        "fields": {"name": ("何剑", "何剑\n教授"), "title": ("教授", "何剑\n教授"),
                   "email": ("drhejian@suda.edu.cn", "电子邮箱：\ndrhejian@suda.edu.cn")},
        "points": [
            ("简介首", "何剑，苏州大学教授、博导，电子科技大学博士"),
            ("简介中", "中国微米纳米学会微系统与微执行器分会理事"),
            ("简介尾/招生", "085501 机械工程（专硕）"),
            ("教育", "2009.09-2014.12, 光学工程, 电子科技大学, 博士"),
            ("工作", "2026.03-至今, 苏州大学未来科学与工程学院, 副院长"),
            ("研究", "无人平台：具身智能、无人值守、人工智能算法、测试评估"),
            ("项目首", "基于铁电单晶电畴精密调控的太赫兹产生机理"),
            ("项目尾", "9、xxx传感器件, 2019.01- 至今, 主持, 航天、兵器集团等单位横向课题, 3000万"),
            ("论文首", "Chip-less,Self-powered electronic patch for wireless sensing and communication"),
            ("论文尾", "Flexible wide-range multidimensional force sensors inspired by bones embedded in muscle."),
            ("专利首", "一种高密度微纳线圈柔性异质集成方法"),
            ("专利尾", "ZL202311617338.7."),
            ("软件著作", "运动数据同步分析工具软件V1.0"),
            ("奖励尾", "自驱动智能感知微系统技术及应用"),
            ("招生尾邮箱", "欢迎联系：drhejian@suda.edu.cn"),
            ("专利小标题", "专利："),
            ("空课程教学标签", "课程教学："),
        ],
        "notes": ["专利小标题和空的课程教学标签遗漏；专利首尾和六条专利正文仍在。",
                  "标题/列表、邮箱及英文标点大量反斜杠转义；这不是独立字段抽取结果。"],
    },
    "ncepu": {
        "fields": {"name": ("王健", "姓名：\n王健"), "title": ("教授", "职称：\n教授，博士生导师"),
                   "email": ("wangjian31791@ncepu.edu.cn", "电子邮箱：wangjian31791@ncepu.edu.cn")},
        "points": [
            ("简介首", "王健，男，1985年12月生，教授，博士生导师"),
            ("教育", "2017年在华北电力大学获得高电压与绝缘技术博士学位"),
            ("研究", "先进绝缘材料（Advanced Insulation Materials）"),
            ("简介中/学生培养", "中国研究生“双碳”创新与创意大赛二等奖"),
            ("项目首", "高经济性多端异构换流装备轻量化集成研制"),
            ("项目尾", "高压大功率****寿命及可靠性强化技术"),
            ("奖励尾", "2023年日内瓦国际发明铜奖"),
            ("论文首", "Gas-Generation Mechanism of Silicone Gel in High-Temperature Thermal Decomposition"),
            ("论文中", "Motion Analysis of the Spherical Metal Particle in AC Gas-Insulated Lines"),
            ("论文尾/简介尾", "含苯硫醚基团的低介损聚酰亚胺薄膜合成及其性能调控机制"),
            ("论文尾页码", "4623-4633"),
        ],
        "notes": ["专业职称为教授；博士生导师另属导师资格，未代入职称。",
                  "官网本文无独立专利条目可核对，不能把该项记为Fetch遗漏。"],
    },
    "shu": {
        "fields": {"name": ("张惠芳", "姓名：\n张惠芳"), "title": ("副研究员", "职称：\n副研究员"),
                   "email": ("hfzhang1967@shu.edu.cn", "hfzhang1967@shu.edu.cn")},
        "points": [
            ("简介首/本人身份", "姓名：张惠芳"),
            ("教育", "1998-09 至 2003-07, 吉林大学物理学院, 光学专业, 理学博士"),
            ("工作", "2005-04 至 今, 上海大学, 理学院物理系, 副研究员"),
            ("研究", "微纳光子学、超材料、量子光学"),
            ("简介中/论文", "Tunable surface plasmon polaritons in the graphene and metamaterials structures"),
            ("论文首", "Tunable multiple plasmon-induced transparencies in multiple T-shaped cavities waveguide based on Dirac semimetals"),
            ("论文尾", "Quantum-interference effects on the index of refraction in an Er3+-doped Yttrium Aluminum Garnet crystal"),
            ("专利", "ZL03111442.3"),
            ("专利批准号", "CN1188742.C"),
            ("项目首", "11804219"),
            ("项目尾", "基于飞秒脉冲整形和绝热传输实现超快相干布局转移控制研究"),
            ("简介尾", "鼓励和督促学生学习考研"),
        ],
        "notes": ["硕士生导师属于导师资格；官网表格明确专业职称为副研究员。",
                  "表格转为分散行并出现转义的---|---，姓名/职称/邮箱文字仍在，表格结构不再可靠。"],
    },
    "ecnu": {
        "fields": {"name": ("李艳青", "李艳青\n教授"), "title": ("教授", "2019年-至今，华东师范大学，物理与电子科学学院，教授"),
                   "email": ("yqli@phy.ecnu.edu.cn", "电子邮箱：\nyqli@phy.ecnu.edu.cn")},
        "points": [
            ("简介首/教育", "2004年-2008年，香港城市大学，材料物理，博士"),
            ("教育尾", "1997年-2001年，浙江大学，物理学，学士"),
            ("工作", "2003年-2004年，新加坡材料研究及工程研究所（IMRE），研究助理"),
            ("简介中/论文概述", "等期刊发表SCI论文200余篇，引用1万余次，H因子58"),
            ("专利概述", "授权发明专利20余项"),
            ("项目概述", "科技部国家重点研发计划课题"),
            ("研究首", "新型显示发光材料与器件"),
            ("简介尾/研究尾", "柔性光电材料与器件集成"),
            ("姓名卡职称", "李艳青教授教授物理与电子科学学院"),
        ],
        "notes": ["姓名卡中独立的教授标签被省去；2019年至今的工作经历仍明确保留教授。",
                  "官网科研项目/学术成果标题下无独立明细；本页仅能核对简介中的项目、论文和专利概述。"],
    },
}


def normalize(text):
    text = re.sub(r"\\([!\"#$%&'()*+,\-./:;<=>?@\[\]^_`{|}~])", r"\1", text)
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def location(text, quote):
    """Map a normalized checkpoint back to consecutive original lines."""
    lines = text.splitlines()
    target = normalize(quote)
    normalized_lines = [normalize(line) for line in lines]
    offset = "".join(normalized_lines).find(target)
    if offset < 0:
        return None
    starts = []
    length = 0
    for line in normalized_lines:
        starts.append(length)
        length += len(line)
    start = bisect_right(starts, offset) - 1
    end = bisect_right(starts, offset + len(target) - 1) - 1
    return {"start_line": start + 1, "end_line": end + 1, "matched_normalized_excerpt": target}


def quote_status(quote, source, target):
    if normalize(quote) not in normalize(source):
        return "unverifiable"
    if normalize(quote) not in normalize(target):
        return "omitted"
    return "retained" if quote in target else "format_changed"


def check(label, quote, source, fetched, selected):
    return {"label": label, "reference_quote": quote, "status": quote_status(quote, source, fetched),
            "official_html_visible_text": location(source, quote),
            "fetch_text": location(fetched, quote),
            "saved_ds_selected_text_contains": normalize(quote) in normalize(selected)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=OUT)
    parser.add_argument("--json", type=Path, default=Path(__file__).with_name("fetch-four-report.json"))
    args = parser.parse_args()
    rows = []
    for sample in SAMPLES[1:]:
        sid = sample["id"]
        source_folder = args.output_root / "browser" / sid
        source_bytes = (source_folder / "source.html").read_bytes()
        source = BeautifulSoup(source_bytes, "html.parser").get_text("\n", strip=True)
        original = json.loads((source_folder / "result.json").read_text(encoding="utf-8"))
        fetch_folder = args.output_root / "deepseek-fetch" / sid
        fetched = (fetch_folder / "provider-content.md").read_text(encoding="utf-8")
        result = json.loads((fetch_folder / "result.json").read_text(encoding="utf-8"))
        if result["url"] != sample["url"]:
            raise SystemExit("Fetch evidence URL mismatch: " + sid)
        plan = json.loads((args.output_root / "ds" / sid / "result.json").read_text(encoding="utf-8"))
        fields = {}
        for field, (value, evidence) in CHECKS[sid]["fields"].items():
            fields[field] = {"value": value, "attribution": "manually_checked_against_saved_official_html",
                             "official_evidence": location(source, evidence),
                             "fetch_field_source": location(fetched, evidence) or location(fetched, value),
                             **check(field, value, source, fetched, plan["biography"])}
        points = [check(label, quote, source, fetched, plan["biography"]) for label, quote in CHECKS[sid]["points"]]
        rows.append({"id": sid, "url": sample["url"], "name": sample["name"],
                     "source": {"path": str(source_folder / "source.html"), "sha256": hashlib.sha256(source_bytes).hexdigest(),
                                "observed_at": original["observed_at"], "http_status": original["http_status"],
                                "text_coordinates": "BeautifulSoup(source.html).get_text(newline, strip=True), 1-based lines"},
                     "fetch": result, "fetch_evidence_path": str(fetch_folder),
                     "saved_content_file_sha256": hashlib.sha256((fetch_folder / "provider-content.md").read_bytes()).hexdigest(),
                     "content_sha256_scope": "provider content string encoded as UTF-8; saved file hash separately records Windows newline conversion",
                     "fields": fields, "checkpoints": points,
                     "saved_ds_comparison": {"new_model_calls": 0, "body_selector": plan["body_selector"],
                                             "source_sha256": plan["source_sha256"],
                                             "same_source": plan["source_sha256"] == hashlib.sha256(source_bytes).hexdigest()},
                     "notes": CHECKS[sid]["notes"], "completeness": "not_verified_by_spot_checks"})
    report = {"issue": "https://github.com/normaltank/NewPlan/issues/25", "parent_spec": "https://github.com/normaltank/NewPlan/issues/24",
              "generated_at": datetime.now(timezone.utc).isoformat(), "new_fetch_calls": sum(row["fetch"]["calls"] for row in rows),
              "new_model_calls": 0, "retry_calls": 0, "billing_verified": False,
              "method": "short official-source checkpoints, manual attribution; whitespace/NFKC/Markdown punctuation unescape only; no length-based completeness",
              "samples": rows}
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for row in rows:
        print(json.dumps({"id": row["id"], "fields": {k: v["status"] for k, v in row["fields"].items()},
                          "checkpoints": {point["label"]: point["status"] for point in row["checkpoints"]}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
