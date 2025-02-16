# Backtest Strategy

암호화폐 백테스팅을 위한 포트폴리오 관리 클래스입니다.

## 개요

`Backtest` 클래스는 백테스팅 과정에서 포트폴리오를 관리하고 거래를 실행하는 기능을 제공합니다
현금 잔고, 보유 자산, 거래 기록 등을 추적하며, 수수료를 고려한 매수/매도를 지원합니다.

## 설치 및 의존성

```bash
pip install sqlalchemy pandas python-dotenv psycopg2-binary
```

## 사용 방법

### 기본 사용 예시

```python
from datetime import datetime
from backtest_strategy import BacktestStrategy

# 전략 인스턴스 생성
backtest = Backtest(
    backtest_id='test_001', # 백테스팅 아이디(필수)
    start_date=datetime(2024, 1, 1), # 백테스팅 시작 날짜(필수)
    market_name='upbit', # 거래소 이름(선택/default: upbit)
    initial_balance=10000000.0, # 초기 투자 금액(선택/default: 10000000.0)
    save_db=False,  # db 저장 여부(선택/default: False)
    debug=False     # 디버그 모드 여부(선택/default: False)
)

# 매수 실행
backtest.buy(
    date=datetime.now(),
    crypto_name='KRW-BTC',
    price=50000000.0,
    quantity=0.1,
    fee_type='percent',
    fee_amount=0.0005
)

# 포트폴리오 가치 조회
portfolio_value = backtest.get_portfolio_value(datetime.now())
```

### 주요 기능

#### 매수 (buy)
```python
backtest.buy(
    date=datetime.now(),
    crypto_name='KRW-BTC',
    price=50000000.0,
    quantity=0.1,
    fee_type='percent',
    fee_amount=0.0005
)
```
- `date`: 거래 시점
- `crypto_name`: 암호화폐 이름
- `price`: 매수 가격
- `quantity`: 매수 수량
- `fee_type`: 수수료 유형 ('percent' 또는 'fixed')
- `fee_amount`: 수수료 금액

#### 매도 (sell)
```python
backtest.sell(
    date=datetime.now(),
    crypto_name='KRW-BTC',
    price=55000000.0,
    quantity=0.1,
    fee_type='percent',
    fee_amount=0.0005
)
```

#### 입금 (deposit)
```python
backtest.deposit(
    date=datetime.now(),
    amount=1000000.0
)
```
- `date`: 입금 시점
- `amount`: 입금 금액

#### 출금 (withdraw)
```python
backtest.withdraw(
    date=datetime.now(),
    amount=1000000.0
)
```
- `date`: 출금 시점
- `amount`: 출금 금액

#### 보유 암호화폐 가치 조회
```python
asset_value = backtest.get_asset_value(datetime.now(), '1hour')
```
- `timestamp`: 가치 계산 시점
- `price_type`: 가격 데이터 타입 ('daily' 또는 '1hour')

#### 포트폴리오 가치 조회
```python
portfolio_value = backtest.get_portfolio_value(datetime.now(), '1hour')
```
- `timestamp`: 가치 계산 시점
- `price_type`: 가격 데이터 타입 ('daily' 또는 '1hour')

#### 거래 기록

```python
transaction_log = backtest.transaction_log
```

모든 거래 내역은 transaction_log에 저장되며, 다음 정보가 저장됩니다:
- 거래 시간
- 암호화폐 이름
- 거래 유형 (매수/매도)
- 가격
- 수량
- 수수료 유형(퍼센트, 고정)
- 수수료
- 총 거래 금액
- 현금 잔고
- 보유 암호화폐 가치
- 포트폴리오 가치
- 수익률

#### 거래 기록 db 저장
```python
backtest = Backtest(
    backtest_id='test_001',
    market_name='upbit',
    initial_balance=10000000.0,
    save_db=True # default: False
)
```
모든 거래 내역은 db 에 저장되며, 다음 정보가 저장됩니다:
- 백테스팅 아이디
- 거래 시간
- 암호화폐 이름
- 거래소 이름
- 거래 유형 (매수/매도)
- 가격
- 수량
- 수수료 유형(퍼센트, 고정)
- 수수료
- 총 거래 금액
- 데이터 생성 시간

## 주의사항

- 매수 시 잔고가 부족한 경우 ValueError가 발생합니다.
- 매도 시 보유 수량이 부족한 경우 ValueError가 발생합니다.
- 데이터베이스 연결 설정이 필요합니다 (환경 변수 사용).

## 환경 변수 설정

`.env` 파일에 다음 설정이 필요합니다:
```
DB_HOST=localhost
DB_PORT=5432
POSTGRES_DB=your_db_name
POSTGRES_USER=your_username
POSTGRES_PASSWORD=your_password
```
