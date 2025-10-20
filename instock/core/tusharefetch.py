from tushare import pro as ts_pro

# 龙虎榜
def fetch_top_list(ts_code: str, trade_date: str):
    """https://tushare.pro/document/2?doc_id=106"""
    pro = ts_pro.ProApi()
    df = pro.top_list(ts_code=ts_code, trade_date=trade_date)
    return df
# 分红送股
def fetch_stocks_bonus(ts_code: str = None, ann_date: str = None):
    """https://tushare.pro/document/2?doc_id=103"""
    pro = ts_pro.ProApi()
    df = pro.bonus(ts_code=ts_code, ann_date=ann_date)
    return df