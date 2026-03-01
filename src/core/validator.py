"""
Result Validator

Features:
- Validate Sub Agent result format
- Check required fields
- Verify data rationality
- Support custom validation rules
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from enum import Enum


class ValidationLevel(str, Enum):
    """Validation levels"""

    STRICT = "strict"  # Strict: must match format exactly
    NORMAL = "normal"  # Normal: key fields must exist
    LENIENT = "lenient"  # Lenient: basic checks only


@dataclass
class ValidationError:
    """Validation error"""

    field: str
    message: str
    severity: str = "error"  # error / warning


@dataclass
class ValidationResult:
    """Validation result"""

    is_valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    corrected: Dict[str, Any] = field(default_factory=dict)

    def add_error(self, field: str, message: str):
        self.errors.append(ValidationError(field, message, "error"))
        self.is_valid = False

    def add_warning(self, field: str, message: str):
        self.warnings.append(ValidationError(field, message, "warning"))

    def merge(self, other: "ValidationResult"):
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        self.corrected.update(other.corrected)
        if not other.is_valid:
            self.is_valid = False


class BaseValidator:
    """Base validator"""

    def __init__(self, level: ValidationLevel = ValidationLevel.NORMAL):
        self.level = level

    def validate(self, result: Dict[str, Any], category: str) -> ValidationResult:
        raise NotImplementedError

    def _check_required_fields(
        self, result: Dict, required: List[str]
    ) -> ValidationResult:
        """Check required fields exist"""
        vr = ValidationResult(is_valid=True)

        for field in required:
            if field not in result or not result[field]:
                vr.add_error(field, f"Missing required field: {field}")
            elif isinstance(result[field], list) and len(result[field]) == 0:
                vr.add_warning(field, f"Empty field: {field}")

        return vr


class OutfitResultValidator(BaseValidator):
    """Outfit result validator"""

    # Required fields for each category
    REQUIRED_FIELDS = {
        "head": ["items", "colors", "styles", "reasons"],
        "top": ["items", "colors", "styles", "reasons"],
        "bottom": ["items", "colors", "styles", "reasons"],
        "shoes": ["items", "colors", "styles", "reasons"],
    }

    # Minimum item count per category
    MIN_ITEMS = {
        "head": 1,
        "top": 1,
        "bottom": 1,
        "shoes": 1,
    }

    def validate(self, result: Dict[str, Any], category: str) -> ValidationResult:
        """Validate outfit result"""
        vr = ValidationResult(is_valid=True)

        # 1. Check required fields
        required = self.REQUIRED_FIELDS.get(category, [])
        field_check = self._check_required_fields(result, required)
        vr.merge(field_check)

        if self.level == ValidationLevel.LENIENT and not vr.is_valid:
            return vr

        # 2. Check data types
        for field in required:
            if field in result:
                if not isinstance(result[field], list):
                    vr.add_error(field, f"Field type error, expected list: {field}")
                elif field == "items" and len(result[field]) < self.MIN_ITEMS.get(
                    category, 1
                ):
                    vr.add_warning(
                        field, f"Low recommendation count: {len(result[field])}"
                    )

        # 3. Check content reasonableness
        if "items" in result:
            for i, item in enumerate(result["items"]):
                if not item or len(item.strip()) < 2:
                    vr.add_warning(f"items[{i}]", f"Recommendation too short: {item}")

        # 4. Check color/style matching
        if "colors" in result and "styles" in result:
            if len(result["colors"]) == 0:
                vr.add_warning("colors", "No color suggestions provided")
            if len(result["styles"]) == 0:
                vr.add_warning("styles", "No style suggestions provided")

        return vr

    def auto_fix(self, result: Dict[str, Any], category: str) -> Dict[str, Any]:
        """Auto fix issues"""
        fixed = result.copy()

        # Fill empty fields
        for field in self.REQUIRED_FIELDS.get(category, []):
            if field not in fixed or not fixed[field]:
                fixed[field] = ["Not provided"]

        # Ensure list type
        for field in ["items", "colors", "styles", "reasons"]:
            if field in fixed and not isinstance(fixed[field], list):
                fixed[field] = [str(fixed[field])]

        return fixed


class ResultValidator:
    """
    Result Validator - Main class

    Supports:
    - Multiple validator types
    - Custom rules
    - Auto-fix
    - Error aggregation
    """

    def __init__(self, level: ValidationLevel = ValidationLevel.NORMAL):
        self.level = level
        self._validators: Dict[str, BaseValidator] = {}
        self._custom_rules: List[Callable] = []

        # Register default validators
        self.register_validator("outfit", OutfitResultValidator(level))

    def register_validator(self, name: str, validator: BaseValidator):
        """Register a validator"""
        self._validators[name] = validator

    def add_rule(self, rule: Callable):
        """Add custom rule"""
        self._custom_rules.append(rule)

    def validate(
        self,
        result: Any,
        validator_name: str = "outfit",
        category: Optional[str] = None,
    ) -> ValidationResult:
        """
        Validate result

        Args:
            result: Result to validate
            validator_name: Validator name
            category: Category (e.g. head/top/bottom/shoes)

        Returns:
            ValidationResult
        """
        # Parse result
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                vr = ValidationResult(is_valid=False)
                vr.add_error("result", "Result format is not valid JSON")
                return vr

        # Use corresponding validator
        validator = self._validators.get(validator_name)
        if not validator:
            vr = ValidationResult(is_valid=False)
            vr.add_error("validator", f"Validator not found: {validator_name}")
            return vr

        vr = validator.validate(result, category or "")

        # Apply custom rules
        for rule in self._custom_rules:
            try:
                rule_result = rule(result, category)
                if rule_result:
                    vr.merge(rule_result)
            except Exception as e:
                vr.add_warning("custom_rule", f"Custom rule execution failed: {e}")

        return vr

    def validate_all(self, results: Dict[str, Any]) -> Dict[str, ValidationResult]:
        """Validate multiple results"""
        validation_results = {}

        for category, result in results.items():
            if result:
                vr = self.validate(result, "outfit", category)
                validation_results[category] = vr

        return validation_results

    def auto_fix(
        self,
        result: Any,
        validator_name: str = "outfit",
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Auto fix result"""
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except (json.JSONDecodeError, ValueError):
                return {
                    "items": ["Fix failed"],
                    "colors": [],
                    "styles": [],
                    "reasons": [],
                }

        validator = self._validators.get(validator_name)
        if validator and hasattr(validator, "auto_fix"):
            return validator.auto_fix(result, category or "")

        return result

    def get_summary(self, results: Dict[str, ValidationResult]) -> str:
        """Generate validation summary"""
        total = len(results)
        valid = sum(1 for r in results.values() if r.is_valid)
        errors = sum(len(r.errors) for r in results.values())
        warnings = sum(len(r.warnings) for r in results.values())

        summary = f"Validation: {valid}/{total} passed"
        if errors > 0:
            summary += f", {errors} errors"
        if warnings > 0:
            summary += f", {warnings} warnings"

        return summary


# Global validator instance
_validator: Optional[ResultValidator] = None


def get_validator(level: ValidationLevel = ValidationLevel.NORMAL) -> ResultValidator:
    """Get validator instance"""
    global _validator
    if _validator is None:
        _validator = ResultValidator(level)
    return _validator
