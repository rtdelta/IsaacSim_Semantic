"""Direct RenderProduct annotator capture without a Replicator Writer graph."""

from __future__ import annotations

from typing import Any, Iterable


def _annotator_name(annotator: Any) -> str:
    name = str(getattr(annotator, "name", "")).strip()
    if not name:
        raise RuntimeError("A directly attached annotator has no public name")
    return name


def attach_annotators(annotators: Iterable[Any], render_product: Any) -> tuple[Any, ...]:
    """Attach all annotators and roll back earlier attachments on failure."""

    attached: list[Any] = []
    try:
        for annotator in annotators:
            _annotator_name(annotator)
            annotator.attach(render_product)
            attached.append(annotator)
    except BaseException:
        for annotator in reversed(attached):
            annotator.detach(render_product)
        raise
    return tuple(attached)


def build_writer_payload(
    annotators: Iterable[Any],
    render_product: Any,
) -> dict[str, Any]:
    """Read one synchronized render and shape it like a Replicator Writer payload."""

    render_product_data: dict[str, Any] = {}
    for annotator in annotators:
        name = _annotator_name(annotator)
        if name in render_product_data:
            raise RuntimeError(f"Duplicate directly attached annotator name: {name}")
        render_product_data[name] = annotator.get_data()

    render_product_name = str(getattr(render_product, "path", render_product))
    if not render_product_name:
        raise RuntimeError("RenderProduct has no stable path/name")
    return {"renderProducts": {render_product_name: render_product_data}}


def detach_annotators(annotators: Iterable[Any], render_product: Any) -> None:
    """Detach directly attached annotators in reverse dependency order."""

    for annotator in reversed(tuple(annotators)):
        annotator.detach(render_product)
