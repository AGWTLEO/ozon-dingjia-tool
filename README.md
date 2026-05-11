# Ozon 定制自动定价工具

这是一个基于 Streamlit 的 Ozon 跨境电商定价、利润和推广测算工具。

当前版本是公开使用版本，不包含登录密码、不做访问限制、不连接 Ozon 后台、不做自动上品。

## 工具用途

工具用于在上架或推广前快速测算 SKU 的价格、利润、物流费用和推广承受能力。

主要功能：

- 单品定价：输入成本、尺寸、货值区间、物流时效、类目、售价和目标利润率，自动计算建议售价、净利润、利润率和上架结论。
- 批量计算：导入 Excel 后批量计算多个 SKU，并导出结果 Excel。
- 推广测算：基于定价结果测算 PPC 点击付费、CPO 订单付费和 PPC + CPO 组合推广风险。
- 规则设置：维护类目佣金率、物流标准、物流价格表、默认费用、税费和汇率。
- 结果导出：导出最近一次单品或批量测算结果。
- 汇率自动更新：可从俄罗斯央行 Bank of Russia 获取 CNY/RUB 汇率，并使用本地缓存。

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

先进入项目根目录，然后安装依赖并启动：

```bash
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py
```

启动后浏览器通常会打开：

```text
http://localhost:8501
```

## GitHub 上传方法

1. 在 GitHub 新建一个仓库。
2. 把本项目文件提交到仓库。
3. 确认至少包含这些文件和目录：

```text
app.py
pricing_engine.py
promotion_engine.py
exchange_rate.py
requirements.txt
README.md
.gitignore
data/
```

4. 推送到 GitHub：

```bash
git add .
git commit -m "准备 Streamlit Cloud 部署版本"
git branch -M main
git remote add origin https://github.com/你的用户名/你的仓库名.git
git push -u origin main
```

如果已经绑定过远程仓库，不需要重复执行 `git remote add origin ...`。

## Streamlit Community Cloud 部署方法

参考 Streamlit 官方文档：

- [Deploy your app on Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)
- [File organization for Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization)

部署步骤：

1. 打开 [share.streamlit.io](https://share.streamlit.io/)。
2. 登录并连接 GitHub。
3. 点击 `Create app`。
4. 选择当前 GitHub 仓库和分支，通常是 `main`。
5. `Main file path` 填：

```text
app.py
```

6. 点击部署。

本阶段不需要配置 Secrets，也不要上传密码、API key 或其他敏感信息。

## 部署时必须一起上传的文件

`data/` 目录里的规则表必须一起上传，否则工具无法使用默认规则：

```text
data/settings.json
data/commission_rules.csv
data/logistics_standards.csv
data/logistics_prices.csv
data/Ozon批量导入模板.xlsx
data/Ozon示例数据.xlsx
```

说明：

- `data/settings.json`：默认费用、税费、汇率等参数。
- `data/commission_rules.csv`：类目佣金率表。
- `data/logistics_standards.csv`：物流标准匹配规则。
- `data/logistics_prices.csv`：物流时效价格表。
- `data/Ozon批量导入模板.xlsx`：批量导入模板。
- `data/Ozon示例数据.xlsx`：示例数据。

## 不要上传的文件

以下文件属于本地环境、缓存或运行输出，不建议上传：

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

## 规则设置在云端的注意事项

公开部署后，别人打开链接即可使用本工具。

由于本阶段没有登录和访问限制，页面里的“规则设置”也会暴露给访问者。Streamlit Community Cloud 的运行文件系统适合临时运行，不适合作为长期数据库。云端页面中修改的规则可能只在当前运行环境临时生效；如果需要永久修改默认规则，建议直接更新 GitHub 仓库里的 `data/` 规则文件后重新部署。

## 批量导入字段

Excel 输入字段：

```text
SKU
产品名称
所属类目
采购成本
境内段运费
包装费
其他费用
重量g
长cm
宽cm
高cm
货值区间
物流时效
当前售价人民币
目标利润率
汇率
广告费比例
提现手续费费率
退货率
税费比例
CPC卢布
CPC人民币
预计点击转化率
测试点击数
PPC每周预算卢布
CPO模式
CPO费率
是否组合推广
```

比例字段可以填小数，例如 `0.2` 表示 20%。如果填 `20`，程序也会按 20% 处理。

`货值区间` 可填：

```text
1-1500
1-1500₽
1501-7000
1501-7000₽
7001-250000
7001-250000₽
```

`物流时效` 可填：

```text
5-10天
10-15天
15-25天
```

Big 和 Premium Big 不支持 `5-10天`。

## 默认规则

- 境内段运费：3 元。
- 广告费比例：0%。
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
