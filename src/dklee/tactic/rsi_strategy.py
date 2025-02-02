import sys
import os

# 상위 디렉토리를 파이썬 경로에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))  # crypto_backtest 디렉토리
src_dir = os.path.join(project_root, 'src')
sys.path.insert(0, src_dir)  # src 디렉토리를 최우선 경로로 추가

# 환경 변수 설정을 위한 .env 파일 경로 설정
from dotenv import load_dotenv
env_path = os.path.join(src_dir, '.env')
load_dotenv(env_path)

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sqlalchemy import text
from util.db_engine import engine
from backtest_class import Backtest
import argparse
from typing import Optional

def fetch_price_data(start_date: datetime, end_date: datetime, market: str = 'KRW-BTC') -> pd.DataFrame:
    """지정된 기간의 가격 데이터를 가져옵니다."""
    query = text("""
        SELECT timestamp_kst, close
        FROM upbit_1hour_price
        WHERE market = :market
        AND timestamp_kst BETWEEN :start_date AND :end_date
        ORDER BY timestamp_kst
    """)
    
    with engine.connect() as conn:
        df = pd.read_sql_query(
            query,
            conn,
            params={"market": market, "start_date": start_date, "end_date": end_date}
        )
    return df

def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """RSI 지표를 계산합니다."""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def run_rsi_strategy(
    start_date: datetime,
    end_date: datetime,
    initial_balance: float = 10_000_000,
    rsi_period: int = 14,
    oversold_threshold: float = 30,
    overbought_threshold: float = 70,
    position_size: float = 0.2,  # 보유 현금의 20%를 투자
    market: str = 'KRW-BTC'
) -> None:
    """RSI 전략으로 백테스팅을 실행합니다."""
    
    # 백테스트 인스턴스 생성
    backtest = Backtest(
        backtest_id=f'rsi_strategy_{datetime.now().strftime("%Y%m%d_%H%M")}',
        market_name='upbit',
        initial_balance=initial_balance,
        save_db=False  # DB 저장 비활성화
    )
    
    # 가격 데이터 조회
    df = fetch_price_data(start_date, end_date, market)
    df['rsi'] = calculate_rsi(df['close'], rsi_period)
    
    # 초기 상태
    in_position = False
    entry_price = 0
    trade_count = 0
    profitable_trades = 0
    total_profit_loss = 0
    current_trade = None  # 현재 진행 중인 거래 정보
    
    print("\n=== RSI 전략 백테스팅 시작 ===")
    print(f"시작 시간: {start_date}")
    print(f"종료 시간: {end_date}")
    print(f"초기 투자금: {initial_balance:,.0f}원")
    print("=" * 60)
    
    # 전략 실행
    for i in range(rsi_period + 1, len(df)):
        current_time = df['timestamp_kst'].iloc[i]
        current_price = df['close'].iloc[i]
        current_rsi = df['rsi'].iloc[i]
        
        try:
            if not in_position and current_rsi <= oversold_threshold:
                # 매수 신호
                available_balance = backtest.cash_balance
                quantity = (available_balance * position_size) / current_price
                
                if quantity * current_price >= 5000:  # 최소 주문금액 5000원
                    trade_count += 1
                    backtest.buy(
                        date=current_time,
                        crypto_name=market,
                        price=current_price,
                        quantity=quantity,
                        fee_type='percent',
                        fee_amount=0.0005
                    )
                    in_position = True
                    entry_price = current_price
                    
                    # 현재 거래 정보 저장
                    current_trade = {
                        'entry_price': current_price,
                        'entry_time': current_time,
                        'quantity': quantity
                    }
                    
                    print(f"\n[매수 #{trade_count}]")
                    print(f"시간: {current_time}")
                    print(f"가격: {current_price:,.0f}원")
                    print(f"수량: {quantity:.8f} {market}")
                    print(f"매수 금액: {(quantity * current_price):,.0f}원")
                    print(f"RSI: {current_rsi:.2f}")
                    print(f"현금 잔고: {backtest.cash_balance:,.0f}원")
                    
            elif in_position and current_rsi >= overbought_threshold:
                # 매도 신호
                quantity = backtest.get_quantity(market)
                if quantity > 0:
                    before_balance = backtest.get_portfolio_value(current_time)
                    backtest.sell(
                        date=current_time,
                        crypto_name=market,
                        price=current_price,
                        quantity=quantity,
                        fee_type='percent',
                        fee_amount=0.0005
                    )
                    after_balance = backtest.get_portfolio_value(current_time)
                    
                    # 거래 수익/손실 계산
                    profit_loss = after_balance - before_balance
                    profit_loss_pct = (current_price / entry_price - 1) * 100
                    total_profit_loss += profit_loss
                    
                    # 수익이 발생한 거래 카운트
                    if profit_loss_pct > 0:
                        profitable_trades += 1
                    
                    print(f"\n[매도 #{trade_count}]")
                    print(f"시간: {current_time}")
                    print(f"가격: {current_price:,.0f}원")
                    print(f"수량: {quantity:.8f} {market}")
                    print(f"매도 금액: {(quantity * current_price):,.0f}원")
                    print(f"RSI: {current_rsi:.2f}")
                    print(f"거래 수익률: {profit_loss_pct:+.2f}%")
                    print(f"거래 손익: {profit_loss:+,.0f}원")
                    print(f"현금 잔고: {backtest.cash_balance:,.0f}원")
                    
                    in_position = False
                    current_trade = None
                    
        except ValueError as e:
            print(f"\n거래 실패: {e}")
            continue
    
    # 최종 결과 출력
    final_value = backtest.get_portfolio_value(end_date)
    total_return = (final_value / initial_balance - 1) * 100
    
    print("\n" + "=" * 60)
    print("=== 백테스팅 최종 결과 ===")
    print(f"투자 코인: {market}")
    print(f"시작 금액: {initial_balance:,.0f}원")
    print(f"최종 금액: {final_value:,.0f}원")
    print(f"총 수익률: {total_return:+.2f}%")
    print(f"총 손익: {(final_value - initial_balance):+,.0f}원")
    print(f"총 거래 횟수: {trade_count}회")
    if trade_count > 0:
        print(f"승률: {(profitable_trades/trade_count*100):.1f}% ({profitable_trades}/{trade_count})")
        print(f"평균 거래 손익: {(total_profit_loss/trade_count):+,.0f}원")
    else:
        print("거래 없음")

