from io import BytesIO

from PIL import Image

from backend.services import Services


def png(color, size=(8, 8)):
    image = Image.new("RGBA", size, color)
    output = BytesIO(); image.save(output, format="PNG")
    return output.getvalue()


def test_restore_outside_mask_preserves_base_pixels():
    mask = Image.new("L", (8, 8), 0)
    mask.putpixel((4, 4), 255)
    output = BytesIO(); mask.save(output, format="PNG")
    result = Image.open(BytesIO(Services._restore_outside_mask(png("red"), png("blue"), output.getvalue())))
    assert result.getpixel((0, 0))[:3] == (255, 0, 0)
    assert result.getpixel((4, 4))[:3] == (0, 0, 255)


def test_pixelize_preserves_dimensions_and_alpha():
    result = Image.open(BytesIO(Services._pixelize_png(png((10, 20, 30, 0), (17, 9)), 4, 4)))
    assert result.size == (17, 9)
    assert result.getchannel("A").getextrema() == (0, 0)


def test_rgba_normalization_accepts_rgb_input():
    source = BytesIO(); Image.new("RGB", (3, 2), "white").save(source, format="PNG")
    result = Image.open(BytesIO(Services._as_rgba_png(source.getvalue())))
    assert result.mode == "RGBA"


def test_bbox_delta_is_numeric():
    assert Services._bbox_center_delta({"left": 0, "top": 0, "right": 10, "bottom": 10},
                                       {"left": 2, "top": 4, "right": 12, "bottom": 14}) == {"x": 2, "y": 4}
