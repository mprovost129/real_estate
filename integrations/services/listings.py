from dataclasses import dataclass
import json
from urllib.parse import quote
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Iterable

from django.conf import settings

from integrations.models import IntegrationConnection


@dataclass
class ListingRecord:
    listing_id: str
    mls_number: str
    address: str
    city: str = ""
    state: str = ""
    postal_code: str = ""
    status: str = ""
    price: float | None = None
    photo_urls: list[str] | None = None
    mlg_can_view: bool | None = None
    mlg_can_use: list[str] | None = None


class BaseListingProvider:
    """Shared interface for MLS/Zillow style listing feeds."""

    def __init__(self, connection: IntegrationConnection):
        self.connection = connection

    def fetch_listing(self, listing_id: str) -> ListingRecord | None:
        raise NotImplementedError

    def fetch_by_mls(self, mls_number: str) -> ListingRecord | None:
        raise NotImplementedError

    def iter_photos(self, listing: ListingRecord) -> Iterable[str]:
        return listing.photo_urls or []


class MlsIdxProvider(BaseListingProvider):
    def _lookup_url(self, mls_number: str):
        config = self.connection.config or {}
        template = config.get("lookup_url_template") or getattr(
            settings,
            "MLS_IDX_LOOKUP_URL_TEMPLATE",
            "",
        )
        if template:
            return template.format(mls=mls_number)

        # MLS Grid OData fallback
        base = config.get("mls_grid_base_url", "https://api.mlsgrid.com/v2/Property").rstrip("?")
        origin = (config.get("originating_system_name") or "").strip()
        if not origin:
            return ""

        filter_parts = [
            f"OriginatingSystemName eq '{origin}'",
            f"(ListingId eq '{mls_number}' or ListingKey eq '{mls_number}')",
        ]
        if mls_number.isdigit():
            filter_parts[1] = (
                f"(ListingId eq '{mls_number}' or ListingKey eq '{mls_number}' "
                f"or ListingIdNumeric eq {mls_number} or ListingKeyNumeric eq {mls_number})"
            )
        filter_expr = " and ".join(filter_parts)
        expand = config.get("expand_resources", "Media")
        params = [
            ("$filter", filter_expr),
            ("$top", "1"),
        ]
        if expand:
            params.append(("$expand", expand))
        safe_chars = ",()'"
        query = "&".join(
            [
                f"{k}={quote(str(v), safe=safe_chars)}"
                for k, v in params
            ]
        ).replace(" ", "%20")
        return f"{base}?{query}"

    def _auth_headers(self):
        config = self.connection.config or {}
        token = config.get("api_token") or self.connection.access_token_encrypted
        key = config.get("api_key") or getattr(settings, "MLS_IDX_API_KEY", "")
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if key:
            headers["X-API-Key"] = key
        return headers

    def _fetch_json(self, url: str):
        headers = {"Accept-Encoding": "gzip"}
        headers.update(self._auth_headers())
        req = Request(url, headers=headers, method="GET")
        try:
            with urlopen(req, timeout=20) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body)
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise ValueError(f"MLS lookup failed ({exc.code}): {body}") from exc
        except URLError as exc:
            raise ValueError(f"MLS lookup failed: {exc}") from exc

    @staticmethod
    def _pick(data: dict, *keys, default=""):
        for key in keys:
            if key in data and data[key] not in [None, ""]:
                return data[key]
        return default

    def _normalize_record(self, raw: dict, fallback_mls: str):
        media = raw.get("Media") or raw.get("media") or []
        photos = raw.get("photo_urls") or raw.get("photos") or []
        if isinstance(media, list):
            for item in media:
                if not isinstance(item, dict):
                    continue
                media_url = (
                    item.get("MediaURL")
                    or item.get("media_url")
                    or item.get("Uri800")
                    or item.get("Uri640")
                    or item.get("url")
                )
                if media_url:
                    photos.append(str(media_url))
        if isinstance(photos, str):
            photos = [photos]
        photos = [str(p) for p in photos if p]

        can_use = raw.get("MlgCanUse")
        if isinstance(can_use, str):
            can_use = [can_use]
        if not isinstance(can_use, list):
            can_use = None

        can_view = raw.get("MlgCanView")
        if not isinstance(can_view, bool):
            can_view = None
        return ListingRecord(
            listing_id=str(
                self._pick(
                    raw,
                    "listing_id",
                    "id",
                    "ListingId",
                    "ListingKey",
                    "ListingIdNumeric",
                    "ListingKeyNumeric",
                    default=fallback_mls,
                )
            ),
            mls_number=str(self._pick(raw, "mls_number", "MLSNumber", "mls", "ListingId", default=fallback_mls)),
            address=str(self._pick(raw, "address", "street", "StreetAddress", "UnparsedAddress", default="")),
            city=str(self._pick(raw, "city", "City", default="")),
            state=str(self._pick(raw, "state", "StateOrProvince", "State", default="")),
            postal_code=str(self._pick(raw, "postal_code", "zip", "PostalCode", "ZipCode", default="")),
            status=str(self._pick(raw, "status", "Status", "StandardStatus", "MlsStatus", default="")).lower(),
            price=float(self._pick(raw, "price", "list_price", "ListPrice", "ClosePrice", default=0) or 0) or None,
            photo_urls=photos,
            mlg_can_view=can_view,
            mlg_can_use=[str(v).upper() for v in can_use] if can_use else None,
        )

    def fetch_listing(self, listing_id: str) -> ListingRecord | None:
        if not listing_id:
            return None
        return self.fetch_by_mls(listing_id)

    def fetch_by_mls(self, mls_number: str) -> ListingRecord | None:
        if not mls_number:
            return None

        url = self._lookup_url(mls_number)
        if not url:
            return ListingRecord(
                listing_id=mls_number,
                mls_number=mls_number,
                address="",
            )

        payload = self._fetch_json(url)
        raw = payload
        if isinstance(payload, dict) and isinstance(payload.get("value"), list):
            if not payload["value"]:
                return None
            raw = payload["value"][0]
        elif isinstance(payload, list):
            if not payload:
                return None
            raw = payload[0]
        if not isinstance(raw, dict):
            return None
        return self._normalize_record(raw, fallback_mls=mls_number)


class ZillowProvider(BaseListingProvider):
    """
    Groundwork adapter that supports deterministic photo URL generation
    from MLS number while full Zillow API auth is pending.
    """

    def fetch_listing(self, listing_id: str) -> ListingRecord | None:
        if not listing_id:
            return None
        return self.fetch_by_mls(listing_id)

    def fetch_by_mls(self, mls_number: str) -> ListingRecord | None:
        if not mls_number:
            return None
        photo_template = getattr(
            settings,
            "ZILLOW_MLS_PHOTO_URL_TEMPLATE",
            "https://media.mlspin.com/photo.aspx?mls={mls}&n={num}&w=1024&h=768",
        )
        photo_urls = [photo_template.format(mls=mls_number, num=n) for n in range(1, 6)]
        return ListingRecord(
            listing_id=mls_number,
            mls_number=mls_number,
            address="",
            photo_urls=photo_urls,
        )


LISTING_PROVIDER_MAP = {
    IntegrationConnection.Provider.MLS_GENERIC: MlsIdxProvider,
    IntegrationConnection.Provider.ZILLOW: ZillowProvider,
}


def get_listing_provider(connection: IntegrationConnection) -> BaseListingProvider:
    provider_cls = LISTING_PROVIDER_MAP.get(connection.provider, MlsIdxProvider)
    return provider_cls(connection)
