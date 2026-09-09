"""Public Food Lion catalog evidence, separate from store inventory snapshots.

The SEO sitemap lists products, not stock. Never promote that evidence to verified.
All derivations can run offline from immutable source observations.
"""

import json
import re
import time
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from .core import atomic_json, atomic_text, load_yaml, now, read_jsonl, stable_id, write_jsonl
from .foodlion import AccessBlocked, RefuseRedirects

BASE = "https://foodlion.com"
USER_AGENT = "PersonalRecipeResearch/1.0"


def classify_observation(observation, configured_store_id=None):
    """Stock at another store is likelihood evidence, never local verification."""
    public_product_id(observation["source_url"])
    if not observation.get("retrieved_at"):
        raise ValueError("Evidence needs an observation timestamp")
    same_store = (
        configured_store_id is not None
        and observation.get("store_id") == configured_store_id
        and observation.get("store_specificity") == "specific_store"
    )
    if same_store and observation.get("availability") is True:
        return "verified_available"
    if same_store and observation.get("availability") is False:
        return "unavailable"
    if observation.get("catalog_listed") is True or observation.get("availability") is True:
        return "likely_available"
    return "unknown"


class StructuredData(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.documents = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.active = dict(attrs).get("type") == "application/ld+json"

    def handle_endtag(self, tag):
        if tag == "script":
            self.active = False

    def handle_data(self, data):
        if self.active:
            self.documents.append(json.loads(data))


def public_product_id(url):
    """IDs are only taken from an actual first-party catalog URL."""
    parsed = urlparse(url)
    if parsed.hostname not in {"foodlion.com", "www.foodlion.com"}:
        raise ValueError("Product evidence must be first-party Food Lion")
    match = re.fullmatch(r"/groceries/product/[^/]+/(\d+)", parsed.path)
    if not match:
        raise ValueError("Not a public Food Lion product URL")
    return match.group(1)


def import_catalog(raw_dir, observed_at):
    """Import sitemap facts; structured names enrich only matching real IDs."""
    raw_dir = Path(raw_dir)
    names = {}
    if (raw_dir / "groceries.txt").exists():
        parser = StructuredData()
        parser.feed((raw_dir / "groceries.txt").read_text())
        for document in parser.documents:
            for item in document.get("itemListElement", []):
                # This official JSON-LD currently has localhost URLs. Only its
                # path/ID joins a separately verified public sitemap URL.
                names[urlparse(item.get("url", "")).path] = item.get("name")
    rows = {}
    for path in sorted(raw_dir.glob("products-*.xml")):
        for node in ET.parse(path).getroot():
            loc = node.find("{*}loc")
            if loc is None or not loc.text:
                continue
            url = loc.text
            product_id = public_product_id(url)
            rows[product_id] = {
                "id": stable_id("foodlion-public-catalog", product_id),
                "product_id": product_id,
                "product_name": names.get(urlparse(url).path),
                "source_url": url,
                "catalog_slug": urlparse(url).path.split("/")[-2],
                "source": "Food Lion public SEO catalog",
                "evidence_source_url": f"{BASE}/groceries/sitemaps/{path.name}",
                "raw_path": str(path),
                "retrieved_at": observed_at,
                "observation_method": "public_sitemap_product_url",
                "name_source_url": f"{BASE}/groceries/" if urlparse(url).path in names else None,
                "store_specificity": "national_catalog",
                "store_id": None,
                "store_address": None,
                "status": "likely_available",
                "confidence": "catalog_existence_only",
                "availability": None,
                "price": None,
                "brand": None,
                "package_size": None,
                "snapshot_id": None,
            }
    return [rows[key] for key in sorted(rows)]


def normalize_evidence(products, rules):
    """Conservative explicit whole-product prefixes, never ingredient substrings.

    A prefix must be immediately followed by a numeric package size. This keeps
    e.g. vegetable oil spreads and salt-flavored chips from proving oil or salt.
    """
    ingredients = []
    for canonical, prefixes in sorted(rules.items()):
        matched = [
            product
            for product in products
            if any(
                re.match(r"^" + re.escape(prefix) + r"(?=\d)", product["catalog_slug"])
                for prefix in prefixes
            )
        ]
        if not matched:
            continue
        evidence = [
            {
                key: product[key]
                for key in (
                    "id",
                    "product_id",
                    "source_url",
                    "source",
                    "evidence_source_url",
                    "raw_path",
                    "store_specificity",
                    "store_id",
                    "store_address",
                    "retrieved_at",
                    "status",
                    "confidence",
                    "snapshot_id",
                    "observation_method",
                )
            }
            for product in sorted(matched, key=lambda row: row["product_id"])
        ]
        ingredients.append(
            {
                "canonical_ingredient": canonical,
                "status": "likely_available",
                "product_ids": sorted({row["product_id"] for row in matched}),
                "product_count": len(matched),
                "evidence": evidence,
                "last_verified_at": None,
                "last_observed_at": max(row["retrieved_at"] for row in matched),
                "snapshot_id": None,
                "normalization_method": "configured_exact_product_slug_prefix",
                "confidence": "catalog_existence_only",
            }
        )
    return ingredients


def rebuild(root):
    root = Path(root)
    directory = root / "data/foodlion/evidence"
    manifest = json.loads((directory / "manifest.json").read_text())
    products = import_catalog(directory / "raw", manifest["retrieved_at"])
    for product in products:
        product["raw_path"] = str(Path(product["raw_path"]).relative_to(root))
    rules = load_yaml(root / "config/foodlion-evidence.yaml")["product_slug_prefixes"]
    ingredients = normalize_evidence(products, rules)
    write_jsonl(directory / "products.jsonl", products)
    write_jsonl(directory / "ingredients.jsonl", ingredients)
    return products, ingredients


def validate_evidence(root):
    root = Path(root)
    directory = root / "data/foodlion/evidence"
    products = {row["product_id"]: row for row in read_jsonl(directory / "products.jsonl")}
    for product_id, product in products.items():
        assert public_product_id(product["source_url"]) == product_id
        assert product["status"] == "likely_available"
        assert product["availability"] is None and product["store_id"] is None
        assert product["retrieved_at"] and (root / product["raw_path"]).exists()
    for ingredient in read_jsonl(directory / "ingredients.jsonl"):
        assert ingredient["product_ids"] and ingredient["evidence"]
        assert set(ingredient["product_ids"]) <= products.keys()
        assert ingredient["status"] == "likely_available"
    return len(products)


def collect(destination):
    """Collect a NEW evidence directory; resume cached successes without bypasses.

    It deliberately requests only the public robots-allowed SEO surface, not
    protected store inventory endpoints. 403/429 stops this run, with a failure.
    """
    destination = Path(destination)
    raw = destination / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    manifest_path = destination / "manifest.json"
    manifest = (
        json.loads(manifest_path.read_text())
        if manifest_path.exists()
        else {
            "retrieved_at": now(),
            "processed": [],
            "failures": [],
            "complete": False,
        }
    )

    def fetch(url, filename, robots=None):
        path = raw / filename
        if path.exists():
            return path.read_text()
        if robots and not all(
            robots.can_fetch(agent, url)
            for agent in [USER_AGENT, "GPTBot", "ChatGPT-User", "OAI-SearchBot"]
        ):
            raise PermissionError(f"robots.txt disallows {url}")
        time.sleep(1)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        opener = urllib.request.build_opener(RefuseRedirects())
        with opener.open(request, timeout=40) as response:
            content = response.read().decode("utf-8")
        atomic_text(path, content)
        manifest["processed"].append({"source_url": url, "path": str(path), "retrieved_at": now()})
        atomic_json(manifest_path, manifest)
        return content

    try:
        robot_text = fetch(BASE + "/robots.txt", "robots.txt")
        robots = urllib.robotparser.RobotFileParser()
        robots.parse(robot_text.splitlines())
        index = fetch(BASE + "/groceries/sitemap.xml", "sitemap.txt", robots)
        fetch(BASE + "/groceries/", "groceries.txt", robots)
        for node in ET.fromstring(index):
            url = node.find("{*}loc").text
            if url.startswith(BASE + "/groceries/sitemaps/"):
                fetch(url, url.rsplit("/", 1)[1], robots)
        manifest["complete"] = True
        manifest["completion_scope"] = "public_sitemap_discovery_only; not store inventory"
    except (OSError, ValueError, ET.ParseError, AccessBlocked) as exc:
        manifest["failures"].append(
            {"error_type": type(exc).__name__, "message": str(exc), "timestamp": now()}
        )
        manifest["complete"] = False
    atomic_json(manifest_path, manifest)
    return manifest


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["rebuild", "validate", "collect"])
    parser.add_argument("path", nargs="?", default=".")
    args = parser.parse_args()
    if args.action == "collect":
        print(json.dumps(collect(args.path), indent=2))
    elif args.action == "validate":
        print(validate_evidence(args.path))
    else:
        products, ingredients = rebuild(args.path)
        print(json.dumps({"products": len(products), "ingredients": len(ingredients)}))
