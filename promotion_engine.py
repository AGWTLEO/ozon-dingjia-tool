from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

import pandas as pd


PROMOTION_INPUT_COLUMNS = [
    "CPC卢布",
    "CPC人民币",
    "预计点击转化率",
    "测试点击数",
    "PPC每周预算卢布",
    "CPO模式",
    "CPO费率",
    "是否组合推广",
]

PROMOTION_OUTPUT_COLUMNS = [
    "推广前净利润",
    "推广前利润率",
    "CPC人民币",
    "PPC盈亏平衡点击数",
    "PPC盈亏平衡转化率",
    "预计每单点击数",
    "预计PPC成本",
    "PPC后净利润",
    "PPC后利润率",
    "CPO模式",
    "CPO费率",
    "CPO费用",
    "CPO后净利润",
    "CPO后利润率",
    "组合推广后净利润",
    "组合推广后利润率",
    "组合盈亏平衡点击数",
    "总广告费用占比",
    "推广建议",
    "风险提示",
]

CPO_RATE_BY_MODE = {
    "不使用CPO": 0.0,
    "全部商品CPO": 0.22,
    "单个产品CPO": 0.30,
    "PPC+CPO组合": 0.10,
}


@dataclass
class PromotionInput:
    price: float
    pre_ad_profit: float
    exchange_rate: float
    cpc_rub: float = 5.0
    cpc_cny: float = 0.0
    expected_cvr: float = 0.02
    test_clicks: float = 30.0
    weekly_budget_rub: float = 2000.0
    cpo_mode: str = "全部商品CPO"
    cpo_rate: float = 0.22
    combo_cpo_rate: float = 0.10
    use_combo: bool = False


def as_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return default
        is_percent = text.endswith("%")
        text = text.rstrip("%")
        try:
            parsed = float(text)
        except ValueError:
            return default
        return parsed / 100 if is_percent else parsed
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if pd.isna(parsed):
        return default
    return parsed


def as_rate(value: Any, default: float = 0.0) -> float:
    parsed = as_float(value, default)
    return parsed / 100 if parsed > 1 else parsed


def clean_text(value: Any, default: str = "") -> str:
    if value is None or pd.isna(value):
        return default
    return str(value).strip()


def safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    result = numerator / denominator
    return result if isfinite(result) else 0.0


def normalize_cpo_mode(value: Any) -> str:
    text = clean_text(value, "全部商品CPO")
    normalized = (
        text.replace(" ", "")
        .replace("＋", "+")
        .replace("/", "")
        .replace("订单付费", "")
    )
    aliases = {
        "不使用CPO": {"不使用CPO", "不用CPO", "无CPO", "不使用", "无", "0"},
        "全部商品CPO": {"全部商品CPO", "全部商品", "全店CPO", "全店"},
        "单个产品CPO": {"单个产品CPO", "针对单个产品CPO", "所选商品CPO", "单品CPO", "单个产品", "所选商品"},
        "PPC+CPO组合": {"PPC+CPO组合", "PPCCPO组合", "组合推广", "组合"},
        "自定义CPO": {"自定义CPO", "自定义"},
    }
    for mode, names in aliases.items():
        if normalized in names:
            return mode
    return text


def cpo_rate_for_mode(mode: str, custom_rate: float = 0.0) -> float:
    mode = normalize_cpo_mode(mode)
    if mode == "自定义CPO":
        return custom_rate
    return CPO_RATE_BY_MODE.get(mode, 0.0)


def parse_bool(value: Any) -> bool:
    text = clean_text(value).lower()
    return text in {"1", "true", "yes", "y", "是", "开启", "组合", "ppc+cpo组合"}


def round2(value: float) -> float:
    return round(value, 2)


def round4(value: float) -> float:
    return round(value, 4)


def get_active_price(pricing_result: dict[str, Any]) -> float:
    for key in ["测算售价", "当前售价", "建议售价"]:
        value = as_float(pricing_result.get(key), 0)
        if value > 0:
            return value
    return 0.0


def get_base_profit(pricing_result: dict[str, Any]) -> dict[str, float]:
    price = get_active_price(pricing_result)
    ad_fee = as_float(pricing_result.get("广告费"), 0)
    total_cost = as_float(pricing_result.get("总成本"), 0)
    non_ad_total_cost = max(total_cost - ad_fee, 0)
    pre_ad_profit = price - non_ad_total_cost
    pre_ad_profit_rate = safe_div(pre_ad_profit, price)
    return {
        "售价": price,
        "非广告总成本": non_ad_total_cost,
        "推广前净利润": pre_ad_profit,
        "推广前利润率": pre_ad_profit_rate,
        "主定价广告费": ad_fee,
    }


