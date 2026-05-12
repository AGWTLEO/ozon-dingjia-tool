from __future__ import annotations

import json
from io import BytesIO
from math import ceil
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from exchange_rate import get_cny_to_rub_rate, load_exchange_cache
from pricing_engine import (
    INPUT_COLUMNS,
    DEFAULT_LOGISTICS_SPEED,
    PricingInput,
    calculate_batch,
    calculate_pricing,
    preview_logistics,
    value_band_options,
)
from promotion_engine import (
    CPO_RATE_BY_MODE,
    PromotionInput,
    calculate_batch_promotions,
    calculate_promotion,
    get_base_profit,
)


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
EXPORT_DIR = BASE_DIR / "exports"

SETTINGS_PATH = DATA_DIR / "settings.json"
COMMISSION_RULES_PATH = DATA_DIR / "commission_rules.csv"
LOGISTICS_STANDARDS_PATH = DATA_DIR / "logistics_standards.csv"
LOGISTICS_PRICES_PATH = DATA_DIR / "logistics_prices.csv"
EXCHANGE_RATE_CACHE_PATH = DATA_DIR / "exchange_rate_cache.json"
TEMPLATE_PATH = DATA_DIR / "Ozon批量导入模板.xlsx"
EXAMPLE_PATH = DATA_DIR / "Ozon示例数据.xlsx"

COMMISSION_COLUMNS = ["所属类目", "售价下限卢布", "售价上限卢布", "佣金率"]
LOGISTICS_STANDARD_COLUMNS = [
    "物流标准",
    "货值区间",
    "重量下限g",
    "重量上限g",
    "三边和上限cm",
    "长边上限cm",
    "体积重上限kg",
    "最大尺寸长cm",
    "最大尺寸宽cm",
    "最大尺寸高cm",
    "计费方式",
]
LOGISTICS_PRICE_COLUMNS = ["物流标准", "物流时效", "渠道名称", "资费标准", "每克单价", "每票固定费", "备注"]

DEFAULT_SETTINGS = {
    "default_domestic_shipping": 3.0,
    "default_ad_rate": 0.0,
    "default_withdrawal_rate": 0.01,
    "default_return_rate": 0.0,
    "default_tax_rate": 0.0,
    "default_other_fee": 0.0,
    "default_exchange_rate": 12.5,
    "default_packaging_fee": 0.0,
    "use_auto_exchange_rate": False,
}


def ensure_dirs() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    EXPORT_DIR.mkdir(exist_ok=True)


def load_settings() -> dict[str, Any]:
    if not SETTINGS_PATH.exists():
        save_settings(DEFAULT_SETTINGS)
    with SETTINGS_PATH.open("r", encoding="utf-8") as f:
        loaded = json.load(f)
    return {**DEFAULT_SETTINGS, **loaded}


