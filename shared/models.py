"""Dataclass models shared between engine and interface."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Address:
    """Physical address of a real-estate offer."""

    city: str
    street: str | None = None
    region: str | None = None

    def to_dict(self) -> dict:
        return {"city": self.city, "street": self.street, "region": self.region}

    @staticmethod
    def from_dict(data: dict) -> "Address":
        return Address(
            city=data.get("city", ""),
            street=data.get("street"),
            region=data.get("region"),
        )


@dataclass
class Offer:
    """Single real-estate listing scraped from kingdomelblag.pl."""

    offer_id: str
    title: str
    category: str
    transaction: str
    url: str
    address: Address
    price: float | None = None
    area_m2: float | None = None
    rooms: int | None = None
    scraped_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "offer_id": self.offer_id,
            "title": self.title,
            "category": self.category,
            "transaction": self.transaction,
            "url": self.url,
            "address": self.address.to_dict(),
            "price": self.price,
            "area_m2": self.area_m2,
            "rooms": self.rooms,
            "scraped_at": self.scraped_at,
        }

    @staticmethod
    def from_dict(data: dict) -> "Offer":
        return Offer(
            offer_id=data["offer_id"],
            title=data["title"],
            category=data["category"],
            transaction=data["transaction"],
            url=data["url"],
            address=Address.from_dict(data.get("address", {})),
            price=data.get("price"),
            area_m2=data.get("area_m2"),
            rooms=data.get("rooms"),
            scraped_at=data.get("scraped_at", datetime.utcnow()),
        )


@dataclass
class Contact:
    """Contact details of a real-estate office."""

    name: str
    email: str
    phone: str
    address: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "address": self.address,
        }

    @staticmethod
    def from_dict(data: dict) -> "Contact":
        return Contact(
            name=data.get("name", ""),
            email=data.get("email", ""),
            phone=data.get("phone", ""),
            address=data.get("address", ""),
        )
