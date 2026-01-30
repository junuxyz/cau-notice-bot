"""
Notice fetching from CAU and Library APIs.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple
from urllib.parse import urlencode

import requests


def get_korea_datetime():
    """Get current datetime in Korea (KST)"""
    kst = timezone(timedelta(hours=9))
    return datetime.now(kst)

def is_notice_in_time_range(notice_datetime: datetime) -> bool:
    """
    Check if the notice is posted between yesterday 8:01 AM and today 8:00 AM
    """
    now = get_korea_datetime()
    yesterday = now - timedelta(days=1)

    # yesterday 8:00 AM ~ today 8:00 AM
    start_time = yesterday.replace(hour=8, minute=0, second=0, microsecond=0)
    end_time = now.replace(hour=8, minute=0, second=0, microsecond=0)

    return start_time <= notice_datetime <= end_time

def check_cau_notices(cau_website_url: str, cau_api_url: str) -> List[Dict[str, str]]:
    params = {
        'SITE_NO': '2',
        'BOARD_SEQ': '4'
    }

    res = requests.get(cau_api_url, params=params)
    res.raise_for_status()

    data = res.json()
    notices = []

    # Handle malformed data
    data_section = data.get('data') if data else None
    notice_list = data_section.get('list', []) if data_section else []

    for notice in notice_list:
        try:
            notice_datetime = datetime.strptime(notice['WRITE_DT'].split('.')[0], '%Y-%m-%d %H:%M:%S')
            notice_datetime = notice_datetime.replace(tzinfo=timezone(timedelta(hours=9)))

            if is_notice_in_time_range(notice_datetime):
                url_params = {
                    'MENU_ID': '100',
                    'CONTENTS_NO': '1',
                    'SITE_NO': '2',
                    'BOARD_SEQ': '4',
                    'BBS_SEQ': notice.get('BBS_SEQ', '')
                }
                notice_url = f"{cau_website_url}?{urlencode(url_params)}"
                display_date = notice_datetime.strftime('%Y-%m-%d %H:%M')
                notices.append({
                    'title': notice.get('SUBJECT', ''),
                    'post_date': display_date,
                    'category': 'CAU 공지',
                    'url': notice_url
                })
        except Exception as e:
            logging.error(f"개별 공지사항 처리 중 오류 발생: {str(e)}")
            continue

    notices.sort(key=lambda x: x['post_date'], reverse=False)
    return notices

def check_library_notices(library_website_url: str, library_api_url: str) -> List[Dict[str, str]]:
    try:
        res = requests.get(library_api_url, timeout=10)
        res.raise_for_status()
        data = res.json()

        notices = []
        if data.get('success') and data.get('data', {}).get('list'):
            for notice in data['data']['list']:
                try:
                    notice_datetime = datetime.strptime(notice['dateCreated'], '%Y-%m-%d %H:%M:%S')
                    notice_datetime = notice_datetime.replace(tzinfo=timezone(timedelta(hours=9)))  # KST 적용

                    if is_notice_in_time_range(notice_datetime):
                        display_date = notice_datetime.strftime('%Y-%m-%d %H:%M')
                        notices.append({
                            'title': notice.get('title', ''),
                            'post_date': display_date,
                            'category': '학술정보원 공지',
                            'url': f"{library_website_url}/{notice['id']}"
                        })

                except Exception as e:
                    logging.error(f"도서관 개별 공지사항 처리 중 오류 발생: {str(e)}")
                    continue

        notices.sort(key=lambda x: x['post_date'], reverse=False)
        return notices

    except Exception as e:
        logging.error(f"도서관 공지사항 크롤링 중 오류 발생: {str(e)}")
        return []


def check_notices(config) -> Tuple[List[Dict], List[Dict]]:
    """Checks notices from CAU and CAU Library and returns them"""
    cau_notices = check_cau_notices(
        config.cau_website_url,
        config.cau_api_url
    )

    library_notices = check_library_notices(
        config.library_website_url,
        config.library_api_url
    )
    return cau_notices, library_notices