def save_settings(settings: dict[str, Any]) -> None:
    ensure_dirs()
    with SETTINGS_PATH.open("w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def load_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    df = pd.read_csv(path)
    for column in columns:
        if column not in df.columns:
            df[column] = None
    return df[columns]


def save_csv(df: pd.DataFrame, path: Path, columns: list[str]) -> None:
    ensure_dirs()
    cleaned = df.copy()
    for column in columns:
        if column not in cleaned.columns:
            cleaned[column] = None
    cleaned = cleaned[columns].dropna(how="all")
    cleaned.to_csv(path, index=False, encoding="utf-8-sig")


def read_uploaded_table(uploaded_file: Any) -> pd.DataFrame:
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(uploaded_file)
    return pd.read_excel(uploaded_file)


def to_excel_bytes(df: pd.DataFrame, sheet_name: str = "结果") -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
        worksheet = writer.sheets[sheet_name[:31]]
        for col_idx, column in enumerate(df.columns, start=1):
            width = min(max(len(str(column)) + 4, 12), 28)
            worksheet.column_dimensions[worksheet.cell(1, col_idx).column_letter].width = width
        worksheet.freeze_panes = "A2"
    buffer.seek(0)
    return buffer.getvalue()


def template_bytes() -> bytes:
    return to_excel_bytes(pd.DataFrame(columns=INPUT_COLUMNS), "批量导入模板")


def file_bytes(path: Path, fallback: bytes) -> bytes:
    return path.read_bytes() if path.exists() else fallback


def category_options(commission_rules: pd.DataFrame) -> list[str]:
    categories = [
        str(x).strip()
        for x in commission_rules.get("所属类目", pd.Series(dtype=str)).dropna().unique()
        if str(x).strip()
    ]
    return sorted(categories) or ["建筑和装修"]


def get_exchange_state(settings: dict[str, Any], force: bool = False) -> dict[str, Any]:
    if bool(settings.get("use_auto_exchange_rate")) or force:
        info = get_cny_to_rub_rate(
            EXCHANGE_RATE_CACHE_PATH,
            default_rate=float(settings.get("default_exchange_rate", 12.5)),
            force=force,
        )
        return {
            "rate": float(info.get("cny_to_rub", settings.get("default_exchange_rate", 12.5))),
            "source": info.get("source", "俄罗斯央行 Bank of Russia"),
            "updated_at": info.get("updated_at", ""),
            "mode": "自动汇率",
            "warning": info.get("warning", ""),
            "ok": bool(info.get("ok")),
        }

    cache = load_exchange_cache(
        EXCHANGE_RATE_CACHE_PATH,
        default_rate=float(settings.get("default_exchange_rate", 12.5)),
    )
    return {
        "rate": float(settings.get("default_exchange_rate", 12.5)),
        "source": "手动汇率",
        "updated_at": cache.get("updated_at", ""),
        "mode": "手动汇率",
        "warning": "",
        "ok": True,
    }


def save_exchange_settings(
    settings: dict[str, Any],
    rate: float,
    use_auto_exchange_rate: bool,
) -> dict[str, Any]:
    updated = {**settings}
    updated["default_exchange_rate"] = rate
    updated["use_auto_exchange_rate"] = use_auto_exchange_rate
    save_settings(updated)
    return updated


def show_exchange_status(exchange_info: dict[str, Any]) -> None:
    st.caption(
        f"当前汇率：1 人民币 = {exchange_info['rate']:.4f} 卢布｜"
        f"汇率来源：{exchange_info['source']}｜"
        f"更新时间：{exchange_info.get('updated_at') or '未更新'}｜"
        f"模式：{exchange_info['mode']}"
    )
    if exchange_info.get("warning"):
        st.warning(exchange_info["warning"])


def settings_for_batch(settings: dict[str, Any], exchange_info: dict[str, Any]) -> dict[str, Any]:
    return {
        **settings,
        "current_exchange_rate": exchange_info["rate"],
        "exchange_source": exchange_info["source"],
        "exchange_updated_at": exchange_info.get("updated_at", ""),
        "exchange_mode": exchange_info["mode"],
    }


def percent_input(
    label: str,
    value: float,
    key: str,
    disabled: bool = False,
    container: Any = st,
) -> float:
    raw = container.number_input(
        label,
        min_value=0.0,
        max_value=99.0,
        value=round(float(value) * 100, 2),
        step=0.5,
        format="%.2f",
        key=key,
        disabled=disabled,
    )
    return raw / 100


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ozon-blue: #1264d8;
            --ozon-bg: #f5f7fb;
            --ozon-card: #ffffff;
            --ozon-border: #d9e1ec;
            --ozon-text: #1f2937;
            --ozon-muted: #64748b;
            --ozon-green: #0f8a4b;
            --ozon-green-bg: #eaf7ef;
            --ozon-orange: #b7791f;
            --ozon-orange-bg: #fff6e5;
            --ozon-red: #c53030;
            --ozon-red-bg: #fff0f0;
        }
        .stApp { background: var(--ozon-bg); }
        .block-container { padding-top: 1.35rem; padding-bottom: 2rem; max-width: 1380px; }
        [data-testid="stSidebar"] {
            background: #ffffff;
            border-right: 1px solid var(--ozon-border);
        }
        [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
            color: var(--ozon-text);
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: var(--ozon-card);
            border-color: var(--ozon-border) !important;
            border-radius: 8px;
        }
        h1, h2, h3, h4 { color: var(--ozon-text); letter-spacing: 0; }
        .ozon-page-title {
            margin-bottom: 4px;
            color: var(--ozon-text);
            font-size: 28px;
            font-weight: 750;
        }
        .ozon-page-caption {
            color: var(--ozon-muted);
            font-size: 14px;
            margin-bottom: 18px;
        }
        .ozon-card-title {
            font-size: 17px;
            font-weight: 700;
            color: var(--ozon-text);
            margin-bottom: 10px;
        }
        .ozon-metric {
            background: #ffffff;
            border: 1px solid var(--ozon-border);
            border-left: 4px solid var(--ozon-blue);
            border-radius: 8px;
            padding: 14px 15px 13px 15px;
            min-height: 98px;
        }
        .ozon-metric .label {
            color: var(--ozon-muted);
            font-size: 13px;
            line-height: 1.25;
            margin-bottom: 8px;
        }
        .ozon-metric .value {
            color: var(--ozon-text);
            font-size: 25px;
            font-weight: 760;
            line-height: 1.15;
            word-break: break-word;
        }
        .ozon-metric .hint {
            color: var(--ozon-muted);
            font-size: 12px;
            margin-top: 7px;
        }
        .ozon-metric.green { border-left-color: var(--ozon-green); background: var(--ozon-green-bg); }
        .ozon-metric.orange { border-left-color: var(--ozon-orange); background: var(--ozon-orange-bg); }
        .ozon-metric.red { border-left-color: var(--ozon-red); background: var(--ozon-red-bg); }
        .ozon-metric.blue { border-left-color: var(--ozon-blue); background: #eef5ff; }
        .ozon-metric.green .value, .ozon-status.green { color: var(--ozon-green); }
        .ozon-metric.orange .value, .ozon-status.orange { color: var(--ozon-orange); }
        .ozon-metric.red .value, .ozon-status.red { color: var(--ozon-red); }
        .ozon-status {
            border: 1px solid var(--ozon-border);
            border-radius: 8px;
            padding: 12px 14px;
            font-weight: 700;
            background: #ffffff;
        }
        .ozon-status.green { background: var(--ozon-green-bg); border-color: #b8e2c6; }
        .ozon-status.orange { background: var(--ozon-orange-bg); border-color: #f1d08a; }
        .ozon-status.red { background: var(--ozon-red-bg); border-color: #f2b8b8; }
        .stDataFrame, div[data-testid="stDataFrame"] {
            border: 1px solid var(--ozon-border);
            border-radius: 8px;
            overflow: hidden;
            background: #ffffff;
        }
        div[data-testid="stDataFrame"] thead tr th {
            background: #f1f5f9 !important;
            color: var(--ozon-text) !important;
            font-weight: 700 !important;
        }
        div[data-testid="stAlert"] {
            border-radius: 8px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(title: str, caption: str = "") -> None:
    st.markdown(f'<div class="ozon-page-title">{title}</div>', unsafe_allow_html=True)
    if caption:
        st.markdown(f'<div class="ozon-page-caption">{caption}</div>', unsafe_allow_html=True)


def card_title(title: str) -> None:
    st.markdown(f'<div class="ozon-card-title">{title}</div>', unsafe_allow_html=True)


def status_variant(text: Any) -> str:
    if isinstance(text, (int, float)):
        if text < 0:
            return "red"
        if text == 0:
            return "orange"
        return "green"
    value = str(text)
    if any(word in value for word in ["亏损", "不建议", "无利润", "不支持", "失败", "未匹配", "否"]):
        return "red"
    if any(word in value for word in ["谨慎", "风险", "观察", "偏低", "需要"]):
        return "orange"
    if any(word in value for word in ["可以", "仍有利润", "较好", "支持", "达标", "是"]):
        return "green"
    return "blue"


def metric_card(label: str, value: Any, hint: str = "", variant: str = "blue") -> None:
    st.markdown(
        f"""
        <div class="ozon-metric {variant}">
            <div class="label">{label}</div>
            <div class="value">{value}</div>
            {f'<div class="hint">{hint}</div>' if hint else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_card(text: str) -> None:
    variant = status_variant(text)
    st.markdown(f'<div class="ozon-status {variant}">{text}</div>', unsafe_allow_html=True)


def money(value: Any) -> str:
    try:
        return f"¥{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value or "-")


def pct(value: Any) -> str:
    try:
        return f"{float(value):.2%}"
    except (TypeError, ValueError):
        return str(value or "-")


def styled_table(df: pd.DataFrame) -> Any:
    numeric_cols = df.select_dtypes(include="number").columns
    styler = df.style.set_properties(**{"text-align": "left"})
    if len(numeric_cols):
        styler = styler.set_properties(subset=numeric_cols, **{"text-align": "right"})
        format_map = {}
        for col in numeric_cols:
            col_name = str(col)
            if any(key in col_name for key in ["汇率", "每克单价"]):
                format_map[col] = "{:,.4f}"
            elif any(key in col_name for key in ["率", "比例", "占比", "转化率"]):
                format_map[col] = "{:.2%}"
            else:
                format_map[col] = "{:,.2f}"
        styler = styler.format(format_map)
    return styler.set_table_styles(
        [
            {"selector": "th", "props": [("background-color", "#f1f5f9"), ("font-weight", "700")]},
            {"selector": "td", "props": [("padding", "8px 10px")]},
        ]
    )


def show_result_tables(result: dict[str, Any]) -> None:
    card_title("计算结果")
    metric_rows = [
        [
            ("建议售价", money(result.get("建议售价")), "", "blue"),
            ("当前售价", money(result.get("当前售价")) if result.get("当前售价") != "" else "未填写", "", "blue"),
            ("总成本", money(result.get("总成本")), "", "blue"),
            ("净利润", money(result.get("净利润")), "", status_variant(result.get("是否适合上架", ""))),
        ],
        [
            ("利润率", pct(result.get("利润率")), "", status_variant(result.get("是否适合上架", ""))),
            ("保本售价", money(result.get("保本售价")), "", "blue"),
            ("物流标准", result.get("物流标准") or "未匹配", result.get("选择时效", ""), status_variant(result.get("时效是否支持", ""))),
            ("是否适合上架", result.get("是否适合上架", "-"), "", status_variant(result.get("是否适合上架", ""))),
        ],
    ]
    for row in metric_rows:
        cols = st.columns(4)
        for col, item in zip(cols, row):
            with col:
                metric_card(*item)

    with st.container(border=True):
        card_title("物流明细")
        st.dataframe(
            styled_table(pd.DataFrame(
            [
                {
                    "匹配物流标准": result["物流标准"],
                    "当前物流标准支持的时效": result.get("支持时效", ""),
                    "用户选择的物流时效": result.get("选择时效", ""),
                    "是否支持该时效": result.get("时效是否支持", ""),
                    "匹配的渠道名称": result.get("匹配渠道名称", ""),
                    "匹配的资费标准": result.get("匹配资费标准", ""),
                    "每克单价": result.get("每克单价", 0),
                    "每票固定费": result.get("每票固定费", 0),
                    "实际重量 g": result.get("实际重量g", ""),
                    "三边和": result["三边和"],
                    "长边": result["长边"],
                    "实际重量 kg": result["实际重量kg"],
                    "体积重量 kg": result["体积重量kg"],
                    "计费重量 g": result.get("计费重量g", ""),
                    "计费重量 kg": result["计费重量kg"],
                    "货值区间": result.get("货值区间", ""),
                    "货值区间人民币换算": result.get("货值区间人民币换算", ""),
                    "跨境物流费": result["跨境物流费"],
                }
            ]
            )),
            width="stretch",
            hide_index=True,
        )

    with st.container(border=True):
        card_title("汇率明细")
        st.dataframe(
            styled_table(pd.DataFrame(
            [
                {
                    "当前使用汇率": result.get("使用汇率", ""),
                    "汇率来源": result.get("汇率来源", ""),
                    "汇率更新时间": result.get("汇率更新时间", ""),
                    "当前是自动汇率还是手动汇率": result.get("汇率模式", ""),
                }
            ]
            )),
            width="stretch",
            hide_index=True,
        )

    with st.container(border=True):
        card_title("费用明细")
        st.dataframe(
            styled_table(pd.DataFrame(
            [
                {
                    "采购成本": result["采购成本"],
                    "境内段运费": result["境内段运费"],
                    "包装费": result["包装费"],
                    "跨境物流费": result["跨境物流费"],
                    "平台佣金率": f"{result['佣金率']:.2%}",
                    "平台佣金": result["平台佣金"],
                    "广告费比例": f"{result['广告费比例']:.2%}",
                    "广告费": result["广告费"],
                    "提现手续费费率": f"{result['提现手续费费率']:.2%}",
                    "提现手续费": result["提现手续费"],
                    "退货率": f"{result['退货率']:.2%}",
                    "退货损失": result["退货损失"],
                    "税费比例": f"{result['税费比例']:.2%}",
                    "税费": result["税费"],
                    "其他费用": result["其他费用"],
                    "总成本": result["总成本"],
                }
            ]
            )),
            width="stretch",
            hide_index=True,
        )

    if result.get("备注"):
        for note in str(result["备注"]).split("；"):
            if note:
                status_card(note)


def simple_ppc_risk_text(break_even_clicks: float) -> str:
    if break_even_clicks < 10:
        return "风险高，不建议直接开 PPC。"
    if break_even_clicks <= 30:
        return "可以小预算测试，但需要严格控制 CPC。"
    if break_even_clicks <= 60:
        return "可以测试，超过该点击数还不出单应暂停观察。"
    return "PPC 承受能力较好，可以进行测试。"


def show_simple_ppc_module(result: dict[str, Any]) -> None:
    with st.container(border=True):
        card_title("PPC 点击付费承受能力")
        cpc_rub = st.number_input(
            "每次点击出价 CPC，卢布",
            min_value=0.0,
            value=10.0,
            step=0.5,
            key="simple_ppc_cpc_rub",
        )
        exchange_rate = float(result.get("使用汇率") or 0)
        net_profit = float(result.get("净利润") or 0)
        cpc_cny = cpc_rub / exchange_rate if cpc_rub > 0 and exchange_rate > 0 else 0

        if cpc_cny <= 0:
            status_card("请先填写大于 0 的 CPC 和有效汇率。")
            return

        if net_profit <= 0:
            metric_cols = st.columns(3)
            with metric_cols[0]:
                metric_card("CPC 卢布", f"₽{cpc_rub:.2f}", variant="blue")
            with metric_cols[1]:
                metric_card("CPC 人民币", money(cpc_cny), variant="blue")
            with metric_cols[2]:
                metric_card("当前单品净利润", money(net_profit), variant="red")
            status_card("当前单品净利润不为正，不建议开 PPC。")
            return

        break_even_clicks = net_profit / cpc_cny
        break_even_cvr = 1 / break_even_clicks if break_even_clicks > 0 else 0
        risk_text = simple_ppc_risk_text(break_even_clicks)

        ppc_cols = st.columns(5)
        with ppc_cols[0]:
            metric_card("CPC 卢布", f"₽{cpc_rub:.2f}", variant="blue")
        with ppc_cols[1]:
            metric_card("CPC 人民币", money(cpc_cny), variant="blue")
        with ppc_cols[2]:
            metric_card("当前单品净利润", money(net_profit), variant=status_variant(net_profit))
        with ppc_cols[3]:
            metric_card("PPC 盈亏平衡点击数", f"{break_even_clicks:.2f} 次", variant=status_variant(risk_text))
        with ppc_cols[4]:
            metric_card("PPC 盈亏平衡转化率", f"{break_even_cvr:.2%}", variant="blue")

        status_card(f"约 {ceil(break_even_clicks)} 次点击内必须出 1 单，PPC 才能盈亏持平。")
        status_card(risk_text)


def compact_cost_table(result: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"项目": "采购成本", "金额": result.get("采购成本", 0)},
            {"项目": "境内段运费", "金额": result.get("境内段运费", 0)},
            {"项目": "包装费", "金额": result.get("包装费", 0)},
            {"项目": "跨境物流费", "金额": result.get("跨境物流费", 0)},
            {"项目": "平台佣金", "金额": result.get("平台佣金", 0)},
            {"项目": "广告费", "金额": result.get("广告费", 0)},
            {"项目": "提现手续费", "金额": result.get("提现手续费", 0)},
            {"项目": "退货损失", "金额": result.get("退货损失", 0)},
            {"项目": "税费", "金额": result.get("税费", 0)},
            {"项目": "其他费用", "金额": result.get("其他费用", 0)},
            {"项目": "总成本", "金额": result.get("总成本", 0)},
        ]
    )


def show_pricing_result_panel(result: dict[str, Any]) -> None:
    suggested_price = float(result.get("建议售价") or 0)
    exchange_rate = float(result.get("使用汇率") or 0)
    suggested_rub = suggested_price * exchange_rate if exchange_rate > 0 else 0
    status = result.get("是否适合上架", "-")
    status_color = status_variant(status)

    with st.container(border=True):
        card_title("核心售价结果")
        price_cols = st.columns(3)
        with price_cols[0]:
            metric_card("建议售价 / 折后售价", money(suggested_price), variant="blue")
        with price_cols[1]:
            metric_card("建议售价对应卢布", f"₽{suggested_rub:,.2f}", variant="blue")
        with price_cols[2]:
            metric_card("保本售价", money(result.get("保本售价")), variant="blue")

    with st.container(border=True):
        card_title("利润摘要")
        profit_cols = st.columns(5)
        with profit_cols[0]:
            metric_card("净利润", money(result.get("净利润")), variant=status_color)
        with profit_cols[1]:
            metric_card("利润率", pct(result.get("利润率")), variant=status_color)
        with profit_cols[2]:
            metric_card("总成本", money(result.get("总成本")), variant="blue")
        with profit_cols[3]:
            metric_card("物流标准", result.get("物流标准") or "未匹配", result.get("选择时效", ""), status_variant(result.get("物流标准", "")))
        with profit_cols[4]:
            metric_card("是否适合上架", status, variant=status_color)

        detail_cols = st.columns(3)
        with detail_cols[0]:
            metric_card("平台佣金率", f"{float(result.get('佣金率') or 0):.2%}", variant="blue")
        with detail_cols[1]:
            metric_card("跨境物流费", money(result.get("跨境物流费")), variant="blue")
        with detail_cols[2]:
            metric_card("计费重量", f"{float(result.get('计费重量g') or 0):,.0f} g", variant="blue")

    with st.container(border=True):
        card_title("成本明细")
        cost_df = compact_cost_table(result)
        st.dataframe(styled_table(cost_df), width="stretch", hide_index=True, height=420)

    show_simple_ppc_module(result)

    if result.get("备注"):
        for note in str(result["备注"]).split("；"):
            if note:
                status_card(note)


def single_pricing_tab(
    settings: dict[str, Any],
    exchange_info: dict[str, Any],
    commission_rules: pd.DataFrame,
    logistics_standards: pd.DataFrame,
    logistics_prices: pd.DataFrame,
) -> None:
    page_header("单品测算", "左侧填写成本和物流参数，右侧查看建议售价、利润和 PPC 承受能力。")

    categories = category_options(commission_rules)
    sku = ""
    product_name = ""
    latest_single_result = None
    latest_df = st.session_state.get("latest_result_df")
    if isinstance(latest_df, pd.DataFrame) and len(latest_df) == 1:
        latest_single_result = latest_df.iloc[0].to_dict()

    input_col, result_col = st.columns([0.42, 0.58], gap="large")

    with input_col:
        with st.container(border=True):
            card_title("基础信息与平台费用")
            category = st.selectbox("所属行业 / 类目 *", categories)
            cost_cols = st.columns(2)
            purchase_cost = cost_cols[0].number_input("采购成本，人民币 *", min_value=0.0, value=0.0, step=1.0)
            domestic_shipping = cost_cols[1].number_input(
                "境内段运费，人民币 *",
                min_value=0.0,
                value=float(settings["default_domestic_shipping"]),
                step=0.5,
            )
            packaging_fee = cost_cols[0].number_input(
                "包装费，人民币",
                min_value=0.0,
                value=float(settings["default_packaging_fee"]),
                step=0.5,
            )
            other_fee = cost_cols[1].number_input(
                "其他费用，人民币",
                min_value=0.0,
                value=float(settings["default_other_fee"]),
                step=0.5,
            )
            target_profit_rate = percent_input("目标利润率 % *", 0.2, "single_target_profit")

            commission_preview = float(latest_single_result.get("佣金率", 0)) if latest_single_result else 0.0
            st.number_input(
                "平台佣金率 %（自动匹配）",
                min_value=0.0,
                max_value=99.0,
                value=round(commission_preview * 100, 2),
                step=0.5,
                format="%.2f",
                disabled=True,
                key="single_commission_preview",
            )

            fee_cols = st.columns(2)
            ad_rate = percent_input(
                "广告费比例 %",
                float(settings.get("default_ad_rate", 0.0)),
                "single_ad_rate",
                container=fee_cols[0],
            )
            withdrawal_rate = percent_input(
                "提现手续费费率 %",
                float(settings["default_withdrawal_rate"]),
                "single_withdrawal_rate",
                container=fee_cols[1],
            )
            return_rate = percent_input(
                "退货率 %",
                float(settings["default_return_rate"]),
                "single_return_rate",
                container=fee_cols[0],
            )
            tax_rate = percent_input(
                "税费比例 %",
                float(settings["default_tax_rate"]),
                "single_tax_rate",
                container=fee_cols[1],
            )

        with st.container(border=True):
            card_title("物流信息")
            exchange_cols = st.columns([1, 1])
            use_auto_exchange = exchange_cols[0].toggle(
                "使用自动汇率",
                value=bool(settings.get("use_auto_exchange_rate")),
                key="single_use_auto_exchange",
            )
            active_exchange_info = exchange_info
            if use_auto_exchange and exchange_info.get("mode") != "自动汇率":
                auto_info = get_cny_to_rub_rate(
                    EXCHANGE_RATE_CACHE_PATH,
                    default_rate=float(settings.get("default_exchange_rate", 12.5)),
                    force=False,
                )
                active_exchange_info = {
                    "rate": float(auto_info.get("cny_to_rub", settings.get("default_exchange_rate", 12.5))),
                    "source": auto_info.get("source", "俄罗斯央行 Bank of Russia"),
                    "updated_at": auto_info.get("updated_at", ""),
                    "mode": "自动汇率",
                    "warning": auto_info.get("warning", ""),
                    "ok": bool(auto_info.get("ok")),
                }
            if exchange_cols[1].button("自动更新今日汇率", key="single_update_exchange"):
                fresh = get_cny_to_rub_rate(
                    EXCHANGE_RATE_CACHE_PATH,
                    default_rate=float(settings.get("default_exchange_rate", 12.5)),
                    force=True,
                )
                save_exchange_settings(settings, float(fresh["cny_to_rub"]), use_auto_exchange)
                st.success("已尝试更新今日汇率。")
                st.rerun()

            exchange_rate = st.number_input(
                "汇率：1 人民币 = 多少卢布 *",
                min_value=0.0001,
                value=float(active_exchange_info["rate"] if use_auto_exchange else settings["default_exchange_rate"]),
                step=0.1,
                format="%.4f",
                key="single_exchange_rate",
                disabled=use_auto_exchange,
            )
            if use_auto_exchange:
                exchange_rate = float(active_exchange_info["rate"])
            exchange_mode = "自动汇率" if use_auto_exchange else "手动汇率"
            exchange_source = active_exchange_info["source"] if use_auto_exchange else "手动汇率"
            exchange_updated_at = active_exchange_info.get("updated_at", "") if use_auto_exchange else ""

            logistics_cols = st.columns(2)
            weight_g = logistics_cols[0].number_input("产品克重 g *", min_value=0.0, value=0.0, step=10.0)
            length_cm = logistics_cols[1].number_input("长 cm *", min_value=0.0, value=0.0, step=1.0)
            width_cm = logistics_cols[0].number_input("宽 cm *", min_value=0.0, value=0.0, step=1.0)
            height_cm = logistics_cols[1].number_input("高 cm *", min_value=0.0, value=0.0, step=1.0)

            band_labels = value_band_options(exchange_rate)
            selected_band_label = st.selectbox("货值区间 *", list(band_labels.values()), key="single_value_band")
            value_band = next(band for band, label in band_labels.items() if label == selected_band_label)

            preview_item = PricingInput(
                weight_g=weight_g,
                length_cm=length_cm,
                width_cm=width_cm,
                height_cm=height_cm,
                value_band=value_band,
                exchange_rate=exchange_rate,
            )
            logistics_preview = preview_logistics(preview_item, logistics_standards, logistics_prices)
            matched_standard = logistics_preview.get("物流标准") or "未匹配"
            supported_speeds = logistics_preview.get("支持时效", [])

            speed_options = supported_speeds or [DEFAULT_LOGISTICS_SPEED]
            current_speed = st.session_state.get("single_last_logistics_speed", DEFAULT_LOGISTICS_SPEED)
            if current_speed not in speed_options and supported_speeds:
                status_card(f"当前物流标准不支持 {current_speed}，请重新选择有效时效。")
                speed_options_for_widget = ["请重新选择有效时效"] + speed_options
                speed_index = 0
            else:
                speed_options_for_widget = speed_options
                speed_index = speed_options_for_widget.index(current_speed) if current_speed in speed_options_for_widget else 0
            logistics_speed = st.radio(
                "物流时效 *",
                speed_options_for_widget,
                index=speed_index,
                horizontal=True,
                key=f"single_logistics_speed_{matched_standard}_{'_'.join(speed_options)}",
            )
            if logistics_speed != "请重新选择有效时效":
                st.session_state["single_last_logistics_speed"] = logistics_speed
            chosen_logistics_speed = current_speed if logistics_speed == "请重新选择有效时效" else logistics_speed

            logistics_metric_cols = st.columns(2)
            with logistics_metric_cols[0]:
                metric_card("物流方式 / 自动匹配结果", matched_standard, "、".join(supported_speeds) or "未匹配", status_variant(matched_standard))
            with logistics_metric_cols[1]:
                metric_card("交货类型", chosen_logistics_speed, "按物流时效计费", "blue")

        with st.expander("更多设置", expanded=False):
            show_exchange_status(
                {
                    "rate": exchange_rate,
                    "source": exchange_source,
                    "updated_at": exchange_updated_at,
                    "mode": exchange_mode,
                    "warning": active_exchange_info.get("warning", "") if use_auto_exchange else "",
                }
            )
            st.caption("平台佣金率根据“类目 + 建议售价卢布区间”自动匹配；货值区间和物流时效价格可在“规则设置”维护。")
            if matched_standard in {"Big", "Premium Big"}:
                st.warning("当前物流标准不支持 5-10天时效。")

        submitted = st.button("计算建议售价", type="primary", use_container_width=True)

    with result_col:
        if submitted:
            item = PricingInput(
                sku=sku,
                product_name=product_name,
                category=category,
                purchase_cost=purchase_cost,
                domestic_shipping=domestic_shipping,
                packaging_fee=packaging_fee,
                other_fee=other_fee,
                weight_g=weight_g,
                length_cm=length_cm,
                width_cm=width_cm,
                height_cm=height_cm,
                value_band=value_band,
                logistics_speed=chosen_logistics_speed,
                current_price_cny=0.0,
                target_profit_rate=target_profit_rate,
                exchange_rate=exchange_rate,
                exchange_source=exchange_source,
                exchange_updated_at=exchange_updated_at,
                exchange_mode=exchange_mode,
                ad_rate=ad_rate,
                withdrawal_rate=withdrawal_rate,
                return_rate=return_rate,
                tax_rate=tax_rate,
            )
            result = calculate_pricing(item, commission_rules, logistics_standards, logistics_prices)
            st.session_state["latest_result_df"] = pd.DataFrame([result])
            st.session_state["latest_result_name"] = f"{sku or '单品'}_定价结果.xlsx"
            show_pricing_result_panel(result)
        elif latest_single_result:
            show_pricing_result_panel(latest_single_result)
        else:
            with st.container(border=True):
                card_title("核心售价结果")
                st.info("填写左侧参数后点击“计算建议售价”，这里会显示建议售价、利润和 PPC 承受能力。")


def batch_tab(
    settings: dict[str, Any],
    exchange_info: dict[str, Any],
    commission_rules: pd.DataFrame,
    logistics_standards: pd.DataFrame,
    logistics_prices: pd.DataFrame,
) -> None:
    page_header("批量计算", "上传 Excel 后，系统会按每行 SKU 批量匹配物流、佣金并输出利润结果。")
    with st.container(border=True):
        card_title("批量导入")
        show_exchange_status(exchange_info)

        dl_cols = st.columns(2)
        dl_cols[0].download_button(
            "下载空白 Excel 模板",
            data=file_bytes(TEMPLATE_PATH, template_bytes()),
            file_name="Ozon批量导入模板.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        dl_cols[1].download_button(
            "下载示例数据",
            data=file_bytes(EXAMPLE_PATH, template_bytes()),
            file_name="Ozon示例数据.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        uploaded = st.file_uploader("上传批量导入 Excel", type=["xlsx", "xls"])
    if not uploaded:
        st.dataframe(styled_table(pd.DataFrame(columns=INPUT_COLUMNS)), width="stretch")
        return

    input_df = pd.read_excel(uploaded)
    with st.container(border=True):
        card_title("导入预览")
        st.dataframe(styled_table(input_df.head(20)), width="stretch")

    missing = [column for column in INPUT_COLUMNS if column not in input_df.columns]
    if missing:
        st.warning("缺少字段会按默认值或空值处理：" + "、".join(missing))

    if st.button("批量计算", type="primary"):
        output_df = calculate_batch(
            input_df,
            defaults=settings_for_batch(settings, exchange_info),
            commission_rules=commission_rules,
            logistics_standards=logistics_standards,
            logistics_prices=logistics_prices,
        )
        promo_df = calculate_batch_promotions(input_df, output_df)
        output_df = pd.concat([output_df.reset_index(drop=True), promo_df], axis=1)
        st.session_state["latest_result_df"] = output_df
        st.session_state["latest_result_name"] = "Ozon批量定价结果.xlsx"
        status_card(f"已完成 {len(output_df)} 个 SKU 的测算。")
        st.dataframe(styled_table(output_df), width="stretch")
        st.download_button(
            "下载批量结果 Excel",
            data=to_excel_bytes(output_df, "批量计算结果"),
            file_name="Ozon批量定价结果.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


def show_metric_table(title: str, data: dict[str, Any]) -> None:
    st.markdown(f"#### {title}")
    st.dataframe(styled_table(pd.DataFrame([data])), width="stretch", hide_index=True)


def ppc_risk_text(break_even_clicks: float) -> str:
    if break_even_clicks < 10:
        return "可承受点击数太少，PPC 风险高，不建议直接推广。"
    if break_even_clicks <= 30:
        return "可以小预算测试，但需要严格控制 CPC，并观察加购和转化。"
    if break_even_clicks <= 60:
        return "PPC 承受能力一般，可以测试，但超过盈亏平衡点击数还不出单应暂停观察。"
    return "PPC 承受能力较好，可以进行 14 天测试。"


def promotion_notice(break_even_clicks: float) -> None:
    st.info("如果没有出单，所有 PPC 点击费用都是亏损；这里的盈亏平衡点击数表示一单利润最多能承受多少次点击。")
    st.caption(
        f"例如盈亏平衡点击数是 {break_even_clicks:.0f} 次，就表示约 {break_even_clicks:.0f} 次点击内必须出 1 单；"
        f"如果 {break_even_clicks:.0f} 次点击都没有出单，这一单利润就被广告费吃掉了。"
    )


def promotion_tab(exchange_info: dict[str, Any]) -> None:
    page_header("推广测算", "基于已完成的定价结果，继续测算 PPC 点击付费、CPO 订单付费和推广风险。")

    latest_df = st.session_state.get("latest_result_df")
    result: Any = None
    with st.container(border=True):
        card_title("基础利润")
        if isinstance(latest_df, pd.DataFrame) and not latest_df.empty:
            label_options = [
                f"{idx + 1}. {row.get('SKU', '') or '未填SKU'} {row.get('产品名称', '') or ''}".strip()
                for idx, row in latest_df.iterrows()
            ]
            selected_label = st.selectbox("选择要测算推广的定价结果", label_options)
            selected_idx = label_options.index(selected_label)
            result = latest_df.iloc[selected_idx].to_dict()
        else:
            status_card("还没有定价结果。可以先去“单品定价”或“批量计算”完成测算，也可以在这里手动输入基础利润做快速测试。")

        if result:
            base = get_base_profit(result)
            price = base["售价"]
            pre_ad_profit = base["推广前净利润"]
            exchange_rate = float(result.get("使用汇率") or exchange_info["rate"])
            ad_fee = base["主定价广告费"]
            if ad_fee > 0:
                status_card("推广测算建议使用不含广告费的基础利润，否则会重复计算广告成本。")
        else:
            manual_cols = st.columns(3)
            price = manual_cols[0].number_input("售价，人民币 *", min_value=0.0, value=100.0, step=1.0)
            pre_ad_profit = manual_cols[1].number_input("推广前净利润，人民币 *", value=30.0, step=1.0)
            exchange_rate = manual_cols[2].number_input(
                "汇率：1 人民币 = 多少卢布 *",
                min_value=0.0001,
                value=float(exchange_info["rate"]),
                step=0.1,
                format="%.4f",
            )
            base = {
                "售价": price,
                "非广告总成本": max(price - pre_ad_profit, 0),
                "推广前净利润": pre_ad_profit,
                "推广前利润率": pre_ad_profit / price if price else 0,
                "主定价广告费": 0,
            }

        base_cols = st.columns(4)
        with base_cols[0]:
            metric_card("售价", money(price), variant="blue")
        with base_cols[1]:
            metric_card("推广前总成本", money(base["非广告总成本"]), variant="blue")
        with base_cols[2]:
            metric_card("推广前净利润", money(pre_ad_profit), variant=status_variant(pre_ad_profit))
        with base_cols[3]:
            metric_card("推广前利润率", pct(base["推广前利润率"]), variant=status_variant(pre_ad_profit))

    with st.container(border=True):
        card_title("PPC 点击付费")
        ppc_cols = st.columns(2)
        cpc_rub = ppc_cols[0].number_input("每次点击出价 CPC，卢布 *", min_value=0.0, value=5.0, step=0.5)
        weekly_budget_rub = ppc_cols[1].number_input("每周预算，卢布 *", min_value=0.0, value=2000.0, step=100.0)

        promo_preview = calculate_promotion(
            PromotionInput(
                price=price,
                pre_ad_profit=pre_ad_profit,
                exchange_rate=exchange_rate,
                cpc_rub=cpc_rub,
                cpc_cny=0,
                expected_cvr=0,
                test_clicks=0,
                weekly_budget_rub=weekly_budget_rub,
                cpo_mode="全部商品CPO",
                cpo_rate=0.22,
                combo_cpo_rate=0.10,
                use_combo=True,
            )
        )
        ppc_risk = ppc_risk_text(promo_preview["PPC盈亏平衡点击数"])
        ppc_metric_cols = st.columns(5)
        with ppc_metric_cols[0]:
            metric_card("PPC 盈亏平衡点击数", f"{promo_preview['PPC盈亏平衡点击数']:.2f} 次", variant=status_variant(ppc_risk))
        with ppc_metric_cols[1]:
            metric_card("盈亏平衡转化率", f"{promo_preview['PPC盈亏平衡转化率']:.2%}", variant="blue")
        with ppc_metric_cols[2]:
            metric_card("每周预算可买点击数", f"{promo_preview['每周预算可购买点击数']:.2f} 次", variant="blue")
        with ppc_metric_cols[3]:
            metric_card("CPC 人民币", money(promo_preview["CPC人民币"]), variant="blue")
        with ppc_metric_cols[4]:
            metric_card("PPC 风险判断", ppc_risk, variant=status_variant(ppc_risk))
        promotion_notice(promo_preview["PPC盈亏平衡点击数"])

    with st.container(border=True):
        card_title("CPO 订单付费")
        st.caption("全部商品 CPO：22%；针对单个产品 CPO：30%；PPC + CPO 组合：10%。10% 只用于组合推广预估。")
        cpo_cols = st.columns(2)
        cpo_mode = cpo_cols[0].selectbox(
            "CPO 模式 *",
            ["不使用CPO", "全部商品CPO", "单个产品CPO", "PPC+CPO组合", "自定义CPO"],
            index=1,
        )
        default_cpo_rate = CPO_RATE_BY_MODE.get(cpo_mode, 0.22)
        cpo_rate = percent_input(
            "CPO 费率 %",
            default_cpo_rate,
            "promo_cpo_rate",
            disabled=cpo_mode != "自定义CPO",
            container=cpo_cols[1],
        )
        if cpo_mode != "自定义CPO":
            cpo_rate = default_cpo_rate

        promo = calculate_promotion(
            PromotionInput(
                price=price,
                pre_ad_profit=pre_ad_profit,
                exchange_rate=exchange_rate,
                cpc_rub=cpc_rub,
                cpc_cny=0,
                expected_cvr=0,
                test_clicks=0,
                weekly_budget_rub=weekly_budget_rub,
                cpo_mode=cpo_mode,
                cpo_rate=cpo_rate,
                combo_cpo_rate=0.10,
                use_combo=True,
            )
        )
        cpo_metric_cols = st.columns(5)
        with cpo_metric_cols[0]:
            metric_card("CPO 费率", f"{promo['CPO费率']:.2%}", variant="blue")
        with cpo_metric_cols[1]:
            metric_card("CPO 费用", money(promo["CPO费用"]), variant="blue")
        with cpo_metric_cols[2]:
            metric_card("CPO 后净利润", money(promo["CPO后净利润"]), variant=status_variant(promo["CPO判断"]))
        with cpo_metric_cols[3]:
            metric_card("CPO 后利润率", f"{promo['CPO后利润率']:.2%}", variant=status_variant(promo["CPO判断"]))
        with cpo_metric_cols[4]:
            metric_card("是否建议开启", promo["CPO判断"], variant=status_variant(promo["CPO判断"]))

        with st.expander("高级：PPC + CPO 组合测算", expanded=False):
            combo_margin = promo["推广前净利润"] - promo["组合CPO费用"]
            combo_cols_out = st.columns(4)
            with combo_cols_out[0]:
                metric_card("组合 CPO 后剩余利润", money(combo_margin), variant=status_variant(combo_margin))
            with combo_cols_out[1]:
                metric_card("组合 CPO 费率", f"{promo['组合CPO费率']:.2%}", variant="blue")
            with combo_cols_out[2]:
                metric_card("组合盈亏平衡点击数", f"{promo['组合盈亏平衡点击数']:.2f} 次", variant=status_variant(promo["组合判断"]))
            with combo_cols_out[3]:
                metric_card("组合 CPO 费用", money(promo["组合CPO费用"]), variant="blue")
            show_metric_table(
                "组合推广结果",
                {
                    "推广前净利润": promo["推广前净利润"],
                    "CPO 费率": f"{promo['组合CPO费率']:.2%}",
                    "CPO 费用": promo["组合CPO费用"],
                    "CPO 后剩余可承受 PPC 金额": round(combo_margin, 2),
                    "CPC 卢布": promo["CPC卢布"],
                    "CPC 人民币": promo["CPC人民币"],
                    "组合盈亏平衡点击数": promo["组合盈亏平衡点击数"],
                    "组合盈亏平衡转化率": f"{promo['组合盈亏平衡转化率']:.2%}",
                    "判断": promo["组合判断"],
                },
            )

    with st.container(border=True):
        card_title("推广建议")
        status_card(ppc_risk)
        status_card(promo["CPO判断"])
        if promo["风险提示"]:
            status_card(promo["风险提示"])

        st.markdown(
            """
- PPC 点击付费适合新商品、促销商品、热门类目但订单少的商品。
- PPC 广告活动建议至少运行 14 天后再判断效果。
- 前几天广告费用占比上升不要马上停，第二周仍异常再优化。
- PPC 广告费用份额建议控制在 18% 以内。
- 同一商品不要放到相同投放位置的多个 PPC 活动里，避免自我竞争。
- 如果展示和点击少，可能是 CPC 出价竞争力不足。
- 如果点击和加购多但订单少，优先优化价格、图片、描述、评价和物流时效。
- CPO 按订单付费只在产生推广订单后扣费。
- 全部商品 CPO 可按 22% 估算。
- 针对单个产品 / 所选商品 CPO 可按 30% 估算。
- PPC + CPO 组合时，CPO 可按 10% 估算。
- 新品如果还没有签收/完成订单，可能暂时无法开启所选商品 CPO。
- 如果商品推广后仍无利润，不要强行推广。
            """
        )
def settings_tab(
    settings: dict[str, Any],
    exchange_info: dict[str, Any],
    commission_rules: pd.DataFrame,
    logistics_standards: pd.DataFrame,
    logistics_prices: pd.DataFrame,
) -> None:
    page_header("规则设置", "左侧选择规则分类，右侧查看、编辑、上传、下载并保存当前规则。")

    nav_col, editor_col = st.columns([0.24, 0.76], gap="large")
    with nav_col:
        with st.container(border=True):
            card_title("规则分类")
            rule_section = st.radio(
                "选择规则",
                [
                    "物流标准规则",
                    "物流价格规则",
                    "平台佣金规则",
                    "默认费用参数",
                    "税费规则",
                    "汇率设置",
                    "货值区间",
                    "物流时效规则",
                ],
                label_visibility="collapsed",
            )

    with editor_col:
        if rule_section in {"默认费用参数", "税费规则", "汇率设置"}:
            with st.container(border=True):
                card_title(rule_section)
                show_exchange_status(exchange_info)
                exchange_action_cols = st.columns([1, 1, 2])
                if exchange_action_cols[0].button("自动更新今日汇率", key="settings_update_exchange"):
                    fresh = get_cny_to_rub_rate(
                        EXCHANGE_RATE_CACHE_PATH,
                        default_rate=float(settings.get("default_exchange_rate", 12.5)),
                        force=True,
                    )
                    save_exchange_settings(
                        settings,
                        float(fresh.get("cny_to_rub", settings.get("default_exchange_rate", 12.5))),
                        True,
                    )
                    st.success("已尝试更新今日汇率。")
                    st.rerun()
                exchange_action_cols[1].download_button(
                    "下载默认参数 JSON",
                    data=json.dumps(settings, ensure_ascii=False, indent=2),
                    file_name="settings.json",
                    mime="application/json",
                    key="download_settings_json",
                )
                exchange_action_cols[2].caption("默认费用、税费比例和汇率设置保存在同一个 settings.json 中。")

                uploaded_settings = st.file_uploader("上传默认参数 JSON", type=["json"], key="upload_settings_json")
                if uploaded_settings and st.button("导入并保存默认参数", key="save_uploaded_settings"):
                    try:
                        imported_settings = json.loads(uploaded_settings.getvalue().decode("utf-8"))
                        save_settings({**DEFAULT_SETTINGS, **imported_settings})
                        st.success("默认参数已导入并保存。")
                        st.rerun()
                    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
                        st.error("默认参数 JSON 解析失败，请检查文件格式。")

                with st.form("default_settings_form"):
                    cols = st.columns(3)
                    default_domestic_shipping = cols[0].number_input(
                        "境内段运费默认值，人民币",
                        min_value=0.0,
                        value=float(settings["default_domestic_shipping"]),
                        step=0.5,
                    )
                    default_other_fee = cols[1].number_input(
                        "其他费用默认值，人民币",
                        min_value=0.0,
                        value=float(settings["default_other_fee"]),
                        step=0.5,
                    )
                    default_packaging_fee = cols[2].number_input(
                        "包装费默认值，人民币",
                        min_value=0.0,
                        value=float(settings["default_packaging_fee"]),
                        step=0.5,
                    )

                    rate_cols = st.columns(4)
                    default_ad_rate = rate_cols[0].number_input(
                        "广告费比例默认值 %",
                        min_value=0.0,
                        max_value=99.0,
                        value=float(settings["default_ad_rate"]) * 100,
                        step=0.5,
                    ) / 100
                    default_withdrawal_rate = rate_cols[1].number_input(
                        "提现手续费费率默认值 %",
                        min_value=0.0,
                        max_value=99.0,
                        value=float(settings["default_withdrawal_rate"]) * 100,
                        step=0.1,
                    ) / 100
                    default_return_rate = rate_cols[2].number_input(
                        "退货率默认值 %",
                        min_value=0.0,
                        max_value=99.0,
                        value=float(settings["default_return_rate"]) * 100,
                        step=0.5,
                    ) / 100
                    default_tax_rate = rate_cols[3].number_input(
                        "税费比例默认值 %",
                        min_value=0.0,
                        max_value=99.0,
                        value=float(settings["default_tax_rate"]) * 100,
                        step=0.5,
                    ) / 100

                    use_auto_exchange_rate = st.toggle(
                        "使用自动汇率",
                        value=bool(settings.get("use_auto_exchange_rate")),
                    )
                    default_exchange_rate = st.number_input(
                        "汇率默认值：1 人民币 = 多少卢布",
                        min_value=0.0001,
                        value=float(exchange_info["rate"] if use_auto_exchange_rate else settings["default_exchange_rate"]),
                        step=0.1,
                        format="%.4f",
                        disabled=use_auto_exchange_rate,
                    )
                    if use_auto_exchange_rate:
                        default_exchange_rate = float(exchange_info["rate"])

                    if st.form_submit_button("保存默认参数", type="primary"):
                        save_settings(
                            {
                                "default_domestic_shipping": default_domestic_shipping,
                                "default_ad_rate": default_ad_rate,
                                "default_withdrawal_rate": default_withdrawal_rate,
                                "default_return_rate": default_return_rate,
                                "default_tax_rate": default_tax_rate,
                                "default_other_fee": default_other_fee,
                                "default_exchange_rate": default_exchange_rate,
                                "default_packaging_fee": default_packaging_fee,
                                "use_auto_exchange_rate": use_auto_exchange_rate,
                            }
                        )
                        st.success("默认参数已保存。")

        elif rule_section == "平台佣金规则":
            with st.container(border=True):
                card_title("平台佣金规则")
                st.caption("比例字段请填小数，例如 12% 填 0.12。售价上限留空表示无上限。")
                commission_tools = st.columns([2, 1])
                uploaded_commission = commission_tools[0].file_uploader(
                    "上传类目佣金率表 CSV / Excel",
                    type=["xlsx", "xls", "csv"],
                    key="upload_commission_rules",
                )
                if uploaded_commission and commission_tools[1].button("导入并保存佣金表", key="save_uploaded_commission"):
                    replacement_df = read_uploaded_table(uploaded_commission)
                    save_csv(replacement_df, COMMISSION_RULES_PATH, COMMISSION_COLUMNS)
                    st.success("类目佣金率表已导入并保存。")
                    st.rerun()

                edited_commission = st.data_editor(
                    commission_rules,
                    num_rows="dynamic",
                    width="stretch",
                    height=520,
                    hide_index=True,
                    column_config={
                        "佣金率": st.column_config.NumberColumn("佣金率", min_value=0.0, max_value=1.0, step=0.01),
                    },
                )
                commission_save_cols = st.columns(2)
                if commission_save_cols[0].button("保存类目佣金率表", type="primary", key="save_commission_rules"):
                    save_csv(edited_commission, COMMISSION_RULES_PATH, COMMISSION_COLUMNS)
                    st.success("类目佣金率表已保存。")
                commission_save_cols[1].download_button(
                    "下载当前佣金率表 CSV",
                    data=edited_commission.to_csv(index=False, encoding="utf-8-sig"),
                    file_name="类目佣金率表.csv",
                    mime="text/csv",
                    key="download_commission_rules",
                )

        elif rule_section in {"物流标准规则", "货值区间"}:
            with st.container(border=True):
                card_title(rule_section)
                st.caption("物流标准规则用于匹配物流方式；货值区间也在这张规则表中维护。删除行、新增行后点击保存即可生效。")
                standard_tools = st.columns([2, 1])
                uploaded_standards = standard_tools[0].file_uploader(
                    "上传物流标准规则 CSV / Excel",
                    type=["xlsx", "xls", "csv"],
                    key="upload_logistics_standards",
                )
                if uploaded_standards and standard_tools[1].button("导入并保存物流标准", key="save_uploaded_standards"):
                    replacement_df = read_uploaded_table(uploaded_standards)
                    save_csv(replacement_df, LOGISTICS_STANDARDS_PATH, LOGISTICS_STANDARD_COLUMNS)
                    st.success("物流标准规则已导入并保存。")
                    st.rerun()

                edited_standards = st.data_editor(
                    logistics_standards,
                    num_rows="dynamic",
                    width="stretch",
                    height=560,
                    hide_index=True,
                )
                standard_save_cols = st.columns(2)
                if standard_save_cols[0].button("保存物流标准", type="primary", key="save_logistics_standards"):
                    save_csv(edited_standards, LOGISTICS_STANDARDS_PATH, LOGISTICS_STANDARD_COLUMNS)
                    st.success("物流标准已保存。")
                standard_save_cols[1].download_button(
                    "下载当前物流标准 CSV",
                    data=edited_standards.to_csv(index=False, encoding="utf-8-sig"),
                    file_name="物流标准.csv",
                    mime="text/csv",
                    key="download_logistics_standards",
                )

        elif rule_section in {"物流价格规则", "物流时效规则"}:
            with st.container(border=True):
                card_title(rule_section)
                st.caption("物流价格表按“物流标准 + 物流时效”匹配。跨境物流费 = 计费重量g × 每克单价 + 每票固定费。")
                upload_cols = st.columns([2, 1])
                replacement = upload_cols[0].file_uploader(
                    "导入物流价格表 CSV / Excel",
                    type=["xlsx", "xls", "csv"],
                    key="upload_logistics_prices",
                )
                if replacement and upload_cols[1].button("导入并保存物流价格", key="save_uploaded_prices"):
                    replacement_df = read_uploaded_table(replacement)
                    save_csv(replacement_df, LOGISTICS_PRICES_PATH, LOGISTICS_PRICE_COLUMNS)
                    st.success("物流价格表已导入并保存。")
                    st.rerun()

                edited_prices = st.data_editor(
                    logistics_prices,
                    num_rows="dynamic",
                    width="stretch",
                    height=560,
                    hide_index=True,
                )
                save_cols = st.columns(2)
                if save_cols[0].button("保存物流价格表", type="primary", key="save_logistics_prices"):
                    save_csv(edited_prices, LOGISTICS_PRICES_PATH, LOGISTICS_PRICE_COLUMNS)
                    st.success("物流价格表已保存。")
                save_cols[1].download_button(
                    "下载当前物流价格表 CSV",
                    data=edited_prices.to_csv(index=False, encoding="utf-8-sig"),
                    file_name="物流价格表.csv",
                    mime="text/csv",
                    key="download_logistics_prices",
                )

def export_tab() -> None:
    page_header("结果导出", "导出最近一次单品或批量测算结果。")
    if "latest_result_df" not in st.session_state:
        st.info("还没有可导出的结果。请先在“单品定价”或“批量计算”中完成一次测算。")
        return

    result_df = st.session_state["latest_result_df"]
    file_name = st.session_state.get("latest_result_name", "Ozon定价结果.xlsx")
    with st.container(border=True):
        card_title("可导出结果")
        st.dataframe(styled_table(result_df), width="stretch")
        st.download_button(
            "导出 Excel 结果",
            data=to_excel_bytes(result_df, "定价结果"),
            file_name=file_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )


def main() -> None:
    ensure_dirs()
    st.set_page_config(
        page_title="Ozon 定制自动定价工具",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_theme()
    st.sidebar.markdown("## Ozon 定价工具")
    st.sidebar.caption("单品测算 + 规则维护")
    page = st.sidebar.radio("导航", ["单品测算", "规则设置"], label_visibility="collapsed")
    st.sidebar.markdown("---")
    st.sidebar.caption("批量、独立推广、CPO、组合推广等复杂功能已隐藏。")

    settings = load_settings()
    exchange_info = get_exchange_state(settings)
    commission_rules = load_csv(COMMISSION_RULES_PATH, COMMISSION_COLUMNS)
    logistics_standards = load_csv(LOGISTICS_STANDARDS_PATH, LOGISTICS_STANDARD_COLUMNS)
    logistics_prices = load_csv(LOGISTICS_PRICES_PATH, LOGISTICS_PRICE_COLUMNS)

    if page == "规则设置":
        settings_tab(settings, exchange_info, commission_rules, logistics_standards, logistics_prices)
    else:
        single_pricing_tab(settings, exchange_info, commission_rules, logistics_standards, logistics_prices)


if __name__ == "__main__":
    main()
