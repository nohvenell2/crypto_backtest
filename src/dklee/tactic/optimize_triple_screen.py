import sys
import os
from itertools import product
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import multiprocessing as mp
from functools import partial
from tqdm import tqdm

# 상위 디렉토리를 파이썬 경로에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
src_dir = os.path.join(project_root, 'src')
sys.path.insert(0, src_dir)

from triple_screen_strategy import (
    TripleScreenStrategy, fetch_price_data, 
    get_available_date_range, parse_date
)
from backtest_class import Backtest
import argparse

# 전역 변수로 카운터와 총 조합 수 선언
progress_counter = None
total_combinations = 0

def evaluate_strategy(
    df: pd.DataFrame,
    params: Dict,
    initial_balance: float,
    position_size: float,
    market: str,
    start_date: datetime,
    end_date: datetime
) -> Tuple[float, float, int, float]:
    """주어진 파라미터로 전략을 평가합니다."""
    
    try:
        strategy = TripleScreenStrategy(params)
        buy_signals, sell_signals = strategy.generate_signals(df)
        
        backtest = Backtest(
            backtest_id=f'optimize_triple_{market}_{datetime.now().strftime("%Y%m%d_%H%M")}',
            market_name='upbit',
            initial_balance=initial_balance,
            save_db=False
        )
        
        in_position = False
        trade_count = 0
        profitable_trades = 0
        entry_price = 0
        
        for i in range(len(df)):
            current_time = df['timestamp_kst'].iloc[i]
            current_price = df['close'].iloc[i]
            
            try:
                if not in_position and buy_signals.iloc[i]:
                    # 매수 신호
                    available_balance = backtest.cash_balance
                    quantity = (available_balance * position_size) / current_price
                    
                    if quantity * current_price >= 5000:
                        trade_count += 1
                        before_balance = backtest.get_portfolio_value(current_time)
                        backtest.buy(
                            date=current_time,
                            crypto_name=market,
                            price=current_price,
                            quantity=quantity,
                            fee_type='percent',
                            fee_amount=0.0005
                        )
                        entry_price = current_price
                        in_position = True
                        
                elif in_position and sell_signals.iloc[i]:
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
                        
                        if after_balance > before_balance:
                            profitable_trades += 1
                            
                        in_position = False
                        
            except ValueError:
                continue
        
        final_value = backtest.get_portfolio_value(end_date)
        total_return = (final_value / initial_balance - 1) * 100
        win_rate = (profitable_trades / trade_count * 100) if trade_count > 0 else 0
        
        return total_return, win_rate, trade_count, final_value
        
    except Exception as e:
        print(f"Error in evaluate_strategy: {str(e)}")
        return 0.0, 0.0, 0, initial_balance

def evaluate_strategy_wrapper(params: Dict, df: pd.DataFrame, initial_balance: float, 
                            position_size: float, market: str, start_date: datetime, 
                            end_date: datetime) -> Dict:
    """병렬 처리를 위한 evaluate_strategy 래퍼 함수"""
    total_return, win_rate, trade_count, final_value = evaluate_strategy(
        df, params, initial_balance, position_size, market, start_date, end_date
    )
    return {
        'params': params,
        'total_return': total_return,
        'win_rate': win_rate,
        'trade_count': trade_count,
        'final_value': final_value
    }

def estimate_execution_time(total_combinations: int, n_processes: int) -> str:
    """예상 실행 시간을 계산합니다."""
    seconds_per_combination = 0.5  # 각 조합당 평균 처리 시간
    total_seconds = (total_combinations * seconds_per_combination) / n_processes
    
    if total_seconds < 60:
        return f"{total_seconds:.1f}초"
    elif total_seconds < 3600:
        minutes = total_seconds / 60
        return f"{minutes:.1f}분"
    else:
        hours = total_seconds / 3600
        return f"{hours:.1f}시간"

def evaluate_with_progress(args):
    """진행률을 표시하는 평가 함수"""
    params, df, initial_balance, position_size, market, start_date, end_date = args
    
    result = evaluate_strategy_wrapper(
        params, df, initial_balance, position_size, market, start_date, end_date
    )
    
    return result

