import os
import time
import json
import base64
import hashlib
import requests
from io import BytesIO
from datetime import datetime

import streamlit as st
from PIL import Image, ImageOps

# ===== 尝试导入 YOLO 相关 =====
YOLO_AVAILABLE = False
try:
    import cv2
    import torch
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    pass

# ============================================================
# 配置
# ============================================================
YOLO_MODEL_PATH = r"C:\Users\66496\yolo\best.pt"
DOUBAO_API_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

st.set_page_config(page_title="青囊AI · 舌象与体质分析", page_icon="🌿", layout="wide")

# ============================================================
# 21种舌象特征元数据
# ============================================================
FEATURE_META = {
    "jiankangshe": {"cn":"健康舌","group":"综合","desc":"模型未发现明显的目标舌象特征","tcm":"健康舌象通常舌体淡红、苔薄白","tips":["保持规律作息","保持充足饮水","维持均衡饮食"],"foods":["新鲜蔬菜","全谷杂粮","优质蛋白","当季水果"]},
    "botaishe": {"cn":"薄苔舌","group":"舌苔","desc":"舌面可见较薄的舌苔覆盖","tcm":"薄苔可见于正常舌象，需结合苔色综合观察","tips":["饮食保持清淡均衡","保持口腔清洁"],"foods":["绿叶蔬菜","全谷物","豆制品","蛋奶类"]},
    "hongshe": {"cn":"红舌","group":"舌色","desc":"舌体颜色整体偏红","tcm":"红舌常被观察为偏'热'的表现","tips":["近期少熬夜","减少过辣过烫饮食","规律饮水"],"foods":["清淡蔬菜","当季水果","豆腐","清汤类"]},
    "zishe": {"cn":"紫舌","group":"舌色","desc":"舌体颜色偏紫或暗紫","tcm":"需结合紫暗程度及全身表现综合判断","tips":["自然光下重新拍摄确认","避免滤镜","若持续异常建议就医"],"foods":["均衡主食","蔬菜","优质蛋白","充足饮水"]},
    "pangdashe": {"cn":"胖大舌","group":"舌形","desc":"舌体相对宽大或饱满","tcm":"舌体胖瘦需与舌色、齿痕共同观察","tips":["拍摄时舌头自然放松","饮食规律","适量运动"],"foods":["清淡家常菜","全谷杂粮","蔬菜","优质蛋白"]},
    "shoushe": {"cn":"瘦舌","group":"舌形","desc":"舌体相对偏瘦或偏薄","tcm":"舌体胖瘦作为形态线索之一","tips":["保证规律三餐","注意营养摄入"],"foods":["蛋奶类","豆制品","鱼肉蛋","谷薯类"]},
    "hongdianshe": {"cn":"红点舌","group":"舌面","desc":"舌面观察到局部红点或点状特征","tcm":"观察红点位置与数量","tips":["减少辛辣过烫食物","注意口腔清洁"],"foods":["温度适宜食物","蔬菜","水果","充足饮水"]},
    "liewenshe": {"cn":"裂纹舌","group":"舌面","desc":"舌面检测到沟纹或裂纹","tcm":"裂纹是舌面形态特征，结合深浅分布观察","tips":["保持口腔清洁","规律饮水"],"foods":["水分充足食物","蔬菜","水果","清淡汤羹"]},
    "chihenshe": {"cn":"齿痕舌","group":"舌形","desc":"舌缘检测到类似牙齿压痕","tcm":"齿痕常与舌体胖瘦一起观察","tips":["拍照时轻轻伸舌","保持规律饮食"],"foods":["清淡家常菜","全谷物","蔬菜","优质蛋白"]},
    "baitaishe": {"cn":"白苔舌","group":"舌苔","desc":"舌苔颜色以白色或偏白为主","tcm":"白苔需结合厚薄润燥共同观察","tips":["保持口腔清洁","饮食规律少油腻"],"foods":["熟制蔬菜","米面杂粮","豆制品","清淡汤类"]},
    "huangtaishe": {"cn":"黄苔舌","group":"舌苔","desc":"舌苔呈黄色或偏黄色","tcm":"黄苔作为舌苔颜色线索之一","tips":["排除咖啡茶等染色","减少油炸过辣食物"],"foods":["绿叶蔬菜","清淡主食","水果","白水"]},
    "heitaishe": {"cn":"黑苔舌","group":"舌苔","desc":"舌苔存在明显灰黑或深色区域","tcm":"需结合肉眼颜色判断，易受染色曝光影响","tips":["自然光下复拍确认","排除深色食物影响","若持续建议就医"],"foods":["清淡均衡饮食","蔬菜","水果","充足饮水"]},
    "huataishe": {"cn":"花苔舌","group":"舌苔","desc":"舌面较湿润光滑或反光明显","tcm":"舌面润燥作为观察维度之一","tips":["拍摄前避免闪光灯","保持正常饮水"],"foods":["均衡饮食","熟制蔬菜","全谷物","优质蛋白"]},
    "shenquao": {"cn":"肾区凹","group":"区域形态","desc":"肾区观察到凹陷样形态","tcm":"区域形态标签，表示局部外观","tips":["自然伸舌复拍确认","结合其他舌象解读"],"foods":["均衡饮食","蔬菜","全谷物","优质蛋白"]},
    "shenqutu": {"cn":"肾区凸","group":"区域形态","desc":"肾区观察到隆起样形态","tcm":"区域形态标签，表示局部外观","tips":["自然伸舌复拍确认","结合其他舌象解读"],"foods":["均衡饮食","蔬菜","全谷物","优质蛋白"]},
    "gandanao": {"cn":"肝胆区凹","group":"区域形态","desc":"肝胆区观察到凹陷样形态","tcm":"区域形态标签，表示局部外观","tips":["自然放松伸舌复拍确认"],"foods":["均衡饮食","蔬菜","水果","优质蛋白"]},
    "gandantu": {"cn":"肝胆区凸","group":"区域形态","desc":"肝胆区观察到隆起样形态","tcm":"区域形态标签，表示局部外观","tips":["自然放松伸舌复拍确认"],"foods":["均衡饮食","蔬菜","水果","优质蛋白"]},
    "piweiao": {"cn":"脾胃区凹","group":"区域形态","desc":"脾胃区观察到凹陷样形态","tcm":"区域形态标签，表示局部外观","tips":["拍摄时舌面平展自然","饮食规律"],"foods":["规律三餐","谷薯类","熟制蔬菜","优质蛋白"]},
    "piweitu": {"cn":"脾胃区凸","group":"区域形态","desc":"脾胃区观察到隆起样形态","tcm":"区域形态标签，表示局部外观","tips":["拍摄时舌面平展自然","饮食规律"],"foods":["规律三餐","谷薯类","熟制蔬菜","优质蛋白"]},
    "xinfeiao": {"cn":"心肺区凹","group":"区域形态","desc":"心肺区观察到凹陷样形态","tcm":"区域形态标签，表示局部外观","tips":["自然放松伸舌复拍确认"],"foods":["均衡饮食","蔬菜","水果","充足饮水"]},
    "xinfeitu": {"cn":"心肺区凸","group":"区域形态","desc":"心肺区观察到隆起样形态","tcm":"区域形态标签，表示局部外观","tips":["自然放松伸舌复拍确认"],"foods":["均衡饮食","蔬菜","水果","充足饮水"]},
}

