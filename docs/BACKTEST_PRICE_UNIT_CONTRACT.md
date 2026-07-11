# Backtest price-unit contract

Research history exports represent broker costs with explicit fields. `spread_points` is the raw MT5 `rates.spread` value in broker points; `point_size` is `symbol_info.point`; `tick_size` is persisted separately from authoritative symbol metadata; and `spread_price` is exactly `spread_points * point_size`.

`slippage_points` is broker points and is normalized to `slippage_price` with the same `point_size`. The backtest runner consumes only `spread_price` and `slippage_price` when calculating an effective entry. It fails closed when a positive point-based cost lacks metadata or when the two spread representations disagree.

Paginated manifests use `aqtf_mt5_paginated_history.v2`; range manifests use `aqtf_mt5_range_history.v2`. Both persist `price_unit_contract` metadata and a CSV SHA-256 hash. Old CSVs with an ambiguous raw `spread` column are not accepted for costed backtests.
