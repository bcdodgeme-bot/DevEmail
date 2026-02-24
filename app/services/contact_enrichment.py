"""
Contact Auto-Enrichment Service

Enriches contacts with publicly available data based on their email address:
  1. Gravatar — avatar URL from email hash
  2. Domain scraping — company name, description, social links from website meta tags
  3. DNS MX lookup — email provider identification

No paid API keys required. All data from public sources.
"""

import hashlib
import logging
import re
from typing import Optional
from urllib.parse import urljoin

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact

logger = logging.getLogger(__name__)

# Free email providers — skip domain enrichment for these
FREE_PROVIDERS = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk",
    "hotmail.com", "outlook.com", "live.com", "msn.com",
    "aol.com", "icloud.com", "me.com", "mac.com",
    "protonmail.com", "proton.me", "zoho.com", "yandex.com",
    "mail.com", "gmx.com", "tutanota.com", "fastmail.com",
}

# Social link patterns to extract from HTML
SOCIAL_PATTERNS = {
    "twitter": re.compile(r'https?://(?:www\.)?(?:twitter|x)\.com/([a-zA-Z0-9_]+)', re.I),
    "linkedin": re.compile(r'https?://(?:www\.)?linkedin\.com/(?:company|in)/([a-zA-Z0-9_-]+)', re.I),
    "github": re.compile(r'https?://(?:www\.)?github\.com/([a-zA-Z0-9_-]+)', re.I),
    "facebook": re.compile(r'https?://(?:www\.)?facebook\.com/([a-zA-Z0-9._-]+)', re.I),
}


class ContactEnrichmentService:
    """Enrich contacts with public data from their email domain."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._http = None

    async def _get_http(self):
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=10.0,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; DevEmail/1.0; contact enrichment)",
                },
            )
        return self._http

    async def close(self):
        if self._http:
            await self._http.aclose()
            self._http = None

    async def enrich_contact(self, contact: Contact) -> dict:
        """
        Enrich a single contact. Returns dict of enriched fields.
        Updates the contact in DB.
        """
        if not contact.email:
            return {}

        email = contact.email.lower().strip()
        domain = email.split("@")[-1] if "@" in email else None
        enriched = {}

        # 1. Gravatar
        avatar_url = self._gravatar_url(email)
        if avatar_url:
            has_gravatar = await self._check_gravatar(avatar_url)
            if has_gravatar:
                enriched["avatar_url"] = avatar_url

        # 2. Domain enrichment (skip free providers)
        if domain and domain not in FREE_PROVIDERS:
            domain_data = await self._scrape_domain(domain)
            if domain_data:
                enriched.update(domain_data)

        # 3. Apply to contact
        if enriched:
            if "company" in enriched and not contact.company:
                contact.company = enriched["company"]
            if "avatar_url" in enriched and not contact.avatar_url:
                contact.avatar_url = enriched["avatar_url"]
            if "company_domain" in enriched:
                contact.company_domain = enriched["company_domain"]
            if "company_description" in enriched and not contact.notes:
                contact.notes = enriched["company_description"]

            # Store social links as JSON in enrichment_data
            socials = {k: v for k, v in enriched.items() if k in SOCIAL_PATTERNS}
            if socials:
                import json
                existing = {}
                if contact.enrichment_data:
                    try:
                        existing = json.loads(contact.enrichment_data)
                    except Exception:
                        pass
                existing["social_links"] = socials
                contact.enrichment_data = json.dumps(existing)

            contact.enriched = True
            await self.db.commit()

        logger.info(f"Enriched contact {email}: {list(enriched.keys())}")
        return enriched

    async def enrich_batch(self, user_id, limit: int = 50) -> dict:
        """Enrich unenriched contacts for a user."""
        result = await self.db.execute(
            select(Contact)
            .where(
                Contact.user_id == user_id,
                Contact.enriched == False,
                Contact.email.isnot(None),
            )
            .limit(limit)
        )
        contacts = result.scalars().all()

        enriched_count = 0
        errors = 0

        for contact in contacts:
            try:
                data = await self.enrich_contact(contact)
                if data:
                    enriched_count += 1
            except Exception as e:
                logger.error(f"Enrichment failed for {contact.email}: {e}")
                # Mark as enriched anyway to avoid retrying bad addresses
                contact.enriched = True
                errors += 1

        await self.db.commit()
        return {
            "processed": len(contacts),
            "enriched": enriched_count,
            "errors": errors,
        }

    # --- Gravatar ---

    def _gravatar_url(self, email: str) -> str:
        """Generate Gravatar URL from email."""
        email_hash = hashlib.md5(email.encode("utf-8")).hexdigest()
        return f"https://www.gravatar.com/avatar/{email_hash}?s=200&d=404"

    async def _check_gravatar(self, url: str) -> bool:
        """Check if a Gravatar exists (returns 404 for default)."""
        try:
            http = await self._get_http()
            resp = await http.head(url)
            return resp.status_code == 200
        except Exception:
            return False

    # --- Domain Scraping ---

    async def _scrape_domain(self, domain: str) -> dict:
        """Scrape a domain's homepage for company info."""
        data = {}
        url = f"https://{domain}"

        try:
            http = await self._get_http()
            resp = await http.get(url)
            if resp.status_code != 200:
                return data

            html = resp.text[:50000]  # Cap at 50KB to avoid huge pages
            data["company_domain"] = domain

            # Extract <title>
            title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
            if title_match:
                title = title_match.group(1).strip()
                # Clean common suffixes
                for sep in [" | ", " - ", " — ", " :: ", " · "]:
                    if sep in title:
                        title = title.split(sep)[0].strip()
                if title and len(title) < 100:
                    data["company"] = title

            # Extract meta description
            desc_match = re.search(
                r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
                html, re.I
            )
            if not desc_match:
                desc_match = re.search(
                    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
                    html, re.I
                )
            if desc_match:
                desc = desc_match.group(1).strip()
                if len(desc) < 500:
                    data["company_description"] = desc

            # Extract social links
            for platform, pattern in SOCIAL_PATTERNS.items():
                match = pattern.search(html)
                if match:
                    handle = match.group(1)
                    if handle and handle.lower() not in {"share", "intent", "sharer"}:
                        data[platform] = handle

            # Extract OG image as company logo
            og_match = re.search(
                r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                html, re.I
            )
            if og_match:
                og_img = og_match.group(1).strip()
                if og_img.startswith("/"):
                    og_img = urljoin(url, og_img)
                if og_img.startswith("http"):
                    data["company_logo"] = og_img

        except Exception as e:
            logger.debug(f"Failed to scrape {domain}: {e}")

        return data
