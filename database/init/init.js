// Initialize MongoDB collections and indexes for kingdom_scraper
db = db.getSiblingDB("kingdom_scraper");

db.createCollection("offers");
db.createCollection("contacts");

db.offers.createIndex({ offer_id: 1 }, { unique: true });
db.offers.createIndex({ category: 1 });
db.offers.createIndex({ transaction: 1 });
db.offers.createIndex({ scraped_at: -1 });

db.contacts.createIndex({ email: 1 }, { unique: true });
