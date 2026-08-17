import os
import sys
import json
import time
import base64
import requests
import numpy as np
from PIL import Image
import io

import streamlit as st

# ===== 页面配置 =====
st.set_page_config(
    page_title="青囊AI · 舌象与体质分析",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ===== YOLO 模型路径 =====
YOLO_MODEL_PATH = r"C:\Users\66496\yolo\best.pt"

# ===== 豆包 API =====
DOUBAO_API_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

# ===== 21种舌象特征中文名映射 =====
FEATURE_MAP = {
    0:  ("jiankangshe",  "健康舌",   "舌象整体良好，淡红舌薄白苔"),
    1:  ("botaishe",     "薄苔舌",   "舌苔薄薄一层，属正常或初起"),
    2:  ("hongshe",      "红舌",     "舌色偏红，身体可能有热"),
    3:  ("zishe",        "紫舌",     "舌色发紫，可能血液循环不畅"),
    4:  ("pangdashe",    "胖大舌",   "舌体胖大，可能脾虚湿盛"),
    5:  ("shoushe",      "瘦舌",     "舌体瘦薄，可能阴血不足"),
    6:  ("hongdianshe",  "红点舌",   "舌面有红点，多有内热"),
    7:  ("liewenshe",    "裂纹舌",   "舌面有裂纹，可能阴液亏虚"),
    8:  ("chihenshe",    "齿痕舌",   "舌边有牙齿印，多属脾虚湿盛"),
    9:  ("baitaishe",    "白苔舌",   "舌苔偏白，多为寒证或湿证"),
    10: ("huangtaishe",  "黄苔舌",   "舌苔发黄，多有热象"),
    11: ("heitaishe",    "黑苔舌",   "舌苔发黑，需警惕，建议就医"),
    12: ("huataishe",    "花苔舌",   "舌苔剥落不均，可能胃气不足"),
    13: ("shenquao",     "肾区凹陷", "舌根区域凹陷，可能肾气偏虚"),
    14: ("shenqutu",     "肾区凸起", "舌根区域凸起，可能肾区有郁滞"),
    15: ("gandanao",     "肝胆区凹陷","舌两侧凹陷，可能肝血不足"),
    16: ("gandantu",     "肝胆区凸起","舌两侧凸起，可能肝气郁结"),
    17: ("piweiao",      "脾胃区凹陷","舌中区域凹陷，可能脾胃虚弱"),
    18: ("piweitu",      "脾胃区凸起","舌中区域凸起，可能脾胃有滞"),
    19: ("xinfeiao",     "心肺区凹陷","舌尖区域凹陷，可能心肺气虚"),
    20: ("xinfeitu",     "心肺区凸起","舌尖区域凸起，可能心肺有热"),
}

# 舌象特征 → 体质倾向映射
FEATURE_CONSTITUTION = {
    "jiankangshe":  {"平和质": 10},
    "botaishe":     {"平和质": 3},
    "hongshe":      {"阴虚质": 5, "阳热质": 4, "湿热质": 3},
    "zishe":        {"气郁质": 5},
    "pangdashe":    {"痰湿质": 5, "阳虚质": 3},
    "shoushe":      {"阴虚质": 4, "气虚质": 3},
    "hongdianshe":  {"阳热质": 5, "阴虚质": 3},
    "liewenshe":    {"阴虚质": 6},
    "chihenshe":    {"气虚质": 5, "痰湿质": 4, "阳虚质": 3},
    "baitaishe":    {"阳虚质": 4, "痰湿质": 3, "气虚质": 2},
    "huangtaishe":  {"湿热质": 6, "阳热质": 3, "食滞质": 3},
    "heitaishe":    {},
    "huataishe":    {"气虚质": 3, "阴虚质": 3},
    "shenquao":     {"阳虚质": 4},
    "shenqutu":     {"气郁质": 2},
    "gandanao":     {"气郁质": 3},
    "gandantu":     {"气郁质": 4, "湿热质": 3},
    "piweiao":      {"气虚质": 5, "食滞质": 2},
    "piweitu":      {"痰湿质": 4, "食滞质": 3},
    "xinfeiao":     {"气虚质": 4},
    "xinfeitu":     {"阳热质": 3, "阴虚质": 2},
}

# ===== 儿童体质问卷数据（来自PDF） =====
# 选项类型: "5pt"=总是/经常/有时/偶尔/从不(5,4,3,2,1), "3pt"=符合/比较符合/不符合(5,3,1), "2pt"=是/否(5,1), "freq"=频率3档(5,3,1)

QUESTIONNAIRES = {
    "平和质": {
        "items": [
            ("体型正常", "3pt"),
            ("肌肉结实", "3pt"),
            ("面色红润", "3pt"),
            ("头发有光泽", "3pt"),
            ("舌象：舌淡红苔薄白", "3pt"),
            ("精力充沛", "5pt"),
            ("声音洪亮（或哭声洪亮）", "5pt"),
            ("食欲好且食量正常", "5pt"),
            ("入睡快，睡眠比较安稳", "5pt"),
            ("便质正常，每日排便1~2次", "5pt"),
            ("性格开朗", "5pt"),
            ("很少生病", "2pt"),
            ("生病后很快能康复", "5pt"),
        ]
    },
    "特禀质": {
        "items": [
            ("下眼圈发青", "3pt"),
            ("接触或食用某过敏原后易皮肤痒（过敏原包括某种食物、花粉、灰尘、宠物等）", "5pt"),
            ("容易出现过敏性疾病如过敏性鼻炎、咳嗽变异性哮喘，或在以下情况下容易出现打喷嚏、流鼻涕、鼻塞、咳嗽（换季、温度变化、接触花粉或带毛的小动物、装修等可能存在过敏原的地方）", "5pt"),
            ("吃某种东西后易出现腹痛或泄泻", "5pt"),
            ("易起湿疹、荨麻疹", "5pt"),
            ("喜欢揉鼻子、揉眼睛或眨眼", "5pt"),
            ("有家族过敏性疾病史", "2pt"),
            ("小时候有慢性腹泻或者湿疹史", "5pt"),
            ("有喘息病史", "2pt"),
        ]
    },
    "气虚质": {
        "items": [
            ("肌肉松软", "3pt"),
            ("面色偏白、没有光泽", "3pt"),
            ("面色偏黄、没有光泽", "3pt"),
            ("头发缺少光泽", "3pt"),
            ("舌象：舌质淡、苔白", "3pt"),
            ("容易劳累、没精神", "5pt"),
            ("声音小（或哭声低怯）", "5pt"),
            ("大便不成形或夹杂未消化的食物", "5pt"),
            ("活动后易出汗", "5pt"),
            ("喜欢安静、不爱户外活动", "5pt"),
            ("胆子小、说话少", "5pt"),
            ("每年患呼吸道感染（如感冒、支气管炎、肺炎）的频率", "freq"),
            ("肚子胀", "5pt"),
        ]
    },
    "阳虚质": {
        "items": [
            ("面色偏白、没有光泽", "3pt"),
            ("舌头表现为舌淡胖，或有齿痕，苔白", "3pt"),
            ("容易劳累、没精神", "5pt"),
            ("食欲差", "5pt"),
            ("吃凉的食物会感到不适，如腹痛、泄泻", "5pt"),
            ("多眠易困", "5pt"),
            ("怕冷", "5pt"),
            ("手脚凉", "5pt"),
            ("喜欢安静、不爱户外活动", "5pt"),
            ("胆子小、说话少", "5pt"),
            ("每年患呼吸道感染（如感冒、支气管炎、肺炎）的频率", "freq"),
        ]
    },
    "阴虚质": {
        "items": [
            ("体型偏瘦", "3pt"),
            ("嘴唇颜色偏红、干燥", "3pt"),
            ("舌象：舌红、少津，苔少或有地图舌", "3pt"),
            ("入睡时间长或轻浅易醒", "5pt"),
            ("大便干燥", "5pt"),
            ("手足心热", "5pt"),
            ("睡觉时易出汗", "5pt"),
            ("脾气急躁", "5pt"),
            ("皮肤干燥或易瘙痒", "5pt"),
            ("易起口疮、嗓子痛", "5pt"),
            ("喜欢揉鼻子、揉眼睛或眨眼", "5pt"),
        ]
    },
    "阳热质": {
        "items": [
            ("面颊偏红", "3pt"),
            ("嘴唇颜色偏红、干燥", "3pt"),
            ("舌象：舌红苔黄或白", "3pt"),
            ("精力旺盛，活动多", "5pt"),
            ("饭量大且容易饿", "5pt"),
            ("睡眠不踏实，来回翻滚", "5pt"),
            ("大便干燥", "5pt"),
            ("大便气味臭", "5pt"),
            ("怕热、活动后出汗多", "5pt"),
            ("脾气急躁", "5pt"),
            ("易起口疮、嗓子痛", "5pt"),
            ("晨起眼屎多", "5pt"),
        ]
    },
    "气郁质": {
        "age_range": "4-12",
        "items": [
            ("体型偏瘦", "3pt"),
            ("舌象：舌色偏暗、苔薄白", "3pt"),
            ("入睡时间长", "5pt"),
            ("大便干燥", "5pt"),
            ("心思细腻、敏感、很在乎别人的看法", "5pt"),
            ("容易闷闷不乐、唉声叹气", "5pt"),
            ("容易焦虑，想事太多", "5pt"),
            ("受挫后情绪低落持续较久（7~12岁）", "5pt"),
            ("容易打嗝或恶心干呕", "5pt"),
            ("觉得喉间有异物感（7~12岁）", "5pt"),
            ("有无明显原因的头痛", "5pt"),
            ("入学后适应集体生活慢", "5pt"),
        ]
    },
    "痰湿质": {
        "items": [
            ("下眼睑浮肿", "3pt"),
            ("舌象：舌体胖大、边有齿痕，苔腻", "3pt"),
            ("容易劳累、没精神", "5pt"),
            ("食欲差", "5pt"),
            ("不喜欢喝水", "5pt"),
            ("多眠易困", "5pt"),
            ("大便不成形", "5pt"),
            ("出汗黏", "5pt"),
            ("喜欢安静、不爱户外活动", "5pt"),
            ("做事拖沓、性子慢（7~12岁）", "5pt"),
            ("易起湿疹、荨麻疹", "5pt"),
            ("肚子胀", "5pt"),
            ("易打嗝或恶心干呕", "5pt"),
            ("觉得嗓子有痰", "5pt"),
            ("咳嗽时容易痰多", "5pt"),
        ]
    },
    "湿热质": {
        "items": [
            ("舌象：舌红苔黄腻", "3pt"),
            ("晚上睡觉容易哭或惊醒", "5pt"),
            ("大便黏便盆，不易冲刷干净", "5pt"),
            ("出汗黏", "5pt"),
            ("脾气急躁", "5pt"),
            ("易起湿疹", "5pt"),
            ("肚子胀", "5pt"),
            ("易起口疮、嗓子痛", "5pt"),
            ("晨起眼屎多", "5pt"),
            ("口气重", "5pt"),
        ]
    },
    "食滞质": {
        "items": [
            ("舌象：舌苔厚", "3pt"),
            ("睡眠不踏实，来回翻滚或喜欢趴着睡觉", "5pt"),
            ("睡觉磨牙", "5pt"),
            ("脾气急躁", "5pt"),
            ("容易肚子疼或胀", "5pt"),
            ("口气重", "5pt"),
            ("打嗝易有酸臭味", "5pt"),
            ("有进食过多、积食情况", "5pt"),
        ]
    },
    # 五脏体质
    "偏心亢质": {
        "items": [
            ("面颊偏红", "3pt"),
            ("舌象：舌尖红绛", "3pt"),
            ("入睡时间长", "5pt"),
            ("易起口疮、嗓子痛", "5pt"),
        ]
    },
    "偏肝亢质": {
        "items": [
            ("山根部位（鼻梁上）发青", "3pt"),
            ("晚上睡觉容易哭或惊醒", "5pt"),
            ("睡眠不踏实，来回翻滚", "5pt"),
            ("脾气急躁", "5pt"),
        ]
    },
    "偏脾虚质": {
        "items": [
            ("全身肌肉松软", "3pt"),
            ("面色偏黄、没有光泽", "3pt"),
            ("饭后容易肚子胀", "5pt"),
            ("大便不成形或夹杂未消化的食物", "5pt"),
        ]
    },
    "偏肺虚质": {
        "items": [
            ("面色偏白、没有光泽", "3pt"),
            ("声音小（或哭声低怯）", "5pt"),
            ("活动后易出汗", "5pt"),
            ("每年患呼吸道感染（如感冒、支气管炎、肺炎）的频率", "freq"),
        ]
    },
    "偏肾虚质": {
        "items": [
            ("体型偏矮", "3pt"),
            ("发量稀少", "3pt"),
            ("睡觉尿床（4~12岁）", "5pt"),
            ("早产儿或低出生体重儿", "2pt"),
        ]
    },
}

# 五脏体质列表
ORGAN_TYPES = ["偏心亢质", "偏肝亢质", "偏脾虚质", "偏肺虚质", "偏肾虚质"]
BASIC_TYPES = ["平和质", "特禀质", "气虚质", "阳虚质", "阴虚质", "阳热质", "气郁质", "痰湿质", "湿热质", "食滞质"]

# 判定标准
STANDARDS = {
    "1-3": {
        "pinghe_score": 60, "pinghe_others_max": 38,
        "pianpo_score": 38, "pianpo_tend_min": 31,
        "organ_score": 42, "organ_tend_min": 31,
    },
    "4-6": {
        "pinghe_score": 58, "pinghe_others_max": 41,
        "pianpo_score": 41, "pianpo_tend_min": 32,
        "organ_score": 42, "organ_tend_min": 34,
    },
    "7-12": {
        "pinghe_score": 60, "pinghe_others_max": 39,
        "pianpo_score": 39, "pianpo_tend_min": 32,
        "organ_score": 37, "organ_tend_min": 29,
    },
}

# 体质特征描述
CONSTITUTION_INFO = {
    "平和质": {"desc": "精神饱满，精力充沛，体形匀称，面色红润，睡眠安稳，二便正常", "tendency": "平素较少生病，病后易于康复"},
    "特禀质": {"desc": "下睑暗影，皮肤易瘙痒，遇冷风或刺激气味后易打喷嚏、鼻塞、流涕", "tendency": "易患过敏性疾病，如湿疹、鼻炎、哮喘"},
    "气虚质": {"desc": "精神欠振，易于疲倦，肌肉松软，面色萎黄，语声低怯，自汗", "tendency": "易患感冒、泄泻、积滞、遗尿"},
    "阳虚质": {"desc": "神疲倦怠，面色无华，畏寒肢冷，不耐生冷食物，小便清长", "tendency": "易患感冒、遗尿"},
    "阴虚质": {"desc": "形体偏瘦，两颧潮红，口鼻干燥，手足心热，夜间汗多，大便偏干", "tendency": "易患盗汗、乳蛾、便秘、口疮"},
    "阳热质": {"desc": "精神亢奋，形体壮实，面赤唇红，畏热喜凉，多食易饥，大便干结", "tendency": "易患发热性疾病、口疮、乳蛾、便秘"},
    "气郁质": {"desc": "神情抑郁，易烦闷，善太息，喉间有异物感，大便偏干", "tendency": "易患头痛、失眠、梅核气"},
    "痰湿质": {"desc": "精神欠振，体型偏胖，面部油腻，喉中常有痰，多汗而黏，大便不成形", "tendency": "易患泄泻、厌食、咳嗽、湿疹"},
    "湿热质": {"desc": "面垢油光，头汗多，有口气，小便短赤，大便黏腻不畅", "tendency": "易患腹胀、口疮、夜啼、湿疹"},
    "食滞质": {"desc": "有口气，嗳气酸腐，腹部胀满，夜寐不安，喜俯卧，易磨牙", "tendency": "易患积滞、厌食、泄泻、便秘"},
    "偏心亢质": {"desc": "面色偏红，哭声大，入睡困难，舌尖红绛，易口舌生疮", "tendency": "心火偏旺相关倾向"},
    "偏肝亢质": {"desc": "山根青筋，夜卧不安，偶有惊惕，暴躁冲动", "tendency": "肝火偏旺相关倾向"},
    "偏脾虚质": {"desc": "面色萎黄，口唇色淡，肌肉松软，食后腹胀，大便偏溏", "tendency": "脾虚相关倾向"},
    "偏肺虚质": {"desc": "面色偏白而欠泽，声音较低微，自汗畏风", "tendency": "易患咳嗽、感冒"},
    "偏肾虚质": {"desc": "形体矮小，头发干枯稀少，多见于低出生体重儿", "tendency": "易患遗尿"},
}


# ===== 评分计算 =====
def get_options(qtype, age_group):
    """返回选项列表 [(标签, 分数), ...]"""
    if qtype == "5pt":
        return [("总是", 5), ("经常", 4), ("有时", 3), ("偶尔", 2), ("从不", 1)]
    elif qtype == "3pt":
        return [("符合", 5), ("比较符合", 3), ("不符合", 1)]
    elif qtype == "2pt":
        return [("是", 5), ("否", 1)]
    elif qtype == "freq":
        if age_group == "1-3":
            return [("每年≥7次", 5), ("每年2~6次", 3), ("每年<2次", 1)]
        elif age_group == "4-6":
            return [("每年≥6次", 5), ("每年2~5次", 3), ("每年<2次", 1)]
        else:
            return [("每年≥5次", 5), ("每年2~4次", 3), ("每年<2次", 1)]
    return [("—", 1)]


def calc_transformed_score(constitution, answers, age_group):
    """计算转化后分数"""
    items = QUESTIONNAIRES[constitution]["items"]
    actual = sum(answers)
    min_score = len(items) * 1  # 每题最低1分
    max_score = sum(get_options(it[1], age_group)[0][1] for it in items)  # 每题最高分
    if max_score == min_score:
        return 0
    return (actual - min_score) / (max_score - min_score) * 100


def determine_constitution(scores, age_group):
    """根据转化分数判定体质"""
    std = STANDARDS[age_group]
    results = []

    pinghe = scores.get("平和质", 0)
    others = {k: v for k, v in scores.items() if k in BASIC_TYPES and k != "平和质"}

    # 平和质判定
    if pinghe >= std["pinghe_score"] and all(v < std["pinghe_others_max"] for v in others.values()):
        results.append(("平和质", "判定", pinghe))

    # 偏颇体质判定
    for name, score in others.items():
        if name == "气郁质" and age_group == "1-3":
            continue
        if score >= std["pianpo_score"]:
            results.append((name, "判定", score))
        elif score >= std["pianpo_tend_min"]:
            results.append((name, "倾向", score))

    # 五脏体质判定
    for name in ORGAN_TYPES:
        score = scores.get(name, 0)
        if score >= std["organ_score"]:
            results.append((name, "判定", score))
        elif score >= std["organ_tend_min"]:
            results.append((name, "倾向", score))

    return results


# ===== YOLO 检测 =====
@st.cache_resource
def load_yolo_model():
    try:
        from ultralytics import YOLO
        model = YOLO(YOLO_MODEL_PATH)
        return model
    except Exception as e:
        return None


def run_tongue_detection(image):
    """运行YOLO舌象检测"""
    model = load_yolo_model()
    if model is None:
        return None, "模型加载失败，请确保ultralytics已安装且模型文件存在"

    try:
        results = model(image)
        r = results[0]

        # 保存标注图
        annotated = r.plot()  # numpy array (BGR)

        # 提取特征
        features = []
        for box in r.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            if conf < 0.3:
                continue
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            if cls_id in FEATURE_MAP:
                en_name, cn_name, desc = FEATURE_MAP[cls_id]
                features.append({
                    "en_name": en_name,
                    "cn_name": cn_name,
                    "desc": desc,
                    "confidence": round(conf, 3),
                    "bbox": [round(x1), round(y1), round(x2), round(y2)]
                })

        return {"annotated": annotated, "features": features}, None
    except Exception as e:
        return None, f"检测出错: {str(e)}"


def tongue_features_to_constitution(features):
    """舌象特征 → 体质倾向"""
    scores = {}
    for feat in features:
        en = feat["en_name"]
        conf = feat["confidence"]
        if en in FEATURE_CONSTITUTION:
            for const, weight in FEATURE_CONSTITUTION[en].items():
                scores[const] = scores.get(const, 0) + weight * conf

    if not scores:
        return "平和质", {}

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    primary = sorted_scores[0][0] if sorted_scores[0][1] > 0 else "平和质"
    return primary, dict(sorted_scores)


# ===== 豆包 API =====
def call_doubao(api_key, model_id, messages):
    """调用豆包API"""
    try:
        resp = requests.post(
            DOUBAO_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model_id,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 4096
            },
            timeout=60
        )
        if resp.status_code != 200:
            err = resp.json().get("error", {})
            return None, f"豆包API错误: {err.get('message', resp.text)}"
        result = resp.json()
        reply = result["choices"][0]["message"]["content"]
        return reply, None
    except Exception as e:
        return None, str(e)


