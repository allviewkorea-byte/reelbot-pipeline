"""쇼핑 검색 공식 API — 쿠팡 파트너스(상품 검색·딥링크) + 네이버 쇼핑 검색 (A2-2). 크롤링 없음.

- 쿠팡 파트너스: HMAC-SHA256(CEA) 서명. message = signed-date(yyMMddTHHmmssZ, GMT) + METHOD + path + query.
  Authorization: "CEA algorithm=HmacSHA256, access-key=…, signed-date=…, signature=…".
  상품 검색 GET /v2/providers/affiliate_open_api/apis/openapi/v1/products/search?keyword=&limit=(≤10)
  → data.productData[{productId, productName, productPrice, productImage, productUrl, categoryName, isRocket}]
  (productUrl 은 이미 제휴 추적 링크). 딥링크 POST …/v1/deeplink {"coupangUrls": [...]}.
  검색 호출 한도: 쿠팡 공식 API 가이드 "1분당 최대 50번"(대표 확인 2026-10-27) → 여유를 두고
  COUPANG_SEARCH_PER_MIN(40)으로 막는다. (예전엔 비공식 "시간당 10회"로 너무 좁게 막았음)
- 네이버 쇼핑: GET https://openapi.naver.com/v1/search/shop.json?query=&display=&sort=sim
  헤더 X-Naver-Client-Id / X-Naver-Client-Secret. items[{title(<b>태그), link, image, lprice, mallName,
  productId, brand, category1~4}]. 하루 25,000회.
키가 없으면 그 통로만 꺼진다(is_available False) — 화면엔 "연결 필요".
"""

from __future__ import annotations

import hashlib
import hmac
import html
import os
import re
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx

COUPANG_HOST = "https://api-gateway.coupang.com"
COUPANG_SEARCH = "/v2/providers/affiliate_open_api/apis/openapi/v1/products/search"
COUPANG_DEEPLINK = "/v2/providers/affiliate_open_api/apis/openapi/v1/deeplink"
COUPANG_SEARCH_PER_MIN = 40      # 공식 50/분 — 여유 10
COUPANG_SEARCH_WINDOW_SEC = 60
RETRY_SLEEP_SEC = 3              # 일시 오류 재시도 전 대기
SEARCH_CACHE_SEC = 3600   # 같은 검색어 결과 1시간 메모리 캐시(저장 아님) — 한도 아끼기
_SEARCH_CACHE: dict[tuple[str, int], tuple[float, list[dict]]] = {}
_CALLS: list[float] = []  # 분당 상한(프로세스 공용 — 픽마다 클라이언트를 새로 만들어도 같이 센다)
_CALLS_LOCK = threading.Lock()
NAVER_SHOP = "https://openapi.naver.com/v1/search/shop.json"


class ShoppingError(RuntimeError):
    pass


class QuotaExceeded(ShoppingError):
    """이 통로의 호출 한도에 걸림(이번 실행에선 건너뜀)."""


def coupang_sign(method: str, path: str, query: str, secret: str, now: datetime | None = None) -> tuple[str, str]:
    """(signed_date, signature). query 는 '?' 없이 url-encoded 문자열."""
    signed = (now or datetime.now(timezone.utc)).strftime("%y%m%dT%H%M%SZ")
    msg = f"{signed}{method}{path}{query}"
    return signed, hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()


