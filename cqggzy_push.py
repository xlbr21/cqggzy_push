#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
重庆市公共资源交易网 - 招投标商机自动推送（一键版）
只需创建这一个文件 + 配置 Secret 即可运行
"""
import json, os, logging, requests
from datetime import datetime, timedelta
from pathlib import Path

SERVERCHAN_SENDKEY = os.environ.get("SERVERCHAN_SENDKEY", "")
_env_kw = os.environ.get("KEYWORDS", "")
KEYWORDS = [k.strip() for k in _env_kw.split(",") if k.strip()] if _env_kw else ["装修","信息化","消防","绿化","监理"]
_env_ex = os.environ.get("EXCLUDE_KEYWORDS", "")
EXCLUDE_KEYWORDS = [k.strip() for k in _env_ex.split(",") if k.strip()] if _env_ex else ["废标","终止","流标","撤回"]
CATEGORIES = [
    {"code":"014001001","name":"工程招标公告"},
    {"code":"014005001","name":"政府采购公告"},
    {"code":"014012001","name":"国企采购公告"},
]
MAX_RECORDS = 20
HISTORY_PATH = Path(__file__).parent / "pushed_history.json"
API_URL = "https://www.cqggzy.com/inteligentsearch/rest/esinteligentsearch/getFullTextDataNew"
BASE_URL = "https://www.cqggzy.com"
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

def load_hist(): return json.loads(HISTORY_PATH.read_text("utf-8")) if HISTORY_PATH.exists() else {}
def save_hist(h): HISTORY_PATH.write_text(json.dumps(h, ensure_ascii=False, indent=2), "utf-8")
def clean_hist(h, days=30):
    cut = (datetime.now()-timedelta(days=days)).strftime("%Y-%m-%d")
    return {k:v for k,v in h.items() if v.get("pushed_at","")[:10]>=cut}

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Origin": "https://www.cqggzy.com",
    "Referer": "https://www.cqggzy.com/xxhz/014001/014001001/transaction_detail.html",
    "X-Requested-With": "XMLHttpRequest",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}

def fetch(cat_code, sd, ed):
    param = {"token":"","pn":0,"rn":MAX_RECORDS,"sdt":"","edt":"","wd":"","inc_wd":"","exc_wd":"",
        "fields":"","cnum":"001","sort":'{"istop":"0","ordernum":"0","webdate":"0","newid":"0"}',
        "ssort":"","cl":10000,"terminal":"",
        "condition":[{"fieldName":"categorynum","equal":cat_code,"notEqual":None,"equalList":None,
            "notEqualList":["014001018","004002005","014001015","014005014","014008011"],"isLike":True,"likeType":2}],
        "time":[{"fieldName":"webdate","startTime":f"{sd} 00:00:00","endTime":f"{ed} 23:59:59"}],
        "highlights":"","statistics":None,"unionCondition":None,"accuracy":"","noParticiple":"1","searchRange":None,"noWd":True}
    try:
        r = requests.post(API_URL, json=param, headers=HEADERS, timeout=15)
        r.raise_for_status(); d = r.json()
        if d.get("code")!=200: return []
        c = d.get("content","")
        if isinstance(c,str): c = json.loads(c)
        recs = c.get("result",{}).get("records",[])
        log.info(f"栏目 {cat_code}: {len(recs)}条")
        return recs
    except Exception as e:
        log.error(f"抓取 {cat_code} 失败: {e}"); return []

def match_kw(title):
    if not KEYWORDS: return True
    for kw in EXCLUDE_KEYWORDS:
        if kw in title: return False
    for kw in KEYWORDS:
        if kw in title: return True
    return False

def fmt(r):
    return {"id":r.get("infoid",""),"title":r.get("title",""),"date":r.get("infodate",""),
        "region":r.get("infoc",""),"biaoduan":r.get("biaoduantype",""),
        "link":BASE_URL+r.get("linkurl","")}

def push_wechat(title, content):
    if not SERVERCHAN_SENDKEY:
        log.warning("未配置SendKey"); print(content[:2000]); return False
    try:
        r = requests.post(f"https://sctapi.ftqq.com/{SERVERCHAN_SENDKEY}.send", data={"title":title,"desp":content}, timeout=10)
        res = r.json()
        if res.get("code")==0: log.info("推送成功"); return True
        log.error(f"推送失败: {res}"); return False
    except Exception as e:
        log.error(f"推送异常: {e}"); return False

def build_msg(by_cat):
    now = datetime.now().strftime("%Y-%m-%d")
    lines = [f"# 招投标商机日报","","**日期**: "+now,"**数据来源**: 重庆市公共资源交易网",""]
    total = 0
    for cn, recs in by_cat.items():
        if not recs: continue
        total += len(recs)
        lines += ["---","",f"## {cn}（{len(recs)}条）","",
            "| 序号 | 标题 | 区域 | 类型 | 发布时间 |","|:----:|:-----|:----:|:----:|:--------:|"]
        for i,r in enumerate(recs,1):
            lines.append(f'| {i} | [{r["title"]}]({r["link"]}) | {r["region"]} | {r["biaoduan"]} | {r["date"][:10]} |')
        lines.append("")
    if total==0: lines.append("*今日暂无符合条件的商机信息*")
    else: lines.insert(3, f"**今日新增**: {total} 条商机")
    lines += ["---","","*数据来源于[重庆市公共资源交易网](https://www.cqggzy.com)，仅供参考*"]
    return f"招投标日报 {now}", "\n".join(lines)

def main():
    log.info("招投标推送任务开始")
    hist = clean_hist(load_hist())
    today = datetime.now(); sd = (today-timedelta(days=2)).strftime("%Y-%m-%d"); ed = today.strftime("%Y-%m-%d")
    by_cat = {}; new_all = []
    for cat in CATEGORIES:
        raws = fetch(cat["code"], sd, ed)
        new_recs = []
        for raw in raws:
            r = fmt(raw); rid = r["id"]
            if rid in hist: continue
            if not match_kw(r["title"]): continue
            new_recs.append(r); new_all.append(r)
        by_cat[cat["name"]] = new_recs
        for raw in raws:
            rid = raw.get("infoid","")
            if rid: hist[rid] = {"title":raw.get("title",""),"category":cat["name"],"pushed_at":datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    if new_all:
        t, c = build_msg(by_cat); push_wechat(t, c); log.info(f"推送 {len(new_all)} 条商机")
    else: log.info("今日暂无新商机")
    save_hist(hist); log.info("任务完成")

if __name__ == "__main__": main()
