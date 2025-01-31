from backtest_class import Backtest
from sqlalchemy import text
from util.db_engine import engine
import pandas as pd
import numpy as np
import math

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


def run_backtest(crypto_name, k=0.7,fee=0.0005, start_date='2022-01-01', end_date='2022-12-31',save_db=False):
    df = get_historical_data(engine, crypto_name, start_date, end_date)
    backtest = Backtest(backtest_id='변동성돌파전략_temp',save_db=save_db)
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
                backtest.buy(
                    date = row['timestamp_kst'],
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
    for i in backtest.transaction_log:
        print(f'{i["date"]} {i["crypto_name"]} {i["transaction_type"]} // {i["price"]} {i["quantity"]} {i["total_amount"]}')
        print(f'CASH : {math.floor(i["cash_balance"])} ASSET : {math.floor(i["asset_value"])} TOTAL : {math.floor(i["total_value"])} RETURN : {math.floor(i["return"]*100)}%')

if __name__ == '__main__':
    run_backtest('KRW-BTC', k=0.7,fee=0.0005, start_date='2024-01-01', end_date='2024-12-31')