def optimize_strategy(
    start_date: datetime,
    end_date: datetime,
    market: str = 'KRW-BTC',
    initial_balance: float = 10_000_000,
    position_size: float = 0.2,
    n_processes: int = None
) -> None:
    """전략의 최적 파라미터를 병렬로 찾습니다."""
    
    if n_processes is None:
        n_processes = mp.cpu_count() - 1
    
    # 파라미터 그리드 정의
    param_grid = {
        'long_term_window': [10, 15, 20, 25],           # EMA 기간
        'medium_term_window': [5, 8, 10, 12],           # 중기 기간
        'short_term_window': [3, 5, 7, 10],             # 단기 기간
        'rsi_period': [7, 9, 14, 21],                   # RSI 기간
        'macd_fast': [8, 10, 12, 15],                   # MACD 빠른선
        'macd_slow': [20, 25, 30, 35],                  # MACD 느린선
        'macd_signal': [5, 7, 9, 11],                   # MACD 시그널
        'bb_window': [15, 20, 25, 30],                  # 볼린저 밴드 기간
        'bb_std': [1.5, 1.8, 2.0, 2.2]                  # 볼린저 밴드 표준편차
    }
    
    # 모든 파라미터 조합 계산
    param_combinations = [dict(zip(param_grid.keys(), v)) 
                        for v in product(*param_grid.values())]
    
    total_combinations = len(param_combinations)
    estimated_time = estimate_execution_time(total_combinations, n_processes)
    
    print("\n=== 최적화 실행 정보 ===")
    print(f"테스트 기간: {start_date.date()} ~ {end_date.date()}")
    print(f"코인: {market}")
    print(f"총 파라미터 조합: {total_combinations}개")
    print(f"사용할 CPU 코어: {n_processes}개")
    print(f"예상 소요 시간: {estimated_time}")
    
    # 사용자 확인
    while True:
        response = input("\n최적화를 시작하시겠습니까? (y/n): ").lower()
        if response in ['y', 'n']:
            break
        print("'y' 또는 'n'을 입력해주세요.")
    
    if response == 'n':
        print("최적화가 취소되었습니다.")
        return
    
    # 데이터 가져오기
    print("\n데이터를 불러오는 중...")
    df = fetch_price_data(start_date, end_date, market)
    
    print(f"최적화를 시작합니다... (병렬 처리 중)")
    start_time = datetime.now()
    
    # 평가 함수에 전달할 인자 준비
    eval_args = [
        (params, df.copy(), initial_balance, position_size, market, start_date, end_date)
        for params in param_combinations
    ]
    
    # Windows에서 멀티프로세싱을 위한 보호
    if __name__ == '__main__':
        mp.freeze_support()  # Windows에서 필요
        
        # 멀티프로세싱 풀 생성 및 실행
        with mp.Pool(n_processes) as pool:
            results = list(tqdm(
                pool.imap(evaluate_with_progress, eval_args),
                total=total_combinations,
                desc="최적화 진행률",
                ncols=100,
                unit="조합"
            ))
    
    end_time = datetime.now()
    elapsed_time = end_time - start_time
    
    print("\n\n=== 최적화 결과 ===")
    print(f"실제 소요 시간: {str(elapsed_time).split('.')[0]}")
    print(f"테스트 기간: {start_date.date()} ~ {end_date.date()}")
    print(f"코인: {market}")
    
    # 결과 정렬 시 수익률과 승률을 모두 고려
    top_results = sorted(
        results,
        key=lambda x: (x['total_return'], x['win_rate']),
        reverse=True
    )[:5]
    
    print("\n수익률 및 승률 기준 상위 5개 파라미터 조합:")
    for i, result in enumerate(top_results, 1):
        print(f"\n{i}위:")
        print(f"수익률: {result['total_return']:+.2f}%")
        print(f"승률: {result['win_rate']:.1f}%")
        print(f"거래 횟수: {result['trade_count']}회")
        print(f"최종 자산: {result['final_value']:,.0f}원")
        print("파라미터:")
        for key, value in result['params'].items():
            print(f"  - {key}: {value}")

if __name__ == '__main__':
    mp.freeze_support()  # Windows에서 필요
    
    parser = argparse.ArgumentParser(description='삼중 스크리닝 전략의 최적 파라미터를 찾습니다.')
    
    parser.add_argument('--start-date', type=str, help='시작 날짜 (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='종료 날짜 (YYYY-MM-DD)')
    parser.add_argument('--initial-balance', type=float, default=10_000_000,
                      help='초기 투자금액 (기본값: 10,000,000원)')
    parser.add_argument('--position-size', type=float, default=0.2,
                      help='포지션 크기 (0.0 ~ 1.0, 기본값: 0.2)')
    parser.add_argument('--coin', type=str, default='KRW-BTC',
                      choices=['KRW-BTC', 'KRW-ETH', 'KRW-XRP'],
                      help='거래할 코인 (기본값: KRW-BTC)')
    parser.add_argument('--processes', type=int, default=None,
                      help='사용할 CPU 코어 수 (기본값: CPU 코어 수 - 1)')
    
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
        
        # 최적화 실행
        optimize_strategy(
            start_date=start_date,
            end_date=end_date,
            market=args.coin,
            initial_balance=args.initial_balance,
            position_size=args.position_size,
            n_processes=args.processes
        )
        
    except ValueError as e:
        print(f"오류: {e}")
        parser.print_help() 