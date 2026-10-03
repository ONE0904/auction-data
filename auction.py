# -*- coding: utf-8 -*-
"""云端版: 9:25竞价数据自动记录 (GitHub Actions运行)"""
import akshare as ak
import pandas as pd
import os
import time
from datetime import datetime, time as dtime

CSV_PATH = "auction_data.csv"
TEST = False   # 云端正式模式

def is_trade_day(today_str):
    d = datetime.strptime(today_str, "%Y%m%d")
    try:
        cal_df = ak.tool_trade_date_hist_sina()
        cal_df["trade_date"] = pd.to_datetime(cal_df["trade_date"]).dt.strftime("%Y-%m-%d")
        trade_set = set(cal_df["trade_date"].tolist())
        return d.strftime("%Y-%m-%d") in trade_set
    except Exception:
        return d.weekday() < 5

def in_auction_window():
    now = datetime.now().time()
    return dtime(9,25,0) <= now <= dtime(9,30,0)

def normalize_df(df):
    rename_map = {
        "代码": "code", "名称": "name", "最新价": "last",
        "昨收": "pre_close", "涨跌幅": "pct_chg", "涨跌幅(%)": "pct_chg",
    }
    df = df.rename(columns=rename_map)
    keep_cols = ["code", "name", "last", "pre_close", "pct_chg"]
    exist_cols = [c for c in keep_cols if c in df.columns]
    return df[exist_cols].copy()

def fetch_all_spot():
    sources = [
        ("新浪", lambda: ak.stock_zh_a_spot()),
        ("东方财富", lambda: ak.stock_zh_a_spot_em()),
        ("腾讯", lambda: ak.stock_zh_a_spot_tx()),
    ]
    for name, func in sources:
        for retry in range(3):
            try:
                print(f"尝试全市场数据源: {name}(第{retry+1}次)...")
                df = normalize_df(func())
                if df is not None and len(df) > 1000:
                    print(f"✓ 使用全市场数据源: {name}")
                    return df
            except Exception as e:
                print(f"  {name}失败: {repr(e)}")
                time.sleep(2)
    raise RuntimeError("全部全市场行情源获取失败")

def classify(row):
    code = str(row["code"]).strip().lower()
    name = str(row["name"])
    if "ST" in name:
        return "st"
    if code.startswith(("sh", "sz", "bj")):
        code = code[2:]
    if code.startswith(("60", "000", "001", "002")):
        return "main"
    if code.startswith("688"):
        return "kcb"
    if code.startswith(("300", "301")):
        return "cyb"
    if code.startswith(("83", "87", "88")):
        return "bj"
    return "other"

def get_pool_by_board(pool_df):
    cnt = {"main":0, "kcb":0, "cyb":0, "bj":0, "st":0}
    pool_df = pool_df.rename(columns={"代码":"code","名称":"name"})
    if "code" not in pool_df.columns or "name" not in pool_df.columns:
        return cnt
    for _, r in pool_df.iterrows():
        b = classify(r)
        if b != "other":
            cnt[b] += 1
    return cnt

def main():
    today = datetime.now().strftime("%Y%m%d")

    if not TEST:
        if not is_trade_day(today):
            print(f"{today} 非交易日, 跳过采集"); return
        if not in_auction_window():
            print(f"当前不在9:25~9:30竞价窗口, 跳过(避免混入盘中数据)"); return

    df = fetch_all_spot()
    df["last"] = pd.to_numeric(df["last"], errors="coerce")
    df["pre_close"] = pd.to_numeric(df["pre_close"], errors="coerce")
    df["pct_chg"] = pd.to_numeric(df["pct_chg"], errors="coerce")
    df = df.dropna(subset=["code","name","last","pre_close","pct_chg"])
    df = df[df["last"] > 0]
    df["board"] = df.apply(classify, axis=1)

    up_down = {}
    for b in ["main","kcb","cyb","bj","st"]:
        sub = df[df["board"]==b]
        up_down[b+"_up"]   = int((sub["pct_chg"] > 0).sum())
        up_down[b+"_down"] = int((sub["pct_chg"] < 0).sum())

    try:
        zt = ak.stock_zt_pool_em(date=today)
        zt_cnt = get_pool_by_board(zt)
    except Exception as e:
        print("涨停池获取失败:", e)
        zt_cnt = {"main":0,"kcb":0,"cyb":0,"bj":0,"st":0}
    try:
        dt = ak.stock_zt_pool_dtgc_em(date=today)
        dt_cnt = get_pool_by_board(dt)
    except Exception as e:
        print("跌停池获取失败:", e)
        dt_cnt = {"main":0,"kcb":0,"cyb":0,"bj":0,"st":0}

    row = {
        "日期": today,
        "主板上涨家数": up_down["main_up"],   "主板下跌家数": up_down["main_down"],
        "主板涨停家数": zt_cnt["main"],       "主板跌停家数": dt_cnt["main"],
        "北交所上涨家数": up_down["bj_up"],   "北交所下跌家数": up_down["bj_down"],
        "北交所涨停家数": zt_cnt["bj"],       "北交所跌停家数": dt_cnt["bj"],
        "科创板上涨家数": up_down["kcb_up"],  "科创板下跌家数": up_down["kcb_down"],
        "科创板涨停家数": zt_cnt["kcb"],      "科创板跌停家数": dt_cnt["kcb"],
        "创业板上涨家数": up_down["cyb_up"],  "创业板下跌家数": up_down["cyb_down"],
        "创业板涨停家数": zt_cnt["cyb"],      "创业板跌停家数": dt_cnt["cyb"],
        "ST上涨家数": up_down["st_up"],       "ST下跌家数": up_down["st_down"],
        "ST涨停家数": zt_cnt["st"],           "ST跌停家数": dt_cnt["st"],
    }
    print(row)

    file_exists = os.path.exists(CSV_PATH)
    pd.DataFrame([row]).to_csv(CSV_PATH, mode="a", header=not file_exists,
                               index=False, encoding="utf-8-sig")
    print("数据写入完成:", CSV_PATH)

if __name__ == "__main__":
    main()
