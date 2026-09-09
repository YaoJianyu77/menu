import json

import pytest

from recipe_system.evidence import (
    classify_observation,
    import_catalog,
    normalize_evidence,
    public_product_id,
)

URL = "https://foodlion.com/groceries/product/food-lion-vegetable-oil-40-oz-btl/383703"
TIME = "2026-09-09T10:00:00-04:00"


def test_public_id_rejects_other_retailers_and_helpers():
    assert public_product_id(URL) == "383703"
    with pytest.raises(ValueError):
        public_product_id(URL.replace("foodlion.com", "other-retailer.com"))
    with pytest.raises(ValueError):
        public_product_id("https://foodlion.com/product/383703")


def test_three_state_evidence_and_other_store():
    evidence = {"source_url": URL, "retrieved_at": TIME}
    assert classify_observation(evidence) == "unknown"
    evidence["catalog_listed"] = True
    assert classify_observation(evidence) == "likely_available"
    evidence.update(store_specificity="specific_store", store_id="OTHER", availability=True)
    assert classify_observation(evidence, "CONFIGURED") == "likely_available"
    assert classify_observation(evidence, "OTHER") == "verified_available"
    evidence["availability"] = False
    assert classify_observation(evidence, "OTHER") == "unavailable"
    assert classify_observation(evidence, "CONFIGURED") == "likely_available"


def test_unknown_store_id_never_counts_as_verified():
    evidence = {
        "source_url": URL,
        "retrieved_at": TIME,
        "store_id": None,
        "store_specificity": "specific_store",
        "availability": True,
    }
    assert classify_observation(evidence, None) == "likely_available"


def test_catalog_offline_import_is_stable_and_no_stock_inference(tmp_path):
    (tmp_path / "products-0.xml").write_text(
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<url><loc>{URL}</loc></url></urlset>"
    )
    structured = {
        "itemListElement": [
            {
                "url": URL.replace("https://foodlion.com", "http://localhost:4321"),
                "name": "Food Lion Vegetable Oil",
            }
        ]
    }
    (tmp_path / "groceries.txt").write_text(
        '<script type="application/ld+json">' + json.dumps(structured) + "</script>"
    )
    products = import_catalog(tmp_path, TIME)
    assert products == import_catalog(tmp_path, TIME)
    assert products[0]["product_name"] == "Food Lion Vegetable Oil"
    assert products[0]["availability"] is None
    assert products[0]["store_id"] is None
    assert products[0]["source_url"] == URL
    assert products[0]["status"] == "likely_available"
    rule = {"vegetable oil": ["food-lion-vegetable-oil-"]}
    ingredients = normalize_evidence(products, rule)
    assert ingredients[0]["product_ids"] == ["383703"]
    assert ingredients[0]["evidence"][0]["raw_path"] == str(tmp_path / "products-0.xml")
    products[0]["catalog_slug"] = "food-lion-vegetable-oil-buttery-spread-16-oz"
    assert normalize_evidence(products, rule) == []


def test_slug_does_not_fabricate_product_name(tmp_path):
    (tmp_path / "products-0.xml").write_text(f"<urlset><url><loc>{URL}</loc></url></urlset>")
    assert import_catalog(tmp_path, TIME)[0]["product_name"] is None


def test_expanded_catalog_mappings_reference_real_specific_products():
    from pathlib import Path

    from recipe_system.core import load_yaml, read_jsonl

    root = Path(__file__).parents[1]
    products = {
        row["product_id"]: row for row in read_jsonl(root / "data/foodlion/evidence/products.jsonl")
    }
    ingredients = {
        row["canonical_ingredient"]: row
        for row in read_jsonl(root / "data/foodlion/evidence/ingredients.jsonl")
    }
    rules = load_yaml(root / "config/foodlion-evidence.yaml")["product_slug_prefixes"]
    for name in (
        "greek yogurt",
        "avocado",
        "quinoa",
        "kale",
        "parsley",
        "lemon juice",
        "ham",
        "chicken leg quarter",
        "dill pickle",
        "rice vinegar",
        "vanilla extract",
    ):
        ingredient = ingredients[name]
        assert ingredient["status"] == "likely_available"
        assert ingredient["product_ids"]
        for product_id in ingredient["product_ids"]:
            product = products[product_id]
            assert public_product_id(product["source_url"]) == product_id
            assert normalize_evidence([product], {name: rules[name]})
            assert product["availability"] is None
    assert "dark soy sauce" not in ingredients  # Tamari is not an automatic substitution.
