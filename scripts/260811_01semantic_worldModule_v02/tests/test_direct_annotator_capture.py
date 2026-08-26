from __future__ import annotations

import unittest

from direct_annotator_capture import (
    attach_annotators,
    build_writer_payload,
    detach_annotators,
)


class FakeRenderProduct:
    path = "/Render/Products/Test"


class FakeAnnotator:
    def __init__(self, name: str, data: object, events: list[str], fail: bool = False):
        self.name = name
        self.data = data
        self.events = events
        self.fail = fail

    def attach(self, render_product: object) -> None:
        self.events.append(f"attach:{self.name}")
        if self.fail:
            raise RuntimeError(f"failed:{self.name}")

    def detach(self, render_product: object) -> None:
        self.events.append(f"detach:{self.name}")

    def get_data(self) -> object:
        self.events.append(f"get:{self.name}")
        return self.data


class DirectAnnotatorCaptureTests(unittest.TestCase):
    def test_builds_one_render_product_writer_payload(self) -> None:
        events: list[str] = []
        annotators = (
            FakeAnnotator("rgb", "rgb-data", events),
            FakeAnnotator("semantic_segmentation", {"data": "ids"}, events),
        )
        render_product = FakeRenderProduct()

        attached = attach_annotators(annotators, render_product)
        payload = build_writer_payload(attached, render_product)
        detach_annotators(attached, render_product)

        self.assertEqual(
            payload,
            {
                "renderProducts": {
                    "/Render/Products/Test": {
                        "rgb": "rgb-data",
                        "semantic_segmentation": {"data": "ids"},
                    }
                }
            },
        )
        self.assertEqual(
            events,
            [
                "attach:rgb",
                "attach:semantic_segmentation",
                "get:rgb",
                "get:semantic_segmentation",
                "detach:semantic_segmentation",
                "detach:rgb",
            ],
        )

    def test_rolls_back_prior_attachment_on_failure(self) -> None:
        events: list[str] = []
        annotators = (
            FakeAnnotator("rgb", None, events),
            FakeAnnotator("semantic_segmentation", None, events, fail=True),
        )

        with self.assertRaisesRegex(RuntimeError, "failed:semantic_segmentation"):
            attach_annotators(annotators, FakeRenderProduct())

        self.assertEqual(
            events,
            ["attach:rgb", "attach:semantic_segmentation", "detach:rgb"],
        )

    def test_rejects_duplicate_annotator_names(self) -> None:
        events: list[str] = []
        annotators = (
            FakeAnnotator("rgb", 1, events),
            FakeAnnotator("rgb", 2, events),
        )
        with self.assertRaisesRegex(RuntimeError, "Duplicate"):
            build_writer_payload(annotators, FakeRenderProduct())


if __name__ == "__main__":
    unittest.main()
