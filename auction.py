import akshare as ak
import pandas as pd
import os
import time
from datetime import datetime

CSV_PATH = "auction_data.csv"

def is_trade_day(today_str):
    """判断是否A股交易日，周末节假日自动跳过"""
    d = datetime.strptime(today_str, "%Y%m%d")
    try:
        cal_df = ak.tool_trade_date_hist_sina()
        cal_df["trade_date"] = pd.to_datetime(cal_df["trade_date"]).dt.strftime("%Y-%m-%d")
        trade_set = set(cal_df["trade_date"].tolist())
        return d.strftime("%Y-%m-%d") in trade_set
    except Exception as e:
        print(f"交易日历获取失败，降级判断周末：{e}")
        return d.weekday() < 5

def normalize_df(df):
    rename_map = {
        "最新价": "最新价", "现价": "最新价", "price": "最新价", "current": "最新价",
        "昨收": "昨收", "pre_close": "昨收", "prev_close": "昨收",
        "涨跌幅": "涨跌幅", "涨幅": "涨跌幅", "change_pct": "涨跌幅", "pct_chg": "涨跌幅",
    }
    df = df.rename(columns=rename_map)
    cols = [c for c in ["最新价", "昨收", "涨跌幅"] if c in df.columns]
    if len(cols) < 3:
        return None
    return df[["最新价", "昨收", "涨跌幅"]].copy()

def fetch_data():
    sources = [
        ("东方财富", lambda: ak.stock_zh_a_spot_em()),
        ("新浪", lambda: ak.stock_zh_a_spot()),
        ("腾讯", lambda: ak.stock_zh_a_spot_tx()),
    ]
    for name, func in sources:
        for retry in range(2):
            try:
                print(f"尝试数据源: {name}(第{retry+1}次)...")
                df = normalize_df(func())
                if df is not None:
                    print(f"✓ 使用数据源: {name}")
                    return df
            except Exception as e:
                print(f"  {name}失败: {type(e).__name__}")
            time.sleep(1)
    raise RuntimeError("所有数据源获取失败")

def main():
    today = datetime.now().strftime("%Y%m%d")
    if not is_trade_day(today):
        print(f"{today} 非交易日，跳过采集")
        return

    df = fetch_data()
    df["最新价"] = pd.to_numeric(df["最新价"], errors="coerce")
    df["昨收"] = pd.to_numeric(df["昨收"], errors="coerce")
    df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
    df = df.dropna(subset=["最新价", "昨收", "涨跌幅"])
    df = df[df["最新价"] > 0]

    up_count = len(df[df["最新价"] > df["昨收"]])
    down_count = len(df[df["最新价"] < df["昨收"]])
    flat_count = len(df[df["最新价"] == df["昨收"]])
    limit_up = len(df[df["涨跌幅"] >= 9.9])
    limit_down = len(df[df["涨跌幅"] <= -9.9])

    row = {
        "日期": today,
        "上涨家数": up_count,
        "下跌家数": down_count,
        "平盘家数": flat_count,
        "涨停家数": limit_up,
        "跌停家数": limit_down
    }
    print(row)

    file_exists = os.path.exists(CSV_PATH)
    pd.DataFrame([row]).to_csv(CSV_PATH, mode="a", header=not file_exists, index=False, encoding="utf-8-sig")
    print("数据写入完成")

if __name__ == "__main__":
    main()
