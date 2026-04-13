from __future__ import annotations

from functools import cached_property

from app.core.config import Settings
from app.core.exceptions import ValidationReportError
from app.models.classification import ClassificationCatalog
from app.services.data.normalization import ClassificationNormalizer


class CatalogLoader:
    def __init__(self, settings: Settings):
        self.settings = settings

    @cached_property
    def _normalizer(self) -> ClassificationNormalizer:
        return ClassificationNormalizer(
            data_path=self.settings.classification_data_path,
            enrichment_path=self.settings.classification_enrichment_path,
        )

    def load(self) -> ClassificationCatalog:
        catalog = self._normalizer.normalize()
        if not catalog.validation_report.is_valid:
            raise ValidationReportError(catalog.validation_report.model_dump(mode="json"))
        return catalog
