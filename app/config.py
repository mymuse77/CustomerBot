"""应用配置"""

# MySQL 数据库配置
DB_HOST = "127.0.0.1"
DB_PORT = 3306
DB_USER = "root"
DB_PASSWORD = "qwer~1234"
DB_NAME = "spkf"

# DeepSeek API 配置
DEEPSEEK_API_KEY = "sk-b4f5d1a133c041c79c519a87a55f6c62"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

# 数据库表结构描述（供 Text2SQL 使用）
DB_SCHEMA = """
数据库: spkf (MySQL)

表结构如下:

1. regions - 区域信息表
   - id INT PRIMARY KEY AUTO_INCREMENT  -- 区域唯一标识
   - name VARCHAR(100) NOT NULL  -- 区域名称
   - parent_id INT DEFAULT 0  -- 父区域ID，0表示顶级区域
   - level TINYINT NOT NULL  -- 区域层级（1:省/直辖市，2:市，3:区/县，4:街道/乡镇）

2. cameras - 摄像机信息表
   - id INT PRIMARY KEY AUTO_INCREMENT  -- 摄像机唯一标识
   - name VARCHAR(100) NOT NULL  -- 摄像机名称
   - region_id INT NOT NULL  -- 所属区域ID，关联regions表id
   - online_status TINYINT NOT NULL  -- 在线状态（0:离线，1:在线）
   - check_time DATETIME NOT NULL  -- 最后状态检查时间

3. cameras_img_checks - 摄像机图片质量检测记录表
   - id INT PRIMARY KEY AUTO_INCREMENT  -- 检测记录唯一标识
   - camera_id INT NOT NULL  -- 关联摄像机ID，关联cameras表id
   - img_status TINYINT NOT NULL  -- 图片状态（0:异常，1:正常，2:模糊，3:过曝，4:欠曝）
   - check_time DATETIME NOT NULL  -- 图片检测时间

表间关系:
- cameras.region_id -> regions.id （摄像机所属区域）
- cameras_img_checks.camera_id -> cameras.id （检测记录关联摄像机）

区域表是树形结构，通过 parent_id 形成父子关系，parent_id=0 为顶级区域。
"""
