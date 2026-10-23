"""Image import compatibility across Pillow upgrades, without GPU or network."""
import asyncio
from io import BytesIO

import httpx
import pytest
from PIL import Image

from backend.services import Services


@pytest.mark.parametrize("image_format", ["PNG", "JPEG", "TIFF", "GIF", "WEBP"])
@pytest.mark.parametrize("source", ["upload", "url"])
def test_import_preserves_image_content(tmp_path, monkeypatch, image_format, source):
    original = Image.new("RGB", (13, 19), (40, 80, 120))
    encoded = BytesIO()
    original.save(encoded, image_format, **({"lossless": True} if image_format == "WEBP" else {}))
    service = Services(uploads_root=tmp_path / "uploads")

    if source == "upload":
        path = service.save_upload(encoded.getvalue(), f"参考画像.{image_format.lower()}")
    else:
        client_type = httpx.AsyncClient

        def respond(request):
            assert str(request.url) == "https://images.example.test/reference"
            return httpx.Response(200, content=encoded.getvalue())

        monkeypatch.setattr(
            "backend.services.httpx.AsyncClient",
            lambda **kwargs: client_type(transport=httpx.MockTransport(respond), **kwargs),
        )
        path = asyncio.run(service._resolve_image("https://images.example.test/reference"))

    assert path.parent == tmp_path / "uploads"
    with Image.open(path) as stored:
        assert stored.format == "PNG"
        assert stored.size == original.size
        pixel = stored.convert("RGB").getpixel((6, 9))
        tolerance = 3 if image_format == "JPEG" else 0
        assert all(abs(actual - expected) <= tolerance for actual, expected in zip(pixel, (40, 80, 120)))


def test_png_import_preserves_transparent_pixels(tmp_path):
    original = Image.new("RGBA", (2, 1))
    original.putdata([(20, 40, 60, 0), (80, 100, 120, 127)])
    encoded = BytesIO()
    original.save(encoded, "PNG")
    path = Services(uploads_root=tmp_path).save_upload(encoded.getvalue())
    with Image.open(path) as stored:
        assert stored.convert("RGBA").tobytes() == original.tobytes()
