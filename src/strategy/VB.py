import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backtest_class import Backtest
from sqlalchemy import text
from util.db_engine import engine
import pandas as pd
import math
from datetime import datetime, timedelta

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


def run_backtest(backtest_id, crypto_name, start_date, end_date, k=0.7,fee=0.0005, save_db=False,debug=False):
    df = get_historical_data(engine, crypto_name, start_date, end_date)
    backtest = Backtest(backtest_id=backtest_id,start_date=datetime.fromisoformat(start_date),save_db=save_db,debug=debug)
    prev_high, prev_low, target_price, position, k_price = 0, 0, 0, False, 0
    for id, row in df.iterrows():
        # 최초 거래 시점 설정
        if id == 0: 
            prev_high = row['high']
            prev_low = row['low']
            target_price = prev_high - (prev_high - prev_low) * k
            continue
        # 목표값 계산
        k_price = (prev_high - prev_low) * k
        target_price = row['open'] + k_price
        # 변동성 돌파전략 판매 실행
        if position:
            backtest.sell(
                date = row['timestamp_kst'],
                price = row['open'],
                quantity = backtest.get_quantity(crypto_name),
                crypto_name = crypto_name,
                fee_type='percent',
                fee_amount=fee
            )
            position = False

        # 변동성 돌파전략 목표 가격으로 매수 실행 
        if row['high'] > target_price:
            try:
                quantity = (backtest.cash_balance / (target_price * (1 + fee)))*0.999
                # 거래 시각을 6시간 뒤로 조정
                trade_time = pd.to_datetime(row['timestamp_kst']) + timedelta(hours=6)
                backtest.buy(
                    date = trade_time,
                    price = target_price,
                    quantity = quantity,
                    crypto_name = crypto_name,
                    fee_type='percent',
                    fee_amount=0.00139
                )
            except Exception as e:
                raise e
            position = True
        # 이전 최고가, 최저가 업데이트
        prev_high = row['high']
        prev_low = row['low']
    print(f'{backtest.trades_count}회 거래 / 수익률 : {backtest.transaction_log[-1]["return_rate"]:.2%}')
if __name__ == '__main__':

    # 년도별 k 값 변경후 백테스트
    # 년도별 k 값 변경후 백테스트
    # 2022 backtest
    print('2022 backtest')
    run_backtest('VB_2022_k_05', 'KRW-BTC', '2022-01-01', '2022-12-31', k=0.5,fee=0.0005, save_db=True)
    run_backtest('VB_2022_k_07', 'KRW-BTC', '2022-01-01', '2022-12-31', k=0.7,fee=0.0005, save_db=True)
    run_backtest('VB_2022_k_10', 'KRW-BTC', '2022-01-01', '2022-12-31', k=1.0,fee=0.0005, save_db=True)
    # 2023 backtest
    print('2023 backtest')
    run_backtest('VB_2023_k_05', 'KRW-BTC', '2023-01-01', '2023-12-31', k=0.5,fee=0.0005, save_db=True)
    run_backtest('VB_2023_k_07', 'KRW-BTC', '2023-01-01', '2023-12-31', k=0.7,fee=0.0005, save_db=True)
    run_backtest('VB_2023_k_10', 'KRW-BTC', '2023-01-01', '2023-12-31', k=1.0,fee=0.0005, save_db=True)
    # 2024 backtest
    print('2024 backtest')
    run_backtest('VB_2024_k_05', 'KRW-BTC', '2024-01-01', '2024-12-31', k=0.5,fee=0.0005, save_db=True)
    run_backtest('VB_2024_k_07', 'KRW-BTC', '2024-01-01', '2024-12-31', k=0.7,fee=0.0005, save_db=True)
    run_backtest('VB_2024_k_10', 'KRW-BTC', '2024-01-01', '2024-12-31', k=1.0,fee=0.0005, save_db=True)
    # 2022-2024 backtest
    print('2022-2024 backtest')
    run_backtest('VB_2022_2024_k_05', 'KRW-BTC', '2022-01-01', '2024-12-31', k=0.5,fee=0.0005, save_db=True)
    run_backtest('VB_2022_2024_k_07', 'KRW-BTC', '2022-01-01', '2024-12-31', k=0.7,fee=0.0005, save_db=True)
    run_backtest('VB_2022_2024_k_10', 'KRW-BTC', '2022-01-01', '2024-12-31', k=1.0,fee=0.0005, save_db=True)    