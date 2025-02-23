import sys
import os
from itertools import product
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import multiprocessing as mp
from functools import partial
from tqdm import tqdm
import numpy as np
from deap import base, creator, tools, algorithms
import random

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
from util.db_engine import engine
from sqlalchemy import text

# 전역 변수로 카운터와 총 조합 수 선언
progress_counter = None
total_combinations = 0

def get_available_date_range(market: str = 'KRW-BTC') -> tuple[datetime, datetime]:
    """데이터베이스에서 사용 가능한 날짜 범위를 조회합니다."""
    query = text("""
        SELECT 
            DATE_TRUNC('day', MIN(timestamp_kst))::timestamp,
            DATE_TRUNC('day', MAX(timestamp_kst))::timestamp
        FROM upbit_1hour_price
        WHERE market = :market
    """)
    
    with engine.connect() as conn:
        result = conn.execute(query, {"market": market}).first()
        return (
            result[0].replace(tzinfo=None),
            result[1].replace(tzinfo=None)
        )

def evaluate_strategy(individual: List[int], data: pd.DataFrame) -> Tuple[float,]:
    """전략의 성능을 평가합니다."""
    params = {
        'long_term_window': individual[0],
        'medium_term_window': individual[1],
        'short_term_window': individual[2],
        'rsi_period': individual[3],
        'macd_fast': individual[4],
        'macd_slow': individual[5],
        'macd_signal': individual[6],
        'bb_window': individual[7],
        'bb_std': individual[8] / 10
    }
    
    strategy = TripleScreenStrategy(params)
    buy_signals, sell_signals = strategy.generate_signals(data)
    
    # 수익률 계산
    position = 0
    entry_price = 0
    total_return = 0
    trades = 0
    profitable_trades = 0
    max_drawdown = 0
    current_drawdown = 0
    peak_value = 1.0  # 초기 자산을 1로 표준화
    
    for i in range(len(data)):
        if position == 0 and buy_signals.iloc[i]:
            position = 1
            entry_price = data['close'].iloc[i]
            trades += 1
        elif position == 1 and sell_signals.iloc[i]:
            position = 0
            exit_price = data['close'].iloc[i]
            returns = (exit_price / entry_price - 1) * 100
            total_return += returns
            
            if returns > 0:
                profitable_trades += 1
                
            # 최대 손실폭 계산
            current_value = 1.0 * (1 + returns/100)
            if current_value > peak_value:
                peak_value = current_value
            current_drawdown = (peak_value - current_value) / peak_value * 100
            max_drawdown = max(max_drawdown, current_drawdown)
    
    if trades < 5:  # 최소 거래 횟수 제한
        return -100.0,
        
    win_rate = (profitable_trades / trades * 100) if trades > 0 else 0
    avg_return = total_return / trades if trades > 0 else 0
    
    # 종합 점수 계산
    score = (
        0.4 * win_rate +           # 승률 40% 반영
        0.3 * avg_return +         # 평균 수익률 30% 반영
        0.2 * (trades * 2) +       # 거래 횟수 20% 반영 (많을수록 좋음)
        0.1 * (-max_drawdown)      # 최대 손실폭 10% 반영 (적을수록 좋음)
    )
    
    return score,