GROUP_ICON = {"综合":"◉","舌色":"●","舌形":"◇","舌面":"✦","舌苔":"≈","区域形态":"⌖"}

# 舌象 → 体质倾向
FEATURE_CONSTITUTION = {
    "jiankangshe":{"平和质":10},"botaishe":{"平和质":3},
    "hongshe":{"阴虚质":5,"阳热质":4,"湿热质":3},
    "zishe":{"气郁质":5},"pangdashe":{"痰湿质":5,"阳虚质":3},
    "shoushe":{"阴虚质":4,"气虚质":3},"hongdianshe":{"阳热质":5,"阴虚质":3},
    "liewenshe":{"阴虚质":6},"chihenshe":{"气虚质":5,"痰湿质":4,"阳虚质":3},
    "baitaishe":{"阳虚质":4,"痰湿质":3,"气虚质":2},
    "huangtaishe":{"湿热质":6,"阳热质":3,"食滞质":3},
    "heitaishe":{},"huataishe":{"气虚质":3,"阴虚质":3},
    "shenquao":{"阳虚质":4},"shenqutu":{"气郁质":2},
    "gandanao":{"气郁质":3},"gandantu":{"气郁质":4,"湿热质":3},
    "piweiao":{"气虚质":5,"食滞质":2},"piweitu":{"痰湿质":4,"食滞质":3},
    "xinfeiao":{"气虚质":4},"xinfeitu":{"阳热质":3,"阴虚质":2},
}

