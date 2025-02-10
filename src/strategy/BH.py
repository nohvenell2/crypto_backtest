import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backtest_class import Backtest
from sqlalchemy import text
from util.db_engine import engine
import pandas as pd

def get_historical_data(engine, market, start_date, end_date):
    query = text("""
        SELECT timestamp_kst, open, high, low, close, volume
        FROM upbit_daily_price
        WHERE market = :market
        AND timestamp_kst BETWEEN :start_date AND :end_date
        ORDER BY timestamp_kst
    """)
    
    df = pd.read_sql_query(
        query,
        engine,
        params={'market': market, 'start_date': start_date, 'end_date': end_date}
    )
    return df
def run_backtest(backtest_id,crypto_name, start_date, end_date, fee=0.0005, initial_balance=10000000, save_db=False, debug=False):
    backtest = Backtest(backtest_id=backtest_id, start_date=start_date, save_db=save_db, debug=debug)
    df = get_historical_data(engine, crypto_name, start_date, end_date)
    buy_price = float(df['open'].iloc[0])
    sell_price = float(df['close'].iloc[-1])
    quantity = (initial_balance / (buy_price * (1 + fee))) * 0.999
    backtest.buy(start_date, crypto_name, buy_price, quantity, fee_type='percent', fee_amount=fee)
    backtest.sell(end_date, crypto_name, sell_price, quantity, fee_type='percent', fee_amount=fee)
    return backtest



if __name__ == '__main__':
    run_backtest('BH_2022', 'KRW-BTC', '2022-01-01', '2022-12-31', fee=0.0005, debug=True,save_db=True)
    run_backtest('BH_2023', 'KRW-BTC', '2023-01-01', '2023-12-31', fee=0.0005, debug=True,save_db=True)
    run_backtest('BH_2024', 'KRW-BTC', '2024-01-01', '2024-12-31', fee=0.0005, debug=True,save_db=True)

