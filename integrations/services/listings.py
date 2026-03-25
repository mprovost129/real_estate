from dataclasses import dataclass
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
    def fetch_listing(self, listing_id: str) -> ListingRecord | None:
        raise NotImplementedError("MLS/IDX adapter is not wired yet.")

    def fetch_by_mls(self, mls_number: str) -> ListingRecord | None:
        raise NotImplementedError("MLS/IDX adapter is not wired yet.")


class ZillowProvider(BaseListingProvider):
    """
    Groundwork adapter that supports deterministic photo URL generation
    from MLS number while full Zillow API auth is pending.
    """

    def fetch_listing(self, listing_id: str) -> ListingRecord | None:
        return None

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