# ===== 自定义样式 =====
st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 1rem 0 1.5rem;
    }
    .main-header h1 {
        font-size: 2.2rem;
        background: linear-gradient(135deg, #1a4d3a, #e8c878);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.5rem;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 0.6rem 1.2rem;
        border-radius: 8px 8px 0 0;
    }
    .disclaimer {
        background: rgba(201, 123, 58, 0.08);
        border: 1px solid rgba(201, 123, 58, 0.2);
        border-radius: 8px;
        padding: 0.8rem 1rem;
        font-size: 0.82rem;
        color: #8C7E72;
        text-align: center;
        margin-top: 1rem;
    }
    .feature-badge {
        display: inline-block;
        padding: 0.2rem 0.6rem;
        border-radius: 999px;
        font-size: 0.8rem;
        margin: 0.2rem;
    }
</style>
""", unsafe_allow_html=True)


# ===== 初始化 session state =====
if 'tongue_results' not in st.session_state:
    st.session_state.tongue_results = None
if 'questionnaire_results' not in st.session_state:
    st.session_state.questionnaire_results = None
if 'qa_answers' not in st.session_state:
    st.session_state.qa_answers = {}


# ===== 主页面 =====
st.markdown('<div class="main-header"><h1>🌿 青囊AI · 舌象与体质分析</h1></div>', unsafe_allow_html=True)
st.markdown('<p style="text-align:center; color:#8C7E72;">基于YOLO舌象检测 + 儿童体质中医分型判定标准 + 豆包AI智能分析</p>', unsafe_allow_html=True)

# 侧边栏设置
with st.sidebar:
    st.markdown("### ⚙️ 设置")
    api_key = st.text_input("豆包 API Key", type="password", value=st.session_state.get('api_key', ''))
    model_id = st.text_input("模型 ID", value=st.session_state.get('model_id', ''), placeholder="如 doubao-pro-32k")
    if st.button("保存设置"):
        st.session_state['api_key'] = api_key
        st.session_state['model_id'] = model_id
        st.success("设置已保存")

    st.markdown("---")
    st.markdown("### 📊 当前状态")
    if st.session_state.tongue_results:
        st.markdown("✅ 舌象分析已完成")
    else:
        st.markdown("⬜ 舌象分析未完成")
    if st.session_state.questionnaire_results:
        st.markdown("✅ 体质问卷已完成")
    else:
        st.markdown("⬜ 体质问卷未完成")

    st.markdown("---")
    st.markdown('<div class="disclaimer">本应用仅作中医体质健康科普参考，不构成医疗诊断，不能替代医师诊疗，身体不适请及时就医。</div>', unsafe_allow_html=True)

# 标签页
tab1, tab2, tab3 = st.tabs(["👅 舌象分析", "📋 体质问卷", "🤖 AI健康报告"])

# ==================== Tab 1: 舌象分析 ====================
with tab1:
    st.markdown("### 👅 舌象智能检测")
    st.markdown("上传舌象图片，AI自动检测21种舌象特征")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("#### 📷 上传图片")
        uploaded = st.file_uploader("选择舌象图片", type=['jpg', 'jpeg', 'png'], label_visibility="collapsed")

        if uploaded:
            img = Image.open(uploaded)
            st.image(img, caption="原始图片", use_column_width=True)

            if st.button("🔍 开始检测", type="primary"):
                with st.spinner("AI正在分析舌象..."):
                    # 转换为numpy数组
                    img_array = np.array(img)
                    if len(img_array.shape) == 2:
                        img_array = np.stack([img_array]*3, axis=-1)
                    elif img_array.shape[2] == 4:
                        img_array = img_array[:, :, :3]

                    result, err = run_tongue_detection(img_array)
                    if err:
                        st.error(err)
                    else:
                        st.session_state.tongue_results = result
                        st.success("检测完成！")
                        st.rerun()

    with col2:
        st.markdown("#### 📊 检测结果")
        if st.session_state.tongue_results:
            result = st.session_state.tongue_results

            # 显示标注图
            st.image(result["annotated"], caption="AI标注图", channels="BGR", use_column_width=True)

            features = result["features"]
            if features:
                st.markdown(f"#### 检测到 {len(features)} 个特征")

                # 特征列表
                for feat in features:
                    color = "#d4625a" if feat["confidence"] > 0.7 else "#e8c878" if feat["confidence"] > 0.5 else "#8C7E72"
                    conf_pct = int(feat["confidence"] * 100)
                    st.markdown(
                        f'<span class="feature-badge" style="background:rgba(184,92,56,0.1); color:{color};">'
                        f'**{feat["cn_name"]}** · {conf_pct}%</span> '
                        f'<small style="color:#8C7E72;">{feat["desc"]}</small>',
                        unsafe_allow_html=True
                    )
                    st.markdown("")

                # 体质倾向
                primary, all_scores = tongue_features_to_constitution(features)
                st.markdown("#### 🏷️ 舌象提示体质倾向")
                st.markdown(f"**主要倾向：{primary}**")

                if all_scores:
                    # 柱状图
                    import pandas as pd
                    df = pd.DataFrame(
                        [(k, v) for k, v in all_scores.items()],
                        columns=["体质", "倾向得分"]
                    )
                    st.bar_chart(df.set_index("体质"))
            else:
                st.info("未检测到明显舌象特征")
        else:
            st.info("请先上传图片并点击检测")

    st.markdown('<div class="disclaimer">⚠️ 图像分析仅作体质参考，不能替代中医师面诊。AI检测结果受拍摄光线、角度等因素影响。</div>', unsafe_allow_html=True)


# ==================== Tab 2: 体质问卷 ====================
with tab2:
    st.markdown("### 📋 儿童中医体质问卷")
    st.markdown("基于《儿童体质中医分型与判定标准》（赵霞等，2023）")

    # 年龄段选择
    age_col1, age_col2 = st.columns([1, 3])
    with age_col1:
        age_group = st.selectbox("选择年龄段", ["1-3岁", "4-6岁", "7-12岁"])
    age_key = age_group.replace("岁", "")

    st.markdown(f"**当前年龄段：{age_group}** | 评分采用Likert 5分法")

    all_scores = {}
    all_answers = {}

    # 按体质类型分组显示
    for const_name, const_data in QUESTIONNAIRES.items():
        # 跳过不适用的体质
        if const_data.get("age_range") == "4-12" and age_key == "1-3":
            continue

        is_organ = const_name in ORGAN_TYPES
        emoji = "🫀" if "心" in const_name else "🫁" if "肺" in const_name else "🌱" if "肝" in const_name else "🌾" if "脾" in const_name else "💧" if "肾" in const_name else "📋"

        with st.expander(f"{emoji} {const_name}（{len(const_data['items'])}题）", expanded=False):
            if const_name in CONSTITUTION_INFO:
                st.caption(f"_{CONSTITUTION_INFO[const_name]['desc']}_")

            answers = []
            for i, (question, qtype) in enumerate(const_data["items"]):
                options = get_options(qtype, age_key)
                labels = [o[0] for o in options]
                choice = st.radio(
                    f"{i+1}. {question}",
                    labels,
                    key=f"{const_name}_{i}",
                    horizontal=True,
                    index=len(labels)-1  # 默认选最低分
                )
                score = next(s for l, s in options if l == choice)
                answers.append(score)

            # 计算分数
            transformed = calc_transformed_score(const_name, answers, age_key)
            all_scores[const_name] = transformed
            all_answers[const_name] = answers

            st.metric("转化分数", f"{transformed:.1f}%")

    # 判定结果
    st.markdown("---")
    st.markdown("### 📊 体质判定结果")

    if st.button("📊 生成体质判定", type="primary"):
        results = determine_constitution(all_scores, age_key)
        st.session_state.questionnaire_results = {
            "scores": all_scores,
            "results": results,
            "age_group": age_group
        }

    if st.session_state.questionnaire_results:
        qr = st.session_state.questionnaire_results
        results = qr["results"]

        if results:
            for name, level, score in results:
                color = "#1a4d3a" if level == "判定" else "#e8c878"
                st.markdown(
                    f'<span style="background:rgba(26,77,58,0.1); color:{color}; '
                    f'padding:0.3rem 1rem; border-radius:999px; font-weight:600;">'
                    f'{name} · {level} · {score:.1f}%</span>',
                    unsafe_allow_html=True
                )

            # 全部分数表格
            st.markdown("#### 全部体质分数")
            import pandas as pd
            df = pd.DataFrame(
                [(k, f"{v:.1f}%") for k, v in qr["scores"].items()],
                columns=["体质类型", "转化分数"]
            )
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("各项体质评分均未达到判定/倾向标准，体质较为均衡")

    st.markdown('<div class="disclaimer">⚠️ 体质判定结果仅作科普参考。五脏体质判定结果仅供参考，需结合四诊资料由医师进行判定。</div>', unsafe_allow_html=True)


# ==================== Tab 3: AI健康报告 ====================
with tab3:
    st.markdown("### 🤖 AI综合健康报告")
    st.markdown("结合舌象检测结果与体质问卷结果，由豆包AI生成个性化健康建议")

    has_tongue = st.session_state.tongue_results is not None
    has_qa = st.session_state.questionnaire_results is not None

    # 状态显示
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("舌象检测", "✅ 已完成" if has_tongue else "⬜ 未完成")
    with c2:
        st.metric("体质问卷", "✅ 已完成" if has_qa else "⬜ 未完成")
    with c3:
        st.metric("API设置", "✅ 已配置" if st.session_state.get('api_key') else "⬜ 未配置")

    if not has_tongue and not has_qa:
        st.warning("请先完成「舌象分析」和/或「体质问卷」，再生成AI报告")
    elif not st.session_state.get('api_key') or not st.session_state.get('model_id'):
        st.warning("请在左侧侧边栏填写豆包API Key和模型ID")
    else:
        # 准备报告内容
        report_parts = []

        if has_tongue:
            features = st.session_state.tongue_results["features"]
            if features:
                feat_text = "\n".join(
                    f"- {f['cn_name']}（{f['en_name']}）：置信度{f['confidence']:.1%}，{f['desc']}"
                    for f in features
                )
                primary, scores = tongue_features_to_constitution(features)
                report_parts.append(f"## 舌象检测结果\n检测到以下舌象特征：\n{feat_text}\n\n舌象提示体质倾向：{primary}")
            else:
                report_parts.append("## 舌象检测结果\n未检测到明显异常舌象特征")

        if has_qa:
            qr = st.session_state.questionnaire_results
            result_text = "\n".join(
                f"- {name}：{level}（转化分数{score:.1f}%）"
                for name, level, score in qr["results"]
            )
            if not result_text:
                result_text = "- 各项体质评分均未达到判定/倾向标准"
            report_parts.append(f"## 体质问卷结果（年龄段：{qr['age_group']}）\n{result_text}")

        combined = "\n\n".join(report_parts)

        st.markdown("#### 📝 分析数据摘要")
        st.markdown(combined)

        st.markdown("---")

        if st.button("🚀 生成AI健康报告", type="primary"):
            prompt = f"""你是一位经验丰富的中医健康管理师，请根据以下检测数据，用通俗易懂的语言为家长生成儿童健康分析报告。

{combined}

请按以下格式输出报告：

1. **综合分析**：结合舌象和体质问卷结果，总结孩子的体质状况（2-3段）
2. **体质特征解读**：用通俗白话解释判定的体质类型代表什么
3. **日常调养建议**：
   - 饮食建议（推荐食材、忌口食材，使用药食同源日常食材，不含处方中药）
   - 起居建议（作息、运动等）
   - 情志建议（情绪管理方面）
4. **注意事项**：需要关注的健康提示

要求：
- 全文禁止使用疾病诊断话术，只描述"体质倾向""身体偏颇""日常调养建议"
- 所有中医术语必须附带白话解释
- 面向家长，语言亲切易懂
- 报告末尾标注："以上分析仅作体质科普参考，不构成医疗诊断，不能替代医师诊疗"
"""

            with st.spinner("AI正在生成健康报告，请稍候..."):
                reply, err = call_doubao(
                    st.session_state['api_key'],
                    st.session_state['model_id'],
                    [{"role": "user", "content": prompt}]
                )

                if err:
                    st.error(f"生成失败：{err}")
                else:
                    st.markdown("#### 📄 AI健康报告")
                    st.markdown(reply)
                    st.markdown("---")
                    st.markdown('<div class="disclaimer">⚠️ 以上报告由AI生成，仅作中医体质健康科普参考，不构成医疗诊断，不能替代医师诊疗，身体不适请及时就医。</div>', unsafe_allow_html=True)

    st.markdown('<div class="disclaimer">⚠️ 本报告由AI生成，仅作中医体质健康科普参考，不构成医疗诊断，不能替代医师诊疗，身体不适请及时就医。</div>', unsafe_allow_html=True)
