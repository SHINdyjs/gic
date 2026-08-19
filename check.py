#!/usr/bin/env python3
"""
CGV 광교 IMAX 예매 오픈 알리미 (GitHub Actions + Discord Webhook)
- 예매 스케줄이 새로 열리면 Discord로 알림
"""

import os
import json
import hashlib
import requests
from datetime import datetime, timezone, timedelta

# ============== 설정 ==============
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
STATE_FILE = "state.json"

# CGV 광교 관련 (필요시 수정)
# 웹에서 theaterCode=0264 로 보이는 경우가 많음
THEATER_NAME = "CGV 광교"
MOVIE_KEYWORD = "오디세이"      # 이 단어가 포함된 영화만
SCREEN_KEYWORD = "IMAX"        # IMAX 상영관만

# 알림에 포함할 날짜 범위 (오늘부터 N일)
DAYS_AHEAD = 14

KST = timezone(timedelta(hours=9))


def send_discord(content: str):
    if not DISCORD_WEBHOOK:
        print("DISCORD_WEBHOOK 환경변수가 없습니다.")
        return
    payload = {
        "content": content,
        "username": "CGV 광교 알리미",
    }
    try:
        r = requests.post(DISCORD_WEBHOOK, json=payload, timeout=15)
        r.raise_for_status()
        print("Discord 알림 전송 성공")
    except Exception as e:
        print(f"Discord 전송 실패: {e}")


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"schedules": {}, "last_check": None}


def save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_schedule_hash(items: list) -> str:
    raw = json.dumps(items, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def fetch_cgv_schedule_simple():
    """
    간단한 방식: CGV 공개 페이지/API를 조회 시도.
    실제로는 브라우저 Network에서 잡은 최신 API를 쓰는 게 안정적입니다.
    
    아래는 '구조 예시'입니다.
    작동이 안 되면 아래 '수동 캡처 방법'을 참고하세요.
    """
    # --- 방법 A: 네이버 플레이스 등 공개 정보 (보조) ---
    # 실제 예매 오픈 감지는 CGV 예매 API가 더 정확합니다.
    
    results = []
    today = datetime.now(KST).date()
    
    # 예시 데이터 구조 (실제 API 연동 시 이 부분을 교체)
    # results.append({
    #     "date": "2026-08-25",
    #     "time": "14:00",
    #     "movie": "오디세이",
    #     "screen": "IMAX관",
    #     "theater": "CGV 광교",
    # })
    
    return results


def fetch_via_legacy_api():
    """
    0w0i0n0g0 레포에서 쓰는 구형 API 스타일.
    TheaterCd 등 암호화된 값이 필요합니다.
    
    브라우저에서 직접 캡처해서 아래 JSON을 채우세요.
    """
    url = "http://ticket.cgv.co.kr/CGV2011/RIA/CJ000.aspx/CJ_TICKET_SCHEDULE_TOTAL_PLAY_YMD"
    
    # ★★★ 여기를 본인 브라우저에서 캡처한 값으로 교체 ★★★
    json_data = {
        "REQSITE": "x02PG4EcdFrHKluSEQQh4A==",
        "TheaterCd": "여기에_광교_TheaterCd_붙여넣기",  # 필수
        "ISNormal": "ECFppiyFz/nvSGsg7VwPQw==",
        "MovieGroupCd": "nG6tVgEQPGU2GvOIdnwTjg==",   # 전체 영화
        "ScreenRatingCd": "kXwoR3tnLM/+Tu0BILP3Qg==", # IMAX
        "MovieTypeCd": "nG6tVgEQPGU2GvOIdnwTjg==",
        "Subtitle_CD": "nG6tVgEQPGU2GvOIdnwTjg==",
        "SOUNDX_YN": "nG6tVgEQPGU2GvOIdnwTjg==",
        "Third_Attr_CD": "nG6tVgEQPGU2GvOIdnwTjg==",
        "Language": "zqWM417GS6dxQ7CIf65+iA==",
    }
    
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/json",
        "Origin": "http://ticket.cgv.co.kr",
        "Referer": "http://ticket.cgv.co.kr/Reservation/Reservation.aspx",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
    }
    
    try:
        r = requests.post(url, json=json_data, headers=headers, timeout=20, verify=False)
        r.raise_for_status()
        data = r.json()
        xml = data.get("d", {}).get("DATA", "")
        # 여기서 XML 파싱해서 날짜/회차 추출
        # (간단화를 위해 raw hash 비교로도 가능)
        return xml
    except Exception as e:
        print(f"Legacy API 실패: {e}")
        return None


def main():
    print(f"[{datetime.now(KST)}] CGV 광교 체크 시작")
    
    state = load_state()
    previous = state.get("schedules", {})
    
    # 실제 스케줄 가져오기 (둘 중 하나 사용)
    # 1) 구형 API (TheaterCd 필요)
    current_raw = fetch_via_legacy_api()
    
    if current_raw is None:
        # API 실패 시 테스트용 알림 (처음 한 번만)
        if not state.get("last_check"):
            send_discord(
                "**CGV 광교 알리미 설정 필요**\n"
                "TheaterCd를 아직 넣지 않았거나 API가 막혔습니다.\n"
                "README의 'TheaterCd 캡처 방법'을 따라주세요."
            )
        state["last_check"] = datetime.now(KST).isoformat()
        save_state(state)
        return
    
    current_hash = hashlib.sha256(current_raw.encode()).hexdigest()
    prev_hash = previous.get("hash")
    
    if prev_hash and prev_hash != current_hash:
        # 변화 감지!
        msg = (
            f"**🎬 CGV 광교 IMAX 예매 변동 감지!**\n"
            f"시간: {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"영화: {MOVIE_KEYWORD} / 상영관: IMAX\n"
            f"→ [CGV 예매하러 가기](https://www.cgv.co.kr/)"
        )
        send_discord(msg)
        print("변화 감지 → 알림 전송")
    else:
        print("변화 없음")
    
    state["schedules"] = {"hash": current_hash, "raw_preview": current_raw[:500]}
    state["last_check"] = datetime.now(KST).isoformat()
    save_state(state)
    print("체크 완료")


if __name__ == "__main__":
    main()
