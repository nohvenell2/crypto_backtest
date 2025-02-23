import sys
import os

# 상위 디렉토리를 파이썬 경로에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
src_dir = os.path.join(project_root, 'src')
sys.path.insert(0, src_dir)

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
from typing import Optional, Dict, Any

def fetch_price_data(start_date: datetime, end_date: datetime, market: str = 'KRW-BTC') -> pd.DataFrame:
    """지정된 기간의 가격 데이터를 가져옵니다."""
    query = text("""
        SELECT timestamp_kst, open, high, low, close, volume
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

class TripleScreenStrategy:
    def __init__(self, params: Dict[str, Any]):
        """
        삼중 스크리닝 전략 파라미터 초기화
        """
        self.params = params
        
    def calculate_weekly_trend(self, data: pd.DataFrame) -> pd.Series:
        """첫 번째 스크린: 주간 트렌드 분석"""
        # 더 긴 기간의 이동평균 사용
        weekly_ema = data['close'].ewm(span=self.params['long_term_window']).mean()
        weekly_sma = data['close'].rolling(window=self.params['long_term_window']*2).mean()
        
        # MACD 계산
        exp1 = data['close'].ewm(span=self.params['macd_fast']).mean()
        exp2 = data['close'].ewm(span=self.params['macd_slow']).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=self.params['macd_signal']).mean()
        macd_hist = macd - signal
        
        # 추세 강도 계산 (개선)
        trend_strength = (
            (data['close'] > weekly_ema) &  # 가격이 EMA 위
            (weekly_ema > weekly_sma) &     # EMA가 SMA 위
            (macd_hist > 0) &               # MACD 히스토그램 양수
            (macd_hist > macd_hist.shift(1))  # MACD 히스토그램 증가
        )
        
        return trend_strength
    
    def calculate_daily_momentum(self, data: pd.DataFrame) -> pd.Series:
        """두 번째 스크린: 일간 모멘텀 분석"""
        # RSI 계산
        delta = data['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.params['rsi_period']).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.params['rsi_period']).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        # 볼린저 밴드 계산
        middle_band = data['close'].rolling(window=self.params['bb_window']).mean()
        std_dev = data['close'].rolling(window=self.params['bb_window']).std()
        lower_band = middle_band - (self.params['bb_std'] * std_dev)
        upper_band = middle_band + (self.params['bb_std'] * std_dev)
        
        # 매수 조건 개선
        buy_condition = (
            (rsi < 40) &  # RSI 과매도
            (data['close'] < lower_band * 1.05) &  # 밴드 하단 근처
            (data['volume'] > data['volume'].rolling(window=20).mean() * 1.3)  # 거래량 증가
        )
        
        # 매도 조건 개선
        sell_condition = (
            (rsi > 70) &  # RSI 과매수
            (
                (data['close'] > upper_band) |  # 상단 밴드 돌파
                (data['close'] < middle_band * 0.98)  # 중간 밴드 하향 이탈
            )
        )
        
        return buy_condition, sell_condition
    
    def calculate_entry_signal(self, data: pd.DataFrame) -> pd.Series:
        """세 번째 스크린: 단기 진입 시그널"""
        # 단기 이동평균 계산
        short_ma = data['close'].rolling(window=self.params['short_term_window']).mean()
        prev_short_ma = short_ma.shift(1)
        
        # 거래량 분석
        volume_ma = data['volume'].rolling(window=self.params['short_term_window']).mean()
        volume_increase = data['volume'] > volume_ma * 1.3
        
        # 가격 모멘텀 계산
        momentum = data['close'].diff(periods=3) / data['close'].shift(3) * 100
        
        # 매수 조건 완화
        buy_signal = (
            (momentum > 0.5) &  # 모멘텀 기준 완화 (1.0->0.5)
            volume_increase &
            (data['close'] > prev_short_ma * 1.002)  # 상승 추세 기준 완화
        )
        
        # 매도 조건 조정
        sell_signal = (
            (momentum < -1.5) |  # 하락 모멘텀 기준 완화
            (data['close'] < prev_short_ma * 0.995)  # 하락 추세 기준 완화
        )
        
        return buy_signal, sell_signal
    
    def calculate_market_condition(self, data: pd.DataFrame) -> pd.Series:
        """시장 상황 분석"""
        # 변동성 계산 (ATR 사용)
        high = data['high']
        low = data['low']
        close = data['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=14).mean()
        
        # 변동성 돌파 계산
        daily_range = (high - low).rolling(window=20).mean()
        volatility_breakthrough = close > (close.shift(1) + daily_range * 0.5)
        
        # 거래량 분석
        volume = data['volume']
        volume_ma = volume.rolling(window=20).mean()
        volume_ratio = volume / volume_ma
        
        # 시간대별 거래량 가중치 (한국 시간 기준)
        hour = pd.to_datetime(data.index).hour
        asia_market = (hour >= 9) & (hour <= 15)  # 아시아 거래시간
        us_market = (hour >= 21) | (hour <= 5)    # 미국 거래시간
        
        # 변동성 점수 (0~30)
        volatility_score = ((atr / close) * 100).rolling(window=20).mean()
        
        # 거래량 점수 (0~40)
        volume_score = (volume_ratio * 20).clip(0, 40)
        
        # 추가: 상승 추세 강도 계산
        ma20 = close.rolling(window=20).mean()
        ma50 = close.rolling(window=50).mean()
        trend_strength = (close > ma20) & (ma20 > ma50)
        
        # 추가: 가격 모멘텀
        momentum = close.pct_change(periods=12).rolling(window=24).mean() * 100
        
        # 시장 점수 계산 수정
        market_score = pd.Series(0, index=data.index)
        market_score += (volatility_score.clip(0, 25))  # 변동성 비중 감소
        market_score += (volume_score.clip(0, 35))      # 거래량 비중 감소
        market_score += trend_strength * 20              # 추세 강도 반영
        market_score += (momentum.clip(-10, 10) + 10) * 2  # 모멘텀 반영
        
        return market_score, volatility_breakthrough
    
    def calculate_position_size(self, market_score: float, current_price: float, 
                              available_balance: float) -> float:
        """시장 상황에 따른 포지션 크기 조절"""
        base_size = 0.15  # 기본 포지션 크기 증가 (0.1->0.15)
        
        # 시장 점수에 따른 포지션 크기 조절
        if market_score >= 85:  # 매우 좋은 시장 상황
            position_size = base_size * 2.0
        elif market_score >= 75:  # 좋은 시장 상황
            position_size = base_size * 1.5
        elif market_score >= 65:  # 괜찮은 시장 상황
            position_size = base_size * 1.2
        elif market_score <= 40:  # 나쁜 시장 상황
            position_size = base_size * 0.5
        else:
            position_size = base_size
        
        return position_size
    
    def generate_signals(self, data: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
        """매수/매도 시그널 생성"""
        trend = self.calculate_weekly_trend(data)
        momentum_buy, momentum_sell = self.calculate_daily_momentum(data)
        entry_buy, entry_sell = self.calculate_entry_signal(data)
        market_score, volatility_breakthrough = self.calculate_market_condition(data)
        
        # 매수 시그널 완화
        buy_signal = (
            trend &  # 추세 확인
            ((momentum_buy & market_score > 50) |  # 시장 점수 기준 완화 (65->50)
             (entry_buy & volatility_breakthrough))  # 진입 시그널과 변동성 돌파
        )
        
        # 매도 시그널 조정
        sell_signal = (
            (~trend & market_score < 35) |  # 시장 점수 기준 완화 (40->35)
            (momentum_sell & market_score < 45) |  # 시장 점수 기준 완화 (50->45)
            entry_sell
        )
        
        return buy_signal, sell_signal, market_score

def run_triple_screen_strategy(
    start_date: datetime,
    end_date: datetime,
    initial_balance: float = 10_000_000,
    position_size: float = 0.1,
    market: str = 'KRW-BTC'
) -> None:
    """삼중 스크리닝 전략으로 백테스팅을 실행합니다."""
    
    # 전략 파라미터 수정
    params = {
        'long_term_window': 40,     # 장기 추세 확인 기간 증가
        'medium_term_window': 20,   # 중기 모멘텀 기간
        'short_term_window': 10,    # 단기 진입 기간
        'rsi_period': 14,
        'macd_fast': 12,
        'macd_slow': 26,
        'macd_signal': 9,
        'bb_window': 20,
        'bb_std': 2.0,
        'profit_target': 8.0,       # 이익실현 목표 상향
        'stop_loss': -4.0,         # 손절 기준 완화
        'trailing_stop': 3.0,      # 트레일링 스탑 범위 확대
        'min_holding_hours': 12,   # 최소 보유 시간 증가
        'max_holding_hours': 96,   # 최대 보유 시간 증가
        'min_market_score': 60,
        'max_loss_per_day': 5.0
    }
    
    # 백테스트 인스턴스 생성
    backtest = Backtest(
        backtest_id=f'triple_screen_{market}_{datetime.now().strftime("%Y%m%d_%H%M")}',
        market_name='upbit',
        initial_balance=initial_balance,
        start_date=start_date,
        save_db=False
    )
    
    # 가격 데이터 조회 및 전략 인스턴스 생성
    df = fetch_price_data(start_date, end_date, market)
    strategy = TripleScreenStrategy(params)
    buy_signals, sell_signals, market_scores = strategy.generate_signals(df)
    
    # 초기 상태
    in_position = False
    entry_price = 0
    entry_time = None  # 매수 시간 저장 변수 추가
    trade_count = 0
    profitable_trades = 0
    total_profit_loss = 0
    trades = []
    
    print("\n=== 삼중 스크리닝 전략 백테스팅 시작 ===")
    print(f"시작 시간: {start_date}")
    print(f"종료 시간: {end_date}")
    print(f"초기 투자금: {initial_balance:,.0f}원")
    print("=" * 60)
    
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
                elif current_return > params['profit_target'] * 0.5:  # 목표 수익의 절반 도달
                    trailing_stop = max(params['trailing_stop'], current_return * 0.5)  # 동적 트레일링 스탑
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
                        
                        profit_loss = after_balance - before_balance
                        profit_loss_pct = (current_price / entry_price - 1) * 100
                        total_profit_loss += profit_loss
                        
                        # 거래 기록 추가
                        trades.append({
                            'date': current_time,
                            'type': 'sell',
                            'price': current_price,
                            'quantity': quantity,
                            'profit': profit_loss,
                            'profit_pct': profit_loss_pct
                        })
                        
                        if profit_loss > 0:
                            profitable_trades += 1
                        
                        print(f"\n[매도 #{trade_count}] - {sell_reason}")
                        print(f"시간: {current_time}")
                        print(f"가격: {current_price:,.0f}원")
                        print(f"수량: {quantity:.8f} {market}")
                        print(f"매도 금액: {(quantity * current_price):,.0f}원")
                        print(f"거래 수익률: {profit_loss_pct:+.2f}%")
                        print(f"거래 손익: {profit_loss:+,.0f}원")
                        print(f"현금 잔고: {backtest.cash_balance:,.0f}원")
                        
                        in_position = False
            
            elif buy_signals.iloc[i]:
                # 매수 전 추가 검증 조건 완화
                if i >= 2:
                    price_change = (df['close'].iloc[i] / df['close'].iloc[i-2] - 1) * 100
                    volume_change = (df['volume'].iloc[i] / df['volume'].iloc[i-2] - 1) * 100
                    
                    # 급격한 가격 상승 제한 완화
                    if price_change > 5.0:  # 3%에서 5%로 상향
                        continue
                    
                    # 거래량 조건 완화
                    if volume_change < 10.0:  # 20%에서 10%로 하향
                        continue
                
                # 매수 신호
                available_balance = backtest.cash_balance
                position_size = strategy.calculate_position_size(
                    market_scores.iloc[i],
                    current_price,
                    available_balance
                )
                
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
                    
                    # 거래 기록 추가
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
                    entry_time = current_time  # 매수 시간 저장
                    
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='삼중 스크리닝 전략으로 암호화폐 백테스팅을 실행합니다.')
    
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
    
    try:
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
            
        print(f"\n=== {args.coin} 삼중 스크리닝 전략 백테스팅 ===")
        print(f"데이터 기간: {db_start_date.date()} ~ {db_end_date.date()}")
        print(f"백테스팅 기간: {start_date.date()} ~ {end_date.date()}")
        
        # 전략 실행
        run_triple_screen_strategy(
            start_date=start_date,
            end_date=end_date,
            initial_balance=args.initial_balance,
            position_size=args.position_size,
            market=args.coin
        )
        
    except ValueError as e:
        print(f"오류: {e}")
        parser.print_help() 