# ============================================================
# 儿童体质问卷数据（来自PDF《儿童体质中医分型与判定标准》）
# ============================================================
QUESTIONNAIRES = {
    "平和质": [("体型正常","3pt"),("肌肉结实","3pt"),("面色红润","3pt"),("头发有光泽","3pt"),("舌象：舌淡红苔薄白","3pt"),("精力充沛","5pt"),("声音洪亮（或哭声洪亮）","5pt"),("食欲好且食量正常","5pt"),("入睡快，睡眠比较安稳","5pt"),("便质正常，每日排便1~2次","5pt"),("性格开朗","5pt"),("很少生病","2pt"),("生病后很快能康复","5pt")],
    "特禀质": [("下眼圈发青","3pt"),("接触或食用某过敏原后易皮肤痒","5pt"),("容易出现过敏性疾病如过敏性鼻炎等","5pt"),("吃某种东西后易出现腹痛或泄泻","5pt"),("易起湿疹、荨麻疹","5pt"),("喜欢揉鼻子、揉眼睛或眨眼","5pt"),("有家族过敏性疾病史","2pt"),("小时候有慢性腹泻或者湿疹史","5pt"),("有喘息病史","2pt")],
    "气虚质": [("肌肉松软","3pt"),("面色偏白、没有光泽","3pt"),("面色偏黄、没有光泽","3pt"),("头发缺少光泽","3pt"),("舌象：舌质淡、苔白","3pt"),("容易劳累、没精神","5pt"),("声音小（或哭声低怯）","5pt"),("大便不成形或夹杂未消化的食物","5pt"),("活动后易出汗","5pt"),("喜欢安静、不爱户外活动","5pt"),("胆子小、说话少","5pt"),("每年患呼吸道感染的频率","freq"),("肚子胀","5pt")],
    "阳虚质": [("面色偏白、没有光泽","3pt"),("舌头表现为舌淡胖或有齿痕苔白","3pt"),("容易劳累、没精神","5pt"),("食欲差","5pt"),("吃凉的食物会感到不适","5pt"),("多眠易困","5pt"),("怕冷","5pt"),("手脚凉","5pt"),("喜欢安静、不爱户外活动","5pt"),("胆子小、说话少","5pt"),("每年患呼吸道感染的频率","freq")],
    "阴虚质": [("体型偏瘦","3pt"),("嘴唇颜色偏红、干燥","3pt"),("舌象：舌红少津苔少或地图舌","3pt"),("入睡时间长或轻浅易醒","5pt"),("大便干燥","5pt"),("手足心热","5pt"),("睡觉时易出汗","5pt"),("脾气急躁","5pt"),("皮肤干燥或易瘙痒","5pt"),("易起口疮、嗓子痛","5pt"),("喜欢揉鼻子、揉眼睛或眨眼","5pt")],
    "阳热质": [("面颊偏红","3pt"),("嘴唇颜色偏红、干燥","3pt"),("舌象：舌红苔黄或白","3pt"),("精力旺盛活动多","5pt"),("饭量大且容易饿","5pt"),("睡眠不踏实来回翻滚","5pt"),("大便干燥","5pt"),("大便气味臭","5pt"),("怕热活动后出汗多","5pt"),("脾气急躁","5pt"),("易起口疮嗓子痛","5pt"),("晨起眼屎多","5pt")],
    "气郁质": {"age_range":"4-12","items":[("体型偏瘦","3pt"),("舌象：舌色偏暗苔薄白","3pt"),("入睡时间长","5pt"),("大便干燥","5pt"),("心思细腻敏感","5pt"),("容易闷闷不乐唉声叹气","5pt"),("容易焦虑想事太多","5pt"),("受挫后情绪低落持续较久","5pt"),("容易打嗝或恶心干呕","5pt"),("觉得喉间有异物感","5pt"),("有无明显原因的头痛","5pt"),("入学后适应集体生活慢","5pt")]},
    "痰湿质": [("下眼睑浮肿","3pt"),("舌象：舌体胖大边有齿痕苔腻","3pt"),("容易劳累没精神","5pt"),("食欲差","5pt"),("不喜欢喝水","5pt"),("多眠易困","5pt"),("大便不成形","5pt"),("出汗黏","5pt"),("喜欢安静不爱户外活动","5pt"),("做事拖沓性子慢","5pt"),("易起湿疹荨麻疹","5pt"),("肚子胀","5pt"),("易打嗝或恶心干呕","5pt"),("觉得嗓子有痰","5pt"),("咳嗽时容易痰多","5pt")],
    "湿热质": [("舌象：舌红苔黄腻","3pt"),("晚上睡觉容易哭或惊醒","5pt"),("大便黏便盆不易冲刷干净","5pt"),("出汗黏","5pt"),("脾气急躁","5pt"),("易起湿疹","5pt"),("肚子胀","5pt"),("易起口疮嗓子痛","5pt"),("晨起眼屎多","5pt"),("口气重","5pt")],
    "食滞质": [("舌象：舌苔厚","3pt"),("睡眠不踏实来回翻滚或喜欢趴着睡","5pt"),("睡觉磨牙","5pt"),("脾气急躁","5pt"),("容易肚子疼或胀","5pt"),("口气重","5pt"),("打嗝易有酸臭味","5pt"),("有进食过多积食情况","5pt")],
    "偏心亢质": [("面颊偏红","3pt"),("舌象：舌尖红绛","3pt"),("入睡时间长","5pt"),("易起口疮嗓子痛","5pt")],
    "偏肝亢质": [("山根部位（鼻梁上）发青","3pt"),("晚上睡觉容易哭或惊醒","5pt"),("睡眠不踏实来回翻滚","5pt"),("脾气急躁","5pt")],
    "偏脾虚质": [("全身肌肉松软","3pt"),("面色偏黄没有光泽","3pt"),("饭后容易肚子胀","5pt"),("大便不成形或夹杂未消化的食物","5pt")],
    "偏肺虚质": [("面色偏白没有光泽","3pt"),("声音小或哭声低怯","5pt"),("活动后易出汗","5pt"),("每年患呼吸道感染的频率","freq")],
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
    "平和质":"精神饱满，精力充沛，体形匀称，面色红润，睡眠安稳，二便正常",
    "特禀质":"下睑暗影，皮肤易瘙痒，遇冷风或刺激气味后易打喷嚏鼻塞流涕",
    "气虚质":"精神欠振，易于疲倦，肌肉松软，面色萎黄，语声低怯，自汗",
    "阳虚质":"神疲倦怠，面色无华，畏寒肢冷，不耐生冷食物，小便清长",
    "阴虚质":"形体偏瘦，两颧潮红，口鼻干燥，手足心热，夜间汗多，大便偏干",
    "阳热质":"精神亢奋，形体壮实，面赤唇红，畏热喜凉，多食易饥，大便干结",
    "气郁质":"神情抑郁，易烦闷，善太息，喉间有异物感，大便偏干",
    "痰湿质":"精神欠振，体型偏胖，面部油腻，喉中常有痰，多汗而黏，大便不成形",
    "湿热质":"面垢油光，头汗多，有口气，小便短赤，大便黏腻不畅",
    "食滞质":"有口气，嗳气酸腐，腹部胀满，夜寐不安，喜俯卧，易磨牙",
    "偏心亢质":"面色偏红，哭声大，入睡困难，舌尖红绛，易口舌生疮",
    "偏肝亢质":"山根青筋，夜卧不安，偶有惊惕，暴躁冲动",
    "偏脾虚质":"面色萎黄，口唇色淡，肌肉松软，食后腹胀，大便偏溏",
    "偏肺虚质":"面色偏白而欠泽，声音较低微，自汗畏风，易患咳嗽感冒",
    "偏肾虚质":"形体矮小，头发干枯稀少，多见于低出生体重儿，易患遗尿",
}

