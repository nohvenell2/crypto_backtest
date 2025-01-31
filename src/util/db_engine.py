from sqlalchemy import create_engine
import os
# 개발 환경에서는 dotenv 사용
try:
    from dotenv import load_dotenv
    load_dotenv()
    #print("개발 환경: .env 파일을 로드했습니다.")
except ImportError:
    print("Docker 환경: 환경변수를 직접 사용합니다.")

# 환경변수 가져오기 (개발환경의 .env 파일 또는 Docker의 환경변수)
try:
    # os.environ.get() 대신 직접 접근
    DB_USER = os.environ['POSTGRES_USER']
    DB_PASSWORD = os.environ['POSTGRES_PASSWORD']
    DB_NAME = os.environ['POSTGRES_DB']
    DB_HOST = os.environ['DB_HOST']
    DB_PORT = os.environ['DB_PORT']
except KeyError as e:
    print(f"환경변수 오류: {e}")
    raise ValueError(f"필수 환경변수가 설정되지 않았습니다: {e}")

# 데이터베이스 엔진 생성
engine = create_engine(f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")