def ppc_judgement(ppc_after_profit: float, break_even_clicks: float) -> list[str]:
    messages: list[str] = []
    if ppc_after_profit > 0:
        messages.append("PPC 后仍有利润")
    elif ppc_after_profit == 0:
        messages.append("PPC 接近盈亏平衡")
    else:
        messages.append("PPC 后亏损，不建议用当前 CPC 推广")

    if break_even_clicks < 10:
        messages.append("可承受点击数太少，PPC 风险高")
    elif break_even_clicks <= 30:
        messages.append("可以小预算测试，但要严格控制点击成本")
    else:
        messages.append("PPC 承受能力较好，可以测试")
    return messages


def cpo_judgement(mode: str, cpo_rate: float, pre_ad_profit_rate: float, cpo_after_profit: float, cpo_after_rate: float) -> list[str]:
    messages: list[str] = []
    if cpo_after_profit > 0:
        messages.append("CPO 后仍有利润")
    elif cpo_after_profit == 0:
        messages.append("CPO 接近盈亏平衡")
    else:
        messages.append("CPO 后亏损，不建议用当前费率")

    if cpo_rate >= pre_ad_profit_rate:
        messages.append("CPO 费率已经吃掉基础利润，开启后利润很低或亏损")
    if cpo_after_rate < 0.10:
        messages.append("CPO 后利润偏低，谨慎开启")
    if mode == "全部商品CPO" and cpo_after_profit > 0 and cpo_after_rate < 0.10:
        messages.append("全部商品 CPO 后仍有利润，但利润率偏低，谨慎开启。")
    if mode == "单个产品CPO" and cpo_after_profit <= 0:
        messages.append("针对单个产品 CPO 后无利润或亏损，不建议单独开启。")
    if mode == "PPC+CPO组合":
        messages.append("PPC + CPO 组合：10%，仅用于组合推广预估。")
    return messages


def combo_judgement(combo_after_profit: float, combo_break_even_clicks: float, total_ad_rate: float, cpo_margin: float) -> list[str]:
    messages: list[str] = []
    if cpo_margin <= 0:
        messages.append("仅 CPO 已经吃掉利润，不能再叠加 PPC。")
    elif combo_after_profit > 0:
        messages.append("PPC + CPO 组合后仍有利润")
    else:
        messages.append("PPC + CPO 组合后亏损，不建议当前出价")

    if combo_break_even_clicks < 10:
        messages.append("组合推广风险高，CPC 或 CPO 需要降低")
    if total_ad_rate > 0.18:
        messages.append("广告费用占比偏高，建议优化商品卡、价格或降低出价")
    else:
        messages.append("广告费用占比在可控范围内")
    return messages


def build_recommendations(
    ppc_break_even_clicks: float,
    cpo_22_after_profit: float,
    cpo_22_after_rate: float,
    cpo_30_after_profit: float,
    cpo_30_after_rate: float,
    combo_after_profit: float,
    combo_total_ad_rate: float,
    max_cpc_cny: float,
    max_cpc_rub: float,
    estimated_clicks_per_order: float,
    expected_cvr: float,
    cpc_cny: float,
) -> tuple[str, str]:
    advice: list[str] = []
    risks: list[str] = []

    if ppc_break_even_clicks < 10:
        advice.append("该产品可承受点击数太少，不建议直接开 PPC。请先提高售价、降低成本或优化利润。")
        risks.append("PPC 盈亏平衡点击数低于 10。")
    elif ppc_break_even_clicks <= 30:
        advice.append("可以小预算测试 PPC，但要控制 CPC，并观察加购和点击转化。")
    else:
        advice.append("该产品 PPC 承受能力较好，可以进行 14 天测试。")

    if cpo_22_after_profit > 0 and cpo_22_after_rate > 0.10:
        advice.append("可以考虑开启全部商品 CPO。")
    elif cpo_22_after_rate < 0.10:
        advice.append("CPO 后利润较低，谨慎开启。")

    if cpo_30_after_profit > 0 and cpo_30_after_rate > 0.10:
        advice.append("可以考虑开启单个产品 CPO。")
    elif cpo_30_after_rate < 0.10:
        advice.append("针对单个产品 CPO 后利润较低，谨慎开启。")

    if combo_after_profit > 0 and combo_total_ad_rate <= 0.18:
        advice.append("可以测试 PPC + CPO 组合推广。")
    else:
        advice.append("不建议同时开启 PPC + CPO。")

    if expected_cvr <= 0:
        risks.append("未填写有效点击转化率，无法判断预计每单点击数。")
    if cpc_cny <= 0:
        risks.append("CPC 未填写或为 0，PPC 测算结果仅供占位。")
    if estimated_clicks_per_order > ppc_break_even_clicks > 0:
        risks.append("按当前转化率，预计出单点击数超过盈亏平衡点击数。")

    advice.append(f"当前 CPC 最高可承受约 ¥{max_cpc_cny:.2f} / {max_cpc_rub:.2f}₽。")
    advice.append(f"预计 {ppc_break_even_clicks:.1f} 次点击内出单不亏；超过该点击数仍不出单，建议暂停观察。")
    advice.append("如果点击和加购多但订单少，优先优化价格、图片、描述、评价和物流时效。")
    return "；".join(dict.fromkeys(advice)), "；".join(dict.fromkeys(risks))