# ============================================================
# 问卷工具函数
# ============================================================
def get_options(qtype, age_key):
    if qtype == "5pt": return [("总是",5),("经常",4),("有时",3),("偶尔",2),("从不",1)]
    if qtype == "3pt": return [("符合",5),("比较符合",3),("不符合",1)]
    if qtype == "2pt": return [("是",5),("否",1)]
    if qtype == "freq":
        if age_key=="1-3": return [("每年≥7次",5),("每年2~6次",3),("每年<2次",1)]
        if age_key=="4-6": return [("每年≥6次",5),("每年2~5次",3),("每年<2次",1)]
        return [("每年≥5次",5),("每年2~4次",3),("每年<2次",1)]
    return [("—",1)]

def calc_score(const_name, answers, age_key):
    items = QUESTIONNAIRES[const_name]
    item_list = items["items"] if isinstance(items, dict) else items
    actual = sum(answers)
    min_s = len(item_list)
    max_s = sum(get_options(it[1], age_key)[0][1] for it in item_list)
    return (actual - min_s) / (max_s - min_s) * 100 if max_s > min_s else 0

def determine(scores, age_key):
    std = STANDARDS[age_key]
    results = []
    ph = scores.get("平和质",0)
    others = {k:v for k,v in scores.items() if k in BASIC_TYPES and k!="平和质"}
    if ph >= std["ph"] and all(v < std["ph_o"] for v in others.values()):
        results.append(("平和质","判定",ph))
    for n,s in others.items():
        if n=="气郁质" and age_key=="1-3": continue
        if s >= std["pp"]: results.append((n,"判定",s))
        elif s >= std["pp_t"]: results.append((n,"倾向",s))
    for n in ORGAN_TYPES:
        s = scores.get(n,0)
        if s >= std["org"]: results.append((n,"判定",s))
        elif s >= std["org_t"]: results.append((n,"倾向",s))
    return results

# ============================================================
# YOLO 工具函数
# ============================================================
@st.cache_resource
def load_model():
    if not YOLO_AVAILABLE:
        return None
    if not os.path.exists(YOLO_MODEL_PATH):
        return None
    return YOLO(YOLO_MODEL_PATH)

def run_detection(image, model, conf=0.30):
    start = time.time()
    results = model.predict(source=image, conf=conf, imgsz=640, verbose=False)
    elapsed = (time.time() - start) * 1000
    r = results[0]
    annotated = r.plot(conf=True, labels=True, boxes=True)
    annotated_rgb = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
    features = []
    best = {}
    for box in r.boxes:
        cls_id = int(box.cls[0].item())
        conf_val = float(box.conf[0].item())
        raw = r.names[cls_id]
        if raw not in best or conf_val > best[raw]["confidence"]:
            best[raw] = {"raw_name":raw,"cn_name":FEATURE_META.get(raw,{}).get("cn",raw),"group":FEATURE_META.get(raw,{}).get("group","其他"),"confidence":conf_val}
    features = sorted(best.values(), key=lambda x: x["confidence"], reverse=True)
    return {"features":features, "annotated":annotated_rgb, "elapsed":elapsed}

def tongue_to_constitution(features):
    scores = {}
    for f in features:
        en = f["raw_name"]
        if en in FEATURE_CONSTITUTION:
            for c,w in FEATURE_CONSTITUTION[en].items():
                scores[c] = scores.get(c,0) + w * f["confidence"]
    if not scores: return "平和质", {}
    sorted_s = sorted(scores.items(), key=lambda x:x[1], reverse=True)
    return sorted_s[0][0], dict(sorted_s)

# ============================================================
# 豆包API
# ============================================================
def call_doubao(api_key, model_id, messages):
    try:
        resp = requests.post(DOUBAO_API_URL, headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"},
            json={"model":model_id,"messages":messages,"temperature":0.7,"max_tokens":4096}, timeout=60)
        if resp.status_code != 200:
            return None, f"API错误: {resp.json().get('error',{}).get('message',resp.text)}"
        return resp.json()["choices"][0]["message"]["content"], None
    except Exception as e:
        return None, str(e)

