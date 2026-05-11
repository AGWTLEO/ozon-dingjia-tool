from __future__ import annotations

from dataclasses import dataclass
from math import inf, isfinite
from typing import Any

import pandas as pd


INPUT_COLUMNS = [
    "SKU",
    "产品名称",
    "所属类目",
    "采购成本",
    "境内段运费",
    "包装费",
    "其他费用",
    "重量g",
    "长cm",
    "宽cm",
    "高cm",
    "货值区间",
    "物流时效",
    "当前售价人民币",
    "目标利润率",
    "汇率",
    "广告费比例",
    "提现手续费费率",
    "退货率",
    "税费比例",
    "CPC卢布",
    "CPC人民币",
    "预计点击转化率",
    "测试点击数",
    "PPC每周预算卢布",
    "CPO模式",
    "CPO费率",
    "是否组合推广",
]

OUTPUT_COLUMNS = [
    "SKU",
    "产品名称",
    "所属类目",
    "物流标准",
    "支持时效",
    "选择时效",
    "时效是否支持",
    "匹配渠道名称",
    "匹配资费标准",
    "每克单价",
    "每票固定费",
    "货值区间",
    "货值区间人民币换算",
    "三边和",
    "长边",
    "实际重量g",
    "实际重量kg",
    "体积重量kg",
    "计费重量g",
    "计费重量kg",
    "跨境物流费",
    "使用汇率",
    "汇率来源",
    "汇率更新时间",
    "汇率模式",
    "佣金率",
    "平台佣金",
    "广告费",
    "提现手续费",
    "退货损失",
    "税费",
    "总成本",
    "当前售价",
    "建议售价",
    "净利润",
    "利润率",
    "结论",
    "备注",
]

DEFAULT_LOGISTICS_SPEED = "10-15天"
LOGISTICS_SPEED_ORDER = ["5-10天", "10-15天", "15-25天"]

VALUE_BANDS = {
    "1-1500₽": {
        "aliases": {"1-1500", "1-1500₽", "1-1500руб"},
        "rub_min": 1.0,
        "rub_max": 1500.0,
    },
    "1501-7000₽": {
        "aliases": {"1501-7000", "1501-7000₽", "1501-7000руб"},
        "rub_min": 1501.0,
        "rub_max": 7000.0,
    },
    "7001-250000₽": {
        "aliases": {"7001-250000", "7001-250000₽", "7001-250000руб"},
        "rub_min": 7001.0,
        "rub_max": 250000.0,
    },
}


@dataclass
class PricingInput:
    sku: str = ""
    product_name: str = ""
    category: str = "建筑和装修"
    purchase_cost: float = 0.0
    domestic_shipping: float = 3.0
    packaging_fee: float = 0.0
    other_fee: float = 0.0
    weight_g: float = 0.0
    length_cm: float = 0.0
    width_cm: float = 0.0
    height_cm: float = 0.0
    value_band: str = ""
    logistics_speed: str = DEFAULT_LOGISTICS_SPEED
    current_price_cny: float = 0.0
    target_profit_rate: float = 0.2
    exchange_rate: float = 12.5
    exchange_source: str = "手动汇率"
    exchange_updated_at: str = ""
    exchange_mode: str = "手动汇率"
    ad_rate: float = 0.0
    withdrawal_rate: float = 0.01
    return_rate: float = 0.0
    tax_rate: float = 0.0


def as_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return default
        is_percent = value.endswith("%")
        value = value.rstrip("%").replace(",", "")
        try:
            parsed = float(value)
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


def normalize_price_upper(value: Any) -> float:
    parsed = as_float(value, inf)
    return parsed if isfinite(parsed) else inf