def calculate_promotion(input_data: PromotionInput) -> dict[str, Any]:
    price = input_data.price
    pre_ad_profit = input_data.pre_ad_profit
    exchange_rate = input_data.exchange_rate
    cpc_cny = input_data.cpc_cny if input_data.cpc_cny > 0 else safe_div(input_data.cpc_rub, exchange_rate)
    cpc_rub = input_data.cpc_rub if input_data.cpc_rub > 0 else cpc_cny * exchange_rate

    ppc_test_cost = input_data.test_clicks * cpc_cny
    ppc_test_after_profit = pre_ad_profit - ppc_test_cost
    break_even_clicks = safe_div(pre_ad_profit, cpc_cny) if pre_ad_profit > 0 and cpc_cny > 0 else 0
    break_even_cvr = safe_div(cpc_cny, pre_ad_profit) if pre_ad_profit > 0 and cpc_cny > 0 else 0
    estimated_clicks_per_order = safe_div(1, input_data.expected_cvr) if input_data.expected_cvr > 0 else 0
    estimated_ppc_cost = estimated_clicks_per_order * cpc_cny
    ppc_after_profit = pre_ad_profit - estimated_ppc_cost
    ppc_after_rate = safe_div(ppc_after_profit, price)
    ppc_ad_rate = safe_div(estimated_ppc_cost, price)
    weekly_budget_cny = safe_div(input_data.weekly_budget_rub, exchange_rate)
    budget_clicks = safe_div(weekly_budget_cny, cpc_cny)
    budget_enough = budget_clicks >= input_data.test_clicks if input_data.test_clicks > 0 else False

    cpo_mode = normalize_cpo_mode(input_data.cpo_mode)
    cpo_rate = cpo_rate_for_mode(cpo_mode, input_data.cpo_rate)
    cpo_fee = price * cpo_rate
    cpo_after_profit = pre_ad_profit - cpo_fee
    cpo_after_rate = safe_div(cpo_after_profit, price)

    combo_cpo_rate = input_data.combo_cpo_rate
    combo_cpo_fee = price * combo_cpo_rate
    combo_margin = pre_ad_profit - combo_cpo_fee
    combo_break_even_clicks = safe_div(combo_margin, cpc_cny) if combo_margin > 0 and cpc_cny > 0 else 0
    combo_break_even_cvr = safe_div(1, combo_break_even_clicks) if combo_break_even_clicks > 0 else 0
    combo_expected_ppc_cost = estimated_ppc_cost
    combo_total_cost = combo_expected_ppc_cost + combo_cpo_fee
    combo_after_profit = pre_ad_profit - combo_total_cost
    combo_after_rate = safe_div(combo_after_profit, price)
    combo_total_ad_rate = safe_div(combo_total_cost, price)

    cpo_22_fee = price * 0.22
    cpo_22_after_profit = pre_ad_profit - cpo_22_fee
    cpo_22_after_rate = safe_div(cpo_22_after_profit, price)
    cpo_30_fee = price * 0.30
    cpo_30_after_profit = pre_ad_profit - cpo_30_fee
    cpo_30_after_rate = safe_div(cpo_30_after_profit, price)

    max_cpc_cny = max(pre_ad_profit * input_data.expected_cvr, 0) if input_data.expected_cvr > 0 else 0
    max_cpc_rub = max_cpc_cny * exchange_rate

    advice, risk = build_recommendations(
        ppc_break_even_clicks=break_even_clicks,
        cpo_22_after_profit=cpo_22_after_profit,
        cpo_22_after_rate=cpo_22_after_rate,
        cpo_30_after_profit=cpo_30_after_profit,
        cpo_30_after_rate=cpo_30_after_rate,
        combo_after_profit=combo_after_profit,
        combo_total_ad_rate=combo_total_ad_rate,
        max_cpc_cny=max_cpc_cny,
        max_cpc_rub=max_cpc_rub,
        estimated_clicks_per_order=estimated_clicks_per_order,
        expected_cvr=input_data.expected_cvr,
        cpc_cny=cpc_cny,
    )

    return {
        "售价": round2(price),
        "推广前净利润": round2(pre_ad_profit),
        "推广前利润率": round4(safe_div(pre_ad_profit, price)),
        "CPC卢布": round4(cpc_rub),
        "CPC人民币": round4(cpc_cny),
        "测试点击数": round2(input_data.test_clicks),
        "PPC测试点击费用": round2(ppc_test_cost),
        "PPC测试点击后利润": round2(ppc_test_after_profit),
        "PPC盈亏平衡点击数": round2(break_even_clicks),
        "PPC盈亏平衡转化率": round4(break_even_cvr),
        "预计点击转化率": round4(input_data.expected_cvr),
        "预计每单点击数": round2(estimated_clicks_per_order),
        "预计PPC成本": round2(estimated_ppc_cost),
        "PPC后净利润": round2(ppc_after_profit),
        "PPC后利润率": round4(ppc_after_rate),
        "预计广告费用占比": round4(ppc_ad_rate),
        "每周预算卢布": round2(input_data.weekly_budget_rub),
        "每周预算人民币": round2(weekly_budget_cny),
        "每周预算可购买点击数": round2(budget_clicks),
        "预算是否足够测试": "是" if budget_enough else "否",
        "PPC判断": "；".join(ppc_judgement(ppc_after_profit, break_even_clicks)),
        "CPO模式": cpo_mode,
        "CPO费率": round4(cpo_rate),
        "CPO费用": round2(cpo_fee),
        "CPO后净利润": round2(cpo_after_profit),
        "CPO后利润率": round4(cpo_after_rate),
        "CPO广告费用占比": round4(safe_div(cpo_fee, price)),
        "CPO判断": "；".join(cpo_judgement(cpo_mode, cpo_rate, safe_div(pre_ad_profit, price), cpo_after_profit, cpo_after_rate)),
        "全部商品CPO22%后净利润": round2(cpo_22_after_profit),
        "全部商品CPO22%后利润率": round4(cpo_22_after_rate),
        "单个产品CPO30%后净利润": round2(cpo_30_after_profit),
        "单个产品CPO30%后利润率": round4(cpo_30_after_rate),
        "组合CPO费率": round4(combo_cpo_rate),
        "组合CPO费用": round2(combo_cpo_fee),
        "组合盈亏平衡点击数": round2(combo_break_even_clicks),
        "组合盈亏平衡转化率": round4(combo_break_even_cvr),
        "组合预计PPC成本": round2(combo_expected_ppc_cost),
        "预计总推广成本": round2(combo_total_cost),
        "组合推广后净利润": round2(combo_after_profit),
        "组合推广后利润率": round4(combo_after_rate),
        "总广告费用占比": round4(combo_total_ad_rate),
        "组合判断": "；".join(combo_judgement(combo_after_profit, combo_break_even_clicks, combo_total_ad_rate, combo_margin)),
        "当前最高可承受CPC人民币": round4(max_cpc_cny),
        "当前最高可承受CPC卢布": round4(max_cpc_rub),
        "推广建议": advice,
        "风险提示": risk,
        "PPC说明": "如果没有出单，所有 PPC 点击费用都是亏损；这里的盈亏平衡点击数表示一单利润最多能承受多少次点击。",
    }