def _clean(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


class CoupangClient:
    def __init__(self, access: str | None = None, secret: str | None = None, http=None):
        self.access = access if access is not None else (os.getenv("COUPANG_PARTNERS_ACCESS_KEY") or "").strip()
        self.secret = secret if secret is not None else (os.getenv("COUPANG_PARTNERS_SECRET_KEY") or "").strip()
        self.http = http  # 테스트 주입: (method, url, headers, json) -> dict

    def is_available(self) -> bool:
        return bool(self.access and self.secret)

    def _auth(self, method: str, path: str, query: str) -> str:
        signed, sig = coupang_sign(method, path, query, self.secret)
        return f"CEA algorithm=HmacSHA256, access-key={self.access}, signed-date={signed}, signature={sig}"

    def _request(self, method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict:
        query = urlencode(params or {})
        url = f"{COUPANG_HOST}{path}{'?' + query if query else ''}"
        headers = {"Authorization": self._auth(method, path, query), "Content-Type": "application/json;charset=UTF-8"}
        if self.http:
            return self.http(method, url, headers, body)
        with httpx.Client(timeout=20.0) as c:
            r = c.request(method, url, headers=headers, json=body)
        if r.status_code in (403, 429):
            raise QuotaExceeded(f"쿠팡 호출 한도/권한: HTTP {r.status_code} {r.text[:120]}")
        r.raise_for_status()
        return r.json()

    def search(self, keyword: str, limit: int = 10) -> list[dict]:
        if not self.is_available():
            raise ShoppingError("쿠팡 파트너스 키 없음")
        limit = max(1, min(int(limit), 10))
        key = (keyword.strip(), limit)
        with _CALLS_LOCK:
            now = time.time()
            hit = _SEARCH_CACHE.get(key)
            if hit and now - hit[0] < SEARCH_CACHE_SEC:
                self.cached = True
                return [dict(x) for x in hit[1]]
            # 분당 상한(이 프로세스 기준 — 하루 합계는 ig_api_usage 에 따로 기록)
            _CALLS[:] = [t for t in _CALLS if now - t < COUPANG_SEARCH_WINDOW_SEC]
            if len(_CALLS) >= COUPANG_SEARCH_PER_MIN:
                raise QuotaExceeded("쿠팡 검색 분당 상한")
            _CALLS.append(now)
        self.cached = False
        try:
            data = self._request("GET", COUPANG_SEARCH, {"keyword": keyword, "limit": limit})
        except QuotaExceeded:
            raise
        except Exception:  # noqa: BLE001 - 일시 오류(타임아웃·5xx)는 잠깐 뒤 1회 재시도
            time.sleep(RETRY_SLEEP_SEC)
            data = self._request("GET", COUPANG_SEARCH, {"keyword": keyword, "limit": limit})
        items = ((data.get("data") or {}).get("productData")) or []
        out = [{
            "channel": "coupang", "product_id": str(it.get("productId")), "name": _clean(it.get("productName", "")),
            "price": int(it.get("productPrice") or 0), "image_url": it.get("productImage"), "link": it.get("productUrl"),
            "mall": "쿠팡" + (" 로켓" if it.get("isRocket") else ""), "category": it.get("categoryName") or "",
            "raw": {k: it.get(k) for k in ("productId", "categoryName", "isRocket", "isFreeShipping", "rank")},
        } for it in items if it.get("productId") and it.get("productImage")]
        with _CALLS_LOCK:
            _SEARCH_CACHE[key] = (time.time(), out)
        return [dict(x) for x in out]

    def deeplinks(self, urls: list[str]) -> dict[str, str]:
        """원래 URL → 제휴 단축 링크. 이미 link.coupang.com 이면 그대로."""
        need = [u for u in urls if u and "link.coupang.com" not in u]
        out = {u: u for u in urls if u and "link.coupang.com" in u}
        if need and self.is_available():
            data = self._request("POST", COUPANG_DEEPLINK, body={"coupangUrls": need})
            for d in data.get("data") or []:
                out[d.get("originalUrl")] = d.get("shortenUrl") or d.get("landingUrl")
        return out


class NaverClient:
    def __init__(self, cid: str | None = None, secret: str | None = None, http=None):
        self.cid = cid if cid is not None else (os.getenv("NAVER_CLIENT_ID") or "").strip()
        self.secret = secret if secret is not None else (os.getenv("NAVER_CLIENT_SECRET") or "").strip()
        self.http = http  # 테스트 주입: (url, params, headers) -> dict

    def is_available(self) -> bool:
        return bool(self.cid and self.secret)

    def search(self, query: str, display: int = 20) -> list[dict]:
        if not self.is_available():
            raise ShoppingError("네이버 검색 키 없음")
        params = {"query": query, "display": max(1, min(int(display), 100)), "sort": "sim"}
        headers = {"X-Naver-Client-Id": self.cid, "X-Naver-Client-Secret": self.secret}
        if self.http:
            data = self.http(NAVER_SHOP, params, headers)
        else:
            with httpx.Client(timeout=20.0) as c:
                r = c.get(NAVER_SHOP, params=params, headers=headers)
            if r.status_code == 429:
                raise QuotaExceeded("네이버 호출 한도")
            r.raise_for_status()
            data = r.json()
        return [{
            "channel": "naver", "product_id": str(it.get("productId")), "name": _clean(it.get("title", "")),
            "price": int(it.get("lprice") or 0), "image_url": it.get("image"), "link": it.get("link"),
            "mall": it.get("mallName") or "네이버", "brand": it.get("brand") or "",
            "category": " > ".join(x for x in (it.get(f"category{i}") for i in range(1, 5)) if x),
            "raw": {k: it.get(k) for k in ("productId", "productType", "brand", "maker", "category1", "category2", "category3")},
        } for it in data.get("items") or [] if it.get("productId") and it.get("image")]
