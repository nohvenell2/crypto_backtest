from sqlalchemy import Column, String, DateTime, Numeric, Integer, Enum, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.schema import UniqueConstraint
import os
from dotenv import load_dotenv
from .db_engine import engine
# .env 파일 로드
load_dotenv()


# 환경변수 가져오기
DB_USER = os.getenv('POSTGRES_USER')
DB_PASSWORD = os.getenv('POSTGRES_PASSWORD')
DB_NAME = os.getenv('POSTGRES_DB')
DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT')

# Base 클래스 생성
Base = declarative_base()

# 트랜잭션 테이블
class Transaction(Base):
    __tablename__ = 'transactions_id_log'
    
    id = Column(Integer, primary_key=True)
    backtest_id = Column(String(30), nullable=False)  # 백테스팅 실행 ID
    transaction_time = Column(DateTime, nullable=False)  # 트랜잭션 날짜
    crypto_name = Column(String(30), nullable=False)  # 암호화폐 이름
    market_name = Column(String(30), nullable=False)  # 시장 이름
    fee_type = Column(Enum('percent', 'fixed', name='fee_type'), nullable=False)  # 수수료 유형
    fee_amount = Column(Numeric(20, 8), nullable=False)  # 수수료 금액
    transaction_type = Column(Enum('Buy', 'Sell','Deposit', 'Withdraw', name='transaction_type'), nullable=False)  # 매수/매도
    price = Column(Numeric(20, 2), nullable=False)  # 가격
    quantity = Column(Numeric(20, 8), nullable=False)  # 수량
    total_amount = Column(Numeric(20, 2), nullable=False)  # 총액
    cash_balance = Column(Numeric(20, 2), nullable=False)  # 현금 잔액
    asset_value = Column(Numeric(20, 2), nullable=False)  # 자산 평가 금액
    total_value = Column(Numeric(20, 2), nullable=False)  # 총 평가 금액
    return_rate = Column(Numeric(20, 2), nullable=False)  # 수익률
    created_at = Column(DateTime(timezone=True), nullable=False)  # 생성 시간

    __table_args__ = (
        Index('idx_backtest_id_log', 'backtest_id', 'transaction_time'),
    )
def create_tables():
    try:
        # 테이블 생성
        Base.metadata.create_all(engine)
        print("테이블이 성공적으로 생성되었습니다.")
        
    except Exception as e:
        print(f"테이블 생성 중 오류 발생: {e}")

if __name__ == "__main__":
    create_tables()
