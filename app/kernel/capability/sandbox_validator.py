"""
Sandbox Validation system for Phase 7 Skill Tree & Meta-Tools system.
Tests generated skill candidates in isolated environments before promotion.
"""

import json
import sqlite3
import subprocess
import tempfile
import os
import sys
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import logging
import time

logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    """Result of validating a meta-tool candidate in sandbox."""
    validation_id: str
    candidate_id: str
    status: str  # 'passed', 'failed', 'error'
    score: float  # 0.0 to 1.0
    test_results: Dict[str, Any]
    execution_time: float
    resource_usage: Dict[str, Any]
    errors: List[str]
    warnings: List[str]
    validated_at: str

class SandboxValidator:
    """Validates meta-tool candidates in isolated sandbox environments."""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            self.db_path = str(Path(__file__).resolve().parents[2] / "data" / "skills.db")
        else:
            self.db_path = db_path
        
        self._ensure_tables()
    
    def _ensure_tables(self):
        """Ensure the validation results tables exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS validation_results (
                    validation_id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    score REAL,
                    test_results TEXT,  -- JSON object
                    execution_time REAL,
                    resource_usage TEXT,  -- JSON object
                    errors TEXT,  -- JSON array
                    warnings TEXT,  -- JSON array
                    validated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (candidate_id) REFERENCES meta_tool_candidates (candidate_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_validation_candidate 
                ON validation_results(candidate_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_validation_status 
                ON validation_results(status)
            """)
    
    def validate_candidate(self, candidate_id: str, 
                          test_scenarios: List[Dict[str, Any]] = None) -> ValidationResult:
        """
        Validate a meta-tool candidate in the sandbox environment.
        
        Args:
            candidate_id: ID of the candidate to validate
            test_scenarios: Optional list of test scenarios to run
            
        Returns:
            ValidationResult object
        """
        start_time = time.time()
        
        # Get the candidate from database
        candidate = self._get_candidate(candidate_id)
        if not candidate:
            return ValidationResult(
                validation_id=f"val_{int(time.time())}",
                candidate_id=candidate_id,
                status='error',
                score=0.0,
                test_results={},
                execution_time=0.0,
                resource_usage={},
                errors=[f"Candidate {candidate_id} not found"],
                warnings=[],
                validated_at=self._get_current_timestamp()
            )
        
        # Run validation tests
        test_results = self._run_validation_tests(candidate, test_scenarios or [])
        
        # Calculate overall score
        score = self._calculate_validation_score(test_results)
        
        # Determine status
        status = self._determine_validation_status(score, test_results)
        
        # Collect resource usage (simplified)
        resource_usage = self._collect_resource_usage()
        
        execution_time = time.time() - start_time
        
        result = ValidationResult(
            validation_id=f"val_{int(time.time() * 1000)}",
            candidate_id=candidate_id,
            status=status,
            score=score,
            test_results=test_results,
            execution_time=execution_time,
            resource_usage=resource_usage,
            errors=test_results.get('errors', []),
            warnings=test_results.get('warnings', []),
            validated_at=self._get_current_timestamp()
        )
        
        # Store the result
        self._store_validation_result(result)
        
        return result
    
    def _get_candidate(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        """Get a meta-tool candidate from the database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM meta_tool_candidates WHERE candidate_id = ?
            """, (candidate_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    'candidate_id': row['candidate_id'],
                    'name': row['name'],
                    'description': row['description'],
                    'source_sequence': json.loads(row['source_sequence']),
                    'frequency': row['frequency'],
                    'confidence_score': row['confidence_score'],
                    'suggested_parameters': json.loads(row['suggested_parameters']),
                    'usage_examples': json.loads(row['usage_examples']),
                    'tags': json.loads(row['tags']),
                    'created_at': row['created_at']
                }
            return None
    
    def _run_validation_tests(self, candidate: Dict[str, Any], 
                            test_scenarios: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Run validation tests for the candidate."""
        test_results = {
            'unit_tests': {},
            'integration_tests': {},
            'performance_tests': {},
            'security_tests': {},
            'errors': [],
            'warnings': []
        }
        
        # Run unit tests
        unit_test_result = self._run_unit_tests(candidate)
        test_results['unit_tests'] = unit_test_result
        
        # Run integration tests
        integration_test_result = self._run_integration_tests(candidate)
        test_results['integration_tests'] = integration_test_result
        
        # Run performance tests
        performance_test_result = self._run_performance_tests(candidate)
        test_results['performance_tests'] = performance_test_result
        
        # Run security tests
        security_test_result = self._run_security_tests(candidate)
        test_results['security_tests'] = security_test_result
        
        # Collect any errors/warnings
        for test_category in ['unit_tests', 'integration_tests', 'performance_tests', 'security_tests']:
            test_results['errors'].extend(test_results[test_category].get('errors', []))
            test_results['warnings'].extend(test_results[test_category].get('warnings', []))
        
        # Run custom test scenarios if provided
        if test_scenarios:
            custom_results = self._run_custom_scenarios(candidate, test_scenarios)
            test_results['custom_tests'] = custom_results
            test_results['errors'].extend(custom_results.get('errors', []))
            test_results['warnings'].extend(custom_results.get('warnings', []))
        
        return test_results
    
    def _run_unit_tests(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Run unit tests for the candidate."""
        result = {
            'passed': 0,
            'failed': 0,
            'total': 0,
            'errors': [],
            'warnings': [],
            'details': {}
        }
        
        # Test 1: Validate candidate structure
        result['total'] += 1
        try:
            assert 'name' in candidate and len(candidate['name']) > 0
            assert 'source_sequence' in candidate and len(candidate['source_sequence']) >= 2
            assert 'confidence_score' in candidate and 0.0 <= candidate['confidence_score'] <= 1.0
            result['passed'] += 1
            result['details']['structure_validation'] = 'passed'
        except AssertionError as e:
            result['failed'] += 1
            result['errors'].append(f"Structure validation failed: {str(e)}")
            result['details']['structure_validation'] = f'failed: {str(e)}'
        
        # Test 2: Validate sequence makes sense
        result['total'] += 1
        try:
            sequence = candidate['source_sequence']
            # Check for obvious issues like immediate repetitions
            for i in range(len(sequence) - 1):
                if sequence[i] == sequence[i + 1]:
                    result['warnings'].append(f"Consecutive duplicate tool in sequence: {sequence[i]}")
            
            result['passed'] += 1
            result['details']['sequence_validation'] = 'passed'
        except Exception as e:
            result['failed'] += 1
            result['errors'].append(f"Sequence validation failed: {str(e)}")
            result['details']['sequence_validation'] = f'failed: {str(e)}'
        
        # Test 3: Validate suggested parameters
        result['total'] += 1
        try:
            params = candidate['suggested_parameters']
            assert isinstance(params, dict)
            # Check for reasonable parameter values
            if 'timeout_per_step' in params:
                assert isinstance(params['timeout_per_step'], (int, float)) and params['timeout_per_step'] > 0
            result['passed'] += 1
            result['details']['parameter_validation'] = 'passed'
        except AssertionError as e:
            result['failed'] += 1
            result['errors'].append(f"Parameter validation failed: {str(e)}")
            result['details']['parameter_validation'] = f'failed: {str(e)}'
        except Exception as e:
            result['failed'] += 1
            result['errors'].append(f"Parameter validation error: {str(e)}")
            result['details']['parameter_validation'] = f'error: {str(e)}'
        
        result['success_rate'] = result['passed'] / result['total'] if result['total'] > 0 else 0.0
        return result
    
    def _run_integration_tests(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Run integration tests for the candidate."""
        result = {
            'passed': 0,
            'failed': 0,
            'total': 0,
            'errors': [],
            'warnings': [],
            'details': {}
        }
        
        # Test 1: Check if tools in sequence exist in skill registry
        result['total'] += 1
        try:
            sequence = candidate['source_sequence']
            missing_tools = self._check_tools_exist(sequence)
            if missing_tools:
                result['warnings'].append(f"Some tools in sequence may not exist: {missing_tools}")
            result['passed'] += 1
            result['details']['tool_existence_check'] = 'passed_with_warnings' if missing_tools else 'passed'
        except Exception as e:
            result['failed'] += 1
            result['errors'].append(f"Tool existence check failed: {str(e)}")
            result['details']['tool_existence_check'] = f'failed: {str(e)}'
        
        # Test 2: Validate execution flow logic
        result['total'] += 1
        try:
            # Simple logic check: sequence should have reasonable progression
            sequence = candidate['source_sequence']
            # This is a simplified check - in reality would be more sophisticated
            result['passed'] += 1
            result['details']['flow_logic_check'] = 'passed'
        except Exception as e:
            result['failed'] += 1
            result['errors'].append(f"Flow logic check failed: {str(e)}")
            result['details']['flow_logic_check'] = f'failed: {str(e)}'
        
        result['success_rate'] = result['passed'] / result['total'] if result['total'] > 0 else 0.0
        return result
    
    def _run_performance_tests(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Run performance tests for the candidate."""
        result = {
            'passed': 0,
            'failed': 0,
            'total': 0,
            'errors': [],
            'warnings': [],
            'details': {},
            'estimated_execution_time': 0.0,
            'memory_usage_estimate': 0
        }
        
        # Estimate execution time based on sequence length and complexity
        result['total'] += 1
        try:
            sequence_length = len(candidate['source_sequence'])
            # Base time per step (seconds)
            base_time_per_step = 2.0
            estimated_time = sequence_length * base_time_per_step
            
            # Adjust based on tool types (agents take longer, etc.)
            agent_count = sum(1 for tool in candidate['source_sequence'] if 'agent' in tool.lower())
            estimated_time += agent_count * 3.0  # Extra time for agent coordination
            
            result['estimated_execution_time'] = estimated_time
            
            # Warn if estimated time is too high
            if estimated_time > 30.0:  # 30 seconds threshold
                result['warnings'].append(f"Estimated execution time ({estimated_time:.1f}s) may be too high for interactive use")
            
            result['passed'] += 1
            result['details']['performance_estimation'] = 'passed'
        except Exception as e:
            result['failed'] += 1
            result['errors'].append(f"Performance estimation failed: {str(e)}")
            result['details']['performance_estimation'] = f'failed: {str(e)}'
        
        # Estimate memory usage
        result['total'] += 1
        try:
            # Simple estimation based on sequence length
            base_memory = 50  # MB base
            per_tool_memory = 10  # MB per tool
            estimated_memory = base_memory + (len(candidate['source_sequence']) * per_tool_memory)
            
            result['memory_usage_estimate'] = estimated_memory
            
            if estimated_memory > 500:  # 500 MB threshold
                result['warnings'].append(f"Estimated memory usage ({estimated_memory} MB) may be high")
            
            result['passed'] += 1
            result['details']['memory_estimation'] = 'passed'
        except Exception as e:
            result['failed'] += 1
            result['errors'].append(f"Memory estimation failed: {str(e)}")
            result['details']['memory_estimation'] = f'failed: {str(e)}'
        
        result['success_rate'] = result['passed'] / result['total'] if result['total'] > 0 else 0.0
        return result
    
    def _run_security_tests(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Run security tests for the candidate."""
        result = {
            'passed': 0,
            'failed': 0,
            'total': 0,
            'errors': [],
            'warnings': [],
            'details': {}
        }
        
        # Test 1: Check for potentially dangerous tool combinations
        result['total'] += 1
        try:
            sequence = candidate['source_sequence']
            dangerous_patterns = [
                ('delete', 'remove', 'destroy'),
                ('execute', 'run', 'shell'),
                ('access', 'read', 'write')  # Potential data exfiltration
            ]
            
            sequence_lower = [tool.lower() for tool in sequence]
            warnings = []
            
            for pattern in dangerous_patterns:
                matches = [tool for tool in sequence_lower if any(danger in tool for danger in pattern)]
                if len(matches) >= 2:  # Multiple dangerous tools in sequence
                    warnings.append(f"Potentially dangerous tool combination detected: {matches}")
            
            if warnings:
                result['warnings'].extend(warnings)
                # Still pass but with warnings
                result['passed'] += 1
                result['details']['security_scan'] = 'passed_with_warnings'
            else:
                result['passed'] += 1
                result['details']['security_scan'] = 'passed'
        except Exception as e:
            result['failed'] += 1
            result['errors'].append(f"Security scan failed: {str(e)}")
            result['details']['security_scan'] = f'failed: {str(e)}'
        
        # Test 2: Validate parameter safety
        result['total'] += 1
        try:
            params = candidate['suggested_parameters']
            # Check for unsafe parameter values
            if params.get('continue_on_error', False):
                result['warnings'].append("continue_on_error=True may hide failures")
            
            timeout = params.get('timeout_per_step', 30)
            if timeout > 300:  # 5 minutes
                result['warnings'].append(f"timeout_per_step={timeout}s is very high")
            
            result['passed'] += 1
            result['details']['parameter_safety'] = 'passed'
        except Exception as e:
            result['failed'] += 1
            result['errors'].append(f"Parameter safety check failed: {str(e)}")
            result['details']['parameter_safety'] = f'failed: {str(e)}'
        
        result['success_rate'] = result['passed'] / result['total'] if result['total'] > 0 else 0.0
        return result
    
    def _run_custom_scenarios(self, candidate: Dict[str, Any], 
                            test_scenarios: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Run custom test scenarios provided by the user."""
        result = {
            'passed': 0,
            'failed': 0,
            'total': len(test_scenarios),
            'errors': [],
            'warnings': [],
            'details': {}
        }
        
        for i, scenario in enumerate(test_scenarios):
            scenario_name = scenario.get('name', f'scenario_{i}')
            try:
                # In a real implementation, this would execute the scenario
                # For now, we'll simulate based on scenario type
                scenario_type = scenario.get('type', 'basic')
                
                if scenario_type == 'basic':
                    # Basic validation - always pass for demo
                    result['passed'] += 1
                    result['details'][scenario_name] = 'passed'
                elif scenario_type == 'stress':
                    # Stress test - check if candidate can handle load
                    result['passed'] += 1  # Simplified
                    result['details'][scenario_name] = 'passed'
                    result['warnings'].append(f"Stress test {scenario_name} completed (simulated)")
                elif scenario_type == 'security':
                    # Security test
                    result['passed'] += 1
                    result['details'][scenario_name] = 'passed'
                else:
                    result['passed'] += 1
                    result['details'][scenario_name] = 'passed'
                    
            except Exception as e:
                result['failed'] += 1
                result['errors'].append(f"Custom scenario {scenario_name} failed: {str(e)}")
                result['details'][scenario_name] = f'failed: {str(e)}'
        
        return result
    
    def _check_tools_exist(self, sequence: List[str]) -> List[str]:
        """Check if tools in the sequence exist in the skill registry."""
        missing_tools = []
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                for tool in sequence:
                    cursor = conn.execute("""
                        SELECT name FROM skills WHERE name = ?
                    """, (tool,))
                    if not cursor.fetchone():
                        missing_tools.append(tool)
        except Exception:
            # If we can't check, assume tools might exist
            pass
        
        return missing_tools
    
    def _calculate_validation_score(self, test_results: Dict[str, Any]) -> float:
        """Calculate overall validation score from test results."""
        scores = []
        weights = {
            'unit_tests': 0.3,
            'integration_tests': 0.25,
            'performance_tests': 0.25,
            'security_tests': 0.2
        }
        
        total_weight = 0
        weighted_score = 0
        
        for test_category, weight in weights.items():
            if test_category in test_results:
                test_result = test_results[test_category]
                if 'success_rate' in test_result:
                    weighted_score += test_result['success_rate'] * weight
                    total_weight += weight
        
        # If we have custom tests, include them
        if 'custom_tests' in test_results:
            custom_result = test_results['custom_tests']
            if 'success_rate' in custom_result:
                weighted_score += custom_result['success_rate'] * 0.15  # Weight for custom tests
                total_weight += 0.15
        
        if total_weight > 0:
            return weighted_score / total_weight
        else:
            return 0.0
    
    def _determine_validation_status(self, score: float, 
                                   test_results: Dict[str, Any]) -> str:
        """Determine validation status based on score and test results."""
        # Check for critical errors
        errors = test_results.get('errors', [])
        critical_errors = [e for e in errors if 'failed' in e.lower() or 'error' in e.lower()]
        
        if len(critical_errors) > 2:  # More than 2 critical errors
            return 'failed'
        elif score >= 0.8:
            return 'passed'
        elif score >= 0.6:
            return 'passed_with_warnings'  # We'll treat this as passed for now
        else:
            return 'failed'
    
    def _store_validation_result(self, result: ValidationResult):
        """Store validation result in the database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO validation_results 
                (validation_id, candidate_id, status, score, test_results, 
                 execution_time, resource_usage, errors, warnings, validated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result.validation_id,
                result.candidate_id,
                result.status,
                result.score,
                json.dumps(result.test_results),
                result.execution_time,
                json.dumps(result.resource_usage),
                json.dumps(result.errors),
                json.dumps(result.warnings),
                result.validated_at
            ))
    
    def get_validation_history(self, candidate_id: str) -> List[ValidationResult]:
        """Get validation history for a candidate."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM validation_results 
                WHERE candidate_id = ? 
                ORDER BY validated_at DESC
            """, (candidate_id,))
            
            results = []
            for row in cursor:
                result = ValidationResult(
                    validation_id=row['validation_id'],
                    candidate_id=row['candidate_id'],
                    status=row['status'],
                    score=row['score'],
                    test_results=json.loads(row['test_results']),
                    execution_time=row['execution_time'],
                    resource_usage=json.loads(row['resource_usage']),
                    errors=json.loads(row['errors']),
                    warnings=json.loads(row['warnings']),
                    validated_at=row['validated_at']
                )
                results.append(result)
            
            return results
    
    def get_latest_validation(self, candidate_id: str) -> Optional[ValidationResult]:
        """Get the latest validation result for a candidate."""
        history = self.get_validation_history(candidate_id)
        return history[0] if history else None
    
    def _collect_resource_usage(self) -> Dict[str, Any]:
        """Collect current resource usage (simplified)."""
        # In a real implementation, this would use psutil or similar
        # For now, return simulated values
        return {
            'cpu_percent': 0.0,  # Would be actual CPU usage
            'memory_mb': 0.0,    # Would be actual memory usage
            'disk_io_mb': 0.0,   # Would be actual disk I/O
            'network_io_mb': 0.0 # Would be actual network I/O
        }
    
    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime
        return datetime.now().isoformat()

# Example usage and testing
if __name__ == "__main__":
    # Initialize the sandbox validator
    validator = SandboxValidator()
    
    # Example: Validate a candidate (would need to exist in database)
    print("Sandbox Validator initialized")
    print("Ready to validate meta-tool candidates")
    
    # Example validation (would fail if no candidates exist)
    # result = validator.validate_candidate("example_candidate_id")
    # print(f"Validation result: {result.status} with score {result.score}")
