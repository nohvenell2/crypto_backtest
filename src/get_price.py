from sqlalchemy import text
from util.db_engine import engine
from datetime import datetime
from typing import Literal

def get_price(crypto_name: str, timestamp: datetime, type: Literal['daily', '1hour'] = 'daily') -> float:
    """특정 시간과 가장 가까운 최근 암호화폐 가격을 조회합니다.
    
    Args:
        crypto_name: 암호화폐 이름 (예: 'KRW-BTC')
        timestamp: 조회할 시간
    
    Returns:
        float: 해당 시간과 가장 가까운 최근 종가
        
    Raises:
        ValueError: 데이터가 없는 경우
    """
    query = text(f"""
        SELECT close
        FROM upbit_{type}_price
        WHERE market = :market
        AND timestamp_kst <= :timestamp
        ORDER BY timestamp_kst DESC
        LIMIT 1
    """)
    
    try:
        with engine.connect() as conn:
            result = conn.execute(
                query,
                {"market": crypto_name, "timestamp": timestamp}
            ).first()
            
            if result is None:
                raise ValueError(f"No price data found for {crypto_name} at or before {timestamp}")
                
            return float(result[0])
            
    except Exception as e:
        raise ValueError(f"Error fetching price: {str(e)}")


if __name__ == '__main__':
    print(get_price('KRW-BTC', datetime.now(), '1hour'))

