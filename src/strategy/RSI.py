import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backtest_class import Backtest
from sqlalchemy import text
from util.db_engine import engine
import pandas as pd
import math
import numpy as np

def get_historical_data(engine, market, start_date, end_date):
    query = text("""
        SELECT timestamp_kst, open, high, low, close, volume
        FROM upbit_1hour_price
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

def calculate_rsi(data, periods=14):
    # 종가 기준 차이 계산
    delta = data['close'].diff()
    
    # 상승분과 하락분 분리
    gain = (delta.where(delta > 0, 0)).rolling(window=periods).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periods).mean()
    
    # RS 계산
    rs = gain / loss
    
    # RSI 계산
    rsi = 100 - (100 / (1 + rs))
    return rsi

def run_backtest(crypto_name, rsi_period=14, overbought=70, oversold=30, fee=0.0005, start_date='2022-01-01', end_date='2022-12-31', save_db=False):
    # 데이터 가져오기
    df = get_historical_data(engine, crypto_name, start_date, end_date)
    
    # RSI 계산
    df['rsi'] = calculate_rsi(df, rsi_period)
    
    # 백테스트 객체 생성
    backtest = Backtest(backtest_id='RSI전략_temp', save_db=save_db)
    position = False

    # RSI가 계산되기 전 기간은 건너뛰기
    df = df[rsi_period+1:].reset_index(drop=True)
    
    for id, row in df.iterrows():
        current_rsi = row['rsi']
        
        # 보유 중인 경우 과매수 상태면 매도
        if position and current_rsi > overbought:
            backtest.sell(
                date = row['timestamp_kst'],
                price = row['close'],
                quantity = backtest.get_quantity(crypto_name),
                crypto_name = crypto_name,
                fee_type='percent',
                fee_amount=fee
            )
            position = False
            
        # 미보유 중인 경우 과매도 상태면 매수
        elif not position and current_rsi < oversold:
            try:
                quantity = (backtest.cash_balance / (row['close'] * (1 + fee))) * 0.999
                backtest.buy(
                    date = row['timestamp_kst'],
                    price = row['close'],
                    quantity = quantity,
                    crypto_name = crypto_name,
                    fee_type='percent',
                    fee_amount=fee
                )
                position = True
            except Exception as e:
                raise e

    # 거래 로그 출력
    for i in backtest.transaction_log:
        print(f'{i["date"]} {i["crypto_name"]} {i["transaction_type"]} // {i["price"]} {i["quantity"]} {i["total_amount"]}')
        print(f'CASH : {math.floor(i["cash_balance"])} ASSET : {math.floor(i["asset_value"])} TOTAL : {math.floor(i["total_value"])} RETURN : {math.floor(i["return"]*10000)/10000}%')

if __name__ == '__main__':
    run_backtest(
        'KRW-BTC',
        rsi_period=14,      # RSI 계산 기간
        overbought=70,      # 과매수 기준값
        oversold=30,        # 과매도 기준값
        fee=0.0005,
        start_date='2024-01-01',
        end_date='2024-12-31'
    )
