from typing import Literal
from datetime import datetime
from util.log_transaction import log_transaction
from get_price import get_price

class Backtest:
    """백테스트 전략 실행을 위한 포트폴리오 관리 클래스입니다.
    
    이 클래스는 백테스트 과정에서 포트폴리오 상태를 관리하고 거래를 실행합니다.
    현금 잔고, 보유 자산, 거래 기록 등을 추적하며, 수수료를 고려한 매수/매도를 지원합니다.

    Attributes:
        cash_balance (float): 현재 현금 잔고
        backtest_id (str): 백테스트 실행 식별자
        market_name (str): 거래소 이름 (예: 'upbit')
        portfolio (dict): 보유 중인 암호화폐 수량 (키: 암호화폐 이름, 값: 수량)
        initial_balance (float): 초기 투자 금액
        trades_count (int): 총 거래 횟수

    Example:
        >>> strategy = Strategy(backtest_id='test_001', initial_balance=10000000.0)
        >>> strategy.buy(
        ...     date=datetime.now(),
        ...     crypto_name='KRW-BTC',
        ...     price=50000000.0,
        ...     quantity=0.1,
        ...     fee_type='percent',
        ...     fee_amount=0.0005
        ... )
        >>> portfolio_value = strategy.get_portfolio_value(datetime.now(), 'daily')
    """
    
    def __init__(self, backtest_id: str, market_name: str = 'upbit', 
                initial_balance: float = 10000000.0, save_db: bool = False):
        """
        Args:
            backtest_id: 백테스트 실행 식별자
            market_name: 거래소 이름 (기본값: 'upbit')
            initial_balance: 초기 투자 금액 (기본값: 10,000,000.0)
            save_db: db 저장 여부 (기본값: False)
        """
        self.cash_balance = initial_balance
        self.backtest_id = backtest_id
        self.market_name = market_name
        self.portfolio = {}
        self.transaction_log = []
        self.initial_balance = initial_balance  # 초기 자본 저장
        self.trades_count = 0  # 거래 횟수 추적
        self.save_db = save_db # db 저장 여부

    def buy(self, date: datetime, crypto_name: str, price: float, quantity: float, 
            fee_type: Literal['percent', 'fixed'] = 'percent', fee_amount: float = 0.0005):
        """암호화폐 매수 거래를 실행합니다.
        
        Args:
            date: 거래 시점
            crypto_name: 암호화폐 이름 (예: 'KRW-BTC')
            price: 매수 가격
            quantity: 매수 수량
            fee_type: 수수료 유형 ('percent' 또는 'fixed')
            fee_amount: 수수료 금액 (percent인 경우 비율, fixed인 경우 고정 금액)
            
        Returns:
            dict: 거래 정보 (시간, 가격, 수량, 총액, 수수료 등)
            
        Raises:
            ValueError: 잔고가 부족한 경우
        """
        # 수수료 포함 total amount 계산
        if fee_type == 'percent':
            total_amount = price * quantity * (1 + fee_amount)
        elif fee_type == 'fixed':
            total_amount = price * quantity + fee_amount
        # 포트폴리오 업데이트
        if self.cash_balance < total_amount:
            print(f'{date} 매수 실패\n현금보유량 : {self.cash_balance}\n투자 시도 금액 : {total_amount}')
            raise ValueError(f"Not enough cash balance to buy {crypto_name}")
        else:
            self.cash_balance -= total_amount
            if crypto_name not in self.portfolio:
                self.portfolio[crypto_name] = quantity
            else:
                self.portfolio[crypto_name] += quantity
        # 거래 내역 기록
        self.trades_count += 1
        asset_value = self.get_asset_value(date, '1hour')
        total_value = asset_value + self.cash_balance
        return_value = total_value / self.initial_balance - 1
        transaction_info = {
            'date': date,
            'crypto_name': crypto_name,
            'price': price,
            'quantity': quantity,
            'total_amount': total_amount,
            'fee_type': fee_type,
            'fee_amount': fee_amount,
            'transaction_type': 'Buy',
            'cash_balance': self.cash_balance,
            'asset_value': asset_value,
            'total_value': total_value,
            'return': return_value
        } 
        self.transaction_log.append(transaction_info)
        # db 저장        
        if self.save_db:
            log_transaction(
                backtest_id=self.backtest_id,
                transaction_time=date,
                crypto_name=crypto_name,
                market_name=self.market_name,
                fee_type=fee_type,
                fee_amount=fee_amount,
                transaction_type='Buy',
                price=price,
                quantity=quantity,
                total_amount=total_amount,
            )
        return transaction_info


    def sell(self, date: datetime, crypto_name: str, price: float, quantity: float, 
            fee_type: Literal['percent', 'fixed'] = 'percent', fee_amount: float = 0.0005):
        """암호화폐 매도 거래를 실행합니다.
        
        Args:
            date: 거래 시점
            crypto_name: 암호화폐 이름 (예: 'KRW-BTC')
            price: 매도 가격
            quantity: 매도 수량
            fee_type: 수수료 유형 ('percent' 또는 'fixed')
            fee_amount: 수수료 금액 (percent인 경우 비율, fixed인 경우 고정 금액)
            
        Returns:
            dict: 거래 정보 (시간, 가격, 수량, 총액, 수수료 등)
            
        Raises:
            ValueError: 보유 수량이 부족한 경우
        """
        # total amount 계산
        if fee_type == 'percent':
            total_amount = price * quantity * (1 - fee_amount)
        elif fee_type == 'fixed':
            total_amount = price * quantity - fee_amount
        # 포트폴리오 업데이트
        if crypto_name not in self.portfolio:
            raise ValueError(f"No {crypto_name} in portfolio")
        elif self.portfolio[crypto_name] < quantity:
            raise ValueError(f"Not enough {crypto_name} in portfolio")
        else:
            self.portfolio[crypto_name] -= quantity
            if self.portfolio[crypto_name] == 0:
                del self.portfolio[crypto_name]
            self.cash_balance += total_amount
        # 거래 내역 기록
        self.trades_count += 1
        asset_value = self.get_asset_value(date, '1hour')
        total_value = asset_value + self.cash_balance
        return_value = total_value / self.initial_balance - 1
        transaction_info = {
            'date': date,
            'crypto_name': crypto_name,
            'price': price,
            'quantity': quantity,
            'total_amount': total_amount,
            'fee_type': fee_type,
            'fee_amount': fee_amount,
            'transaction_type': 'Sell',
            'cash_balance': self.cash_balance,
            'asset_value': asset_value,
            'total_value': total_value,
            'return': return_value
        }
        self.transaction_log.append(transaction_info)
        # db 저장
        if self.save_db:
            log_transaction(
                backtest_id=self.backtest_id,
                transaction_time=date,
                crypto_name=crypto_name,
                market_name=self.market_name,
                fee_type=fee_type,
                fee_amount=fee_amount,
                transaction_type='Sell',
                price=price,
                quantity=quantity,
                total_amount=total_amount,
            )
        return transaction_info

    def get_quantity(self, crypto_name: str):
        if crypto_name not in self.portfolio:
            return 0
        else:
            return self.portfolio[crypto_name]
        
    def get_asset_value(self, timestamp: datetime, price_type: Literal['daily', '1hour'] = '1hour') -> float:
        """특정 시점 보유 암호화폐 총 가치 계산
        
        Args:
            timestamp: 가치 계산 시점
            price_type: 가격 데이터 타입 ('daily' 또는 '1hour')
            
        Returns:
            float: 암호화폐 가치 
        """
        total_asset_value = sum(
            amount * get_price(crypto_name, timestamp, price_type) 
            for crypto_name, amount in self.portfolio.items()
        )
        return total_asset_value
    
    def get_portfolio_value(self, timestamp: datetime, price_type: Literal['daily', '1hour'] = '1hour') -> float:
        """특정 시점 포트폴리오 총 가치 계산
        
        Args:
            timestamp: 가치 계산 시점
            price_type: 가격 데이터 타입 ('daily' 또는 '1hour')
            
        Returns:
            float: 포트폴리오 총 가치 (현금 + 자산)
        """
        total_value = self.cash_balance + self.get_asset_value(timestamp, price_type)
        return total_value

if __name__ == '__main__':
    strategy = Backtest(backtest_id='test', market_name='upbit')
    strategy.buy(datetime.now(), 'KRW-BTC', 10000000, 0.0001, fee_type='percent', fee_amount=0.005)
    strategy.sell(datetime.now(), 'KRW-BTC', 10000000, 0.0001, fee_type='percent', fee_amount=0.005)