def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """날짜 문자열을 datetime 객체로 변환합니다."""
    if not date_str:
        return None
    try:
        # 날짜를 KST timezone으로 변환
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    except ValueError:
        raise ValueError("날짜는 YYYY-MM-DD 형식으로 입력해주세요.")

def get_available_date_range() -> tuple[datetime, datetime]:
    """데이터베이스에서 사용 가능한 날짜 범위를 조회합니다."""
    query = text("""
        SELECT 
            DATE_TRUNC('day', MIN(timestamp_kst))::timestamp,
            DATE_TRUNC('day', MAX(timestamp_kst))::timestamp
        FROM upbit_1hour_price
        WHERE market = 'KRW-BTC'
    """)
    
    with engine.connect() as conn:
        result = conn.execute(query).first()
        # timezone 정보 제거
        return (
            result[0].replace(tzinfo=None),
            result[1].replace(tzinfo=None)
        )

def get_available_coins() -> list[str]:
    """데이터베이스에서 사용 가능한 코인 목록을 조회합니다."""
    query = text("""
        SELECT DISTINCT market
        FROM upbit_1hour_price
        WHERE market IN ('KRW-BTC', 'KRW-ETH', 'KRW-XRP')
        ORDER BY market
    """)
    
    with engine.connect() as conn:
        result = conn.execute(query)
        return [row[0] for row in result]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='RSI 전략으로 암호화폐 백테스팅을 실행합니다.')
    
    parser.add_argument('--start-date', type=str, help='시작 날짜 (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='종료 날짜 (YYYY-MM-DD)')
    parser.add_argument('--initial-balance', type=float, default=10_000_000,
                      help='초기 투자금액 (기본값: 10,000,000원)')
    parser.add_argument('--rsi-period', type=int, default=14,
                      help='RSI 계산 기간 (기본값: 14)')
    parser.add_argument('--oversold', type=float, default=30,
                      help='과매도 RSI 기준값 (기본값: 30)')
    parser.add_argument('--overbought', type=float, default=70,
                      help='과매수 RSI 기준값 (기본값: 70)')
    parser.add_argument('--position-size', type=float, default=0.2,
                      help='포지션 크기 (0.0 ~ 1.0, 기본값: 0.2)')
    
    # 코인 선택 인자 추가
    parser.add_argument('--coin', type=str, default='KRW-BTC',
                      choices=['KRW-BTC', 'KRW-ETH', 'KRW-XRP'],
                      help='거래할 코인 (기본값: KRW-BTC)')
    
    args = parser.parse_args()
    
    try:
        # 사용 가능한 코인 목록 조회
        available_coins = get_available_coins()
        if args.coin not in available_coins:
            raise ValueError(f"선택한 코인({args.coin})의 데이터가 없습니다. 사용 가능한 코인: {', '.join(available_coins)}")
        
        # 사용 가능한 전체 날짜 범위 조회
        db_start_date, db_end_date = get_available_date_range()
        
        # 입력된 날짜 파싱
        start_date = parse_date(args.start_date)
        end_date = parse_date(args.end_date)
        
        # 날짜 범위 조정
        if start_date is None:
            start_date = db_start_date
        if end_date is None:
            end_date = db_end_date
            
        # 날짜 범위 유효성 검사
        if start_date > end_date:
            raise ValueError("시작 날짜가 종료 날짜보다 늦을 수 없습니다.")
        if start_date < db_start_date:
            print(f"경고: 시작 날짜가 가능한 범위보다 이릅니다. {db_start_date.date()}로 조정됩니다.")
            start_date = db_start_date
        if end_date > db_end_date:
            print(f"경고: 종료 날짜가 가능한 범위보다 늦습니다. {db_end_date.date()}로 조정됩니다.")
            end_date = db_end_date
            
        print(f"\n=== {args.coin} RSI 전략 백테스팅 ===")
        print(f"데이터 기간: {db_start_date.date()} ~ {db_end_date.date()}")
        print(f"백테스팅 기간: {start_date.date()} ~ {end_date.date()}")
        
        # RSI 전략 실행 시 선택한 코인 전달
        run_rsi_strategy(
            start_date=start_date,
            end_date=end_date,
            initial_balance=args.initial_balance,
            rsi_period=args.rsi_period,
            oversold_threshold=args.oversold,
            overbought_threshold=args.overbought,
            position_size=args.position_size,
            market=args.coin  # 코인 정보 전달
        )
        
    except ValueError as e:
        print(f"오류: {e}")
        parser.print_help() 