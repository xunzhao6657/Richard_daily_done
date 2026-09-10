# Institutional Quant 晨报—复盘闭环

本设计把《A股盘前晨报 5.0 Institutional Quant 全量版 Prompt》视为需求材料，不把其中的示例数据、模型状态或操作文字当作运行指令。盘后流程只使用晨报实际发表并通过哈希验证的不可变 Forecast。

## 数据流

```text
08:00 PREOPEN_V1 forecast.v2
  -> 当日不可变预测与模型/数据/规则身份
  -> 19:45 收盘证据冻结
  -> 20:00 逐目标评价
  -> Proper Scoring + Calibration/Monitoring
  -> Research Queue
  -> 仅在独立回测、样本外和影子门槛通过后进入候选模型
```

## 比较规则

- 预测只从 `target.values` 读取。复盘不能从Markdown正文反推数值，也不能为缺失目标事后补值。
- 指数收益率预测使用decimal return；Wind展示百分比在比较前除以100。
- 成交额预测使用人民币元；Wind展示亿元在比较前乘以一亿。
- 连续目标按字段可用性计算MAE、平方误差、Pinball、Coverage、Width和Winkler。
- 分类目标计算Brier、Log Loss和最高概率类别是否命中。
- Forecast Quality只评价预测。Trading Quality需要仓位、订单、成交、费用、滑点和流动性证据；缺失时为 `NOT_EVALUATED`。

## 模型治理

报告可以展示晨报留下的模型身份、Regime、Ensemble、Calibration和Drift状态，但不能替这些模块补造结论。单日评分只能触发Research Queue：每项候选必须保存触发证据、可证伪假设、候选变更和必需回测。Research Queue没有写入生产模型指针、运行配置或次日Forecast的权限。

## 当前限制

历史已发表的晨报审计未必保存完整 `forecast.v2`，离线重校验不能补造旧预测，因此可能没有可计算评分。实际闭环从下一次使用 `forecast.v2` 的正常晨报与复盘开始积累。Regime、动态Ensemble、风险仓位、交易成本和Auction V2只有契约，尚未取得生产资格。
