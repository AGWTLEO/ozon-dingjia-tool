# Ozon 单品自动定价工具

这是一个基于 Streamlit 的 Ozon 跨境电商单品测算工具。

当前版本是公开使用的简化版，不包含登录密码、不做访问限制、不连接 Ozon 后台、不做自动上品。

## 工具用途

工具用于在上架前快速测算单个商品的建议售价、物流费用、平台费用、净利润、利润率和 PPC 点击付费承受能力。

单品测算页采用左侧输入、右侧结果的桌面端布局：

- 左侧输入区：基础信息与平台费用、物流信息、更多设置。
- 右侧结果区：核心售价结果、利润摘要、成本明细、PPC 点击付费承受能力。

工具不再要求用户输入“当前售价”，统一根据成本、物流、平台费用和目标利润率反推建议售价，并基于建议售价计算利润结果。

当前普通用户页面只保留两个入口：

- 单品测算
- 规则设置

单品测算保留：

- 物流标准匹配
- 物流时效选择
- 货值区间选择
- CNY/RUB 汇率手动填写或自动更新
- 平台佣金、提现手续费、退货率、税费预留
- 建议售价、总成本、净利润、利润率、保本售价和上架判断
- 简化 PPC 点击付费承受能力测算

规则设置可以维护：

- 默认费用参数
- 税费比例
- 汇率设置
- 平台佣金率规则
- 物流标准规则
- 货值区间
- 物流价格规则
- 物流时效价格

批量计算、独立推广测算、CPO、PPC + CPO 组合推广、复杂推广建议等入口已在页面中隐藏。

## 项目入口

Streamlit 入口文件：

```text
app.py
```

Streamlit Community Cloud 部署时，`Main file path` 填：

```text
app.py
```

## 本地运行方法

进入项目根目录后运行：

```bash
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py
```

启动后浏览器通常会打开：

```text
http://localhost:8501
```

## Streamlit Community Cloud 部署方法

1. 将项目上传到 GitHub。
2. 打开 [share.streamlit.io](https://share.streamlit.io/)。
3. 登录并连接 GitHub。
4. 点击 `Create app`。
5. 选择仓库和分支，通常是 `main`。
6. `Main file path` 填 `app.py`。
7. 点击部署。

本阶段不需要配置 Secrets，也不要上传密码、API key 或其他敏感信息。

## 必须上传的文件

```text
app.py
pricing_engine.py
promotion_engine.py
exchange_rate.py
requirements.txt
README.md
.gitignore
data/settings.json
data/commission_rules.csv
data/logistics_standards.csv
data/logistics_prices.csv
```

建议同时上传：

```text
scripts/generate_assets.py
data/Ozon批量导入模板.xlsx
data/Ozon示例数据.xlsx
```

模板和示例数据当前不会在简化页面中展示，但保留它们方便后续恢复批量功能。

## 不要上传的文件

```text
venv/
.venv/
__pycache__/
*.pyc
.env
.DS_Store
data/exchange_rate_cache.json
.streamlit/secrets.toml
exports/
outputs/
```

`data/exchange_rate_cache.json` 是汇率缓存文件。部署到 Streamlit Community Cloud 后，工具会在运行时自动重新生成缓存。

## PPC 简化测算口径

单品测算完成后，结果区下方会显示“PPC 点击付费承受能力”。

只需要输入：

```text
每次点击出价 CPC，单位卢布
```

计算公式：

```text
CPC 人民币 = CPC 卢布 ÷ 当前汇率
PPC 盈亏平衡点击数 = 当前单品净利润 ÷ CPC 人民币
PPC 盈亏平衡转化率 = 1 ÷ PPC 盈亏平衡点击数
```

页面会显示：

```text
约 X 次点击内必须出 1 单，PPC 才能盈亏持平。
```

## 默认规则

- 境内段运费：3 元。
- 提现手续费费率：1%。
- 退货率：0%。
- 其他费用：0 元。
- 税费比例：0%。
- 默认汇率：1 人民币 = 12.5 卢布，可手动修改，也可自动更新。
- 默认类目：建筑和装修。

## 汇率缓存

自动汇率缓存文件：

```text
data/exchange_rate_cache.json
```

该文件不需要上传 GitHub。网络正常时，工具会从俄罗斯央行 Bank of Russia 获取 CNY/RUB 汇率；如果自动获取失败，会使用上一次缓存汇率；如果没有缓存，则使用默认汇率并提示用户手动确认。
