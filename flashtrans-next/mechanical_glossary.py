"""机械工程术语校正层。

为什么需要它
------------
NLLB-200 是固定训练好的多语模型，词表与参数已定，**无法向 .bin 里直接“加词”**
（那等于重训练）。两个尺寸（1.3B / 3.3b）对同一机械词常常给出不同、甚至
明显偏差的译名，这是容量差异导致的固有现象，3.3b 通常更准。

本模块在翻译*结果*上做一层确定性后处理：当原文出现了某个机械术语、而译文
却没有出现规范译名、反而出现了已知错误译法时，把错误译法替换成规范译名。
它不会凭空注入内容，只在 NLLB 明显译错时纠正，因此对 1.3b 和 3.3b 都生效，
能把两者的领域译名统一到同一套规范词表，缩小“差距很大”的问题。

术语来源
--------
- MECH_TERMS：内置常用机械工程术语（中英对照 + 常见错误译法）。
- 用户可放一个 `mechanical_terms.json` 与本文件同级（或设置环境变量
  FLASHTRANS_GLOSSARY 指向任意 JSON），格式与 MECH_TERMS 一致，会自动合并，
  方便自行扩充“更多机械相关词语”。

JSON 格式示例：
    [
      {"en": "bearing", "zh": "轴承",
       "wrong_en": ["support", "holder", "seat"],
       "wrong_zh": ["支承", "轴承座", "支撑座"]}
    ]
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

# 内置机械工程术语表。
# wrong_en：ZH→EN 时，若原文含 zh 且译文没出现规范 en、却出现这些词，则替换。
# wrong_zh：EN→ZH 时，若原文含 en 且译文没出现规范 zh、却出现这些词，则替换。
MECH_TERMS: list[dict[str, Any]] = [
    # —— 轴承 / 轴系 ——
    {"en": "bearing", "zh": "轴承", "wrong_en": ["support", "holder", "seat", "bracket"], "wrong_zh": ["支承", "轴承座", "支撑"]},
    {"en": "ball bearing", "zh": "球轴承", "wrong_en": ["roller bearing"], "wrong_zh": ["滚珠轴承"]},
    {"en": "roller bearing", "zh": "滚子轴承", "wrong_en": ["ball bearing"], "wrong_zh": ["滚筒轴承"]},
    {"en": "thrust bearing", "zh": "推力轴承", "wrong_en": ["axial bearing"], "wrong_zh": ["止推轴承"]},
    {"en": "journal bearing", "zh": "滑动轴承", "wrong_en": ["sleeve bearing", "plain bearing"], "wrong_zh": ["轴颈轴承"]},
    {"en": "spherical bearing", "zh": "关节轴承", "wrong_en": [], "wrong_zh": ["球面轴承"]},
    {"en": "shaft", "zh": "轴", "wrong_en": ["rod", "axle", "spindle"], "wrong_zh": ["杆", "轴心"]},
    {"en": "axle", "zh": "车轴", "wrong_en": ["shaft"], "wrong_zh": ["轴"]},
    {"en": "spindle", "zh": "主轴", "wrong_en": ["shaft"], "wrong_zh": ["心轴"]},
    {"en": "keyway", "zh": "键槽", "wrong_en": ["key slot"], "wrong_zh": ["键沟"]},
    {"en": "coupling", "zh": "联轴器", "wrong_en": ["connector", "joint"], "wrong_zh": ["联接器", "耦合器"]},
    {"en": "universal joint", "zh": "万向节", "wrong_en": ["u-joint"], "wrong_zh": ["万向接头"]},
    {"en": "spline", "zh": "花键", "wrong_en": ["gear teeth"], "wrong_zh": ["齿条"]},
    # —— 齿轮 / 传动 ——
    {"en": "gear", "zh": "齿轮", "wrong_en": ["cog", "wheel"], "wrong_zh": ["齿", "齿盘"]},
    {"en": "pinion", "zh": "小齿轮", "wrong_en": ["gear"], "wrong_zh": ["齿轮"]},
    {"en": "bevel gear", "zh": "锥齿轮", "wrong_en": ["angle gear"], "wrong_zh": ["斜齿轮"]},
    {"en": "helical gear", "zh": "斜齿轮", "wrong_en": ["spiral gear"], "wrong_zh": ["螺旋齿轮"]},
    {"en": "worm gear", "zh": "蜗轮", "wrong_en": ["spiral gear"], "wrong_zh": ["蜗杆齿轮"]},
    {"en": "worm", "zh": "蜗杆", "wrong_en": ["worm shaft"], "wrong_zh": ["蜗轮杆"]},
    {"en": "rack", "zh": "齿条", "wrong_en": ["bar"], "wrong_zh": ["齿轨"]},
    {"en": "belt", "zh": "皮带", "wrong_en": ["strap"], "wrong_zh": ["带"]},
    {"en": "timing belt", "zh": "同步带", "wrong_en": ["toothed belt"], "wrong_zh": ["齿形带"]},
    {"en": "chain", "zh": "链条", "wrong_en": ["link"], "wrong_zh": ["链"]},
    {"en": "sprocket", "zh": "链轮", "wrong_en": ["gear"], "wrong_zh": ["链齿轮"]},
    {"en": "clutch", "zh": "离合器", "wrong_en": ["coupling"], "wrong_zh": ["离合"]},
    {"en": "brake", "zh": "制动器", "wrong_en": ["stopper"], "wrong_zh": ["刹车", "闸"]},
    {"en": "ratchet", "zh": "棘轮", "wrong_en": [], "wrong_zh": ["棘齿"]},
    {"en": "cam", "zh": "凸轮", "wrong_en": ["lobe"], "wrong_zh": ["凸轮盘"]},
    {"en": "flywheel", "zh": "飞轮", "wrong_en": [], "wrong_zh": ["飞盘"]},
    {"en": "reduction ratio", "zh": "减速比", "wrong_en": ["gear ratio"], "wrong_zh": ["传动比"]},
    {"en": "gear ratio", "zh": "传动比", "wrong_en": ["ratio"], "wrong_zh": ["齿轮比"]},
    # —— 紧固件 ——
    {"en": "bolt", "zh": "螺栓", "wrong_en": ["screw", "stud"], "wrong_zh": ["螺钉"]},
    {"en": "screw", "zh": "螺钉", "wrong_en": ["bolt"], "wrong_zh": ["螺丝"]},
    {"en": "nut", "zh": "螺母", "wrong_en": ["cap"], "wrong_zh": ["螺帽"]},
    {"en": "stud", "zh": "双头螺柱", "wrong_en": ["bolt"], "wrong_zh": ["螺柱"]},
    {"en": "washer", "zh": "垫圈", "wrong_en": ["spacer"], "wrong_zh": ["垫片"]},
    {"en": "thread", "zh": "螺纹", "wrong_en": ["screw thread"], "wrong_zh": ["丝扣"]},
    {"en": "fastener", "zh": "紧固件", "wrong_en": ["fixing", "connector"], "wrong_zh": ["固定件"]},
    {"en": "rivet", "zh": "铆钉", "wrong_en": [], "wrong_zh": ["铆"]},
    {"en": "tolerance", "zh": "公差", "wrong_en": ["allowance", "error"], "wrong_zh": ["容差", "误差"]},
    {"en": "fit", "zh": "配合", "wrong_en": ["matching"], "wrong_zh": ["适配"]},
    {"en": "clearance", "zh": "间隙", "wrong_en": ["gap", "space"], "wrong_zh": ["空隙"]},
    {"en": "interference fit", "zh": "过盈配合", "wrong_en": ["tight fit"], "wrong_zh": ["紧配合"]},
    # —— 材料 ——
    {"en": "steel", "zh": "钢", "wrong_en": ["metal"], "wrong_zh": ["铁"]},
    {"en": "stainless steel", "zh": "不锈钢", "wrong_en": ["rustless steel"], "wrong_zh": ["耐锈钢"]},
    {"en": "cast iron", "zh": "铸铁", "wrong_en": ["iron"], "wrong_zh": ["生铁"]},
    {"en": "alloy", "zh": "合金", "wrong_en": ["metal"], "wrong_zh": ["合金属"]},
    {"en": "aluminum", "zh": "铝", "wrong_en": ["aluminium alloy"], "wrong_zh": ["铝材"]},
    {"en": "brass", "zh": "黄铜", "wrong_en": ["copper alloy"], "wrong_zh": ["铜"]},
    {"en": "bronze", "zh": "青铜", "wrong_en": [], "wrong_zh": ["铜"]},
    {"en": "ductile iron", "zh": "球墨铸铁", "wrong_en": ["nodular iron"], "wrong_zh": ["韧性铁"]},
    # —— 加工工艺 ——
    {"en": "machining", "zh": "机械加工", "wrong_en": ["processing"], "wrong_zh": ["加工"]},
    {"en": "turning", "zh": "车削", "wrong_en": ["lathe"], "wrong_zh": ["车工"]},
    {"en": "milling", "zh": "铣削", "wrong_en": ["mill"], "wrong_zh": ["铣工"]},
    {"en": "grinding", "zh": "磨削", "wrong_en": ["polishing"], "wrong_zh": ["打磨"]},
    {"en": "drilling", "zh": "钻孔", "wrong_en": ["boring"], "wrong_zh": ["打孔"]},
    {"en": "boring", "zh": "镗削", "wrong_en": ["drilling"], "wrong_zh": ["镗孔"]},
    {"en": "forging", "zh": "锻造", "wrong_en": ["forming"], "wrong_zh": ["锻"]},
    {"en": "casting", "zh": "铸造", "wrong_en": ["molding"], "wrong_zh": ["铸"]},
    {"en": "stamping", "zh": "冲压", "wrong_en": ["pressing"], "wrong_zh": ["冲"]},
    {"en": "welding", "zh": "焊接", "wrong_en": ["soldering"], "wrong_zh": ["焊"]},
    {"en": "heat treatment", "zh": "热处理", "wrong_en": ["thermal treatment"], "wrong_zh": ["加热处理"]},
    {"en": "annealing", "zh": "退火", "wrong_en": [], "wrong_zh": ["退火处理"]},
    {"en": "quenching", "zh": "淬火", "wrong_en": ["hardening"], "wrong_zh": ["淬"]},
    {"en": "tempering", "zh": "回火", "wrong_en": [], "wrong_zh": ["调质"]},
    # —— 液压 / 气动 ——
    {"en": "hydraulic", "zh": "液压", "wrong_en": ["fluid", "oil"], "wrong_zh": ["油压"]},
    {"en": "pneumatic", "zh": "气动", "wrong_en": ["air"], "wrong_zh": ["气压"]},
    {"en": "cylinder", "zh": "液压缸", "wrong_en": ["piston"], "wrong_zh": ["油缸", "汽缸"]},
    {"en": "pump", "zh": "泵", "wrong_en": ["compressor"], "wrong_zh": ["抽泵"]},
    {"en": "valve", "zh": "阀", "wrong_en": ["gate"], "wrong_zh": ["阀门"]},
    {"en": "relief valve", "zh": "溢流阀", "wrong_en": ["pressure valve"], "wrong_zh": ["减压阀"]},
    {"en": "actuator", "zh": "执行器", "wrong_en": ["driver"], "wrong_zh": ["促动器"]},
    # —— 电机 / 控制 ——
    {"en": "motor", "zh": "电机", "wrong_en": ["engine", "drive"], "wrong_zh": ["马达", "电动机"]},
    {"en": "servo motor", "zh": "伺服电机", "wrong_en": ["servo"], "wrong_zh": ["伺服马达"]},
    {"en": "encoder", "zh": "编码器", "wrong_en": ["coder"], "wrong_zh": ["译码器"]},
    {"en": "inverter", "zh": "变频器", "wrong_en": ["converter"], "wrong_zh": ["逆变"]},
    {"en": "torque", "zh": "扭矩", "wrong_en": ["moment", "force"], "wrong_zh": ["转矩", "力矩"]},
    {"en": "rpm", "zh": "转速", "wrong_en": ["speed"], "wrong_zh": ["每分钟转数"]},
    # —— 测量 / 形位 ——
    {"en": "dimension", "zh": "尺寸", "wrong_en": ["size"], "wrong_zh": ["量度"]},
    {"en": "surface roughness", "zh": "表面粗糙度", "wrong_en": ["roughness"], "wrong_zh": ["光洁度"]},
    {"en": "flatness", "zh": "平面度", "wrong_en": [], "wrong_zh": ["平整度"]},
    {"en": "concentricity", "zh": "同轴度", "wrong_en": [], "wrong_zh": ["同心度"]},
    {"en": "hardness", "zh": "硬度", "wrong_en": [], "wrong_zh": ["坚硬性"]},
    {"en": "caliper", "zh": "卡尺", "wrong_en": ["gauge"], "wrong_zh": ["卡规"]},
    {"en": "gauge", "zh": "量规", "wrong_en": ["gauge tool"], "wrong_zh": ["规"]},
    # —— 结构 / 通用 ——
    {"en": "flange", "zh": "法兰", "wrong_en": ["rim", "collar"], "wrong_zh": ["凸缘"]},
    {"en": "housing", "zh": "壳体", "wrong_en": ["case", "cover"], "wrong_zh": ["外壳", "机壳"]},
    {"en": "housing", "zh": "轴承座", "wrong_en": ["bearing block"], "wrong_zh": ["壳"]},
    {"en": "chassis", "zh": "底盘", "wrong_en": ["frame"], "wrong_zh": ["底架"]},
    {"en": "frame", "zh": "机架", "wrong_en": ["structure"], "wrong_zh": ["框架"]},
    {"en": "assembly", "zh": "装配体", "wrong_en": ["unit", "module"], "wrong_zh": ["组件"]},
    {"en": "workpiece", "zh": "工件", "wrong_en": ["part", "piece"], "wrong_zh": ["工件物"]},
    {"en": "fixture", "zh": "夹具", "wrong_en": ["clamp", "jig"], "wrong_zh": ["固定具"]},
    {"en": "jig", "zh": "钻模", "wrong_en": ["fixture"], "wrong_zh": ["模具"]},
    {"en": "lubrication", "zh": "润滑", "wrong_en": ["grease"], "wrong_zh": ["加油"]},
    {"en": "seal", "zh": "密封件", "wrong_en": ["gasket"], "wrong_zh": ["封"]},
    {"en": "gasket", "zh": "垫片", "wrong_en": ["seal", "washer"], "wrong_zh": ["垫圈"]},
]

_CUSTOM_CACHE: list[dict[str, Any]] | None = None
_CUSTOM_LOADED = False


def _load_custom() -> list[dict[str, Any]]:
    """合并用户自定义术语（mechanical_terms.json 或 FLASHTRANS_GLOSSARY 指向的文件）。"""
    global _CUSTOM_CACHE, _CUSTOM_LOADED
    if _CUSTOM_LOADED:
        return _CUSTOM_CACHE or []
    _CUSTOM_LOADED = True
    _CUSTOM_CACHE = []
    candidates: list[str] = []
    env = os.environ.get("FLASHTRANS_GLOSSARY")
    if env:
        candidates.append(env)
    here = Path(__file__).resolve().parent
    candidates.append(str(here / "mechanical_terms.json"))
    for path in candidates:
        try:
            p = Path(path)
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    _CUSTOM_CACHE.extend(d for d in data if isinstance(d, dict) and d.get("en") and d.get("zh"))
        except Exception:
            # 自定义术语表解析失败不应影响主翻译流程
            pass
    return _CUSTOM_CACHE


def _all_terms() -> list[dict[str, Any]]:
    custom = _load_custom()
    if not custom:
        return MECH_TERMS
    return MECH_TERMS + custom


_CJK_RE = re.compile(r"[一-鿿]")


def _target_is_chinese(prefix: str) -> bool:
    p = (prefix or "").lower()
    return ("zh" in p) or ("hans" in p) or ("yue" in p) or ("cmn" in p)


def _source_is_chinese(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def apply_glossary(
    translated: str,
    source_text: str,
    source_prefix: str = "",
    target_prefix: str = "",
) -> str:
    """对翻译结果做机械术语校正。

    - 目标为中文（EN→ZH）：原文出现英文术语、译文却没出现规范中文、反而出现已知
      错误中文时，替换为规范中文。
    - 源文为中文（ZH→EN）：原文出现中文术语、译文却没出现规范英文、反而出现已知
      错误英文时，替换为规范英文。
    - 只在“明显译错”时动手，绝不凭空注入，因此对 1.3b / 3.3b 都安全且能统一译名。
    """
    if not translated:
        return translated

    to_zh = _target_is_chinese(target_prefix) or (
        not _target_is_chinese(source_prefix) and _target_is_chinese("") and _source_is_chinese(translated)
    )
    to_en = (not to_zh) and _source_is_chinese(source_text or translated)

    out = translated
    for term in _all_terms():
        en = term.get("en", "")
        zh = term.get("zh", "")
        if not en or not zh:
            continue
        if to_zh:
            if re.search(r"\b" + re.escape(en) + r"\b", source_text or "", re.IGNORECASE) and zh not in out:
                for w in term.get("wrong_zh", []) or []:
                    if w and w in out:
                        out = out.replace(w, zh, 1)
                        break
        elif to_en:
            if zh in (source_text or ""):
                if en.lower() not in out.lower():
                    for w in term.get("wrong_en", []) or []:
                        if w and re.search(r"\b" + re.escape(w) + r"\b", out, re.IGNORECASE):
                            out = re.sub(r"\b" + re.escape(w) + r"\b", en, out, count=1, flags=re.IGNORECASE)
                            break
    return out
