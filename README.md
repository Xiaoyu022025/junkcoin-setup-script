### 监控 bonk.fun（SOL 底池）交易对

本仓库提供一个轻量脚本，基于 DexScreener 公共 API，监控给定 Solana 代币的 SOL 报价交易对（适用于 bonk.fun / Pump 风格代币）。

#### 环境要求
- Python 3.9+
- 无需额外依赖（使用标准库）

#### 快速开始
1) 将目标代币的 Mint 地址准备好

2) 直接运行：
```bash
python3 monitor_bonk_fun_pools.py --mints <MINT1> <MINT2> --interval 5 --min-sol-liq 5 --sort fdv --dex pumpswap
```

参数说明：
- `--mints`: 一个或多个代币的 Mint 地址
- `--interval`: 轮询周期（秒）。0 表示只查询一次
- `--min-sol-liq`: 仅显示 SOL 数量不小于该值的底池
- `--sort`: 排序字段，可选：price, fdv, solLiq, usdLiq, volume24h
- `--json`: 以 JSON 行输出，方便管道处理
 - `--dex`: 仅展示指定 DEX（默认 `pumpswap`，代表 bonk.fun/pump 风格；传 `any` 关闭过滤）

示例（只查询一次，显示人类可读信息）：
```bash
python3 monitor_bonk_fun_pools.py --mints <MINT1> <MINT2> --min-sol-liq 3 --sort volume24h --dex pumpswap
```

示例（持续轮询并输出 JSON，适合日志采集对接）：
```bash
python3 monitor_bonk_fun_pools.py --mints <MINT1> --interval 10 --dex pumpswap --json | jq '.'
```

#### 工作原理
- 通过 `https://api.dexscreener.com/latest/dex/tokens/{MINT}` 查询交易对
- 过滤 `quote` 为 WSOL（`So11111111111111111111111111111111111111112`）或 symbol 为 `SOL` 的池子
- 打印价格、FDV、池子流动性（包含 SOL 数量）、24h 成交量与交易数等

#### 进阶：链上实时订阅
如果需要更实时、细粒度的逐笔交易级监听，可结合 Helius / Shyft / Jito 等服务使用 Webhook 或 WebSocket 订阅 Solana 交易，并解析相关 AMM 或 Pump Program 的事件。

#### 免责声明
本脚本仅用于数据观察与学习，谨慎交易，风险自担。

# junkcoin-setup-script