def promotion_input_from_row(row: dict[str, Any], pricing_result: dict[str, Any]) -> PromotionInput:
    base = get_base_profit(pricing_result)
    exchange_rate = as_float(pricing_result.get("使用汇率"), 12.5)
    cpo_mode = normalize_cpo_mode(row.get("CPO模式"))
    custom_cpo_rate = as_rate(row.get("CPO费率"), cpo_rate_for_mode(cpo_mode))
    is_combo = parse_bool(row.get("是否组合推广")) or cpo_mode == "PPC+CPO组合"
    combo_rate = custom_cpo_rate if cpo_mode == "PPC+CPO组合" and custom_cpo_rate > 0 else 0.10
    return PromotionInput(
        price=base["售价"],
        pre_ad_profit=base["推广前净利润"],
        exchange_rate=exchange_rate,
        cpc_rub=as_float(row.get("CPC卢布"), 5),
        cpc_cny=as_float(row.get("CPC人民币"), 0),
        expected_cvr=as_rate(row.get("预计点击转化率"), 0.02),
        test_clicks=as_float(row.get("测试点击数"), 30),
        weekly_budget_rub=as_float(row.get("PPC每周预算卢布"), 2000),
        cpo_mode=cpo_mode,
        cpo_rate=custom_cpo_rate,
        combo_cpo_rate=combo_rate,
        use_combo=is_combo,
    )


def calculate_batch_promotions(input_df: pd.DataFrame, pricing_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    normalized = input_df.copy()
    for column in PROMOTION_INPUT_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = None

    for position, (_, row) in enumerate(normalized.iterrows()):
        pricing_result = pricing_df.iloc[position].to_dict()
        promo_input = promotion_input_from_row(row.to_dict(), pricing_result)
        promo = calculate_promotion(promo_input)
        rows.append({column: promo.get(column, "") for column in PROMOTION_OUTPUT_COLUMNS})
    return pd.DataFrame(rows)
