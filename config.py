import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # 数据库配置
    MYSQL_HOST = os.getenv('MYSQL_HOST', 'localhost')
    MYSQL_PORT = int(os.getenv('MYSQL_PORT', 3306))
    MYSQL_USER = os.getenv('MYSQL_USER', 'cuotiji_user')
    MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', 'Cuotiji@2024')
    MYSQL_DB = os.getenv('MYSQL_DB', 'cuotiji')
    
    # URL 编码处理特殊字符
    SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://{user}:{password}@{host}:{port}/{db}'.format(
        user=MYSQL_USER,
        password=MYSQL_PASSWORD.replace('@', '%40'),  # URL 编码 @ 符号
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        db=MYSQL_DB
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # 百度OCR配置
    BAIDU_APP_ID = os.getenv('BAIDU_APP_ID', '')
    BAIDU_API_KEY = os.getenv('BAIDU_API_KEY', '')
    BAIDU_SECRET_KEY = os.getenv('BAIDU_SECRET_KEY', '')
    
    # 上传文件配置
    UPLOAD_FOLDER = 'uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max-limit
    
    # 添加 Deepseek 配置
    DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY', '') 