def optimize_parameters(
    market: str = 'KRW-BTC',
    train_months: int = 12,  # 연 단위에서 월 단위로 변경
    population_size: int = 50,
    generations: int = 30,
    cpu_count: int = None
) -> Dict:
    """유전 알고리즘을 사용하여 전략 파라미터를 최적화합니다."""
    
    # 데이터 준비
    end_date = datetime.now()
    start_date = end_date - timedelta(days=train_months*30)  # 연 단위를 월 단위로 변경
    data = fetch_price_data(start_date, end_date, market)
    
    if cpu_count is None:
        cpu_count = mp.cpu_count() - 1
    
    # DEAP 설정
    creator.create("FitnessMax", base.Fitness, weights=(1.0,))
    creator.create("Individual", list, fitness=creator.FitnessMax)
    
    toolbox = base.Toolbox()
    
    # 파라미터 범위 정의
    toolbox.register("long_term_window", random.randint, 20, 40)
    toolbox.register("medium_term_window", random.randint, 10, 20)
    toolbox.register("short_term_window", random.randint, 5, 15)
    toolbox.register("rsi_period", random.randint, 10, 20)
    toolbox.register("macd_fast", random.randint, 8, 16)
    toolbox.register("macd_slow", random.randint, 20, 30)
    toolbox.register("macd_signal", random.randint, 7, 12)
    toolbox.register("bb_window", random.randint, 15, 25)
    toolbox.register("bb_std", random.randint, 15, 25)  # 1.5 ~ 2.5를 위해 10으로 나눔
    
    # 개체 생성 함수
    def create_individual():
        return [
            toolbox.long_term_window(),
            toolbox.medium_term_window(),
            toolbox.short_term_window(),
            toolbox.rsi_period(),
            toolbox.macd_fast(),
            toolbox.macd_slow(),
            toolbox.macd_signal(),
            toolbox.bb_window(),
            toolbox.bb_std()
        ]
    
    toolbox.register("individual", tools.initIterate, creator.Individual, create_individual)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)
    
    # 유전 연산자 설정
    toolbox.register("evaluate", evaluate_strategy, data=data)
    toolbox.register("mate", tools.cxTwoPoint)
    toolbox.register("mutate", tools.mutUniformInt, low=[20,10,5,10,8,20,7,15,15], 
                     up=[40,20,15,20,16,30,12,25,25], indpb=0.2)
    toolbox.register("select", tools.selTournament, tournsize=3)
    
    # 병렬 처리 설정
    pool = mp.Pool(cpu_count)
    toolbox.register("map", pool.map)
    
    # 초기 population 생성
    pop = toolbox.population(n=population_size)
    hof = tools.HallOfFame(1)
    stats = tools.Statistics(lambda ind: ind.fitness.values)
    stats.register("avg", np.mean)
    stats.register("min", np.min)
    stats.register("max", np.max)
    
    print(f"\n=== {market} 파라미터 최적화 시작 ===")
    print(f"학습 기간: {start_date.date()} ~ {end_date.date()}")
    print(f"Population 크기: {population_size}")
    print(f"세대 수: {generations}")
    print(f"CPU 코어 수: {cpu_count}")
    print("=" * 50)
    
    # 유전 알고리즘 실행
    pop, logbook = algorithms.eaSimple(pop, toolbox, cxpb=0.7, mutpb=0.3, 
                                     ngen=generations, stats=stats, 
                                     halloffame=hof, verbose=True)
    
    pool.close()
    
    # 최적 파라미터 반환
    best_individual = hof[0]
    best_params = {
        'long_term_window': best_individual[0],
        'medium_term_window': best_individual[1],
        'short_term_window': best_individual[2],
        'rsi_period': best_individual[3],
        'macd_fast': best_individual[4],
        'macd_slow': best_individual[5],
        'macd_signal': best_individual[6],
        'bb_window': best_individual[7],
        'bb_std': best_individual[8] / 10
    }
    
    print("\n=== 최적화 결과 ===")
    print(f"최적 파라미터:")
    for key, value in best_params.items():
        print(f"- {key}: {value}")
    print(f"평균 거래 수익률: {hof[0].fitness.values[0]:.2f}%")
    
    return best_params

def evaluate_strategy_wrapper(params: Dict, df: pd.DataFrame, initial_balance: float, 
                            position_size: float, market: str, start_date: datetime, 
                            end_date: datetime) -> Dict:
    """병렬 처리를 위한 evaluate_strategy 래퍼 함수"""
    result = evaluate_strategy(params, df)
    return {
        'params': params,
        'total_return': result[0],
        'win_rate': 0.0,  # win_rate는 유전 알고리즘에서 계산되지 않음
        'trade_count': 0,  # trade_count는 유전 알고리즘에서 계산되지 않음
        'final_value': initial_balance * (1 + result[0] / 100)
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
    
    parser = argparse.ArgumentParser(description='삼중 스크리닝 전략의 파라미터를 최적화합니다.')
    
    parser.add_argument('--market', type=str, default='KRW-BTC',
                      choices=['KRW-BTC', 'KRW-ETH', 'KRW-XRP'],
                      help='최적화할 코인 (기본값: KRW-BTC)')
    parser.add_argument('--months', type=int, default=12,  # years를 months로 변경
                      help='학습에 사용할 기간(월) (기본값: 12)')
    parser.add_argument('--population', type=int, default=50,
                      help='유전 알고리즘 population 크기 (기본값: 50)')
    parser.add_argument('--generations', type=int, default=30,
                      help='유전 알고리즘 세대 수 (기본값: 30)')
    parser.add_argument('--cpu', type=int, default=None,
                      help='사용할 CPU 코어 수 (기본값: 사용 가능한 코어 수 - 1)')
    
    args = parser.parse_args()
    
    try:
        # 사용 가능한 데이터 기간 확인
        db_start_date, db_end_date = get_available_date_range(args.market)
        available_months = (db_end_date - db_start_date).days / 30  # 연 단위를 월 단위로 변경
        
        if args.months > available_months:
            print(f"경고: 요청한 기간({args.months}개월)이 가용 데이터 기간({available_months:.1f}개월)보다 깁니다.")
            print(f"가용 기간으로 조정합니다.")
            args.months = int(available_months)
        
        # 최적화 실행
        best_params = optimize_parameters(
            market=args.market,
            train_months=args.months,  # years를 months로 변경
            population_size=args.population,
            generations=args.generations,
            cpu_count=args.cpu
        )
        
    except Exception as e:
        print(f"오류 발생: {e}")
        parser.print_help() 