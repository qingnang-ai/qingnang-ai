# 青囊AI · 中医体质智能分析平台

> 取意「青囊书」——华佗所传中医经典之名，以AI之眼观舌象，以古人之智辨体质。

## 项目简介

青囊AI 是一个面向普通家庭的中医体质智能分析平台，结合传统中医 **望闻问切** 四诊理论，通过 YOLO 目标检测、DeepSeek AI 大模型等技术，为用户提供便捷的中医体质分析和调养建议。

## 核心功能

### 望 · 舌象分析
- 基于 YOLOv8 本地模型检测 21 种舌象特征
- 自动生成标注图片，输出体质倾向判断
- 支持图片上传和摄像头拍照两种方式

### 闻 · 声音分析
- 录制语音，AI 分析声音力度、音调、清晰度、语速
- 结合中医闻诊理论判断体质偏向

### 问 · 体质问卷
- 15 项大白话体质量表（专业术语通俗化 + 对比参照）
- 依据九种体质理论评分，输出 Top3 体质倾向

### 切 · 面相检测
- 上传面部照片，AI 分析面相特征
- 结合中医切诊理论辅助体质判断

### AI 健康报告
- DeepSeek AI 综合分析四诊数据
- 解锁条件：望 + 闻 + 切 三项必做，问选做
- 输出体质解析 + 调养建议 + 食疗推荐

### 青囊客服
- 平台智能客服，解答功能使用、产品咨询、订单问题
- 结合用户检测数据推荐合适的养生产品
- 健康咨询引导至四诊功能检测

### 养生坊商城
- 基于体质分析的商品推荐
- 支付宝支付集成（RSA2签名）
- 订单管理

### 舌象图谱
- 中医舌象科普图谱展示

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.10+ · Flask |
| AI 引擎 | DeepSeek API · YOLOv8 (Ultralytics) |
| 图像处理 | OpenCV · Pillow |
| 数据库 | SQLite |
| 支付 | 支付宝当面付（RSA2签名） |
| 前端 | HTML / CSS / JavaScript |
| 认证 | Werkzeug PBKDF2 |

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/your-username/qingnang-ai.git
cd qingnang-ai
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 环境配置

复制 `.env.example` 为 `.env` 并填入你的配置：

```bash
cp .env.example .env
```

```env
# 必填
FLASK_SECRET_KEY=your-random-secret-key
DEEPSEEK_API_KEY=your-deepseek-api-key
ADMIN_NAME=青囊馆主
ADMIN_PASSWORD=your-admin-password

# 可选（支付宝）
ALIPAY_APP_ID=your-app-id
ALIPAY_APP_PRIVATE_KEY=your-private-key
ALIPAY_ALIPAY_PUBLIC_KEY=alipay-public-key
```

> 也可直接在 `app.py` 顶部配置区域修改。

### 4. 放置模型

将训练好的 YOLO 模型放置到默认路径：

```
~/yolo/best.pt
```

或通过环境变量指定：

```env
YOLO_MODEL_PATH=/path/to/your/best.pt
```

### 5. 启动

```bash
python app.py
```

访问 http://127.0.0.1:5000

## 管理员后台

- 访问 http://127.0.0.1:5000/admin/login
- 账号密码通过环境变量 `ADMIN_NAME` 和 `ADMIN_PASSWORD` 配置
- 修改方式：编辑 `.env` 文件或 `app.py` 中对应变量

## 项目结构

```
qingnang-ai/
├── app.py                 # 主应用（路由、模型、API）
├── .env.example           # 环境变量示例
├── .gitignore
├── requirements.txt       # Python 依赖
├── LICENSE                # MIT 协议
├── README.md
├── static/
│   ├── css/style.css      # 中国风样式
│   └── images/            # 望闻问切图片
└── templates/
    ├── base.html          # 基础模板（导航栏、弹窗）
    ├── index.html         # 首页
    ├── tongue.html        # 舌象分析（支持拍照）
    ├── voice.html         # 声音分析
    ├── face.html          # 面相分析
    ├── questionnaire.html # 体质问卷
    ├── report.html        # AI健康报告
    ├── agent.html         # 青囊客服
    ├── shop.html          # 养生坊商城
    ├── orders.html        # 订单管理
    ├── pay_result.html    # 支付结果
    ├── atlas.html         # 舌象图谱
    ├── auth.html          # 登录注册
    ├── dashboard.html     # 用户仪表盘
    └── admin*.html        # 管理后台页面
```

## 免责声明

本应用仅作中医体质健康科普参考，不构成医疗诊断。身体不适请及时就医。

## 开源协议

MIT License
