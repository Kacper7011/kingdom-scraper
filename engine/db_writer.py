"""MongoDB writer: upsert offers and contacts, pagination reads, index setup."""

import logging

import pymongo
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from shared.constants import (
    COLLECTION_CONTACTS,
    COLLECTION_OFFERS,
    MONGO_DB,
    MONGO_URI,
)
from shared.models import Contact, Offer

logger = logging.getLogger(__name__)


class DBError(Exception):
    """Raised when a MongoDB operation fails."""


def _get_client() -> MongoClient:
    try:
        client: MongoClient = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        return client
    except PyMongoError as exc:
        raise DBError(f"Cannot connect to MongoDB at {MONGO_URI}") from exc


def _offers_col(client: MongoClient) -> Collection:
    return client[MONGO_DB][COLLECTION_OFFERS]


def _contacts_col(client: MongoClient) -> Collection:
    return client[MONGO_DB][COLLECTION_CONTACTS]


def ensure_indexes(client: MongoClient) -> None:
    """Create all required indexes. Safe to call multiple times (idempotent)."""
    try:
        offers = _offers_col(client)
        offers.create_index([("offer_id", pymongo.ASCENDING)], unique=True)
        offers.create_index([("category", pymongo.ASCENDING)])
        offers.create_index([("transaction", pymongo.ASCENDING)])
        offers.create_index([("scraped_at", pymongo.DESCENDING)])

        contacts = _contacts_col(client)
        contacts.create_index([("email", pymongo.ASCENDING)], unique=True)

        logger.info("MongoDB indexes ensured")
    except PyMongoError as exc:
        raise DBError("ensure_indexes failed") from exc


def save_offer(client: MongoClient, offer: Offer) -> None:
    """Upsert an offer by offer_id. Updates all fields on conflict."""
    try:
        doc = offer.to_dict()
        _offers_col(client).update_one(
            {"offer_id": offer.offer_id},
            {"$set": doc},
            upsert=True,
        )
        logger.debug("Saved offer %s", offer.offer_id)
    except PyMongoError as exc:
        raise DBError(f"save_offer failed for {offer.offer_id}") from exc


def save_contact(client: MongoClient, contact: Contact) -> None:
    """Upsert a contact by email. Updates all fields on conflict."""
    try:
        doc = contact.to_dict()
        _contacts_col(client).update_one(
            {"email": contact.email},
            {"$set": doc},
            upsert=True,
        )
        logger.debug("Saved contact %s", contact.email)
    except PyMongoError as exc:
        raise DBError(f"save_contact failed for {contact.email}") from exc


def get_all_offers(client: MongoClient, limit: int = 20, skip: int = 0) -> list[dict]:
    """Paginated read of offers, newest first."""
    try:
        cursor = (
            _offers_col(client)
            .find({}, {"_id": 0})
            .sort("scraped_at", pymongo.DESCENDING)
            .skip(skip)
            .limit(limit)
        )
        return list(cursor)
    except PyMongoError as exc:
        raise DBError("get_all_offers failed") from exc


def get_stats(client: MongoClient) -> dict:
    """Return document counts per collection."""
    try:
        return {
            "offers": _offers_col(client).count_documents({}),
            "contacts": _contacts_col(client).count_documents({}),
        }
    except PyMongoError as exc:
        raise DBError("get_stats failed") from exc
