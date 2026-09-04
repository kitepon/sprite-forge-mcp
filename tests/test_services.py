import asyncio
import struct
import zlib
from backend.services import Services

def test_generated_path_is_cache_scoped():
    assert ".cache/generated/" in str(Services._generated_path("job", 2))

def test_first_image_reads_comfy_output():
    image = Services._first_image({"outputs":{"9":{"images":[{"filename":"x.png","subfolder":"sprite-forge","type":"output"}]}}})
    assert image["filename"] == "x.png"

def test_invalid_sprite_count_fails_before_network():
    service = Services()
    try:
        asyncio.run(service.generate_sprite("mage", count=0))
    except ValueError as error:
        assert "count" in str(error)
    else:
        raise AssertionError("expected validation error")

def test_rgba_measurement_reports_actual_transparency():
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + b"\0\0\0\0"
    pixels = b"\x00\x00\x00\x00\x00\x00\x00\xff\x00\x00\x00\xff\x00\x00\x00\x00"
    image = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 0))
    image += chunk(b"IDAT", zlib.compress(b"\0" + pixels[:8] + b"\0" + pixels[8:])) + chunk(b"IEND", b"")
    measurement = Services._measure_rgba_png(image)
    assert measurement == {"canvas": {"width": 2, "height": 2}, "corners_alpha": [0, 255, 255, 0],
                           "bbox": {"left": 0, "top": 0, "right": 2, "bottom": 2}}
