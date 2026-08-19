#!/usr/bin/env python3
"""
CGV 광교 IMAX - 예매 오픈/잔여좌석 알리미
알림 형식:
예매 오픈 알림 : 날짜: 20260827, 상영관: IMAX관, 영화: 오디세이(IMAX LASER 2D), 시간: 0700~1002, 잔여좌석: 5
"""

import os
import json
import hashlib
import requests
from datetime import datetime, timezone, timedelta

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
STATE_FILE = "state.json"

SITE_NO = "0257"          # CGV 광교
CO_CD = "A420"
MOVIE_KEYWORD = "오디세이"
IMAX_KEYWORDS = ("IMAX", "아이맥스")
DAYS_AHEAD = 14
MIN_SEATS_TO_NOTIFY = 1   # 잔여석 이 수 이상일 때만 알림 (원하면 수정)

KST = timezone(timedelta(hours=9))


def send_discord(content: str):
    if not DISCORD_WEBHOOK:
        print("DISCORD_WEBHOOK 없음")
        return
    # Discord는 2000자 제한 → 길면 나눠 전송
    chunks = [content[i:i+1900] for i in range(0, len(content), 1900)]
    for chunk in chunks:
        try:
            r = requests.post(
                DISCORD_WEBHOOK,
                json={"content": chunk, "username": "CGV 광교 IMAX"},
                timeout=15,
            )
            r.raise_for_status()
        except Exception as e:
            print(f"Discord 실패: {e}")


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"sessions": {}, "last_check": None}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_dates():
    today = datetime.now(KST).date()
    return [(today + timedelta(days=i)).strftime("%Y%m%d") for i in range(DAYS_AHEAD)]


def fetch_schedule(date_str: str):
    url = "https://cgv.co.kr/api/v1/booking/searchMovScnInfo"
    params = {
        "coCd": CO_CD,
        "siteNo": SITE_NO,
        "scnYmd": date_str,
        "rtctlScopCd": "08",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://cgv.co.kr/",
        "Origin": "https://cgv.co.kr",
    }
    try:
        r = requests.get(url, params=params, headers=headers, timeout=20)
        if r.status_code != 200:
            print(f"{date_str} HTTP {r.status_code}")
            return None
        # Cloudflare HTML 차단 체크
        if "text/html" in r.headers.get("Content-Type", "") or r.text.strip().startswith("<!"):
            print(f"{date_str} Cloudflare 차단 또는 HTML 응답")
            return None
        return r.json()
    except Exception as e:
        print(f"{date_str} 조회 실패: {e}")
        return None


def walk_find_sessions(obj, date_str, results):
    """JSON 전체를 돌면서 회차 정보 추출"""
    if isinstance(obj, dict):
        # 한 회차처럼 보이는 필드 조합
        mov = obj.get("movNm") or obj.get("movieNm") or obj.get("MOVIE_NM") or ""
        start = obj.get("scnsrtTm") or obj.get("startTm") or obj.get("PLAY_START_TM") or ""
        end = obj.get("scnendTm") or obj.get("endTm") or obj.get("PLAY_END_TM") or ""
        seats = obj.get("frSeatCnt") or obj.get("remainSeat") or obj.get("REST_SEAT") or obj.get("seatCnt")
        screen = (
            obj.get("scnsNm")
            or obj.get("screenNm")
            or obj.get("SCREEN_NM")
            or obj.get("ratingNm")
            or obj.get("RATING_NM")
            or ""
        )

        text_blob = json.dumps(obj, ensure_ascii=False)
        is_movie = MOVIE_KEYWORD in str(mov) or MOVIE_KEYWORD in text_blob
        is_imax = any(k in str(screen).upper() or k in text_blob.upper() for k in IMAX_KEYWORDS)

        if is_movie and is_imax and start:
            try:
                seat_n = int(seats) if seats is not None else -1
            except (TypeError, ValueError):
                seat_n = -1

            key = f"{date_str}|{start}|{end}|{mov}|{screen}"
            results[key] = {
                "date": date_str,
                "screen": screen or "IMAX관",
                "movie": mov or "오디세이(IMAX LASER 2D)",
                "start": str(start).zfill(4) if str(start).isdigit() else str(start),
                "end": str(end).zfill(4) if str(end).isdigit() else str(end),
                "seats": seat_n,
            }

        for v in obj.values():
            walk_find_sessions(v, date_str, results)

    elif isinstance(obj, list):
        for item in obj:
            walk_find_sessions(item, date_str, results)


def format_msg(s):
    return (
        f"예매 오픈 알림 : 날짜: {s['date']}, 상영관: {s['screen']}, "
        f"영화: {s['movie']}, 시간: {s['start']}~{s['end']}, 잔여좌석: {s['seats']}"
    )


def main():
    print(f"[{datetime.now(KST)}] CGV 광교 체크 시작")
    state = load_state()
    prev = state.get("sessions", {})
    current = {}

    for date_str in get_dates():
        data = fetch_schedule(date_str)
        if data is None:
            continue
        walk_find_sessions(data, date_str, current)
        print(f"{date_str}: 회차 {len([k for k in current if k.startswith(date_str)])}건")

    # 새로 생긴 회차 / 잔여석 늘어난 회차
    new_msgs = []
    for key, s in current.items():
        if s["seats"] >= 0 and s["seats"] < MIN_SEATS_TO_NOTIFY:
            continue
        old = prev.get(key)
        if old is None:
            # 새 회차
            new_msgs.append(format_msg(s))
        elif old.get("seats", -1) == 0 and s["seats"] > 0:
            # 매진 → 잔여 생김 (취소표)
            new_msgs.append("취소표 " + format_msg(s))
        elif old.get("seats", -1) >= 0 and s["seats"] > old.get("seats", -1):
            # 잔여석 증가
            new_msgs.append("잔여증가 " + format_msg(s))

    if not prev:
        # 첫 실행: 기준만 저장, 알림은 요약만
        send_discord(
            f"**CGV 광교 IMAX 알리미 시작**\n"
            f"감시: 광교 IMAX / 오디세이\n"
            f"현재 감지 회차: {len(current)}건\n"
            f"이후 새 회차·잔여석 변동 시 알림합니다."
        )
        print(f"첫 실행 - 기준 {len(current)}건 저장")
    elif new_msgs:
        # 원하신 형식 그대로 (여러 건이면 여러 줄)
        body = "\n".join(new_msgs[:20])  # 한 번에 너무 많으면 20개까지
        if len(new_msgs) > 20:
            body += f"\n... 외 {len(new_msgs)-20}건"
        send_discord(body)
        print(f"알림 {len(new_msgs)}건 전송")
    else:
        print("변화 없음")

    state["sessions"] = current
    state["last_check"] = datetime.now(KST).isoformat()
    save_state(state)
    print("체크 완료")


if __name__ == "__main__":
    main()
