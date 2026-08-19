#!/usr/bin/env python3
"""
CGV 광교 IMAX 예매 오픈/변동 알리미
GitHub Actions + Discord Webhook
"""

import os
import json
import hashlib
import requests
from datetime import datetime, timezone, timedelta

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
STATE_FILE = "state.json"

# ===== 광교 설정 (캡처한 값) =====
SITE_NO = "0257"          # CGV 광교
CO_CD = "A420"
SCREEN_NO = "006"         # IMAX관 (6관)
MOVIE_KEYWORD = "오디세이"
DAYS_AHEAD = 10           # 오늘부터 며칠까지 볼지

KST = timezone(timedelta(hours=9))


def send_discord(content: str):
    if not DISCORD_WEBHOOK:
        print("DISCORD_WEBHOOK 없음")
        return
    try:
        r = requests.post(
            DISCORD_WEBHOOK,
            json={"content": content, "username": "CGV 광교 IMAX 알리미"},
            timeout=15,
        )
        r.raise_for_status()
        print("Discord 전송 성공")
    except Exception as e:
        print(f"Discord 실패: {e}")


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"hash": None, "last_check": None}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_dates():
    today = datetime.now(KST).date()
    return [(today + timedelta(days=i)).strftime("%Y%m%d") for i in range(DAYS_AHEAD)]


def fetch_schedule(date_str: str):
    """광교 특정 날짜 스케줄 조회"""
    url = "https://cgv.co.kr/api/v1/booking/searchMovScnInfo"
    params = {
        "coCd": CO_CD,
        "siteNo": SITE_NO,
        "scnYmd": date_str,
        "rtctlScopCd": "08",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://cgv.co.kr/",
    }
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"{date_str} 조회 실패: {e}")
        return None


def extract_imax_odyssey(data):
    """오디세이 + IMAX 회차만 추출"""
    if not data:
        return []
    items = []
    raw = json.dumps(data, ensure_ascii=False)
    if MOVIE_KEYWORD in raw and ("IMAX" in raw.upper() or SCREEN_NO in raw):
        items.append(raw[:800])
    return items


def main():
    print(f"[{datetime.now(KST)}] CGV 광교 체크 시작")
    state = load_state()
    all_items = []

    for date_str in get_dates():
        data = fetch_schedule(date_str)
        found = extract_imax_odyssey(data)
        if found:
            all_items.append({"date": date_str, "data": found})
            print(f"{date_str}: 데이터 있음")
        else:
            print(f"{date_str}: 해당 없음")

    current_raw = json.dumps(all_items, ensure_ascii=False, sort_keys=True)
    current_hash = hashlib.sha256(current_raw.encode()).hexdigest()
    prev_hash = state.get("hash")

    if prev_hash is None:
        send_discord(
            f"**CGV 광교 IMAX 알리미 시작**\n"
            f"감시 극장: 광교 (siteNo={SITE_NO})\n"
            f"영화: {MOVIE_KEYWORD} / IMAX\n"
            f"체크 시각: {datetime.now(KST).strftime('%Y-%m-%d %H:%M')}"
        )
        print("첫 실행 - 기준값 저장")
    elif prev_hash != current_hash:
        send_discord(
            f"**🎬 CGV 광교 IMAX 예매 변동 감지!**\n"
            f"시간: {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"영화: {MOVIE_KEYWORD}\n"
            f"→ [예매하러 가기](https://cgv.co.kr/)"
        )
        print("변화 감지 → 알림 전송")
    else:
        print("변화 없음")

    state["hash"] = current_hash
    state["last_check"] = datetime.now(KST).isoformat()
    state["preview"] = current_raw[:500]
    save_state(state)
    print("체크 완료")


if __name__ == "__main__":
    main()
