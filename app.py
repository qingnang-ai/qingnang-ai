import os
import io
import json
import base64
import time
import socket
import hashlib
import sqlite3
import wave as wavemodule
from datetime import datetime
from functools import wraps

if hasattr(socket, 'getfqdn'):
    _orig_getfqdn = socket.getfqdn
    def _safe_getfqdn(name=''):
        try:
            return _orig_getfqdn(name)
        except Exception:
            return 'localhost'
    socket.getfqdn = _safe_getfqdn

import cv2
import requests
import numpy as np
from PIL import Image, ImageOps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, g
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "qingnang-dev-change-in-production")

YOLO_MODEL_PATH = os.environ.get("YOLO_MODEL_PATH", os.path.join(os.path.expanduser("~"), "yolo", "best.pt"))
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qingnang.db")

# ============================================================
# 数据库初始化
# ============================================================

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DB_PATH)
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS health_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            child_name TEXT DEFAULT '',
            child_age TEXT DEFAULT '',
            tongue_features TEXT DEFAULT '',
            tongue_primary TEXT DEFAULT '',
            constitution_scores TEXT DEFAULT '',
            qa_results TEXT DEFAULT '',
            qa_age TEXT DEFAULT '',
            wellness_tips TEXT DEFAULT '',
            wellness_foods TEXT DEFAULT '',
            ai_report TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    db.commit()
    db.close()