# ============================================================
# 样式
# ============================================================
st.markdown("""
<style>
:root{--tcm-green:#0d6b5b;--tcm-deep:#073b35;--jade:#e7f4ef;--gold:#c89b47;--paper:#fbfaf6;--ink:#17332f;--muted:#6a7d78;--line:rgba(13,107,91,.13)}
.stApp{background:radial-gradient(circle at 82% 5%,rgba(200,155,71,.09),transparent 27%),radial-gradient(circle at 9% 18%,rgba(13,107,91,.07),transparent 24%),linear-gradient(180deg,#fbfcf9 0%,#f6faf7 100%)}
.main .block-container{padding-top:1.4rem;max-width:1380px}
.hero{position:relative;overflow:hidden;padding:28px 32px;border-radius:24px;margin-bottom:18px;color:white;background:linear-gradient(125deg,rgba(7,59,53,.97),rgba(13,107,91,.93) 60%,rgba(16,128,106,.88));box-shadow:0 16px 45px rgba(7,59,53,.13)}
.hero:after{content:"青";position:absolute;right:34px;top:-35px;font-size:178px;font-family:serif;color:rgba(255,255,255,.055);transform:rotate(-8deg)}
.hero-kicker{display:inline-block;font-size:12px;letter-spacing:.18em;padding:6px 10px;border:1px solid rgba(255,255,255,.25);border-radius:999px;background:rgba(255,255,255,.08);margin-bottom:12px}
.hero h1{margin:0;font-size:clamp(31px,4vw,46px);line-height:1.12;font-weight:760}
.hero p{margin:10px 0 0;max-width:760px;color:rgba(255,255,255,.82);font-size:15px;line-height:1.7}
.workflow{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:14px 0 22px}
.flow-item{padding:12px 14px;border-radius:15px;border:1px solid var(--line);background:rgba(255,255,255,.74);color:var(--ink);box-shadow:0 6px 22px rgba(23,51,47,.035);font-size:13px}
.flow-num{display:inline-flex;align-items:center;justify-content:center;width:23px;height:23px;margin-right:6px;border-radius:50%;color:white;background:var(--tcm-green);font-size:11px;font-weight:700}
.soft-card{padding:16px 17px;border-radius:17px;border:1px solid var(--line);background:rgba(255,255,255,.86);box-shadow:0 8px 26px rgba(23,51,47,.04);min-height:100%}
.feature-card{padding:16px 17px;border-radius:17px;border:1px solid rgba(13,107,91,.12);border-top:3px solid rgba(13,107,91,.72);background:linear-gradient(180deg,rgba(255,255,255,.97),rgba(247,251,249,.94));box-shadow:0 8px 24px rgba(23,51,47,.04);min-height:184px}
.feature-title{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:9px}
.feature-name{font-size:18px;font-weight:750;color:var(--ink)}
.tag{display:inline-block;padding:3px 8px;border-radius:999px;background:var(--jade);color:var(--tcm-green);font-size:11px;font-weight:650;white-space:nowrap}
.conf{color:var(--gold);font-size:12px;font-weight:700}
.feature-card p{margin:7px 0;color:#51625e;line-height:1.62;font-size:13px}
.tip-strip{padding:12px 15px;border-left:4px solid var(--gold);border-radius:10px;background:rgba(200,155,71,.08);color:#5f5338;font-size:13px;margin:10px 0}
.danger-strip{padding:12px 15px;border-left:4px solid #b56458;border-radius:10px;background:rgba(181,100,88,.07);color:#6a4038;font-size:13px;margin:10px 0}
.food-chip{display:inline-block;margin:4px 5px 4px 0;padding:7px 10px;border-radius:999px;border:1px solid rgba(13,107,91,.14);background:rgba(231,244,239,.66);color:#28564e;font-size:12px}
.small-note{color:var(--muted);font-size:12px;line-height:1.65}
.section-kicker{color:var(--tcm-green);font-weight:750;letter-spacing:.05em;font-size:12px;margin-bottom:3px}
.footer{text-align:center;color:#80918c;padding:30px 0 12px;font-size:12px}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#f4faf7 0%,#fbfbf8 100%);border-right:1px solid rgba(13,107,91,.09)}
@media(max-width:800px){.workflow{grid-template-columns:1fr 1fr}.hero{padding:24px 22px}}
</style>
""", unsafe_allow_html=True)

# ============================================================
# 初始化 session state
# ============================================================
for key in ['tongue_analysis', 'qa_scores', 'qa_results', 'qa_age', 'ai_report', 'api_key', 'model_id']:
    if key not in st.session_state:
        st.session_state[key] = None if key != 'api_key' and key != 'model_id' else st.session_state.get(key, '')

