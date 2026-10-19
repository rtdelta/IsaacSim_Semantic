import json
import tempfile
import unittest
from pathlib import Path

from semantic_world_v04.core.errors import ProjectIOError, SchemaError
from semantic_world_v04.core.models import ProjectDefinition
from semantic_world_v04.core.serde import content_sha256
from semantic_world_v04.project import ProjectPathResolver, ProjectRepository

from helpers import make_project


class ModelsAndRepositoryTests(unittest.TestCase):
    def test_repository_refuses_project_that_cannot_be_loaded_again(self) -> None:
        project = make_project()
        project.stage.usd_path = ""

        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "invalid.swproject"
            with self.assertRaises(SchemaError):
                ProjectRepository().save(destination, project)
            self.assertFalse(destination.exists())

    def test_strict_schema_rejects_unknown_field(self) -> None:
        data = make_project().to_dict()
        data["sensors"][0]["prim_pth"] = "/typo"
        with self.assertRaisesRegex(SchemaError, "unknown field"):
            ProjectDefinition.from_dict(data)

    def test_round_trip_revisioned_repository(self) -> None:
        project = make_project()
        with tempfile.TemporaryDirectory() as temp:
            project_dir = Path(temp) / "demo.swproject"
            repository = ProjectRepository()
            repository.save(project_dir, project)
            manifest = json.loads(
                (project_dir / "project.json").read_text(encoding="utf-8")
            )
            self.assertEqual(project.project_id, manifest["project_id"])
            self.assertTrue((project_dir / manifest["components"]["stage"]).is_file())
            self.assertEqual(project, repository.load(project_dir))

            # Saving the same content is idempotent and retains one revision.
            repository.save(project_dir, project)
            revisions = [path for path in (project_dir / ".revisions").iterdir()]
            self.assertEqual(1, len(revisions))

    def test_revision_tamper_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = Path(temp) / "demo.swproject"
            repository = ProjectRepository()
            repository.save(project_dir, make_project())
            manifest = json.loads(
                (project_dir / "project.json").read_text(encoding="utf-8")
            )
            render_path = project_dir / manifest["components"]["render"]
            render_doc = json.loads(render_path.read_text(encoding="utf-8"))
            render_doc["render"]["resolution_width"] = 999
            render_path.write_text(json.dumps(render_doc), encoding="utf-8")
            with self.assertRaisesRegex(ProjectIOError, "digest"):
                repository.load(project_dir)

    def test_project_path_resolution(self) -> None:
        root = Path("C:/projects/demo")
        self.assertEqual(
            str((root / "assets/scene.usda").resolve()),
            ProjectPathResolver.resolve("assets/scene.usda", root),
        )
        self.assertEqual(
            "omniverse://server/scene.usd",
            ProjectPathResolver.resolve("omniverse://server/scene.usd", root),
        )
        self.assertEqual(
            "/root/data/scene.usd",
            ProjectPathResolver.resolve("/root/data/scene.usd", root),
        )

    def test_v041_project_without_execution_component_is_migrated(self) -> None:
        project = make_project()
        data = project.to_dict()
        data["schema_version"] = 1
        data.pop("execution")
        data.pop("rigs")
        for sensor in data["sensors"]:
            sensor.pop("plugin_version")
            sensor.pop("backend")
            sensor.pop("sync_group_id")
        for modality in data["modalities"]:
            modality.pop("plugin_version")
        revision = content_sha256(data)
        component_names = {
            "stage": "stage.json",
            "sensors": "sensors.json",
            "variants": "variants.json",
            "modalities": "modalities.json",
            "render": "render.json",
            "capture": "capture.json",
            "motion": "motion.json",
            "semantics": "semantics.json",
            "output": "output.json",
        }
        with tempfile.TemporaryDirectory() as temp:
            project_dir = Path(temp) / "legacy.swproject"
            revision_dir = project_dir / ".revisions" / revision
            revision_dir.mkdir(parents=True)
            components = {}
            for key, filename in component_names.items():
                (revision_dir / filename).write_text(
                    json.dumps({"schema_version": 1, key: data[key]}),
                    encoding="utf-8",
                )
                components[key] = f".revisions/{revision}/{filename}"
            (project_dir / "project.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "project_id": project.project_id,
                        "name": project.name,
                        "description": project.description,
                        "revision": revision,
                        "components": components,
                    }
                ),
                encoding="utf-8",
            )

            loaded = ProjectRepository().load(project_dir)

            self.assertEqual("auto", loaded.execution.segmentation_strategy)
            self.assertEqual(2, loaded.schema_version)
            self.assertEqual("boom_camera", loaded.sensors[0].sync_group_id)
            repository = ProjectRepository()
            repository.save(project_dir, loaded)
            self.assertTrue((project_dir / "project.schema_v1.backup.json").is_file())
            self.assertEqual(2, repository.load(project_dir).schema_version)


if __name__ == "__main__":
    unittest.main()
