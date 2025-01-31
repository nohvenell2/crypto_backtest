from typing import Literal
from datetime import datetime
from sqlalchemy.orm import Session
from .table_trasaction import Transaction
from .db_engine import engine

def log_transaction(
    backtest_id: str,
    transaction_time: datetime,
    crypto_name: str,
    market_name: str,
    fee_type: Literal['percent', 'fixed'],  
    fee_amount: float,
    transaction_type: Literal['Buy', 'Sell'],
    price: float,
    quantity: float,
    total_amount: float,
):
    """백테스팅 거래 기록을 데이터베이스에 저장합니다."""
    
    try:
        with Session(engine) as session:
            transaction = Transaction(
                backtest_id=backtest_id,
                transaction_time=transaction_time,
                crypto_name=crypto_name,
                market_name=market_name,
                fee_type=fee_type,
                fee_amount=fee_amount,
                transaction_type=transaction_type,
                price=price,
                quantity=quantity,
                total_amount=total_amount,
                created_at=datetime.now()
            )
            session.add(transaction)
            session.commit()
            
    except Exception as e:
        print(f"거래 기록 저장 중 오류 발생: {e}")
if __name__ == "__main__":
    log_transaction(
        backtest_id="test",
        transaction_time=datetime.now(),
        crypto_name="BTC",
        market_name="KRAKEN",
        fee_type="percent",
        fee_amount=0.0005,
        transaction_type="Buy",
        price=10000,
        quantity=1,
        total_amount=10000,
    )