# ============================================================
# 页头
# ============================================================
st.markdown("""
<div class="hero">
    <div class="hero-kicker">青囊AI · TCM × COMPUTER VISION × AI</div>
    <h1>🌿 青囊AI · 舌象与体质智能分析</h1>
    <p>本地YOLO舌象检测 + 儿童中医体质分型问卷（基于《儿童体质中医分型与判定标准》） + 豆包AI智能健康报告。三合一综合分析，为儿童健康提供中医体质科普参考。</p>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="workflow">
    <div class="flow-item"><span class="flow-num">1</span>舌象拍照检测</div>
    <div class="flow-item"><span class="flow-num">2</span>体质问卷评分</div>
    <div class="flow-item"><span class="flow-num">3</span>豆包AI综合分析</div>
    <div class="flow-item"><span class="flow-num">4</span>健康饮食建议</div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# 侧边栏
# ============================================================
with st.sidebar:
    st.markdown("### 🌿 青囊AI 控制台")

    st.divider()
    st.markdown("#### ✨ 豆包AI设置")
    st.session_state['api_key'] = st.text_input("API Key", type="password", value=st.session_state.get('api_key',''))
    st.session_state['model_id'] = st.text_input("模型ID", value=st.session_state.get('model_id',''), placeholder="如 doubao-pro-32k")

    st.divider()
    st.markdown("#### 🧠 本地模型")
    if YOLO_AVAILABLE:
        if os.path.exists(YOLO_MODEL_PATH):
            st.success(f"已加载：best.pt")
            if torch.cuda.is_available():
                st.success(f"GPU · {torch.cuda.get_device_name(0)}")
            else:
                st.info("CPU 模式")
        else:
            st.warning(f"模型文件不存在：{YOLO_MODEL_PATH}")
    else:
        st.error("ultralytics/torch 未安装")
        st.caption("请安装：pip install torch ultralytics opencv-python")

    st.divider()
    st.markdown("#### 📊 当前状态")
    st.markdown(f"{'✅' if st.session_state.tongue_analysis else '⬜'} 舌象分析")
    st.markdown(f"{'✅' if st.session_state.qa_results else '⬜'} 体质问卷")
    st.markdown(f"{'✅' if st.session_state.ai_report else '⬜'} AI报告")

    st.divider()
    st.markdown("""
    <div class="small-note">
    <b>拍摄建议</b><br>
    • 使用自然光或柔和白光<br>
    • 舌头自然伸出、尽量平展<br>
    • 不使用美颜、滤镜<br>
    • 避免图片过暗或模糊
    </div>
    """, unsafe_allow_html=True)

    st.divider()
    st.markdown('<div class="danger-strip" style="font-size:11px;">本应用仅作中医体质健康科普参考，不构成医疗诊断，不能替代医师诊疗，身体不适请及时就医。</div>', unsafe_allow_html=True)

# ============================================================
# 状态指标
# ============================================================
m1,m2,m3,m4 = st.columns(4)
with m1: st.metric("本地模型", "best.pt" if YOLO_AVAILABLE and os.path.exists(YOLO_MODEL_PATH) else "未就绪", border=True)
with m2: st.metric("舌象特征", "21类", border=True)
with m3: st.metric("体质类型", "15种", border=True)
with m4: st.metric("AI引擎", "豆包" if st.session_state.get('api_key') else "未配置", border=True)

# ============================================================
# 功能页签
# ============================================================
tab_tongue, tab_qa, tab_report, tab_atlas = st.tabs(["👅 舌象分析", "📋 体质问卷", "🤖 AI健康报告", "📚 舌象图谱"])

# ==================== Tab 1: 舌象分析 ====================
with tab_tongue:
    st.markdown("### 👅 舌象智能检测")
    st.caption("上传舌象图片，YOLO模型自动检测21种舌象特征")

    col_l, col_r = st.columns([1.6, 1])

    with col_l:
        st.markdown("#### 📷 上传舌象图片")
        uploaded = st.file_uploader("选择图片", type=['jpg','jpeg','png','webp'], label_visibility="collapsed")

    with col_r:
        st.markdown("#### 📝 拍摄提示")
        st.markdown("""
        <div class="soft-card">
            <span class="food-chip">☀️ 光线自然</span>
            <span class="food-chip">👅 舌体平展</span>
            <span class="food-chip">🎨 无滤镜</span>
            <span class="food-chip">🔍 画面清晰</span>
            <div class="small-note" style="margin-top:10px;">舌色和舌苔易受光照、白平衡和食物染色影响。若结果与肉眼差异明显，优先重新拍摄。</div>
        </div>
        """, unsafe_allow_html=True)

    if uploaded:
        img = Image.open(BytesIO(uploaded.getvalue()))
        img = ImageOps.exif_transpose(img).convert("RGB")
        st.markdown("#### 图片预览")
        st.image(img, caption="待分析舌象", use_column_width=True)

        confidence = st.slider("置信度阈值", 0.10, 0.90, 0.30, 0.05, help="默认0.30保留弱特征")

        if st.button("🚀 开始AI舌象分析", type="primary"):
            if not YOLO_AVAILABLE:
                st.error("ultralytics/torch 未安装，无法运行检测。请先安装：pip install torch ultralytics opencv-python")
            elif not os.path.exists(YOLO_MODEL_PATH):
                st.error(f"模型文件不存在：{YOLO_MODEL_PATH}")
            else:
                model = load_model()
                if model:
                    with st.spinner("best.pt 正在识别舌象特征……"):
                        try:
                            result = run_detection(img, model, confidence)
                            import io as _io
                            buf = _io.BytesIO()
                            img.save(buf, format="JPEG", quality=92)
                            st.session_state.tongue_analysis = {
                                "features": result["features"],
                                "annotated": result["annotated"],
                                "elapsed": result["elapsed"],
                                "original": buf.getvalue(),
                                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "confidence": confidence,
                            }
                            st.success(f"检测完成！耗时 {result['elapsed']:.0f}ms")
                            st.rerun()
                        except Exception as e:
                            st.error(f"检测失败：{e}")

    if st.session_state.tongue_analysis:
        ta = st.session_state.tongue_analysis
        st.divider()
        st.markdown("### 🔍 AI识别结果")

        c1,c2 = st.columns(2)
        with c1:
            st.markdown("**原始舌象**")
            st.image(ta["original"], use_column_width=True)
        with c2:
            st.markdown("**特征检测框**")
            st.image(ta["annotated"], use_column_width=True)

        features = ta["features"]
        a,b,c,d = st.columns(4)
        with a: st.metric("检测特征", len(features), border=True)
        with b: st.metric("推理耗时", f"{ta['elapsed']:.0f}ms", border=True)
        with c:
            avg = sum(f["confidence"] for f in features)/len(features) if features else 0
            st.metric("平均置信度", f"{avg*100:.1f}%", border=True)
        with d:
            primary, _ = tongue_to_constitution(features)
            st.metric("舌象体质倾向", primary, border=True)

        if features:
            for i in range(0, len(features), 3):
                row = features[i:i+3]
                cols = st.columns(3)
                for col, item in zip(cols, row):
                    meta = FEATURE_META.get(item["raw_name"], {"cn":item["raw_name"],"group":"其他","desc":"","tcm":""})
                    with col:
                        st.markdown(f"""
                        <div class="feature-card">
                            <div class="feature-title">
                                <div class="feature-name">{GROUP_ICON.get(meta['group'],'•')} {meta['cn']}</div>
                                <span class="tag">{meta['group']}</span>
                            </div>
                            <div class="conf">置信度 {item['confidence']*100:.1f}%</div>
                            <p>{meta['desc']}</p>
                            <p><b>传统舌象：</b>{meta['tcm']}</p>
                        </div>
                        """, unsafe_allow_html=True)

            st.markdown("#### 🏷️ 舌象提示体质倾向")
            primary, all_scores = tongue_to_constitution(features)
            st.markdown(f"**主要倾向：{primary}**")
            if all_scores:
                import pandas as pd
                df = pd.DataFrame([(k,v) for k,v in all_scores.items()], columns=["体质","倾向得分"])
                st.bar_chart(df.set_index("体质"))

            # 饮食参考
            st.markdown("#### 🥗 饮食参考")
            all_foods = []
            for f in features:
                meta = FEATURE_META.get(f["raw_name"], {})
                for food in meta.get("foods", []):
                    if food not in all_foods:
                        all_foods.append(food)
            food_html = "".join(f'<span class="food-chip">{f}</span>' for f in all_foods[:12])
            st.markdown(food_html, unsafe_allow_html=True)

    st.markdown('<div class="danger-strip">⚠️ 图像分析仅作体质参考，不能替代中医师面诊。AI检测结果受拍摄光线、角度等因素影响。</div>', unsafe_allow_html=True)

# ==================== Tab 2: 体质问卷 ====================
with tab_qa:
    st.markdown("### 📋 儿童中医体质问卷")
    st.markdown("基于《儿童体质中医分型与判定标准》（赵霞等，2023）| 评分采用Likert 5分法")

    age_group = st.selectbox("选择年龄段", ["1-3岁","4-6岁","7-12岁"])
    age_key = age_group.replace("岁","")
    st.session_state.qa_age = age_key

    all_scores = {}

    for const_name, const_data in QUESTIONNAIRES.items():
        items_list = const_data["items"] if isinstance(const_data, dict) else const_data
        if isinstance(const_data, dict) and const_data.get("age_range") == "4-12" and age_key == "1-3":
            continue

        is_organ = const_name in ORGAN_TYPES
        emoji = "🫀" if "心" in const_name else "🫁" if "肺" in const_name else "🌱" if "肝" in const_name else "🌾" if "脾" in const_name else "💧" if "肾" in const_name else "📋"

        with st.expander(f"{emoji} {const_name}（{len(items_list)}题）", expanded=False):
            if const_name in CONSTITUTION_INFO:
                st.caption(f"_{CONSTITUTION_INFO[const_name]}_")

            answers = []
            for i, (question, qtype) in enumerate(items_list):
                options = get_options(qtype, age_key)
                labels = [o[0] for o in options]
                choice = st.radio(f"{i+1}. {question}", labels, key=f"{const_name}_{i}", horizontal=True, index=len(labels)-1)
                score = next(s for l,s in options if l == choice)
                answers.append(score)

            transformed = calc_score(const_name, answers, age_key)
            all_scores[const_name] = transformed
            st.metric("转化分数", f"{transformed:.1f}%")

    st.markdown("---")
    st.markdown("### 📊 体质判定结果")

    if st.button("📊 生成体质判定", type="primary"):
        results = determine(all_scores, age_key)
        st.session_state.qa_scores = all_scores
        st.session_state.qa_results = results

    if st.session_state.qa_results:
        results = st.session_state.qa_results
        if results:
            for name, level, score in results:
                color = "#0d6b5b" if level == "判定" else "#c89b47"
                st.markdown(f'<span style="background:rgba(13,107,91,0.1);color:{color};padding:0.3rem 1rem;border-radius:999px;font-weight:600;">{name} · {level} · {score:.1f}%</span>', unsafe_allow_html=True)
                st.markdown("")

        import pandas as pd
        st.markdown("#### 全部体质分数")
        df = pd.DataFrame([(k,f"{v:.1f}%") for k,v in st.session_state.qa_scores.items()], columns=["体质类型","转化分数"])
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown('<div class="danger-strip">⚠️ 体质判定结果仅作科普参考。五脏体质判定结果仅供参考，需结合四诊资料由医师判定。</div>', unsafe_allow_html=True)

# ==================== Tab 3: AI健康报告 ====================
with tab_report:
    st.markdown("### 🤖 AI综合健康报告")
    st.markdown("结合舌象检测与体质问卷，由豆包AI生成个性化健康建议")

    has_tongue = st.session_state.tongue_analysis is not None
    has_qa = st.session_state.qa_results is not None
    has_api = bool(st.session_state.get('api_key')) and bool(st.session_state.get('model_id'))

    c1,c2,c3 = st.columns(3)
    with c1: st.metric("舌象检测", "✅ 已完成" if has_tongue else "⬜ 未完成", border=True)
    with c2: st.metric("体质问卷", "✅ 已完成" if has_qa else "⬜ 未完成", border=True)
    with c3: st.metric("API设置", "✅ 已配置" if has_api else "⬜ 未配置", border=True)

    if not has_api:
        st.warning("请在左侧填写豆包API Key和模型ID")
    elif not has_tongue and not has_qa:
        st.warning("请先完成「舌象分析」和/或「体质问卷」")
    else:
        report_parts = []

        if has_tongue:
            features = st.session_state.tongue_analysis["features"]
            if features:
                feat_text = "\n".join(f"- {FEATURE_META.get(f['raw_name'],{}).get('cn',f['raw_name'])}（{f['raw_name']}）：置信度{f['confidence']:.1%}" for f in features)
                primary, scores = tongue_to_constitution(features)
                report_parts.append(f"## 舌象检测结果\n检测到以下舌象特征：\n{feat_text}\n\n舌象提示体质倾向：{primary}")
            else:
                report_parts.append("## 舌象检测结果\n未检测到明显异常舌象特征")

        if has_qa:
            qr = st.session_state.qa_results
            result_text = "\n".join(f"- {name}：{level}（转化分数{score:.1f}%）" for name,level,score in qr) or "- 各项评分均未达判定标准"
            report_parts.append(f"## 体质问卷结果（年龄段：{st.session_state.qa_age}）\n{result_text}")

        combined = "\n\n".join(report_parts)
        st.markdown("#### 📝 分析数据摘要")
        st.markdown(combined)
        st.markdown("---")

        if st.button("🚀 生成AI健康报告", type="primary"):
            prompt = f"""你是一位经验丰富的中医健康管理师，请根据以下检测数据，用通俗易懂的语言为家长生成儿童健康分析报告。

{combined}

请按以下格式输出：
1. **综合分析**：结合舌象和体质问卷结果，总结体质状况（2-3段）
2. **体质特征解读**：用通俗白话解释体质类型
3. **日常调养建议**：
   - 饮食建议（推荐食材、忌口食材，药食同源日常食材）
   - 起居建议（作息、运动）
   - 情志建议（情绪管理）
4. **注意事项**

要求：
- 禁止疾病诊断话术，只描述"体质倾向""身体偏颇""调养建议"
- 中医术语必须附带白话解释
- 面向家长，语言亲切易懂
- 末尾标注："以上分析仅作体质科普参考，不构成医疗诊断，不能替代医师诊疗"
"""
            with st.spinner("豆包AI正在生成健康报告……"):
                reply, err = call_doubao(st.session_state['api_key'], st.session_state['model_id'], [{"role":"user","content":prompt}])
                if err:
                    st.error(f"生成失败：{err}")
                else:
                    st.session_state.ai_report = reply
                    st.success("报告生成成功！")

    if st.session_state.ai_report:
        st.markdown("#### 📄 AI健康报告")
        st.markdown(st.session_state.ai_report)

    st.markdown('<div class="danger-strip">⚠️ 以上报告由AI生成，仅作中医体质健康科普参考，不构成医疗诊断，不能替代医师诊疗，身体不适请及时就医。</div>', unsafe_allow_html=True)

# ==================== Tab 4: 舌象图谱 ====================
with tab_atlas:
    st.markdown("### 📚 21类舌象特征图谱")
    st.caption("best.pt 模型标签字典及中文解释")

    import pandas as pd
    rows = []
    for idx, raw_name in enumerate([k for k in FEATURE_META.keys()]):
        meta = FEATURE_META[raw_name]
        rows.append({"ID":idx, "模型标签":raw_name, "中文名称":meta["cn"], "类别":meta["group"], "观察内容":meta["desc"]})

    atlas_df = pd.DataFrame(rows)
    group_filter = st.multiselect("筛选类别", options=list(dict.fromkeys(atlas_df["类别"].tolist())), default=[])
    if group_filter:
        atlas_df = atlas_df[atlas_df["类别"].isin(group_filter)]
    st.dataframe(atlas_df, hide_index=True, use_container_width=True)

    st.markdown('<div class="tip-strip"><b>特别说明：</b>"肾区/肝胆区/脾胃区/心肺区"的凹凸标签是区域形态类别，应展示为"区域形态观察"，不代表对应脏器疾病。</div>', unsafe_allow_html=True)

# ============================================================
# 页脚
# ============================================================
st.markdown("""
<div class="footer">
    青囊AI · best.pt + YOLO + Streamlit + 豆包AI · 舌象识别 + 体质问卷 + 健康科普<br>
    本应用仅作中医体质健康科普参考，不能替代医生诊断、检查或治疗建议
</div>
""", unsafe_allow_html=True)
