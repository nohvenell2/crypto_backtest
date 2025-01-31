from datetime import datetime
from sqlalchemy.orm import Session
from util.table_trasaction import Transaction
from util.db_engine import engine

def log_transaction(
    backtest_id: int,
    date: datetime,
    transaction_type: str,
    price: float,
    quantity: float,
    cash_balance: float,
    asset_balance: float,
    user_id = None
):
    """백테스팅 거래 기록을 데이터베이스에 저장합니다."""
    
    try:
        with Session(engine) as session:
            transaction = Transaction(
                user_id=user_id,
                backtest_id=backtest_id,
                date=date,
                type=transaction_type,
                price=price,
                quantity=quantity,
                total_amount=price * quantity,
                cash_balance=cash_balance,
                asset_balance=asset_balance,
                created_at=datetime.now()
            )
            
            session.add(transaction)
            session.commit()
            
    except Exception as e:
        print(f"거래 기록 저장 중 오류 발생: {e}")
