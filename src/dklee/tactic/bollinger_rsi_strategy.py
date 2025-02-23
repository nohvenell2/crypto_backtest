import argparse
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

import pandas as pd
from sqlalchemy import text

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from util.db_engine import engine
from backtest_class import Backtest

class BollingerRSIStrategy:
    def __init__(self, params: Dict[str, Any]):
        """
        볼린저 밴드 + RSI 전략 파라미터 초기화
        """
        self.params = params
    
    def calculate_signals(self, data: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """매수/매도 신호 생성"""
        # 볼린저 밴드 계산
        middle = data['close'].rolling(window=self.params['bb_period']).mean()
        std = data['close'].rolling(window=self.params['bb_period']).std()
        lower = middle - (std * self.params['bb_std'])
        upper = middle + (std * self.params['bb_std'])
        
        # RSI 계산
        delta = data['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.params['rsi_period']).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.params['rsi_period']).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        # 거래량 분석
        volume_ma = data['volume'].rolling(window=self.params['volume_ma_period']).mean()
        volume_surge = data['volume'] > volume_ma * self.params['volume_ratio']
        
        # 추세 분석
        short_ma = data['close'].rolling(window=10).mean()
        long_ma = data['close'].rolling(window=30).mean()
        trend = short_ma > long_ma
        
        # 매수 신호 - 조건 완화
        buy_signal = (
            (data['close'] < lower * 1.02) &  # 하단 밴드 근처 (1.01 -> 1.02)
            (rsi < self.params['rsi_oversold']) &  # 과매도
            (
                volume_surge |  # 거래량 급증 OR
                (data['close'].diff(2) > 0)  # 2시간 상승 반전
            )
        )
        
        # 매도 신호 - 조건 완화
        sell_signal = (
            (data['close'] > upper * 0.98) |  # 상단 밴드 근처
            (rsi > self.params['rsi_overbought']) |  # 과매수
            (
                (data['close'] < middle) &  # 중간 밴드 아래로 이탈
                (data['close'].diff(2) < 0)  # 2시간 하락 전환
            )
        )
        
        return buy_signal, sell_signal

# 전략 파라미터
params = {
    'bb_period': 20,        # 기본값으로 복원 (15 -> 20)
    'bb_std': 2.0,         # 기준 완화 (2.5 -> 2.0)
    'rsi_period': 14,      # RSI 기간 유지
    'rsi_oversold': 35,    # 과매도 기준 완화 (25 -> 35)
    'rsi_overbought': 70,  # 과매수 기준 완화 (75 -> 70)
    'volume_ma_period': 20, # 기본값으로 복원 (15 -> 20)
    'volume_ratio': 1.8,   # 거래량 기준 완화 (2.5 -> 1.8)
    'profit_target': 2.0,  # 이익실현 목표 완화 (2.5 -> 2.0)
    'stop_loss': -1.8,     # 손절 기준 조정 (-1.5 -> -1.8)
    'trailing_stop': 1.0,  # 트레일링 스탑 완화 (1.2 -> 1.0)
    'min_holding_hours': 3, # 최소 보유 시간 감소 (6 -> 3)
    'max_holding_hours': 48,# 최대 보유 시간 유지
    'max_loss_per_day': 2.5 # 일일 손실 한도 조정 (2.0 -> 2.5)
}

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
        return (
            result[0].replace(tzinfo=None),
            result[1].replace(tzinfo=None)
        )

def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """날짜 문자열을 datetime 객체로 변환합니다."""
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    except ValueError:
        raise ValueError("날짜는 YYYY-MM-DD 형식으로 입력해주세요.")

def run_bollinger_rsi_strategy(
    market: str,
    start_date: datetime,
    end_date: datetime,
    initial_balance: float = 10_000_000,
    position_size: float = 0.1
) -> None:
    """볼린저 밴드 + RSI 전략으로 백테스팅을 실행합니다."""
    
    # 데이터 조회
    query = text("""
        SELECT *
        FROM upbit_1hour_price
        WHERE market = :market
        AND timestamp_kst >= :start_date
        AND timestamp_kst < :end_date
        ORDER BY timestamp_kst
    """)
    
    with engine.connect() as conn:
        df = pd.read_sql_query(
            query,
            conn,
            params={
                'market': market,
                'start_date': start_date,
                'end_date': end_date
            }
        )
    
    if df.empty:
        print("해당 기간에 데이터가 없습니다.")
        return
    
    print(f"\n=== 볼린저 밴드 + RSI 전략 백테스팅 ===")
    print(f"데이터 기간: {df['timestamp_kst'].min().strftime('%Y-%m-%d')} ~ {df['timestamp_kst'].max().strftime('%Y-%m-%d')}")
    print(f"백테스팅 기간: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}")
    print(f"초기 투자금: {initial_balance:,.0f}원")
    print("=" * 60)
    
    # 백테스트 초기화
    backtest = Backtest(initial_balance, start_date)  # start_date 추가
    
    # 전략 인스턴스 생성
    strategy = BollingerRSIStrategy(params)
    
    # 매수/매도 신호 생성
    buy_signals, sell_signals = strategy.calculate_signals(df)
    
    # 초기 상태
    in_position = False
    entry_price = 0
    entry_time = None
    trade_count = 0
    profitable_trades = 0
    total_profit_loss = 0
    trades = []
    
    # 전략 실행
    for i in range(len(df)):
        current_time = df['timestamp_kst'].iloc[i]
        current_price = df['close'].iloc[i]
        
        try:
            if in_position:
                # 매도 여부 초기화
                should_sell = False
                sell_reason = ""
                
                # 최소 보유 시간 체크
                holding_hours = (current_time - entry_time).total_seconds() / 3600
                if holding_hours < params['min_holding_hours']:
                    continue
                
                # 최대 보유 시간 체크
                if holding_hours > params['max_holding_hours']:
                    should_sell = True
                    sell_reason = "보유시간 초과"
                
                # 현재 수익률 계산
                current_return = (current_price / entry_price - 1) * 100
                
                # 손절 체크
                if current_return <= params['stop_loss']:
                    should_sell = True
                    sell_reason = "손절"
                
                # 이익실현 체크
                elif current_return >= params['profit_target']:
                    should_sell = True
                    sell_reason = "이익실현"
                
                # 트레일링 스탑 로직
                elif current_return > params['profit_target'] * 0.5:
                    trailing_stop = max(params['trailing_stop'], current_return * 0.5)
                    if current_return - trailing_stop < 0:
                        should_sell = True
                        sell_reason = "트레일링 스탑"
                
                # 매도 시그널 체크
                elif sell_signals.iloc[i]:
                    should_sell = True
                    sell_reason = "매도신호"
                
                if should_sell:
                    quantity = backtest.get_quantity(market)
                    if quantity > 0:
                        backtest.sell(
                            date=current_time,
                            crypto_name=market,
                            price=current_price,
                            quantity=quantity,
                            fee_type='percent',
                            fee_amount=0.0005
                        )
                        
                        profit = (current_price / entry_price - 1) * 100
                        if profit > 0:
                            profitable_trades += 1
                        total_profit_loss += profit
                        
                        print(f"\n[매도 #{trade_count}] - {sell_reason}")
                        print(f"시간: {current_time}")
                        print(f"가격: {current_price:,.0f}원")
                        print(f"수량: {quantity:.8f} {market}")
                        print(f"매도 금액: {(quantity * current_price):,.0f}원")
                        print(f"거래 수익률: {profit:+.2f}%")
                        print(f"거래 손익: {(quantity * current_price - quantity * entry_price):+,.0f}원")
                        print(f"현금 잔고: {backtest.cash_balance:,.0f}원")
                        
                        in_position = False
                        
            else:
                available_balance = backtest.cash_balance
                
                if buy_signals.iloc[i] and available_balance > 5000:
                    # 일일 손실 체크
                    today = current_time.date()
                    today_trades = [t for t in trades if t['date'].date() == today]
                    today_loss = sum(t['profit'] for t in today_trades if t['profit'] < 0)
                    
                    if abs(today_loss) > params['max_loss_per_day'] * initial_balance / 100:
                        print(f"일일 손실 한도 도달: {today_loss:,.0f}원")
                        continue
                    
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
                        
                        trades.append({
                            'date': current_time,
                            'type': 'buy',
                            'price': current_price,
                            'quantity': quantity,
                            'profit': 0,
                            'profit_pct': 0
                        })
                        
                        in_position = True
                        entry_price = current_price
                        entry_time = current_time
                        
                        print(f"\n[매수 #{trade_count}]")
                        print(f"시간: {current_time}")
                        print(f"가격: {current_price:,.0f}원")
                        print(f"수량: {quantity:.8f} {market}")
                        print(f"매수 금액: {(quantity * current_price):,.0f}원")
                        print(f"현금 잔고: {backtest.cash_balance:,.0f}원")
                        
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='볼린저 밴드 + RSI 전략으로 암호화폐 백테스팅을 실행합니다.')
    
    parser.add_argument('--start-date', type=str, help='시작 날짜 (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='종료 날짜 (YYYY-MM-DD)')
    parser.add_argument('--initial-balance', type=float, default=10_000_000,
                      help='초기 투자금액 (기본값: 10,000,000원)')
    parser.add_argument('--position-size', type=float, default=0.1,
                      help='포지션 크기 (0.0 ~ 1.0, 기본값: 0.1)')
    parser.add_argument('--coin', type=str, default='KRW-BTC',
                      choices=['KRW-BTC', 'KRW-ETH', 'KRW-XRP'],
                      help='거래할 코인 (기본값: KRW-BTC)')
    
    args = parser.parse_args()
    
    # 사용 가능한 날짜 범위 확인
    available_start, available_end = get_available_date_range()
    
    # 시작일/종료일 설정
    start_date = parse_date(args.start_date) or available_start
    end_date = parse_date(args.end_date) or available_end
    
    if start_date < available_start:
        start_date = available_start
    if end_date > available_end:
        end_date = available_end
    
    run_bollinger_rsi_strategy(
        market=args.coin,
        start_date=start_date,
        end_date=end_date,
        initial_balance=args.initial_balance,
        position_size=args.position_size
    ) 