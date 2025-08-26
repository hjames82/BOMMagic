import re
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ValidationRule:
    """Represents a validation rule"""
    field: str
    rule_type: str
    pattern: Optional[str] = None
    required: bool = False
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    description: str = ""


class ValidationService:
    """Service for validating extracted BOM data"""
    
    def __init__(self):
        self.validation_rules = self._initialize_validation_rules()
        self.confidence_weights = {
            'header_validation': 0.2,
            'data_completeness': 0.3,
            'format_compliance': 0.3,
            'consistency_check': 0.2
        }
    
    def validate_bom_data(self, bom_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Validate extracted BOM data and calculate confidence scores
        
        Args:
            bom_data: List of extracted BOM items
            
        Returns:
            Dictionary containing validation results and confidence scores
        """
        result = {
            'overall_confidence': 0.0,
            'item_validations': [],
            'metadata': {},
            'validation_summary': {}
        }
        
        try:
            if not bom_data:
                result['metadata']['error'] = "No BOM data to validate"
                return result
            
            # Validate each item
            item_validations = []
            for i, item in enumerate(bom_data):
                validation = self._validate_item(item, i)
                item_validations.append(validation)
            
            result['item_validations'] = item_validations
            
            # Calculate overall confidence
            overall_confidence = self._calculate_overall_confidence(bom_data, item_validations)
            result['overall_confidence'] = overall_confidence
            
            # Generate validation summary
            summary = self._generate_validation_summary(item_validations)
            result['validation_summary'] = summary
            
            # Generate metadata
            result['metadata'] = {
                'total_items': len(bom_data),
                'valid_items': summary['valid_items'],
                'items_with_errors': summary['items_with_errors'],
                'items_with_warnings': summary['items_with_warnings'],
                'average_item_confidence': summary['average_confidence'],
                'validation_passed': overall_confidence >= 0.7
            }
            
        except Exception as e:
            logger.error(f"Validation failed: {str(e)}")
            result['metadata']['error'] = str(e)
        
        return result
    
    def _initialize_validation_rules(self) -> List[ValidationRule]:
        """Initialize standard BOM validation rules"""
        rules = [
            # Item number rules
            ValidationRule(
                field='item_number',
                rule_type='pattern',
                pattern=r'^\d+$',
                description="Item number should be numeric"
            ),
            
            # Part number rules
            ValidationRule(
                field='part_number',
                rule_type='pattern',
                pattern=r'^[A-Z0-9\-_\.]+$',
                min_length=3,
                description="Part number should contain alphanumeric characters, hyphens, underscores, or periods"
            ),
            
            # Description rules
            ValidationRule(
                field='description',
                rule_type='required',
                required=True,
                min_length=5,
                description="Description is required and should be descriptive"
            ),
            
            # Quantity rules
            ValidationRule(
                field='quantity',
                rule_type='pattern',
                pattern=r'^\d+(\.\d+)?$',
                description="Quantity should be a positive number"
            ),
            
            # Unit rules
            ValidationRule(
                field='unit',
                rule_type='pattern',
                pattern=r'^(ea|each|pcs?|pieces?|kg|lb|ft|m|mm|cm|in|inches?|units?)$',
                description="Unit should be a standard unit of measure"
            ),
            
            # Cost rules
            ValidationRule(
                field='cost',
                rule_type='pattern',
                pattern=r'^\$?\d+(\.\d{2})?$',
                description="Cost should be a valid monetary amount"
            )
        ]
        
        return rules
    
    def _validate_item(self, item: Dict[str, Any], item_index: int) -> Dict[str, Any]:
        """Validate individual BOM item"""
        validation = {
            'item_index': item_index,
            'confidence_score': 0.0,
            'errors': [],
            'warnings': [],
            'field_scores': {}
        }
        
        total_score = 0.0
        field_count = 0
        
        # Validate each field against rules
        for rule in self.validation_rules:
            field_value = item.get(rule.field, '')
            field_score, issues = self._validate_field(field_value, rule)
            
            validation['field_scores'][rule.field] = field_score
            total_score += field_score
            field_count += 1
            
            # Categorize issues
            for issue in issues:
                if issue['severity'] == 'error':
                    validation['errors'].append(issue)
                else:
                    validation['warnings'].append(issue)
        
        # Calculate item confidence
        validation['confidence_score'] = total_score / field_count if field_count > 0 else 0.0
        
        # Apply penalties for critical errors
        if validation['errors']:
            validation['confidence_score'] *= 0.5  # Reduce confidence by 50% for errors
        
        return validation
    
    def _validate_field(self, value: str, rule: ValidationRule) -> Tuple[float, List[Dict[str, Any]]]:
        """Validate individual field against a rule"""
        issues = []
        score = 1.0
        
        value_str = str(value).strip() if value else ''
        
        # Check if required field is present
        if rule.required and not value_str:
            issues.append({
                'field': rule.field,
                'severity': 'error',
                'message': f"{rule.field} is required but missing",
                'rule': rule.description
            })
            return 0.0, issues
        
        # Skip validation if field is empty and not required
        if not value_str:
            return 0.5, issues  # Partial score for optional empty fields
        
        # Check minimum length
        if rule.min_length and len(value_str) < rule.min_length:
            issues.append({
                'field': rule.field,
                'severity': 'warning',
                'message': f"{rule.field} is shorter than expected minimum length ({rule.min_length})",
                'rule': rule.description
            })
            score *= 0.8
        
        # Check maximum length
        if rule.max_length and len(value_str) > rule.max_length:
            issues.append({
                'field': rule.field,
                'severity': 'warning',
                'message': f"{rule.field} exceeds maximum length ({rule.max_length})",
                'rule': rule.description
            })
            score *= 0.9
        
        # Check pattern matching
        if rule.pattern and not re.match(rule.pattern, value_str, re.IGNORECASE):
            issues.append({
                'field': rule.field,
                'severity': 'error',
                'message': f"{rule.field} format is invalid",
                'rule': rule.description
            })
            score *= 0.3
        
        return score, issues
    
    def _calculate_overall_confidence(self, bom_data: List[Dict[str, Any]], validations: List[Dict[str, Any]]) -> float:
        """Calculate overall confidence score for the BOM data"""
        if not validations:
            return 0.0
        
        # Header validation score (check if we have expected BOM structure)
        header_score = self._calculate_header_score(bom_data)
        
        # Data completeness score
        completeness_score = self._calculate_completeness_score(bom_data)
        
        # Format compliance score (average of individual item scores)
        format_score = sum(v['confidence_score'] for v in validations) / len(validations)
        
        # Consistency check score
        consistency_score = self._calculate_consistency_score(bom_data)
        
        # Weighted average
        overall_score = (
            header_score * self.confidence_weights['header_validation'] +
            completeness_score * self.confidence_weights['data_completeness'] +
            format_score * self.confidence_weights['format_compliance'] +
            consistency_score * self.confidence_weights['consistency_check']
        )
        
        return min(overall_score, 1.0)
    
    def _calculate_header_score(self, bom_data: List[Dict[str, Any]]) -> float:
        """Calculate score based on expected BOM headers/fields"""
        if not bom_data:
            return 0.0
        
        expected_fields = ['item_number', 'part_number', 'description', 'quantity']
        sample_item = bom_data[0]
        
        present_fields = sum(1 for field in expected_fields if sample_item.get(field))
        return present_fields / len(expected_fields)
    
    def _calculate_completeness_score(self, bom_data: List[Dict[str, Any]]) -> float:
        """Calculate score based on data completeness"""
        if not bom_data:
            return 0.0
        
        total_fields = 0
        filled_fields = 0
        
        for item in bom_data:
            for field in ['item_number', 'part_number', 'description', 'quantity']:
                total_fields += 1
                if item.get(field) and str(item[field]).strip():
                    filled_fields += 1
        
        return filled_fields / total_fields if total_fields > 0 else 0.0
    
    def _calculate_consistency_score(self, bom_data: List[Dict[str, Any]]) -> float:
        """Calculate score based on data consistency"""
        if len(bom_data) < 2:
            return 1.0  # Single item is consistent by definition
        
        consistency_checks = []
        
        # Check item number sequence
        item_numbers = [item.get('item_number', '') for item in bom_data]
        numeric_items = [int(x) for x in item_numbers if x.isdigit()]
        if len(numeric_items) > 1:
            is_sequential = all(
                numeric_items[i] <= numeric_items[i + 1] 
                for i in range(len(numeric_items) - 1)
            )
            consistency_checks.append(1.0 if is_sequential else 0.5)
        
        # Check format consistency for part numbers
        part_numbers = [item.get('part_number', '') for item in bom_data if item.get('part_number')]
        if part_numbers:
            # Check if part numbers follow similar patterns
            patterns = set()
            for pn in part_numbers:
                pattern = re.sub(r'\d+', 'N', pn)  # Replace numbers with 'N'
                pattern = re.sub(r'[A-Z]+', 'A', pattern)  # Replace letters with 'A'
                patterns.add(pattern)
            
            pattern_consistency = 1.0 / len(patterns) if patterns else 1.0
            consistency_checks.append(pattern_consistency)
        
        # Check unit consistency
        units = [item.get('unit', '') for item in bom_data if item.get('unit')]
        if units:
            unique_units = set(units)
            unit_consistency = min(1.0, 3.0 / len(unique_units)) if unique_units else 1.0
            consistency_checks.append(unit_consistency)
        
        return sum(consistency_checks) / len(consistency_checks) if consistency_checks else 0.5
    
    def _generate_validation_summary(self, validations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate summary of validation results"""
        total_items = len(validations)
        valid_items = sum(1 for v in validations if v['confidence_score'] >= 0.8)
        items_with_errors = sum(1 for v in validations if v['errors'])
        items_with_warnings = sum(1 for v in validations if v['warnings'])
        
        avg_confidence = sum(v['confidence_score'] for v in validations) / total_items if total_items > 0 else 0.0
        
        # Collect all error types
        error_types = {}
        warning_types = {}
        
        for validation in validations:
            for error in validation['errors']:
                error_type = error['field']
                error_types[error_type] = error_types.get(error_type, 0) + 1
            
            for warning in validation['warnings']:
                warning_type = warning['field']
                warning_types[warning_type] = warning_types.get(warning_type, 0) + 1
        
        return {
            'total_items': total_items,
            'valid_items': valid_items,
            'items_with_errors': items_with_errors,
            'items_with_warnings': items_with_warnings,
            'average_confidence': avg_confidence,
            'most_common_errors': sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:5],
            'most_common_warnings': sorted(warning_types.items(), key=lambda x: x[1], reverse=True)[:5]
        }
    
    def get_confidence_threshold(self) -> float:
        """Get the confidence threshold for requiring manual review"""
        return float(os.getenv('CONFIDENCE_THRESHOLD', '0.8'))
    
    def requires_manual_review(self, confidence_score: float) -> bool:
        """Determine if BOM extraction requires manual review"""
        return confidence_score < self.get_confidence_threshold()