def normalize_value_band(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    normalized = (
        text.replace(" ", "")
        .replace("－", "-")
        .replace("—", "-")
        .replace("~", "-")
        .replace("～", "-")
        .replace("₽", "")
        .replace("руб.", "")
        .replace("руб", "")
    )
    for band, meta in VALUE_BANDS.items():
        aliases = {alias.replace("₽", "").replace("руб", "") for alias in meta["aliases"]}
        if normalized in aliases or normalized == band.replace("₽", ""):
            return band
    return text


def normalize_logistics_speed(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    text = text.replace(" ", "").replace("－", "-").replace("—", "-")
    for speed in LOGISTICS_SPEED_ORDER:
        if text == speed:
            return speed
    return text


def format_money(value: float) -> str:
    formatted = f"{value:.2f}".rstrip("0").rstrip(".")
    return formatted or "0"


def value_band_cny_range(value_band: str, exchange_rate: float) -> str:
    value_band = normalize_value_band(value_band)
    meta = VALUE_BANDS.get(value_band)
    if not meta or exchange_rate <= 0:
        return ""
    lower = meta["rub_min"] / exchange_rate
    upper = meta["rub_max"] / exchange_rate
    return f"约 ¥{format_money(lower)}-¥{format_money(upper)}，按当前汇率"


def value_band_options(exchange_rate: float) -> dict[str, str]:
    return {
        band: f"{band}（{value_band_cny_range(band, exchange_rate)}）"
        for band in VALUE_BANDS
    }


def fits_max_dimensions(
    length_cm: float,
    width_cm: float,
    height_cm: float,
    row: pd.Series,
) -> bool:
    limits = [
        as_float(row.get("最大尺寸长cm"), 0),
        as_float(row.get("最大尺寸宽cm"), 0),
        as_float(row.get("最大尺寸高cm"), 0),
    ]
    if not all(limit > 0 for limit in limits):
        return True
    return all(dim <= limit for dim, limit in zip(sorted([length_cm, width_cm, height_cm]), sorted(limits)))


def match_logistics_standard(
    item: PricingInput,
    logistics_standards: pd.DataFrame,
) -> dict[str, Any]:
    dims = [item.length_cm, item.width_cm, item.height_cm]
    side_sum = sum(dims)
    longest_side = max(dims) if dims else 0.0
    actual_weight_kg = item.weight_g / 1000 if item.weight_g else 0.0
    volume_weight_kg = (
        item.length_cm * item.width_cm * item.height_cm / 12000
        if item.length_cm and item.width_cm and item.height_cm
        else 0.0
    )
    value_band = normalize_value_band(item.value_band)

    matches: list[dict[str, Any]] = []
    for _, row in logistics_standards.iterrows():
        min_weight = as_float(row.get("重量下限g"), 0)
        max_weight = as_float(row.get("重量上限g"), inf)
        max_side_sum = as_float(row.get("三边和上限cm"), inf)
        max_longest_side = as_float(row.get("长边上限cm"), inf)
        row_value_band = normalize_value_band(row.get("货值区间"))
        max_volume_weight = as_float(row.get("体积重上限kg"), inf)

        if not (min_weight <= item.weight_g <= max_weight):
            continue
        if not (side_sum <= max_side_sum and longest_side <= max_longest_side):
            continue
        if not value_band or row_value_band != value_band:
            continue
        if volume_weight_kg > max_volume_weight:
            continue
        if not fits_max_dimensions(item.length_cm, item.width_cm, item.height_cm, row):
            continue
        matches.append(row.to_dict())

    if not matches:
        return {
            "物流标准": "",
            "三边和": side_sum,
            "长边": longest_side,
            "实际重量kg": actual_weight_kg,
            "体积重量kg": volume_weight_kg,
            "计费重量kg": actual_weight_kg,
            "计费方式": "",
            "货值区间": value_band,
            "matched": False,
        }

    match = matches[0]
    billing_method = clean_text(match.get("计费方式"), "实际重量")
    use_volume = any(key in billing_method.lower() for key in ["max", "volume"])
    use_volume = use_volume or "体积" in billing_method or "较大" in billing_method
    billable_weight_kg = max(actual_weight_kg, volume_weight_kg) if use_volume else actual_weight_kg

    return {
        "物流标准": clean_text(match.get("物流标准")),
        "三边和": side_sum,
        "长边": longest_side,
        "实际重量kg": actual_weight_kg,
        "体积重量kg": volume_weight_kg,
        "计费重量kg": billable_weight_kg,
        "计费方式": billing_method,
        "货值区间": value_band,
        "matched": True,
    }


def supported_logistics_speeds(logistics_standard: str, logistics_prices: pd.DataFrame) -> list[str]:
    if not logistics_standard or "物流标准" not in logistics_prices.columns:
        return []
    prices = logistics_prices.copy()
    prices["物流标准"] = prices["物流标准"].astype(str).str.strip()
    if "物流时效" not in prices.columns:
        return []
    speeds = [
        normalize_logistics_speed(value)
        for value in prices.loc[prices["物流标准"] == logistics_standard, "物流时效"].dropna().unique()
    ]
    speed_set = {speed for speed in speeds if speed}
    ordered = [speed for speed in LOGISTICS_SPEED_ORDER if speed in speed_set]
    ordered.extend(sorted(speed_set - set(ordered)))
    return ordered


def match_logistics_price(
    logistics_standard: str,
    logistics_speed: str,
    billable_weight_g: float,
    logistics_prices: pd.DataFrame,
) -> tuple[dict[str, Any], bool]:
    empty = {
        "跨境物流费": 0.0,
        "匹配渠道名称": "",
        "匹配资费标准": "",
        "每克单价": 0.0,
        "每票固定费": 0.0,
    }
    if not logistics_standard:
        return empty, False

    prices = logistics_prices.copy()
    prices["物流标准"] = prices["物流标准"].astype(str).str.strip()
    if "物流时效" not in prices.columns:
        prices["物流时效"] = ""
    prices["物流时效"] = prices["物流时效"].astype(str).map(normalize_logistics_speed)
    logistics_speed = normalize_logistics_speed(logistics_speed)
    candidates = prices[
        (prices["物流标准"] == logistics_standard)
        & (prices["物流时效"] == logistics_speed)
    ]

    if candidates.empty:
        return empty, False

    row = candidates.iloc[0]
    rate_per_g = as_float(row.get("每克单价"), 0)
    fixed_fee = as_float(row.get("每票固定费"), 0)
    fee = billable_weight_g * rate_per_g + fixed_fee
    return {
        "跨境物流费": round(fee, 2),
        "匹配渠道名称": clean_text(row.get("渠道名称")),
        "匹配资费标准": clean_text(row.get("资费标准")),
        "每克单价": rate_per_g,
        "每票固定费": fixed_fee,
    }, True


def invalid_speed_message(logistics_standard: str, logistics_speed: str, supported: list[str]) -> str:
    if not logistics_standard or not logistics_speed:
        return ""
    if logistics_speed == "5-10天" and logistics_standard in {"Big", "Premium Big"}:
        return f"当前物流标准 {logistics_standard} 不支持 5-10天，请选择 10-15天或 15-25天。"
    if supported:
        return f"当前物流标准 {logistics_standard} 不支持 {logistics_speed}，请改为 {'或'.join(supported)}。"
    return f"当前物流标准 {logistics_standard} 未配置 {logistics_speed} 时效，请检查物流价格表。"


def preview_logistics(
    item: PricingInput,
    logistics_standards: pd.DataFrame,
    logistics_prices: pd.DataFrame,
) -> dict[str, Any]:
    logistics = match_logistics_standard(item, logistics_standards)
    speeds = supported_logistics_speeds(logistics["物流标准"], logistics_prices)
    return {
        **logistics,
        "支持时效": speeds,
        "支持时效文本": "、".join(speeds),
    }


def match_commission_rate(
    category: str,
    price_cny: float,
    exchange_rate: float,
    commission_rules: pd.DataFrame,
) -> tuple[float, bool]:
    price_rub = price_cny * exchange_rate
    category = category.strip()
    candidates = commission_rules[
        commission_rules["所属类目"].astype(str).str.strip() == category
    ]

    for _, row in candidates.iterrows():
        lower = as_float(row.get("售价下限卢布"), 0)
        upper = normalize_price_upper(row.get("售价上限卢布"))
        if lower <= price_rub <= upper:
            return as_rate(row.get("佣金率"), 0), True
    return 0.0, False


def variable_rate_sum(item: PricingInput, commission_rate: float) -> float:
    return (
        commission_rate
        + item.ad_rate
        + item.withdrawal_rate
        + item.return_rate
        + item.tax_rate
    )


def solve_price_for_profit(
    fixed_cost: float,
    item: PricingInput,
    commission_rules: pd.DataFrame,
    target_profit_rate: float,
    max_iterations: int = 50,
) -> dict[str, Any]:
    notes: list[str] = []
    if item.exchange_rate <= 0:
        return {
            "price": 0.0,
            "commission_rate": 0.0,
            "matched": False,
            "iterations": 0,
            "notes": ["汇率必须大于 0，无法反推售价。"],
        }

    base_rate = item.ad_rate + item.withdrawal_rate + item.return_rate + item.tax_rate
    denominator = 1 - base_rate - target_profit_rate
    if denominator <= 0:
        return {
            "price": 0.0,
            "commission_rate": 0.0,
            "matched": False,
            "iterations": 0,
            "notes": ["目标利润率和比例费用合计过高，无法反推售价。"],
        }

    price = fixed_cost / denominator if denominator else 0.0
    commission_rate = 0.0
    matched = False
    iterations = 0

    for i in range(max_iterations):
        iterations = i + 1
        commission_rate, matched = match_commission_rate(
            item.category, price, item.exchange_rate, commission_rules
        )
        denominator = 1 - variable_rate_sum(item, commission_rate) - target_profit_rate
        if denominator <= 0:
            notes.append("佣金率、比例费用和目标利润率合计过高，无法反推售价。")
            return {
                "price": 0.0,
                "commission_rate": commission_rate,
                "matched": matched,
                "iterations": iterations,
                "notes": notes,
            }
        new_price = fixed_cost / denominator
        if abs(new_price - price) < 0.01:
            price = new_price
            break
        price = new_price

    if not matched:
        notes.append("未匹配到佣金率，请检查类目佣金率表。")

    return {
        "price": round(price, 2),
        "commission_rate": commission_rate,
        "matched": matched,
        "iterations": iterations,
        "notes": notes,
    }


def conclusion_from_profit_rate(profit_rate: float) -> str:
    if profit_rate >= 0.2:
        return "可以上架"
    if profit_rate >= 0.1:
        return "谨慎上架"
    if profit_rate >= 0:
        return "利润偏低，不建议推广"
    return "亏损，不建议上架"


def build_notes(item: PricingInput, extra_notes: list[str]) -> str:
    notes = [note for note in extra_notes if note]
    if item.ad_rate == 0:
        notes.append("当前未预留广告费，正式推广前建议重新测算。")
    if item.tax_rate == 0:
        notes.append("当前未计入税费，找到税率表后需要补充测算。")
    return "；".join(dict.fromkeys(notes))


def calculate_pricing(
    item: PricingInput,
    commission_rules: pd.DataFrame,
    logistics_standards: pd.DataFrame,
    logistics_prices: pd.DataFrame,
) -> dict[str, Any]:
    notes: list[str] = []

    logistics = match_logistics_standard(item, logistics_standards)
    selected_speed = normalize_logistics_speed(item.logistics_speed)
    if not selected_speed:
        selected_speed = DEFAULT_LOGISTICS_SPEED
        notes.append("未填写物流时效，默认使用 10-15天。")

    supported_speeds = supported_logistics_speeds(logistics["物流标准"], logistics_prices)
    speed_supported = bool(selected_speed and selected_speed in supported_speeds)
    billable_weight_g = logistics["计费重量kg"] * 1000

    price_detail, price_matched = match_logistics_price(
        logistics["物流标准"], selected_speed, billable_weight_g, logistics_prices
    )
    logistics_fee = price_detail["跨境物流费"] if speed_supported else 0.0

    if not logistics["matched"]:
        if not normalize_value_band(item.value_band):
            notes.append("未选择货值区间，无法准确匹配物流标准。")
        else:
            notes.append("未匹配到物流标准，请检查重量、尺寸和货值区间。")
    if logistics["matched"] and not speed_supported:
        notes.append(invalid_speed_message(logistics["物流标准"], selected_speed, supported_speeds))
        notes.append("未匹配有效物流费，跨境物流费按 0 暂存，请修正后再看利润。")
    elif logistics["matched"] and not price_matched:
        notes.append("未匹配到物流价格，请检查物流价格表。")

    fixed_cost = (
        item.purchase_cost
        + item.domestic_shipping
        + item.packaging_fee
        + logistics_fee
        + item.other_fee
    )

    suggested = solve_price_for_profit(
        fixed_cost=fixed_cost,
        item=item,
        commission_rules=commission_rules,
        target_profit_rate=item.target_profit_rate,
    )
    notes.extend(suggested["notes"])
    suggested_price = suggested["price"]

    break_even = solve_price_for_profit(
        fixed_cost=fixed_cost,
        item=item,
        commission_rules=commission_rules,
        target_profit_rate=0.0,
    )
    notes.extend(break_even["notes"])
    break_even_price = break_even["price"]

    calculation_price = item.current_price_cny if item.current_price_cny > 0 else suggested_price
    if calculation_price <= 0:
        commission_rate, commission_matched = 0.0, False
    else:
        commission_rate, commission_matched = match_commission_rate(
            item.category,
            calculation_price,
            item.exchange_rate,
            commission_rules,
        )
    if calculation_price > 0 and not commission_matched:
        notes.append("未匹配到佣金率，请检查类目佣金率表。")

    platform_commission = calculation_price * commission_rate
    ad_fee = calculation_price * item.ad_rate
    withdrawal_fee = calculation_price * item.withdrawal_rate
    return_loss = calculation_price * item.return_rate
    tax_fee = calculation_price * item.tax_rate

    total_cost = (
        fixed_cost
        + platform_commission
        + ad_fee
        + withdrawal_fee
        + return_loss
        + tax_fee
    )
    net_profit = calculation_price - total_cost
    profit_rate = net_profit / calculation_price if calculation_price else 0.0
    conclusion = conclusion_from_profit_rate(profit_rate)
    if logistics["matched"] and not speed_supported:
        conclusion = "物流时效无效，需修改后再判断"
    reached_target = profit_rate >= item.target_profit_rate

    notes_text = build_notes(item, notes)

    return {
        "SKU": item.sku,
        "产品名称": item.product_name,
        "所属类目": item.category,
        "物流标准": logistics["物流标准"],
        "支持时效": "、".join(supported_speeds),
        "选择时效": selected_speed,
        "时效是否支持": "是" if speed_supported else "否",
        "匹配渠道名称": price_detail["匹配渠道名称"] if speed_supported else "",
        "匹配资费标准": price_detail["匹配资费标准"] if speed_supported else "",
        "每克单价": round(price_detail["每克单价"], 5) if speed_supported else 0,
        "每票固定费": round(price_detail["每票固定费"], 2) if speed_supported else 0,
        "货值区间": normalize_value_band(item.value_band),
        "货值区间人民币换算": value_band_cny_range(item.value_band, item.exchange_rate),
        "三边和": round(logistics["三边和"], 2),
        "长边": round(logistics["长边"], 2),
        "实际重量g": round(item.weight_g, 2),
        "实际重量kg": round(logistics["实际重量kg"], 4),
        "体积重量kg": round(logistics["体积重量kg"], 4),
        "计费重量g": round(billable_weight_g, 2),
        "计费重量kg": round(logistics["计费重量kg"], 4),
        "跨境物流费": round(logistics_fee, 2),
        "使用汇率": round(item.exchange_rate, 4),
        "汇率来源": item.exchange_source,
        "汇率更新时间": item.exchange_updated_at,
        "汇率模式": item.exchange_mode,
        "采购成本": round(item.purchase_cost, 2),
        "境内段运费": round(item.domestic_shipping, 2),
        "包装费": round(item.packaging_fee, 2),
        "其他费用": round(item.other_fee, 2),
        "固定成本": round(fixed_cost, 2),
        "佣金率": round(commission_rate, 4),
        "平台佣金": round(platform_commission, 2),
        "广告费比例": round(item.ad_rate, 4),
        "广告费": round(ad_fee, 2),
        "提现手续费费率": round(item.withdrawal_rate, 4),
        "提现手续费": round(withdrawal_fee, 2),
        "退货率": round(item.return_rate, 4),
        "退货损失": round(return_loss, 2),
        "税费比例": round(item.tax_rate, 4),
        "税费": round(tax_fee, 2),
        "总成本": round(total_cost, 2),
        "当前售价": round(item.current_price_cny, 2) if item.current_price_cny > 0 else "",
        "测算售价": round(calculation_price, 2),
        "建议售价": round(suggested_price, 2),
        "净利润": round(net_profit, 2),
        "利润率": round(profit_rate, 4),
        "保本售价": round(break_even_price, 2),
        "是否达到目标利润率": "是" if reached_target else "否",
        "是否适合上架": conclusion,
        "结论": conclusion,
        "备注": notes_text,
    }


def item_from_mapping(row: dict[str, Any], defaults: dict[str, Any]) -> PricingInput:
    row_exchange_rate = as_float(row.get("汇率"), 0)
    if row_exchange_rate > 0:
        exchange_rate = row_exchange_rate
        exchange_source = "Excel手动汇率"
        exchange_updated_at = ""
        exchange_mode = "Excel填写汇率"
    else:
        exchange_rate = as_float(
            defaults.get("current_exchange_rate"),
            as_float(defaults.get("default_exchange_rate"), 12.5),
        )
        exchange_source = clean_text(defaults.get("exchange_source"), "规则设置汇率")
        exchange_updated_at = clean_text(defaults.get("exchange_updated_at"))
        exchange_mode = clean_text(defaults.get("exchange_mode"), "工具当前汇率")

    return PricingInput(
        sku=clean_text(row.get("SKU")),
        product_name=clean_text(row.get("产品名称")),
        category=clean_text(row.get("所属类目"), "建筑和装修"),
        purchase_cost=as_float(row.get("采购成本")),
        domestic_shipping=as_float(
            row.get("境内段运费"), as_float(defaults.get("default_domestic_shipping"), 3)
        ),
        packaging_fee=as_float(row.get("包装费")),
        other_fee=as_float(row.get("其他费用"), as_float(defaults.get("default_other_fee"), 0)),
        weight_g=as_float(row.get("重量g")),
        length_cm=as_float(row.get("长cm")),
        width_cm=as_float(row.get("宽cm")),
        height_cm=as_float(row.get("高cm")),
        value_band=normalize_value_band(row.get("货值区间")),
        logistics_speed=normalize_logistics_speed(row.get("物流时效")),
        current_price_cny=as_float(row.get("当前售价人民币")),
        target_profit_rate=as_rate(row.get("目标利润率"), 0.2),
        exchange_rate=exchange_rate,
        exchange_source=exchange_source,
        exchange_updated_at=exchange_updated_at,
        exchange_mode=exchange_mode,
        ad_rate=as_rate(row.get("广告费比例"), as_rate(defaults.get("default_ad_rate"), 0)),
        withdrawal_rate=as_rate(
            row.get("提现手续费费率"), as_rate(defaults.get("default_withdrawal_rate"), 0.01)
        ),
        return_rate=as_rate(row.get("退货率"), as_rate(defaults.get("default_return_rate"), 0)),
        tax_rate=as_rate(row.get("税费比例"), as_rate(defaults.get("default_tax_rate"), 0)),
    )


def calculate_batch(
    input_df: pd.DataFrame,
    defaults: dict[str, Any],
    commission_rules: pd.DataFrame,
    logistics_standards: pd.DataFrame,
    logistics_prices: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    normalized = input_df.copy()
    for column in INPUT_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = None

    for _, row in normalized.iterrows():
        item = item_from_mapping(row.to_dict(), defaults)
        rows.append(
            calculate_pricing(
                item,
                commission_rules=commission_rules,
                logistics_standards=logistics_standards,
                logistics_prices=logistics_prices,
            )
        )

    output = pd.DataFrame(rows)
    for column in OUTPUT_COLUMNS:
        if column not in output.columns:
            output[column] = ""
    return output[OUTPUT_COLUMNS]
