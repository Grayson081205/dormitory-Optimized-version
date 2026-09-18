import logging
import os
from dotenv import load_dotenv
from app import create_app

# 加载 .env 文件（override=True 强制覆盖已存在的环境变量）
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path, override=True)
    print(f"已加载环境变量文件: {dotenv_path}")
    print(f"ADMIN_PASSWORD: {os.getenv('ADMIN_PASSWORD', 'NOT SET')}")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
)

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
