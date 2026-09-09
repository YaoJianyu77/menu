from copy import deepcopy

import pytest

from recipe_system.recipe_images import select_image


def photo(**changes):
    return {
        "url": "https://recipes.example/chicken.jpg",
        "source_url": "https://recipes.example/chicken/",
        "attribution": "Photograph by Recipe Author",
        "license": "CC-BY-4.0",
        **changes,
    }


def test_explicit_image_rights_preserve_attribution_without_mutation():
    recipe = {"image": photo()}
    original = deepcopy(recipe)
    assert select_image(recipe) == photo()
    assert recipe == original


@pytest.mark.parametrize(
    "image",
    [
        photo(license="unknown"),
        photo(attribution=None),
        photo(url="javascript:alert(1)"),
        photo(url="https://user:password@example.com/image.jpg"),
        photo(source_url=None),
        photo(publication_allowed=False),
    ],
)
def test_unsafe_or_unsupported_image_is_omitted(image):
    assert select_image({"image": image}) is None


def test_recipe_license_does_not_establish_image_rights():
    assert select_image({"image_url": photo()["url"], "source_license": "CC-BY-4.0"}) is None
    assert select_image({"raw_text": '<img src="https://recipes.example/photo.jpg">'}) is None
    assert select_image({}) is None


def test_raw_image_fallback_requires_same_recipe_identity():
    raw = {"id": "raw-1", "image": photo()}
    assert select_image({"raw_id": "raw-1"}, raw) == photo()
    assert select_image({"raw_id": "other"}, raw) is None


def test_flat_image_fields_and_explicit_permission():
    record = {
        "image_url": photo()["url"],
        "image_source_url": photo()["source_url"],
        "image_publication_allowed": True,
        "image_permission_evidence": "https://recipes.example/photo-permission",
    }
    assert select_image(record)["license"] == "Explicit permission"
    record.pop("image_permission_evidence")
    assert select_image(record) is None


def test_public_domain_requires_no_attribution():
    assert select_image({"image": photo(license="CC0-1.0", attribution=None)}) is not None