def init_db():
    db = sqlite3.connect(DB_PATH)
    db.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT UNIQUE NOT NULL,
            user_id INTEGER,
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            amount TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            alipay_trade_no TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            paid_at TEXT DEFAULT ''
        )
    """)
    db.commit()
    db.close()

init_db()

# ============================================================
# 认证工具
# ============================================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def current_user():
    if 'user_id' in session:
        db = get_db()
        return db.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    return None

ADMIN_NAME = os.environ.get("ADMIN_NAME", "青囊馆主")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change-me-in-production")

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# ============================================================
# ★★★ DeepSeek API配置（服务端，用户无需填写）★★★
#
# 你只需要改下面 4 个值，改完重启即可
#
# 1. DEEPSEEK_API_KEY  ：DeepSeek平台 → API Keys → 创建
# 2. DEEPSEEK_MODEL    ：模型名称，deepseek-chat（通用对话）或 deepseek-reasoner（深度推理）
# 3. DEEPSEEK_TEMPERATURE：生成随机性 0.0~1.0，越高越发散，越低越稳定
# 4. DEEPSEEK_MAX_TOKENS：返回最大字数
#
# ============================================================
DEEPSEEK_API_URL      = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_API_KEY      = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL        = "deepseek-chat"
DEEPSEEK_TEMPERATURE  = 0.7
DEEPSEEK_MAX_TOKENS   = 4096

# ============================================================
# ★★★ 支付宝支付配置（服务端，用户无需填写）★★★
#
# 你只需要改下面 5 个值，改完重启即可
#
# 1. ALIPAY_APP_ID      ：支付宝开放平台 → 应用 → APPID
# 2. ALIPAY_APP_PRIVATE_KEY：应用私钥（RSA2，一长串）
# 3. ALIPAY_ALIPAY_PUBLIC_KEY：支付宝公钥（用于验签）
# 4. ALIPAY_GATEWAY     ：网关地址（正式环境 alipay.com，沙箱 openapi.alipaydev.com）
# 5. ALIPAY_NOTIFY_URL  ：异步通知地址（需公网HTTPS，本地测试可留空）
#
# ============================================================
ALIPAY_APP_ID          = ""  # ← 填你的支付宝APPID
ALIPAY_APP_PRIVATE_KEY = ""  # ← 填你的应用私钥
ALIPAY_ALIPAY_PUBLIC_KEY = ""  # ← 填支付宝公钥
ALIPAY_GATEWAY         = "https://openapi.alipay.com/gateway.do"
ALIPAY_NOTIFY_URL      = ""  # ← 填异步通知URL（需公网HTTPS）
ALIPAY_RETURN_URL      = "http://127.0.0.1:5000/pay/return"

# 虚拟商品列表
SHOP_PRODUCTS = [
    {"id": "p001", "name": "青囊·四季养生茶饮包", "price": "68.00", "desc": "根据体质定制四季茶饮搭配方案", "icon": "🍵"},
    {"id": "p002", "name": "青囊·体质食疗食材礼盒", "price": "128.00", "desc": "针对您体质倾向精选药食同源食材", "icon": "🥗"},
    {"id": "p003", "name": "青囊·儿童健脾开胃糊", "price": "88.00", "desc": "山药莲子芡实等健脾食材研磨", "icon": "🥣"},
    {"id": "p004", "name": "青囊·节气养生汤包", "price": "58.00", "desc": "二十四节气对应养生汤料搭配", "icon": "🍲"},
]

# ============================================================
# 21类标签：完整版（来自原版 tongue_ai_app.py）
# ============================================================

FEATURE_META = {
    "jiankangshe": {
        "cn": "健康舌", "group": "综合",
        "desc": "模型未发现明显的目标舌象特征，仍需结合拍摄质量与日常状态观察。",
        "tcm": "传统舌诊通常会综合舌色、舌形、舌苔等多方面信息判断，单一标签不能代表完整健康状态。",
        "tips": ["保持规律作息", "保持充足饮水", "维持均衡饮食与日常运动"],
        "foods": ["新鲜蔬菜", "全谷杂粮", "优质蛋白", "当季水果"],
    },
    "botaishe": {
        "cn": "薄苔舌", "group": "舌苔",
        "desc": "舌面可见较薄的舌苔覆盖。",
        "tcm": "薄苔在传统舌诊中可见于正常舌象，也需要结合苔色、舌色及其他信息综合观察。",
        "tips": ["饮食保持清淡均衡", "避免因一次检测自行大量忌口", "保持口腔清洁"],
        "foods": ["绿叶蔬菜", "全谷物", "豆制品", "蛋奶类"],
    },
    "hongshe": {
        "cn": "红舌", "group": "舌色",
        "desc": "模型观察到舌体颜色整体偏红。",
        "tcm": "传统舌诊中红舌常被用于观察偏\u201c热\u201d的舌象表现，但不能单凭舌色判断具体证候或疾病。",
        "tips": ["近期少熬夜", "减少过辣、过烫饮食", "规律饮水并观察是否持续"],
        "foods": ["清淡蔬菜", "当季水果", "豆腐/豆制品", "清汤类食物"],
    },
    "zishe": {
        "cn": "紫舌", "group": "舌色",
        "desc": "模型观察到舌体颜色偏紫或暗紫。",
        "tcm": "传统舌诊会结合紫暗程度、舌下络脉及全身表现综合判断；照片白平衡也可能造成色彩偏差。",
        "tips": ["优先在自然光下重新拍摄确认", "避免滤镜和强色温灯光", "若肉眼持续明显异常并伴不适，及时咨询专业医疗人员"],
        "foods": ["均衡主食", "蔬菜", "优质蛋白", "充足饮水"],
    },
    "pangdashe": {
        "cn": "胖大舌", "group": "舌形",
        "desc": "模型观察到舌体相对宽大或饱满。",
        "tcm": "传统舌诊会将舌体胖瘦与舌色、齿痕、津液等共同观察，不宜单独解释。",
        "tips": ["拍摄时让舌头自然放松", "饮食规律，避免暴饮暴食", "保持适量运动和稳定作息"],
        "foods": ["清淡家常菜", "全谷杂粮", "蔬菜", "优质蛋白"],
    },
    "shoushe": {
        "cn": "瘦舌", "group": "舌形",
        "desc": "模型观察到舌体相对偏瘦或偏薄。",
        "tcm": "传统舌诊会把舌体胖瘦作为形态线索之一，需与营养、体型、舌色和其他舌象共同判断。",
        "tips": ["保证规律三餐", "注意整体营养摄入", "避免仅依据舌象自行进补"],
        "foods": ["蛋奶类", "豆制品", "鱼肉蛋等优质蛋白", "谷薯类"],
    },
    "hongdianshe": {
        "cn": "红点舌", "group": "舌面",
        "desc": "模型在舌面观察到局部红点或点状特征。",
        "tcm": "传统舌诊会观察红点的位置与数量；局部刺激、饮食、拍摄清晰度等也可能影响识别。",
        "tips": ["减少辛辣和过烫食物刺激", "注意口腔清洁", "若伴疼痛、溃疡或持续加重，建议就医检查"],
        "foods": ["温度适宜的食物", "蔬菜", "水果", "充足饮水"],
    },
    "liewenshe": {
        "cn": "裂纹舌", "group": "舌面",
        "desc": "模型在舌面检测到沟纹或裂纹样结构。",
        "tcm": "裂纹是可见的舌面形态特征，传统舌诊会结合深浅、分布和舌色进一步观察。",
        "tips": ["保持口腔清洁", "规律饮水", "清洁舌面时动作轻柔，避免损伤"],
        "foods": ["水分充足的普通食物", "蔬菜", "水果", "清淡汤羹"],
    },
    "chihenshe": {
        "cn": "齿痕舌", "group": "舌形",
        "desc": "模型在舌缘检测到类似牙齿压痕的边缘形态。",
        "tcm": "传统舌诊常将齿痕与舌体胖瘦等一起观察；伸舌姿势和牙列也会影响外观。",
        "tips": ["拍照时轻轻伸舌，不要用力顶牙", "保持规律饮食", "若长期明显伴咬舌、肿痛等情况，可咨询口腔科"],
        "foods": ["清淡家常菜", "全谷物", "蔬菜", "优质蛋白"],
    },
    "baitaishe": {
        "cn": "白苔舌", "group": "舌苔",
        "desc": "模型观察到舌苔颜色以白色或偏白为主。",
        "tcm": "白苔是常见舌苔颜色之一，需要结合厚薄、润燥、舌色等共同观察。",
        "tips": ["保持口腔清洁", "饮食规律、少油腻", "观察是否受奶制品或食物残留影响"],
        "foods": ["熟制蔬菜", "米面杂粮", "豆制品", "清淡汤类"],
    },
    "huangtaishe": {
        "cn": "黄苔舌", "group": "舌苔",
        "desc": "模型观察到舌苔呈黄色或偏黄色。",
        "tcm": "传统舌诊常会把黄苔作为舌苔颜色线索之一，但食物、饮料、吸烟及光照也可能造成着色。",
        "tips": ["先排除咖啡、茶、深色食物等染色", "减少油炸、过辣食物", "加强刷牙和温和舌面清洁"],
        "foods": ["绿叶蔬菜", "清淡主食", "水果", "白水"],
    },
    "heitaishe": {
        "cn": "黑苔舌", "group": "舌苔",
        "desc": "模型观察到舌苔存在明显灰黑或深色区域。",
        "tcm": "深色舌苔需要结合实际肉眼颜色和口腔情况判断，模型结果尤其容易受到染色、曝光和阴影影响。",
        "tips": ["自然光下复拍确认", "排除深色食物、咖啡、茶、吸烟等影响", "若肉眼持续明显黑苔或伴不适，建议咨询医生或口腔科"],
        "foods": ["清淡均衡饮食", "蔬菜", "水果", "充足饮水"],
    },
    "huataishe": {
        "cn": "滑苔舌", "group": "舌苔",
        "desc": "模型观察到舌面较湿润、光滑或反光明显。",
        "tcm": "传统舌诊会把舌面润燥作为观察维度之一；拍摄闪光、唾液和曝光会明显影响这一特征。",
        "tips": ["拍摄前避免使用闪光灯直射", "保持正常饮水即可", "不要为改变舌象而刻意大量饮水或限制饮水"],
        "foods": ["均衡饮食", "熟制蔬菜", "全谷物", "优质蛋白"],
    },
    "shenquao": {
        "cn": "肾区凹", "group": "区域形态",
        "desc": "模型在其定义的“肾区”观察到凹陷样形态。",
        "tcm": "这是模型的区域形态标签，只表示图像中的局部外观，不能据此判断肾脏疾病或功能异常。",
        "tips": ["保持自然伸舌姿势并复拍确认", "结合其他舌象而非单独解读该区域"],
        "foods": ["均衡饮食", "蔬菜", "全谷物", "优质蛋白"],
    },
    "shenqutu": {
        "cn": "肾区凸", "group": "区域形态",
        "desc": "模型在其定义的“肾区”观察到隆起样形态。",
        "tcm": "这是模型的区域形态标签，只表示图像中的局部外观，不能据此判断肾脏疾病或功能异常。",
        "tips": ["保持自然伸舌姿势并复拍确认", "结合其他舌象而非单独解读该区域"],
        "foods": ["均衡饮食", "蔬菜", "全谷物", "优质蛋白"],
    },
    "gandanao": {
        "cn": "肝胆区凹", "group": "区域形态",
        "desc": "模型在其定义的“肝胆区”观察到凹陷样形态。",
        "tcm": "这是模型的区域形态标签，只表示图像中的局部外观，不能据此判断肝胆疾病或功能异常。",
        "tips": ["自然放松伸舌并复拍确认", "不要仅根据区域凹凸进行健康判断"],
        "foods": ["均衡饮食", "蔬菜", "水果", "优质蛋白"],
    },
    "gandantu": {
        "cn": "肝胆区凸", "group": "区域形态",
        "desc": "模型在其定义的“肝胆区”观察到隆起样形态。",
        "tcm": "这是模型的区域形态标签，只表示图像中的局部外观，不能据此判断肝胆疾病或功能异常。",
        "tips": ["自然放松伸舌并复拍确认", "不要仅根据区域凹凸进行健康判断"],
        "foods": ["均衡饮食", "蔬菜", "水果", "优质蛋白"],
    },
    "piweiao": {
        "cn": "脾胃区凹", "group": "区域形态",
        "desc": "模型在其定义的“脾胃区”观察到凹陷样形态。",
        "tcm": "这是模型的区域形态标签，只表示图像中的局部外观，不能据此判断胃肠疾病或消化功能异常。",
        "tips": ["拍摄时让舌面平展自然", "饮食规律，不依据单一标签自行治疗"],
        "foods": ["规律三餐", "谷薯类", "熟制蔬菜", "优质蛋白"],
    },
    "piweitu": {
        "cn": "脾胃区凸", "group": "区域形态",
        "desc": "模型在其定义的“脾胃区”观察到隆起样形态。",
        "tcm": "这是模型的区域形态标签，只表示图像中的局部外观，不能据此判断胃肠疾病或消化功能异常。",
        "tips": ["拍摄时让舌面平展自然", "饮食规律，不依据单一标签自行治疗"],
        "foods": ["规律三餐", "谷薯类", "熟制蔬菜", "优质蛋白"],
    },
    "xinfeiao": {
        "cn": "心肺区凹", "group": "区域形态",
        "desc": "模型在其定义的“心肺区”观察到凹陷样形态。",
        "tcm": "这是模型的区域形态标签，只表示图像中的局部外观，不能据此判断心肺疾病或功能异常。",
        "tips": ["自然放松伸舌并复拍确认", "不要根据区域形态自行推断器官状态"],
        "foods": ["均衡饮食", "蔬菜", "水果", "充足饮水"],
    },
    "xinfeitu": {
        "cn": "心肺区凸", "group": "区域形态",
        "desc": "模型在其定义的“心肺区”观察到隆起样形态。",
        "tcm": "这是模型的区域形态标签，只表示图像中的局部外观，不能据此判断心肺疾病或功能异常。",
        "tips": ["自然放松伸舌并复拍确认", "不要根据区域形态自行推断器官状态"],
        "foods": ["均衡饮食", "蔬菜", "水果", "充足饮水"],
    },
}

GROUP_ICON = {"综合": "◉", "舌色": "●", "舌形": "◇", "舌面": "✦", "舌苔": "≈", "区域形态": "⌖"}

# 舌象→体质倾向映射
FEATURE_CONSTITUTION = {
    "jiankangshe": {"平和质": 10}, "botaishe": {"平和质": 3},
    "hongshe": {"阴虚质": 5, "阳热质": 4, "湿热质": 3},
    "zishe": {"气郁质": 5}, "pangdashe": {"痰湿质": 5, "阳虚质": 3},
    "shoushe": {"阴虚质": 4, "气虚质": 3}, "hongdianshe": {"阳热质": 5, "阴虚质": 3},
    "liewenshe": {"阴虚质": 6}, "chihenshe": {"气虚质": 5, "痰湿质": 4, "阳虚质": 3},
    "baitaishe": {"阳虚质": 4, "痰湿质": 3, "气虚质": 2},
    "huangtaishe": {"湿热质": 6, "阳热质": 3, "食滞质": 3},
    "heitaishe": {}, "huataishe": {"气虚质": 3, "阴虚质": 3},
    "shenquao": {"阳虚质": 4}, "shenqutu": {"气郁质": 2},
    "gandanao": {"气郁质": 3}, "gandantu": {"气郁质": 4, "湿热质": 3},
    "piweiao": {"气虚质": 5, "食滞质": 2}, "piweitu": {"痰湿质": 4, "食滞质": 3},
    "xinfeiao": {"气虚质": 4}, "xinfeitu": {"阳热质": 3, "阴虚质": 2},
}

# ============================================================
# 问卷数据（来自 PDF《儿童体质中医分型与判定标准》）
# ============================================================

QUESTIONNAIRES = {
    "平和质": [("体型正常","3pt"),("肌肉结实","3pt"),("脸色红润有气色（跟手臂内侧比，脸上有自然粉红色）","3pt"),("头发有光泽","3pt"),("精力充沛","5pt"),("声音洪亮","5pt"),("食欲好且食量正常","5pt"),("入睡快睡眠安稳","5pt"),("便质正常每日排便1~2次","5pt"),("性格开朗","5pt"),("很少生病","2pt"),("生病后很快康复","5pt")],
    "特禀质": [("眼下有青黑色的圈（跟周围皮肤比，下眼皮下方发青发暗）","3pt"),("接触过敏原后易皮肤痒","5pt"),("易出现过敏性疾病如鼻炎等","5pt"),("吃某种东西后易腹痛泄泻","5pt"),("易起湿疹荨麻疹","5pt"),("喜欢揉鼻子揉眼睛或眨眼","5pt"),("有家族过敏性疾病史","2pt"),("小时候有慢性腹泻或湿疹史","5pt"),("有喘息病史","2pt")],
    "气虚质": [("肌肉松软","3pt"),("脸色偏白看起来没血色（跟同龄孩子比，脸色明显偏白）","3pt"),("脸色偏黄看起来暗沉（跟手臂内侧皮肤比，脸明显偏黄发暗）","3pt"),("头发缺少光泽","3pt"),("容易劳累没精神","5pt"),("声音小或哭声微弱","5pt"),("大便不成形或夹杂未消化食物","5pt"),("活动后易出汗","5pt"),("喜欢安静不爱户外活动","5pt"),("胆子小说话少","5pt"),("每年患呼吸道感染频率","freq"),("肚子胀","5pt")],
    "阳虚质": [("脸色偏白看起来没血色（跟同龄孩子比，脸色明显偏白）","3pt"),("容易劳累没精神","5pt"),("食欲差","5pt"),("吃凉的食物会不适","5pt"),("多眠易困","5pt"),("怕冷","5pt"),("手脚凉","5pt"),("喜欢安静不爱户外活动","5pt"),("胆子小说话少","5pt"),("每年患呼吸道感染频率","freq")],
    "阴虚质": [("体型偏瘦","3pt"),("嘴唇偏红且干燥起皮（跟大人嘴唇比，红得不正常）","3pt"),("入睡时间长或轻浅易醒","5pt"),("大便干燥","5pt"),("手心脚心发烫","5pt"),("睡觉时易出汗","5pt"),("脾气急躁","5pt"),("皮肤干燥或易瘙痒","5pt"),("易起口疮嗓子痛","5pt"),("喜欢揉鼻子揉眼睛或眨眼","5pt")],
    "阳热质": [("脸颊明显发红（跟额头下巴比，两颊明显更红）","3pt"),("嘴唇偏红且干燥起皮（跟大人嘴唇比，红得不正常）","3pt"),("精力旺盛活动多","5pt"),("饭量大且容易饿","5pt"),("睡眠不踏实来回翻滚","5pt"),("大便干燥","5pt"),("大便气味臭","5pt"),("怕热活动后出汗多","5pt"),("脾气急躁","5pt"),("易起口疮嗓子痛","5pt"),("晨起眼屎多","5pt")],
    "气郁质": {"age_range":"4-12","items":[("体型偏瘦","3pt"),("入睡时间长","5pt"),("大便干燥","5pt"),("心思细腻敏感","5pt"),("容易闷闷不乐唉声叹气","5pt"),("容易焦虑想事太多","5pt"),("受挫后情绪低落持续较久","5pt"),("容易打嗝或恶心干呕","5pt"),("总觉得喉咙里有东西卡着","5pt"),("有无明显原因的头痛","5pt"),("入学后适应集体生活慢","5pt")]},
    "痰湿质": [("下眼皮浮肿（看起来鼓鼓的，有水肿感）","3pt"),("容易劳累没精神","5pt"),("食欲差","5pt"),("不喜欢喝水","5pt"),("多眠易困","5pt"),("大便不成形","5pt"),("出汗时汗液发黏不清爽","5pt"),("喜欢安静不爱户外活动","5pt"),("做事拖沓性子慢","5pt"),("易起湿疹荨麻疹","5pt"),("肚子胀","5pt"),("易打嗝或恶心干呕","5pt"),("觉得嗓子有痰","5pt"),("咳嗽时容易痰多","5pt")],
    "湿热质": [("晚上睡觉容易哭或惊醒","5pt"),("大便黏便盆不易冲刷","5pt"),("出汗时汗液发黏不清爽","5pt"),("脾气急躁","5pt"),("易起湿疹","5pt"),("肚子胀","5pt"),("易起口疮嗓子痛","5pt"),("晨起眼屎多","5pt"),("口气重","5pt")],
    "食滞质": [("睡眠不踏实或喜欢趴着睡","5pt"),("睡觉磨牙","5pt"),("脾气急躁","5pt"),("容易肚子疼或胀","5pt"),("口气重","5pt"),("打嗝易有酸臭味","5pt"),("有进食过多积食情况","5pt")],
    "偏心亢质": [("脸颊明显发红（跟额头下巴比，两颊明显更红）","3pt"),("入睡时间长","5pt"),("易起口疮嗓子痛","5pt")],
    "偏肝亢质": [("鼻梁中间皮肤发青或能看到青色血管（跟两颊比，偏青偏暗）","3pt"),("晚上睡觉容易哭或惊醒","5pt"),("睡眠不踏实来回翻滚","5pt"),("脾气急躁","5pt")],
    "偏脾虚质": [("全身肌肉松软","3pt"),("脸色偏黄看起来暗沉（跟手臂内侧皮肤比，脸明显偏黄发暗）","3pt"),("饭后容易肚子胀","5pt"),("大便不成形或夹杂未消化食物","5pt")],
    "偏肺虚质": [("脸色偏白看起来没血色（跟同龄孩子比，脸色明显偏白）","3pt"),("声音小或哭声微弱","5pt"),("活动后易出汗","5pt"),("每年患呼吸道感染频率","freq")],
    "偏肾虚质": [("体型偏矮","3pt"),("发量稀少","3pt"),("睡觉尿床","5pt"),("早产儿或低出生体重儿","2pt")],
}

ORGAN_TYPES = ["偏心亢质","偏肝亢质","偏脾虚质","偏肺虚质","偏肾虚质"]
BASIC_TYPES = ["平和质","特禀质","气虚质","阳虚质","阴虚质","阳热质","气郁质","痰湿质","湿热质","食滞质"]

STANDARDS = {
    "1-3": {"ph":60,"ph_o":38,"pp":38,"pp_t":31,"org":42,"org_t":31},
    "4-6": {"ph":58,"ph_o":41,"pp":41,"pp_t":32,"org":42,"org_t":34},
    "7-12": {"ph":60,"ph_o":39,"pp":39,"pp_t":32,"org":37,"org_t":29},
}

CONSTITUTION_INFO = {
    "平和质":"精神饱满，精力充沛，体形匀称，面色红润",
    "特禀质":"下睑暗影，皮肤易瘙痒，易打喷嚏鼻塞",
    "气虚质":"精神欠振，易于疲倦，肌肉松软，脸色偏黄没血色",
    "阳虚质":"神疲倦怠，脸色没有光泽，畏寒肢冷",
    "阴虚质":"形体偏瘦，两颧潮红，口鼻干燥，手足心热",
    "阳热质":"精神亢奋，形体壮实，面赤唇红，畏热喜凉",
    "气郁质":"神情抑郁，易烦闷，善太息",
    "痰湿质":"精神欠振，体型偏胖，面部油腻，喉中常有痰",
    "湿热质":"面垢油光，头汗多，有口气，大便黏腻",
    "食滞质":"有口气，嗳气酸腐，腹部胀满，夜寐不安",
    "偏心亢质":"面色偏红，哭声大，入睡困难，舌尖红绛",
    "偏肝亢质":"鼻梁有青筋，夜卧不安，偶有惊惕",
    "偏脾虚质":"脸色偏黄没血色，口唇色淡，肌肉松软，食后腹胀",
    "偏肺虚质":"面色偏白，声音较低微，自汗畏风",
    "偏肾虚质":"形体矮小，头发干枯稀少",
}

# ============================================================
# 工具函数（来自原版 + 新增）
# ============================================================

_model = None
def get_model():
    global _model
    if _model is not None:
        return _model
    try:
        from ultralytics import YOLO
        if os.path.exists(YOLO_MODEL_PATH):
            _model = YOLO(YOLO_MODEL_PATH)
            return _model
    except Exception:
        pass
    return None

def feature_meta(raw_name):
    return FEATURE_META.get(raw_name, {
        "cn": raw_name, "group": "其他",
        "desc": "模型检测到该自定义类别。",
        "tcm": "该类别尚未配置解释。",
        "tips": ["建议结合原始图像人工复核"],
        "foods": ["均衡饮食"],
    })

def confidence_text(conf):
    if conf >= 0.80: return "较高"
    if conf >= 0.55: return "中等"
    return "较低"

def aggregate_features(detections):
    best = {}
    for item in detections:
        key = item["raw_name"]
        if key not in best or item["confidence"] > best[key]["confidence"]:
            best[key] = item
    return sorted(best.values(), key=lambda x: x["confidence"], reverse=True)

def build_wellness_summary(unique_features):
    non_healthy = [x for x in unique_features if x["raw_name"] != "jiankangshe"]
    tips, foods = [], []
    for item in non_healthy if non_healthy else unique_features:
        meta = feature_meta(item["raw_name"])
        for tip in meta["tips"]:
            if tip not in tips: tips.append(tip)
        for food in meta["foods"]:
            if food not in foods: foods.append(food)
    tips = tips[:7]
    foods = foods[:10]
    if not unique_features:
        headline = "本次未检测到达到阈值的舌象特征。"
    elif not non_healthy:
        headline = "本次以“健康舌”标签为主，建议结合拍摄质量和日常状态持续观察。"
    else:
        names = "、".join(feature_meta(x["raw_name"])["cn"] for x in non_healthy[:5])
        headline = f"本次模型主要观察到：{names}。以下内容仅作为健康生活方式提示。"
    return headline, tips, foods

def tongue_to_constitution(features):
    scores = {}
    for f in features:
        en = f["raw_name"]
        if en in FEATURE_CONSTITUTION:
            for c, w in FEATURE_CONSTITUTION[en].items():
                scores[c] = scores.get(c, 0) + w * f["confidence"]
    if not scores:
        return "平和质", {}
    sorted_s = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_s[0][0], dict(sorted_s)

def get_options(qtype, age_key):
    if qtype == "5pt": return [("总是",5),("经常",4),("有时",3),("偶尔",2),("从不",1)]
    if qtype == "3pt": return [("符合",5),("比较符合",3),("不符合",1)]
    if qtype == "2pt": return [("是",5),("否",1)]
    if qtype == "freq":
        if age_key == "1-3": return [("每年≥7次",5),("每年2~6次",3),("每年<2次",1)]
        if age_key == "4-6": return [("每年≥6次",5),("每年2~5次",3),("每年<2次",1)]
        return [("每年≥5次",5),("每年2~4次",3),("每年<2次",1)]
    return [("—",1)]

def calc_score(const_name, answers, age_key):
    items = QUESTIONNAIRES[const_name]
    item_list = items["items"] if isinstance(items, dict) else items
    actual = sum(answers)
    min_s = len(item_list)
    max_s = sum(get_options(it[1], age_key)[0][1] for it in item_list)
    return round((actual - min_s) / (max_s - min_s) * 100, 1) if max_s > min_s else 0

def determine(scores, age_key):
    std = STANDARDS[age_key]
    results = []
    ph = scores.get("平和质", 0)
    others = {k: v for k, v in scores.items() if k in BASIC_TYPES and k != "平和质"}
    if ph >= std["ph"] and all(v < std["ph_o"] for v in others.values()):
        results.append({"name": "平和质", "level": "判定", "score": ph})
    for n, s in others.items():
        if n == "气郁质" and age_key == "1-3":
            continue
        if s >= std["pp"]:
            results.append({"name": n, "level": "判定", "score": s})
        elif s >= std["pp_t"]:
            results.append({"name": n, "level": "倾向", "score": s})
    for n in ORGAN_TYPES:
        s = scores.get(n, 0)
        if s >= std["org"]:
            results.append({"name": n, "level": "判定", "score": s})
        elif s >= std["org_t"]:
            results.append({"name": n, "level": "倾向", "score": s})
    return results

def run_detection(img_pil, conf=0.30, iou=0.50, imgsz=640):
    model = get_model()
    if model is None:
        return None, "模型未加载，请检查 best.pt 路径"
    img_np = np.array(img_pil)
    if len(img_np.shape) == 2:
        img_np = np.stack([img_np] * 3, axis=-1)
    elif img_np.shape[2] == 4:
        img_np = img_np[:, :, :3]
    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
    width, height = img_pil.size
    image_area = max(width * height, 1)
    start = time.time()
    results = model.predict(source=img_bgr, conf=conf, iou=iou, imgsz=imgsz, verbose=False)
    elapsed_ms = (time.time() - start) * 1000
    r = results[0]
    annotated_bgr = r.plot(conf=True, labels=True, boxes=True)
    annotated_rgb = cv2.cvtColor(annotated_bgr, cv2.COLOR_BGR2RGB)
    detections = []
    for index, box in enumerate(r.boxes):
        cls_id = int(box.cls[0].item())
        conf_val = float(box.conf[0].item())
        x1, y1, x2, y2 = box.xyxy[0].cpu().tolist()
        raw_name = r.names[cls_id]
        meta = feature_meta(raw_name)
        bbox_area = max(x2 - x1, 0) * max(y2 - y1, 0)
        detections.append({
            "index": index + 1,
            "class_id": cls_id,
            "raw_name": raw_name,
            "cn_name": meta["cn"],
            "group": meta["group"],
            "confidence": round(conf_val, 4),
            "confidence_level": confidence_text(conf_val),
            "x1": round(x1), "y1": round(y1), "x2": round(x2), "y2": round(y2),
            "box_area_percent": round(bbox_area / image_area * 100, 2),
            "desc": meta["desc"],
            "tcm": meta["tcm"],
            "tips": meta["tips"],
            "foods": meta["foods"],
        })
    unique_features = aggregate_features(detections)
    return {
        "detections": detections,
        "unique_features": unique_features,
        "annotated": annotated_rgb,
        "elapsed": round(elapsed_ms),
    }, None

def call_deepseek(messages):
    try:
        resp = requests.post(DEEPSEEK_API_URL,
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": DEEPSEEK_MODEL,
                "messages": messages,
                "temperature": DEEPSEEK_TEMPERATURE,
                "max_tokens": DEEPSEEK_MAX_TOKENS,
            },
            timeout=60)
        if resp.status_code != 200:
            err_data = resp.json()
            return None, f"API错误: {err_data.get('error',{}).get('message',resp.text)}"
        return resp.json()["choices"][0]["message"]["content"], None
    except Exception as e:
        return None, str(e)

# ============================================================
# 路由
# ============================================================

@app.context_processor
def inject_user():
    return {'current_user': current_user(), 'admin_name': ADMIN_NAME}

@app.template_filter('from_json')
def from_json_filter(value):
    try:
        return json.loads(value) if value else []
    except (json.JSONDecodeError, TypeError):
        return []

# ----- 认证路由 -----

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            return render_template("auth.html", mode="register", error="请输入用户名和密码")
        if len(username) < 2:
            return render_template("auth.html", mode="register", error="用户名至少2个字符")
        if len(password) < 6:
            return render_template("auth.html", mode="register", error="密码至少6个字符")
        db = get_db()
        existing = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            return render_template("auth.html", mode="register", error="该用户名已被注册")
        db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                   (username, generate_password_hash(password)))
        db.commit()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        session.clear()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="register")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not user or not check_password_hash(user["password_hash"], password):
            return render_template("auth.html", mode="login", error="用户名或密码错误")
        session.clear()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="login")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ----- 用户仪表盘 -----

@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    records = db.execute(
        "SELECT * FROM health_records WHERE user_id = ? ORDER BY created_at DESC",
        (session["user_id"],)
    ).fetchall()
    return render_template("dashboard.html", records=records)

@app.route("/dashboard/record/<int:record_id>")
@login_required
def view_record(record_id):
    db = get_db()
    record = db.execute(
        "SELECT * FROM health_records WHERE id = ? AND user_id = ?",
        (record_id, session["user_id"])
    ).fetchone()
    if not record:
        return redirect(url_for("dashboard"))
    return render_template("record_detail.html", record=record)

@app.route("/api/save_record", methods=["POST"])
@login_required
def save_record():
    data = request.json
    db = get_db()
    tongue_features = ""
    tongue_primary = ""
    constitution_scores = ""
    wellness_tips = ""
    wellness_foods = ""
    ta = session.get("tongue_analysis")
    if ta:
        tongue_features = json.dumps(ta.get("unique_features", []), ensure_ascii=False)
        tongue_primary = ta.get("primary_constitution", "")
        constitution_scores = json.dumps(ta.get("constitution_scores", {}), ensure_ascii=False)
        wellness_tips = json.dumps(ta.get("wellness", {}).get("tips", []), ensure_ascii=False)
        wellness_foods = json.dumps(ta.get("wellness", {}).get("foods", []), ensure_ascii=False)
    qa_results = json.dumps(session.get("qa_results", []), ensure_ascii=False)
    qa_age = session.get("qa_age", "")
    child_name = data.get("child_name", "")
    child_age = data.get("child_age", "")
    ai_report = data.get("ai_report", "")
    db.execute("""
        INSERT INTO health_records
        (user_id, child_name, child_age, tongue_features, tongue_primary,
         constitution_scores, qa_results, qa_age, wellness_tips, wellness_foods, ai_report)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (session["user_id"], child_name, child_age, tongue_features, tongue_primary,
          constitution_scores, qa_results, qa_age, wellness_tips, wellness_foods, ai_report))
    db.commit()
    return jsonify({"ok": True, "message": "记录已保存"})

