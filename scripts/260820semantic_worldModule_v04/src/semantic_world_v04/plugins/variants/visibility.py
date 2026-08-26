"""Pure visibility planning; USD opinions are authored by an adapter."""

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from semantic_world_v04.core.models import ValidationIssue, VariantDefinition
from semantic_world_v04.stage.index import StageIndex, paths_related


@dataclass(frozen=True)
class VisibilityPlan:
    hidden_roots: Tuple[str, ...]
    protected_paths: Tuple[str, ...]


class FullSceneVariant:
    strategy_id = "full_scene"

    def validate(
        self, variant: VariantDefinition, stage_index: Optional[StageIndex]
    ) -> Sequence[ValidationIssue]:
        issues = []
        if variant.include_paths or variant.exclude_paths:
            issues.append(
                ValidationIssue(
                    "variant.full_scene_paths",
                    "full_scene ignores include_paths and exclude_paths; remove them",
                    f"variants.{variant.variant_id}",
                )
            )
        return issues

    def visibility_plan(
        self,
        variant: VariantDefinition,
        stage_index: StageIndex,
        sensor_paths: Sequence[str],
    ) -> VisibilityPlan:
        protected = tuple(sorted(set(sensor_paths) | set(variant.protected_paths)))
        return VisibilityPlan(hidden_roots=(), protected_paths=protected)


class IncludePathsVariant:
    strategy_id = "include_paths"

    def validate(
        self, variant: VariantDefinition, stage_index: Optional[StageIndex]
    ) -> Sequence[ValidationIssue]:
        issues = []
        if not variant.include_paths:
            issues.append(
                ValidationIssue(
                    "variant.include_paths.empty",
                    "include_paths strategy requires at least one included Prim path",
                    f"variants.{variant.variant_id}.include_paths",
                )
            )
        for kind, paths in (
            ("include_paths", variant.include_paths),
            ("protected_paths", variant.protected_paths),
        ):
            for index, path in enumerate(paths):
                issue_path = f"variants.{variant.variant_id}.{kind}[{index}]"
                if not path.startswith("/"):
                    issues.append(
                        ValidationIssue(
                            "variant.prim_path",
                            "Prim path must start with '/'",
                            issue_path,
                        )
                    )
                elif stage_index is not None and stage_index.get(path) is None:
                    issues.append(
                        ValidationIssue(
                            "variant.prim_missing",
                            "Prim path does not exist in the Stage",
                            issue_path,
                        )
                    )
        return issues

    def visibility_plan(
        self,
        variant: VariantDefinition,
        stage_index: StageIndex,
        sensor_paths: Sequence[str],
    ) -> VisibilityPlan:
        whitelist = tuple(
            sorted(
                set(variant.include_paths)
                | set(variant.protected_paths)
                | set(sensor_paths)
            )
        )
        hidden = []
        for prim in stage_index.iter_prims():
            if prim.path == "/":
                continue
            if any(paths_related(prim.path, allowed) for allowed in whitelist):
                continue
            if any(prim.path == root or prim.path.startswith(root + "/") for root in hidden):
                continue
            hidden.append(prim.path)
        return VisibilityPlan(
            hidden_roots=tuple(hidden),
            protected_paths=whitelist,
        )


PLUGIN_CLASSES = (FullSceneVariant, IncludePathsVariant)
