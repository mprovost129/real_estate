import hashlib
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from django.core.files.base import ContentFile
from django.utils import timezone

from integrations.models import IntegrationConnection, ListingSyncState
from integrations.services.listings import ListingRecord, get_listing_provider
from properties.models import Property, PropertyPhoto


STATUS_MAP = {
    "active": Property.Status.ACTIVE,
    "pending": Property.Status.PENDING,
    "under_contract": Property.Status.UNDER_CONTRACT,
    "under contract": Property.Status.UNDER_CONTRACT,
    "sold": Property.Status.SOLD,
    "coming_soon": Property.Status.COMING_SOON,
    "coming soon": Property.Status.COMING_SOON,
    "withdrawn": Property.Status.WITHDRAWN,
    "expired": Property.Status.EXPIRED,
    "cancelled": Property.Status.CANCELLED,
    "canceled": Property.Status.CANCELLED,
    "off_market": Property.Status.OFF_MARKET,
    "off market": Property.Status.OFF_MARKET,
}


def _payload_checksum(listing: ListingRecord):
    payload = json.dumps(
        {
            "listing_id": listing.listing_id,
            "mls_number": listing.mls_number,
            "address": listing.address,
            "city": listing.city,
            "state": listing.state,
            "postal_code": listing.postal_code,
            "status": listing.status,
            "price": listing.price,
            "photo_urls": listing.photo_urls or [],
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _download_photo(url: str):
    req = Request(url, method="GET")
    try:
        with urlopen(req, timeout=20) as resp:
            content_type = resp.headers.get("Content-Type", "")
            data = resp.read()
            return data, content_type
    except (HTTPError, URLError):
        return None, ""


def _file_ext(url: str, content_type: str):
    path = urlparse(url).path.lower()
    for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
        if path.endswith(ext):
            return ext
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    if "gif" in content_type:
        return ".gif"
    return ".jpg"


def _apply_listing_to_property(prop: Property, listing: ListingRecord, overwrite: bool = False):
    changed = False

    if listing.address and (overwrite or not prop.address):
        prop.address = listing.address
        changed = True
    if listing.city and (overwrite or not prop.city):
        prop.city = listing.city
        changed = True
    if listing.state and (overwrite or not prop.state):
        prop.state = listing.state
        changed = True
    if listing.postal_code and (overwrite or not prop.zip_code):
        prop.zip_code = listing.postal_code
        changed = True
    if listing.price is not None and (overwrite or prop.list_price in [None, 0]):
        prop.list_price = listing.price
        changed = True
    if listing.status:
        mapped = STATUS_MAP.get(listing.status.lower())
        if mapped and (overwrite or prop.status == Property.Status.OFF_MARKET):
            prop.status = mapped
            changed = True
    if listing.mls_number and (overwrite or not prop.mls_number):
        prop.mls_number = listing.mls_number
        changed = True

    if changed:
        prop.save()
    return changed


def _import_listing_photos(prop: Property, listing: ListingRecord, limit: int = 5):
    urls = (listing.photo_urls or [])[: max(0, limit)]
    if not urls:
        return {"imported": 0, "failed": 0}

    imported = 0
    failed = 0
    has_primary = prop.photos.filter(is_primary=True).exists()
    next_order = prop.photos.count()

    existing_captions = set(
        prop.photos.values_list("caption", flat=True)
    )

    for idx, url in enumerate(urls):
        marker = f"Imported URL: {url}"[:200]
        if marker in existing_captions:
            continue

        data, content_type = _download_photo(url)
        if not data:
            failed += 1
            continue

        digest = hashlib.md5(url.encode("utf-8")).hexdigest()  # nosec - deterministic filename hash
        ext = _file_ext(url, content_type)
        filename = f"listing_{prop.pk}_{digest}{ext}"

        photo = PropertyPhoto(
            property=prop,
            caption=marker,
            order=next_order + idx,
            is_primary=(not has_primary and imported == 0),
        )
        photo.image.save(filename, ContentFile(data), save=True)
        imported += 1

    return {"imported": imported, "failed": failed}


def sync_listing_for_property(
    connection: IntegrationConnection,
    prop: Property,
    overwrite: bool = False,
    import_photos: bool = False,
    photo_limit: int = 5,
):
    if not prop.mls_number:
        return {"skipped": "property_missing_mls"}

    provider = get_listing_provider(connection)
    listing = provider.fetch_by_mls(prop.mls_number)
    if not listing:
        state, _ = ListingSyncState.objects.for_org(connection.organization).get_or_create(
            connection=connection,
            remote_listing_id=prop.mls_number,
            defaults={
                "organization": connection.organization,
                "property": prop,
                "source_mls_number": prop.mls_number,
            },
        )
        state.status = ListingSyncState.Status.ERROR
        state.last_error = "No listing data returned from provider."
        state.last_synced_at = timezone.now()
        state.save(update_fields=["status", "last_error", "last_synced_at", "updated_at"])
        return {"error": state.last_error}

    checksum = _payload_checksum(listing)
    remote_listing_id = listing.listing_id or listing.mls_number or prop.mls_number
    state, _ = ListingSyncState.objects.for_org(connection.organization).get_or_create(
        connection=connection,
        remote_listing_id=remote_listing_id,
        defaults={
            "organization": connection.organization,
            "property": prop,
            "source_mls_number": listing.mls_number or prop.mls_number,
        },
    )
    state.property = prop
    state.source_mls_number = listing.mls_number or prop.mls_number
    state.payload_checksum = checksum
    state.status = ListingSyncState.Status.SYNCED
    state.last_error = ""
    state.last_synced_at = timezone.now()
    state.save(
        update_fields=[
            "property",
            "source_mls_number",
            "payload_checksum",
            "status",
            "last_error",
            "last_synced_at",
            "updated_at",
        ]
    )

    prop_changed = _apply_listing_to_property(prop, listing, overwrite=overwrite)
    photos_result = {"imported": 0, "failed": 0}
    if import_photos:
        photos_result = _import_listing_photos(prop, listing, limit=photo_limit)

    return {
        "status": "synced",
        "property_changed": prop_changed,
        "photos_imported": photos_result["imported"],
        "photos_failed": photos_result["failed"],
        "remote_listing_id": remote_listing_id,
    }