@app.route("/api/delete_record/<int:record_id>", methods=["POST"])
@login_required
def delete_record(record_id):
    db = get_db()
    db.execute("DELETE FROM health_records WHERE id = ? AND user_id = ?",
               (record_id, session["user_id"]))
    db.commit()
    return jsonify({"ok": True})

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/tongue")
def tongue():
    return render_template("tongue.html")

@app.route("/questionnaire")
def questionnaire_page():
    return render_template("questionnaire.html")

@app.route("/report")
def report_page():
    return render_template("report.html")

@app.route("/atlas")
def atlas_page():
    return render_template("atlas.html", features=FEATURE_META)

@app.route("/api/detect", methods=["POST"])
def api_detect():
    try:
        if "image" not in request.files:
            return jsonify({"error": "未上传图片"}), 400
        file = request.files["image"]
        img = Image.open(io.BytesIO(file.read()))
        img = ImageOps.exif_transpose(img).convert("RGB")
        # 缩放过大图片，避免响应超限
        max_size = 1024
        if max(img.size) > max_size:
            ratio = max_size / max(img.size)
            img = img.resize((int(img.size[0]*ratio), int(img.size[1]*ratio)), Image.LANCZOS)
        conf = float(request.form.get("confidence", 0.30))
        iou = float(request.form.get("iou", 0.50))
        imgsz = int(request.form.get("imgsz", 640))
        result, err = run_detection(img, conf, iou, imgsz)
        if err:
            return jsonify({"error": err}), 500
        _, buf = cv2.imencode(".jpg", result["annotated"], [int(cv2.IMWRITE_JPEG_QUALITY), 75])
        annotated_b64 = base64.b64encode(buf).decode("utf-8")
        orig_buf = io.BytesIO()
        img.save(orig_buf, format="JPEG", quality=75)
        orig_b64 = base64.b64encode(orig_buf.getvalue()).decode("utf-8")
        unique_features = result["unique_features"]
        headline, tips, foods = build_wellness_summary(unique_features)
        primary, const_scores = tongue_to_constitution(unique_features)
        data = {
            "detections": result["detections"],
            "unique_features": unique_features,
            "annotated_image": annotated_b64,
            "original_image": orig_b64,
            "elapsed": result["elapsed"],
            "primary_constitution": primary,
            "constitution_scores": const_scores,
            "wellness": {"headline": headline, "tips": tips, "foods": foods},
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        session_data = {
            "detections": result["detections"],
            "unique_features": unique_features,
            "elapsed": result["elapsed"],
            "primary_constitution": primary,
            "constitution_scores": const_scores,
            "wellness": {"headline": headline, "tips": tips, "foods": foods},
            "time": data["time"],
        }
        session["tongue_analysis"] = session_data
        history = session.get("tongue_history", [])
        history.insert(0, {
            "time": data["time"],
            "features": "、".join(f["cn_name"] for f in unique_features) or "无",
            "count": len(unique_features),
            "elapsed": result["elapsed"],
        })
        session["tongue_history"] = history[:12]
        return jsonify(data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/questionnaire", methods=["POST"])
def api_questionnaire():
    data = request.json
    age_key = data.get("age_group", "1-3")
    answers_map = data.get("answers", {})
    all_scores = {}
    for const_name, const_data in QUESTIONNAIRES.items():
        items_list = const_data["items"] if isinstance(const_data, dict) else const_data
        if isinstance(const_data, dict) and const_data.get("age_range") == "4-12" and age_key == "1-3":
            continue
        answers = answers_map.get(const_name, [])
        if len(answers) != len(items_list):
            answers = [1] * len(items_list)
        all_scores[const_name] = calc_score(const_name, answers, age_key)

    tongue_integrated = False
    ta = session.get("tongue_analysis")
    if ta and ta.get("constitution_scores"):
        tongue_integrated = True
        for const_name, t_score in ta["constitution_scores"].items():
            bonus = min(15, round(t_score * 5, 1))
            all_scores[const_name] = round(min(100, all_scores.get(const_name, 0) + bonus), 1)

    results = determine(all_scores, age_key)
    session["qa_scores"] = all_scores
    session["qa_results"] = results
    session["qa_age"] = age_key
    return jsonify({
        "scores": all_scores,
        "results": results,
        "age_group": age_key,
        "tongue_integrated": tongue_integrated,
    })

@app.route("/api/report", methods=["POST"])
def api_report():
    if not DEEPSEEK_API_KEY:
        return jsonify({"error": "服务端未配置DeepSeek API Key，请联系管理员"}), 500
    report_parts = []

    # 望诊 · 舌象检测
    ta = session.get("tongue_analysis")
    if ta:
        features = ta.get("unique_features", [])
        if features:
            feat_text = "\n".join(
                f"- {feature_meta(f['raw_name'])['cn']}（{f['raw_name']}）：置信度{f['confidence']:.1%}，{feature_meta(f['raw_name'])['desc']}"
                for f in features
            )
            report_parts.append(
                f"### 望诊 · 舌象检测\n检测到以下舌象特征：\n{feat_text}\n\n"
                f"舌象提示体质倾向：{ta.get('primary_constitution', '未知')}\n\n"
                f"健康提示：{ta.get('wellness', {}).get('headline', '')}"
            )
        else:
            report_parts.append("### 望诊 · 舌象检测\n未检测到明显异常舌象特征")

    # 闻诊 · 声音分析
    va = session.get("voice_analysis")
    if va:
        voice_text = f"声音综合判断：{va.get('summary', '')}\n声音体质提示：{va.get('primary_constitution', '未明确')}"
        report_parts.append(f"### 闻诊 · 声音分析\n{voice_text}")

    # 问诊 · 体质问卷
    qa_results = session.get("qa_results")
    if qa_results:
        result_text = "\n".join(
            f"- {r['name']}：{r['level']}（转化分数{r['score']:.1f}%）"
            for r in qa_results
        ) or "- 各项评分均未达判定标准"
        report_parts.append(
            f"### 问诊 · 体质问卷（年龄段：{session.get('qa_age', '未知')}）\n{result_text}"
        )

    # 切诊 · 面相分析
    fa = session.get("face_analysis")
    if fa:
        zone_text = ""
        for z in fa.get("zones", []):
            zone_text += f"- {z['zone']}（候{z['organ']}）：{z['color']}色 — {z['tcm']}\n"
        face_text = f"面色综合判断：{fa.get('summary', '')}\n面部主色：{fa.get('dominant_color', '未明确')}\n各区域分析：\n{zone_text}"
        report_parts.append(f"### 切诊 · 面相分析\n{face_text}")

    missing = []
    if not session.get("tongue_analysis"):
        missing.append("望·舌诊")
    if not session.get("voice_analysis"):
        missing.append("闻·声音")
    if not session.get("face_analysis"):
        missing.append("切·面相")
    if missing:
        return jsonify({"error": f"需完成望闻切三项检测才能解锁AI报告，还差：{'、'.join(missing)}"}), 400
    combined = "\n\n".join(report_parts)
    diag_count = len(report_parts)
    prompt = f"""你是一位经验丰富的中医健康管理师，请根据以下"望闻问切"四诊检测数据，用通俗易懂的语言为家长生成儿童健康综合分析报告。

本次共完成 {diag_count} 项检测：

{combined}

请按以下格式输出：

一、**四诊综合分析**
结合已完成的检测结果，从望（舌象）、闻（声音）、问（问卷）、切（面相）四个维度综合分析体质状况。对于未完成的检测项，不做推测。已完成的检测项越多，分析越全面。

二、**体质判定与解读**
综合四诊数据，给出最可能的体质类型（如平和质、气虚质、阴虚质、阳虚质、痰湿质、湿热质、气郁质、特禀质、食滞质等），并用通俗白话解释该体质的特征。如四诊数据指向不同体质，说明主次关系。

三、**日常调养建议**
1. 饮食建议：推荐食材、忌口食材（药食同源的日常食材）
2. 起居建议：作息、运动、睡眠
3. 情志建议：情绪管理与心理调适
4. 望闻问切专项建议：针对舌象、声音、面相、问卷中的具体异常给出针对性建议

四、**注意事项**

要求：
- 禁止疾病诊断话术，只描述"体质倾向""身体偏颇""调养建议"
- 中医术语必须附带白话解释
- 面向家长，语言亲切易懂
- 每项检测数据都要在分析中有所体现
- 末尾标注："以上分析仅作体质科普参考，不构成医疗诊断，不能替代医师诊疗"
"""
    reply, err = call_deepseek([{"role": "user", "content": prompt}])
    if err:
        return jsonify({"error": err}), 500

    constitution = ""
    if ta and ta.get("primary_constitution"):
        constitution = ta["primary_constitution"]
    food_prompt = f"""你是一位中医食疗顾问，请根据以下健康报告和体质分析结果，给出食疗推荐。

体质倾向：{constitution}

检测数据摘要：
{combined[:1500]}

请按以下格式输出食疗推荐（只推荐药食同源的日常食材，不推荐中药方剂）：

### 🍲 体质食疗推荐

**适合多吃的食材**（列出5-8种，每种用一句话说明为什么适合）
- 食材名：功效说明

**建议少吃的食材**（列出3-5种，每种说明原因）
- 食材名：原因

**推荐食疗方**（2-3道家常食疗，用日常食材）
1. 菜名：食材 + 简单做法 + 适合原因

要求：
- 所有推荐必须是超市/菜市场能买到的普通食材，不是药品
- 语言通俗，面向普通家长
- 末尾标注："以上食材推荐仅作日常饮食参考，不替代专业营养师或医师建议"
"""

    food_reply, food_err = call_deepseek([{"role": "user", "content": food_prompt}])

    VIRTUAL_SHELF = [
        {"id": 1, "name": "青囊·四季养生茶饮包", "tag": "药食同源", "desc": "根据体质定制四季茶饮搭配方案", "price": "即将上架", "icon": "🍵", "status": "coming"},
        {"id": 2, "name": "青囊·体质食疗食材礼盒", "tag": "食材精选", "desc": "针对您体质倾向挑选的药食同源食材组合", "price": "即将上架", "icon": "🥗", "status": "coming"},
        {"id": 3, "name": "青囊·儿童健脾开胃糊", "tag": "药膳辅食", "desc": "山药、莲子、芡实等健脾食材研磨", "price": "即将上架", "icon": "🥣", "status": "coming"},
        {"id": 4, "name": "青囊·节气养生汤包", "tag": "时令推荐", "desc": "二十四节气对应养生汤料搭配", "price": "即将上架", "icon": "🍲", "status": "coming"},
    ]

    return jsonify({
        "report": reply,
        "food_therapy": food_reply if not food_err else None,
        "shelf": VIRTUAL_SHELF,
        "constitution": constitution,
    })

@app.route("/api/status")
def api_status():
    return jsonify({
        "tongue": session.get("tongue_analysis") is not None,
        "voice": session.get("voice_analysis") is not None,
        "qa": session.get("qa_results") is not None,
        "face": session.get("face_analysis") is not None,
        "model_loaded": get_model() is not None,
        "api_ready": bool(DEEPSEEK_API_KEY),
        "logged_in": 'user_id' in session,
        "username": session.get("username", ""),
    })

@app.route("/api/wellness")
def api_wellness():
    ta = session.get("tongue_analysis")
    if not ta:
        return jsonify({"error": "请先完成舌象分析"}), 400
    return jsonify(ta.get("wellness", {}))

@app.route("/api/history")
def api_history():
    return jsonify({"history": session.get("tongue_history", [])})

@app.route("/api/history/clear", methods=["POST"])
def api_history_clear():
    session["tongue_history"] = []
    return jsonify({"ok": True})

@app.route("/api/questionnaire_data")
def api_questionnaire_data():
    age_key = request.args.get("age", "1-3")
    data = {}
    for const_name, const_data in QUESTIONNAIRES.items():
        items_list = const_data["items"] if isinstance(const_data, dict) else const_data
        if isinstance(const_data, dict) and const_data.get("age_range") == "4-12" and age_key == "1-3":
            continue
        is_organ = const_name in ORGAN_TYPES
        data[const_name] = {
            "items": [{"question": q, "type": t, "options": get_options(t, age_key)} for q, t in items_list],
            "desc": CONSTITUTION_INFO.get(const_name, ""),
            "is_organ": is_organ,
        }
    return jsonify(data)

# ============================================================
# 面相分析（中医望诊 · 面部五色）
# ============================================================

FACE_ZONES = {
    "额头": {"organ": "心/肺", "desc": "额头候上焦，反映心肺状况"},
    "鼻部": {"organ": "脾胃", "desc": "鼻部候中焦，反映脾胃状况"},
    "左颊": {"organ": "肝", "desc": "左颊候肝胆，反映肝气状况"},
    "右颊": {"organ": "肺", "desc": "右颊候肺气，反映肺气状况"},
    "下颌": {"organ": "肾", "desc": "下颌候下焦，反映肾气状况"},
}

FIVE_COLORS = {
    "青": {"tcm": "青色主寒证、痛证、瘀证，多见于气滞血瘀或寒凝", "hint": "多与肝气不舒有关"},
    "赤": {"tcm": "赤色主热证，满面红赤为实热，午后颧红为虚热", "hint": "多与心火或阴虚火旺有关"},
    "黄": {"tcm": "黄色主虚证、湿证，萎黄为脾虚，黄胖为湿盛", "hint": "多与脾胃虚弱或湿邪困脾有关"},
    "白": {"tcm": "白色主虚证、寒证，淡白为气血不足，㿠白为阳虚", "hint": "多与肺气虚或阳虚有关"},
    "黑": {"tcm": "黑色主肾虚、水饮、瘀血，面色黧黑为肾阳虚", "hint": "多与肾阳不足或肾精亏损有关"},
}

_face_cascade = None
def get_face_cascade():
    global _face_cascade
    if _face_cascade is not None:
        return _face_cascade
    try:
        path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        _face_cascade = cv2.CascadeClassifier(path)
        if _face_cascade.empty():
            _face_cascade = None
    except Exception:
        _face_cascade = None
    return _face_cascade

def classify_face_color(h, s, v):
    """HSV → 中医五色"""
    if s < 35:
        if v > 160:
            return "白", FIVE_COLORS["白"]
        if v < 90:
            return "黑", FIVE_COLORS["黑"]
    if h < 8 or h > 172:
        return "赤", FIVE_COLORS["赤"]
    if 8 <= h < 25:
        if s > 80 and v < 140:
            return "黄", FIVE_COLORS["黄"]
        return "赤", FIVE_COLORS["赤"]
    if 25 <= h < 45:
        return "黄", FIVE_COLORS["黄"]
    if 45 <= h < 85:
        return "青", FIVE_COLORS["青"]
    if v < 100:
        return "黑", FIVE_COLORS["黑"]
    return "青", FIVE_COLORS["青"]

def analyze_face(img_pil):
    cascade = get_face_cascade()
    if cascade is None:
        return None, "人脸检测模块未加载"
    img_np = np.array(img_pil)
    if len(img_np.shape) == 2:
        img_np = np.stack([img_np] * 3, axis=-1)
    elif img_np.shape[2] == 4:
        img_np = img_np[:, :, :3]
    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    faces = cascade.detectMultiScale(gray, scaleFactor=1.3, minNeighbors=5, minSize=(100, 100))
    if len(faces) == 0:
        return None, "未检测到人脸，请正对镜头并保证光线充足"
    areas = [w * h for (x, y, w, h) in faces]
    x, y, w, h = faces[int(np.argmax(areas))]
    annotated = img_bgr.copy()
    cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 200, 100), 3)
    zones_def = {
        "额头": (x, y, x + w, y + h // 3),
        "左颊": (x, y + h // 4, x + w // 2, y + 3 * h // 4),
        "右颊": (x + w // 2, y + h // 4, x + w, y + 3 * h // 4),
        "鼻部": (x + w // 3, y + h // 4, x + 2 * w // 3, y + 2 * h // 3),
        "下颌": (x + w // 4, y + 2 * h // 3, x + 3 * w // 4, y + h),
    }
    zone_colors = [(220, 200, 0), (0, 180, 220), (0, 180, 220), (0, 200, 100), (200, 100, 200)]
    zone_results = []
    color_count = {}
    for i, (zname, (zx1, zy1, zx2, zy2)) in enumerate(zones_def.items()):
        zone_img = img_bgr[zy1:zy2, zx1:zx2]
        if zone_img.size == 0:
            continue
        hsv = cv2.cvtColor(zone_img, cv2.COLOR_BGR2HSV)
        hm, sm, vm = float(np.mean(hsv[:, :, 0])), float(np.mean(hsv[:, :, 1])), float(np.mean(hsv[:, :, 2]))
        cname, cinfo = classify_face_color(hm, sm, vm)
        zmeta = FACE_ZONES.get(zname, {})
        zone_results.append({
            "zone": zname, "organ": zmeta.get("organ", ""), "desc": zmeta.get("desc", ""),
            "color": cname, "tcm": cinfo.get("tcm", ""), "hint": cinfo.get("hint", ""),
        })
        if cname != "正常":
            color_count[cname] = color_count.get(cname, 0) + 1
        cv2.rectangle(annotated, (zx1, zy1), (zx2, zy2), zone_colors[i], 2)
        cv2.putText(annotated, zname, (zx1 + 4, zy1 + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, zone_colors[i], 2)
    if color_count:
        dominant = max(color_count, key=color_count.get)
        summary = f"面部以「{dominant}」色为主，{FIVE_COLORS[dominant]['tcm']}"
    else:
        dominant = "正常"
        summary = "面部各区域色泽尚可，无明显异常偏色"
    annotated_rgb = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
    return {
        "zones": zone_results, "dominant_color": dominant, "summary": summary,
        "annotated": annotated_rgb,
    }, None

@app.route("/face")
def face_page():
    return render_template("face.html")

@app.route("/api/face_analyze", methods=["POST"])
def api_face_analyze():
    try:
        if "image" not in request.files:
            return jsonify({"error": "未上传图片"}), 400
        file = request.files["image"]
        img = Image.open(io.BytesIO(file.read()))
        img = ImageOps.exif_transpose(img).convert("RGB")
        max_size = 1024
        if max(img.size) > max_size:
            ratio = max_size / max(img.size)
            img = img.resize((int(img.size[0] * ratio), int(img.size[1] * ratio)), Image.LANCZOS)
        result, err = analyze_face(img)
        if err:
            return jsonify({"error": err}), 500
        _, buf = cv2.imencode(".jpg", result["annotated"], [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        annotated_b64 = base64.b64encode(buf).decode("utf-8")
        data = {
            "zones": result["zones"],
            "dominant_color": result["dominant_color"],
            "summary": result["summary"],
            "annotated_image": annotated_b64,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        session["face_analysis"] = {
            "zones": result["zones"],
            "dominant_color": result["dominant_color"],
            "summary": result["summary"],
            "time": data["time"],
        }
        return jsonify(data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ============================================================
# 声音分析（中医闻诊 · 声音辨析）
# ============================================================

VOICE_READING_TEXT = "青囊AI，望闻问切，辨体质，调阴阳。中医智慧，千年传承，护佑健康。"

def analyze_voice(wav_bytes):
    try:
        wf = wavemodule.open(io.BytesIO(wav_bytes), 'rb')
        sr = wf.getframerate()
        n_ch = wf.getnchannels()
        sw = wf.getsampwidth()
        n = wf.getnframes()
        raw = wf.readframes(n)
        wf.close()
        if sw == 2:
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        elif sw == 4:
            samples = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            samples = np.frombuffer(raw, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0
        if n_ch > 1:
            samples = samples[::n_ch]
        if len(samples) < sr * 0.5:
            return None, "录音时间过短，请至少录制3秒"
        rms = float(np.sqrt(np.mean(samples ** 2)))
        seg_start = len(samples) // 4
        seg_len = min(sr, len(samples) - seg_start)
        segment = samples[seg_start:seg_start + seg_len]
        autocorr = np.correlate(segment, segment, mode='full')
        autocorr = autocorr[len(autocorr) // 2:]
        if autocorr[0] > 0:
            autocorr = autocorr / autocorr[0]
        min_p = max(1, int(sr / 500))
        max_p = min(int(sr / 80), len(autocorr) - 1)
        pitch = 0.0
        if max_p > min_p:
            region = autocorr[min_p:max_p]
            if len(region) > 0:
                pi = int(np.argmax(region)) + min_p
                if autocorr[pi] > 0.25:
                    pitch = float(sr / pi)
        zcr = float(np.mean(np.abs(np.diff(np.sign(samples)))) / 2)
        duration = float(len(samples) / sr)
        fft_r = np.fft.rfft(segment)
        mag = np.abs(fft_r)
        freqs = np.fft.rfftfreq(len(segment), 1.0 / sr)
        centroid = float(np.sum(freqs * mag) / np.sum(mag)) if mag.sum() > 0 else 0.0
        result = map_voice_to_tcm(rms, pitch, zcr, duration, centroid)
        result["raw"] = {
            "rms": round(rms, 4), "pitch": round(pitch, 1), "zcr": round(zcr, 4),
            "duration": round(duration, 1), "centroid": round(centroid, 1),
        }
        return result, None
    except Exception as e:
        return None, f"音频分析失败: {str(e)}"

def map_voice_to_tcm(rms, pitch, zcr, duration, centroid):
    if rms > 0.08:
        e_desc, e_tcm, e_tag = "声音洪亮", "声音洪亮有力，提示正气尚充，多为实证、热证", "实证"
    elif rms > 0.03:
        e_desc, e_tcm, e_tag = "声音适中", "声音力度适中，无明显偏颇", ""
    else:
        e_desc, e_tcm, e_tag = "声音低微", "声音低微无力，提示正气不足，多为虚证、气虚", "虚证"
    if pitch > 220:
        p_desc, p_tcm, p_tag = "声调偏高", "声调偏高尖，提示偏热或情绪偏急", "热"
    elif pitch > 120:
        p_desc, p_tcm, p_tag = "声调适中", "声调适中，无明显异常", ""
    elif pitch > 0:
        p_desc, p_tcm, p_tag = "声调偏低", "声调偏低沉，提示偏寒或气机偏滞", "寒"
    else:
        p_desc, p_tcm, p_tag = "声调未检出", "未能稳定检出音调，建议在安静环境重新录制", ""
    if zcr < 0.08:
        c_desc, c_tcm, c_tag = "声音清晰", "发声清晰，嗓音状态良好", ""
    elif zcr < 0.15:
        c_desc, c_tcm, c_tag = "声音略沙", "声音略带沙哑，提示肺气或阴液可能偏弱", "阴虚"
    else:
        c_desc, c_tcm, c_tag = "声音嘶哑", "声音嘶哑明显，中医称'金破不鸣'，多见于肺阴虚", "阴虚"
    expected = 8.0
    if duration < expected * 0.6:
        s_desc, s_tcm, s_tag = "语速偏快", "语速偏快，提示阳气偏盛或性情偏急", "阳热"
    elif duration > expected * 1.5:
        s_desc, s_tcm, s_tag = "语速偏慢", "语速偏慢，提示气虚或性格偏缓", "气虚"
    else:
        s_desc, s_tcm, s_tag = "语速适中", "语速适中，无明显偏颇", ""
    hints = {}
    if e_tag == "虚证":
        hints["气虚质"] = 5
    if e_tag == "实证":
        hints["阳热质"] = hints.get("阳热质", 0) + 3
    if p_tag == "热":
        hints["阳热质"] = hints.get("阳热质", 0) + 4
    if p_tag == "寒":
        hints["阳虚质"] = 4
    if c_tag == "阴虚":
        hints["阴虚质"] = 5
    if s_tag == "阳热":
        hints["阳热质"] = hints.get("阳热质", 0) + 3
    if s_tag == "气虚":
        hints["气虚质"] = hints.get("气虚质", 0) + 3
    primary = max(hints, key=hints.get) if hints else "平和质"
    parts = [e_desc, p_desc]
    if c_tag:
        parts.append(c_desc)
    parts.append(s_desc)
    summary = "、".join(parts) + "。"
    if hints:
        summary += f"综合声音特征，提示偏向「{primary}」。"
    else:
        summary += "声音特征整体平稳，无明显偏颇。"
    return {
        "energy": {"desc": e_desc, "tcm": e_tcm},
        "pitch": {"desc": p_desc, "tcm": p_tcm},
        "clarity": {"desc": c_desc, "tcm": c_tcm},
        "speed": {"desc": s_desc, "tcm": s_tcm},
        "constitution_hints": hints,
        "primary_constitution": primary,
        "summary": summary,
    }

@app.route("/voice")
def voice_page():
    return render_template("voice.html", reading_text=VOICE_READING_TEXT)

@app.route("/api/voice_analyze", methods=["POST"])
def api_voice_analyze():
    try:
        if "audio" not in request.files:
            return jsonify({"error": "未上传音频"}), 400
        file = request.files["audio"]
        wav_bytes = file.read()
        result, err = analyze_voice(wav_bytes)
        if err:
            return jsonify({"error": err}), 500
        result["time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        session["voice_analysis"] = {
            "summary": result["summary"],
            "primary_constitution": result["primary_constitution"],
            "constitution_hints": result["constitution_hints"],
            "time": result["time"],
        }
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ============================================================
# 管理员后台
# ============================================================

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin_dashboard"))
        return render_template("admin_login.html", error="密码错误")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("index"))

@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    users = db.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    records = db.execute("""
        SELECT hr.*, u.username
        FROM health_records hr
        JOIN users u ON hr.user_id = u.id
        ORDER BY hr.created_at DESC
    """).fetchall()
    stats = {
        "total_users": len(users),
        "total_records": len(records),
        "with_ai_report": sum(1 for r in records if r["ai_report"]),
        "with_tongue": sum(1 for r in records if r["tongue_primary"]),
    }
    return render_template("admin.html", users=users, records=records, stats=stats)

@app.route("/admin/record/<int:record_id>")
@admin_required
def admin_view_record(record_id):
    db = get_db()
    record = db.execute("""
        SELECT hr.*, u.username
        FROM health_records hr
        JOIN users u ON hr.user_id = u.id
        WHERE hr.id = ?
    """, (record_id,)).fetchone()
    if not record:
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_record.html", record=record)

@app.route("/admin/user/<int:user_id>")
@admin_required
def admin_view_user(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    records = db.execute(
        "SELECT * FROM health_records WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    ).fetchall()
    return render_template("admin_user.html", user=user, records=records)

# ============================================================
# 青囊客服 — 平台智能客服
# ============================================================

QINGNANG_AGENT_PROMPT = """你是青囊客服，青囊AI平台的智能客服助手。
你的任务：为用户提供平台使用指引、功能咨询、产品答疑、订单帮助等服务。

平台功能介绍：
1. 望·舌象分析：支持拍照或上传图片，YOLO模型自动检测21种舌象特征，给出体质倾向分析。
2. 闻·声音分析：录制声音，分析声音特征辅助体质判断。
3. 问·体质问卷：填写问卷，通过日常生活习惯判断体质偏颇。
4. 切·面相检测：上传面部照片，分析面相特征。
5. AI健康报告：完成望闻切三项检测后可生成综合AI体质报告，问诊为可选项。
6. 养生坊：提供四季养生茶饮包、体质食疗食材礼盒、儿童健脾开胃糊、节气养生汤包等产品，支持支付宝支付。
7. 图谱：中医舌象科普图谱。

服务规范：
1. 热情友好，耐心解答用户的每一个问题。
2. 回答简洁明了，分点说明，不要长篇大论。
3. 用户问怎么用某个功能时，给出具体操作步骤。
4. 用户问产品相关问题（价格、功效、适合人群）时，基于已知产品信息回答。
5. 用户问订单或支付问题时，引导用户查看订单页面，如需人工处理请提示联系管理员。
6. 用户咨询健康/疾病问题时，委婉告知客服不提供医学诊断，引导用户使用平台的四诊功能进行体质检测，或建议就医。
7. 如果用户之前做过检测，你会收到相关检测结果，可以据此推荐适合的养生坊产品。

回答风格：
- 口语亲切，像朋友一样自然交流；
- 条理清晰，适当使用分点；
- 遇到不知道的问题，诚实说"这个问题我需要帮您转接管理员"，不要编造答案。"""

@app.route("/agent")
def agent_chat():
    user = current_user()
    tongue = session.get("tongue_analysis")
    qa = session.get("qa_results")
    face = session.get("face_analysis")
    voice = session.get("voice_analysis")
    diag_context = ""
    if tongue:
        diag_context += f"\n[望诊·舌象检测结果] 主体质：{tongue.get('primary','未知')}；特征：{', '.join(tongue.get('features',[]))}"
    if voice:
        diag_context += f"\n[闻诊·声音检测结果] {voice.get('summary','')}"
    if qa:
        scores = qa.get("scores", {})
        top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
        diag_context += f"\n[问诊·问卷结果] 体质评分Top3：{', '.join(f'{k}({v}分)' for k,v in top)}"
    if face:
        diag_context += f"\n[切诊·面相检测结果] {face.get('summary','')}"
    return render_template("agent.html", current_user=user, diag_context=diag_context)

@app.route("/api/agent_chat", methods=["POST"])
def api_agent_chat():
    if not DEEPSEEK_API_KEY:
        return jsonify({"error": "AI引擎尚未配置，请等待管理员填入API密钥后使用"}), 503

    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "请输入您想咨询的内容"}), 400

    messages = [{"role": "system", "content": QINGNANG_AGENT_PROMPT}]

    diag_context = data.get("diag_context", "")
    if diag_context:
        messages.append({"role": "system", "content": f"用户已有的检测数据如下，请结合分析：{diag_context}"})

    history = data.get("history", [])
    for h in history[-10:]:
        messages.append({"role": "user", "content": h.get("user", "")})
        if h.get("agent"):
            messages.append({"role": "assistant", "content": h.get("agent", "")})

    messages.append({"role": "user", "content": message})

    reply, err = call_deepseek(messages)
    if err:
        if "timeout" in str(err).lower():
            return jsonify({"error": "AI回复超时，请稍后再试"}), 504
        return jsonify({"error": f"AI服务暂时不可用：{err}"}), 502
    return jsonify({"reply": reply})


# ============================================================
# ★★★ 支付宝支付功能 ★★★
# ============================================================

def _alipay_sign(params, private_key_str):
    """使用RSA2对参数进行签名"""
    try:
        from Crypto.PublicKey import RSA
        from Crypto.Signature import PKCS1_v1_5
        from Crypto.Hash import SHA256
        import urllib.parse
    except ImportError:
        return None

    sorted_params = sorted(params.items())
    sign_str = "&".join(f"{k}={v}" for k, v in sorted_params if v != "" and k != "sign")
    sign_str = urllib.parse.unquote(sign_str)

    key_bytes = private_key_str.encode("utf-8")
    if b"BEGIN" not in key_bytes:
        key_bytes = b"-----BEGIN RSA PRIVATE KEY-----\n" + key_bytes + b"\n-----END RSA PRIVATE KEY-----\n"

    key = RSA.importKey(key_bytes)
    h = SHA256.new(sign_str.encode("utf-8"))
    signer = PKCS1_v1_5.new(key)
    signature = signer.sign(h)
    return base64.b64encode(signature).decode("utf-8")


@app.route("/shop")
def shop():
    user = current_user()
    return render_template("shop.html", current_user=user, products=SHOP_PRODUCTS)


@app.route("/api/create_order", methods=["POST"])
def create_order():
    data = request.get_json(silent=True) or {}
    product_id = data.get("product_id", "").strip()
    product = next((p for p in SHOP_PRODUCTS if p["id"] == product_id), None)
    if not product:
        return jsonify({"error": "商品不存在"}), 400

    user = current_user()
    user_id = user["id"] if user else None
    order_no = f"QN{datetime.now().strftime('%Y%m%d%H%M%S')}{os.urandom(3).hex()}"

    db = get_db()
    db.execute(
        "INSERT INTO orders (order_no, user_id, product_id, product_name, amount, status) VALUES (?, ?, ?, ?, ?, 'pending')",
        (order_no, user_id, product_id, product["name"], product["price"])
    )
    db.commit()

    if not ALIPAY_APP_ID or not ALIPAY_APP_PRIVATE_KEY:
        return jsonify({
            "order_no": order_no,
            "pay_url": None,
            "message": "支付宝尚未配置，订单已创建（测试模式）"
        })

    biz_content = json.dumps({
        "out_trade_no": order_no,
        "total_amount": product["price"],
        "subject": product["name"],
        "product_code": "FAST_INSTANT_TRADE_PAY",
    }, ensure_ascii=False)

    params = {
        "app_id": ALIPAY_APP_ID,
        "method": "alipay.trade.page.pay",
        "charset": "utf-8",
        "sign_type": "RSA2",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "version": "1.0",
        "biz_content": biz_content,
        "notify_url": ALIPAY_NOTIFY_URL,
        "return_url": ALIPAY_RETURN_URL,
    }

    sign = _alipay_sign(params, ALIPAY_APP_PRIVATE_KEY)
    if not sign:
        return jsonify({"error": "签名失败，请检查私钥配置"}), 500

    params["sign"] = sign
    import urllib.parse
    query_str = urllib.parse.urlencode(params, doseq=True)
    pay_url = f"{ALIPAY_GATEWAY}?{query_str}"

    return jsonify({"order_no": order_no, "pay_url": pay_url})


@app.route("/pay/return")
def pay_return():
    order_no = request.args.get("out_trade_no", "")
    trade_no = request.args.get("trade_no", "")
    if order_no and trade_no:
        db = get_db()
        db.execute(
            "UPDATE orders SET status='paid', alipay_trade_no=?, paid_at=datetime('now','localtime') WHERE order_no=?",
            (trade_no, order_no)
        )
        db.commit()
    return render_template("pay_result.html", order_no=order_no, trade_no=trade_no, success=True)


@app.route("/pay/notify", methods=["POST"])
def pay_notify():
    trade_status = request.form.get("trade_status", "")
    order_no = request.form.get("out_trade_no", "")
    trade_no = request.form.get("trade_no", "")
    if trade_status in ("TRADE_SUCCESS", "TRADE_FINISHED") and order_no:
        db = get_db()
        db.execute(
            "UPDATE orders SET status='paid', alipay_trade_no=?, paid_at=datetime('now','localtime') WHERE order_no=? AND status='pending'",
            (trade_no, order_no)
        )
        db.commit()
    return "success"


@app.route("/orders")
def orders():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    db = get_db()
    order_list = db.execute(
        "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC", (user["id"],)
    ).fetchall()
    return render_template("orders.html", current_user=user, orders=order_list)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
