#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Contract extractor - dynamically extract method contracts from sub prompts"""

import re
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class DynamicContract:
    """Dynamic contract object (extracted from sub prompts)"""
    
    stage: str = ""
    stage_name: str = ""

    required_methods: Dict[str, str] = field(default_factory=dict)  
    alternative_method_groups: List[Dict[str, List[Tuple[str, str]]]] = field(default_factory=list)  
    recommended_methods: Dict[str, str] = field(default_factory=dict)
    method_patterns: Dict[str, str] = field(default_factory=dict)  
    mandatory_files: List[str] = field(default_factory=lambda: ['main_output.csv', 'analysis_summary.json'])
    recommended_files: List[str] = field(default_factory=list)
    optional_files: List[str] = field(default_factory=list)
    has_validation_template: bool = False
    validation_patterns: List[str] = field(default_factory=list)
    required_packages: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'stage': self.stage,
            'stage_name': self.stage_name,
            'required_methods': self.required_methods,
            'method_patterns': self.method_patterns,
            'mandatory_files': self.mandatory_files,
            'recommended_files': self.recommended_files,
            'optional_files': self.optional_files,
            'has_validation_template': self.has_validation_template,
            'validation_patterns': self.validation_patterns,
            'required_packages': self.required_packages
        }


class ContractExtractor:
    """Extract method contracts from sub prompts dynamically"""

    METHOD_PATTERNS = {
        'GLMM': r'glmer\(',
        'LMM': r'lmer\(',
        'Cox': r'coxph\(',
        'survey': r'svydesign\(',
        'mice': r'mice\(',
        'log_binomial': r'binomial\s*\(\s*link\s*=\s*["\']log["\']',
        'quasipoisson': r'(family\s*=\s*)?quasipoisson',
        'poisson': r'(family\s*=\s*)?poisson',
        'logistic': r'family\s*=\s*binomial',
    }
    
    METHOD_SYNONYMS = {
        'GLMM': ['GLMM', 'glmer', 'Generalized Linear Mixed Model', 'generalized linear mixed model', 
                 'mixed effects model', 'Mixed-effects model', 'random effects model'],
        'LMM': ['LMM', 'lmer', 'Linear Mixed Model', 'linear mixed model', 
                'linear mixed effects', 'Linear mixed-effects model'],
        'Cox': ['Cox', 'coxph', 'Cox regression', 'cox regression', 
                'Cox proportional hazards', 'survival analysis', 'Survival analysis'],
        'survey': ['survey', 'svydesign', 'Survey design', 'survey design', 
                   'complex survey', 'Survey-weighted'],
        'mice': ['MICE', 'mice', 'Multiple Imputation', 'multiple imputation', 
                 'Multiple imputation by chained equations'],
        'log_binomial': ['log-binomial', 'log binomial', 'binomial(link="log")', 
                         'binomial regression with log link', 'Log-binomial regression'],
        'quasipoisson': ['quasipoisson', 'quasi-Poisson', 'Quasi-Poisson', 
                         'modified Poisson', 'Modified Poisson'],
        'poisson': ['Poisson', 'poisson', 'Poisson regression', 'poisson regression'],
        'logistic': ['logistic', 'Logistic', 'logistic regression', 'Logistic regression', 
                     'binomial regression', 'binary logistic'],
    }
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def extract_from_file(self, prompt_file_path: str) -> DynamicContract:
        """
        Extract method contracts from sub prompt file
        
        Args:
            prompt_file_path: Sub prompt file path
            
        Returns:
            Dynamic contract object
        """
        from pathlib import Path

        filename = Path(prompt_file_path).stem
        parts = filename.split('_')
        stage = parts[1] if len(parts) > 1 else "unknown"
        stage_name = "_".join(parts[2:]) if len(parts) > 2 else "unknown"

        with open(prompt_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return self.extract_from_content(content, stage, stage_name)
    
    def extract_from_content(self, content: str, stage: str = "", stage_name: str = "") -> DynamicContract:
        """
        Extract method contracts from sub prompt content

        Args:
            content: Sub prompt text content
            stage: Stage number
            stage_name: Stage name
            
        Returns:
            Dynamic contract object
        """
        contract = DynamicContract(stage=stage, stage_name=stage_name)

        methods_result = self._extract_methods(content)
        contract.required_methods = methods_result.get('required', {})
        contract.alternative_method_groups = methods_result.get('alternatives', [])
        contract.recommended_methods = methods_result.get('recommended', {})

        contract.method_patterns = {**contract.required_methods, **contract.recommended_methods}

        contract.recommended_files, contract.optional_files = self._extract_output_files(content)

        contract.has_validation_template = self._check_validation_template(content)
        if contract.has_validation_template:
            contract.validation_patterns = self._extract_validation_patterns(content)

        contract.required_packages = self._extract_packages(content)
        
        self.logger.info(
            f"Extract method contracts from sub prompt: {stage} - "
            f"Required methods={len(contract.required_methods)}, "
            f"Alternative method groups={len(contract.alternative_method_groups)}, "
            f"Recommended methods={len(contract.recommended_methods)}, "
            f"Files={len(contract.recommended_files)}"
        )
        
        return contract
    
    def _extract_methods(self, content: str) -> Dict:
        """Extract required statistical methods
        
        Returns:
            {
                'required': {},  # Required methods
                'alternatives': [],  # Alternative method groups
                'recommended': {}  # Recommended methods
            }
        """
        content_cleaned = content.replace('Box-Cox', 'BoxCox_transform')
        content_cleaned = content_cleaned.replace('box-cox', 'boxcox_transform')
        
        core_section = self._extract_section(content_cleaned, ["## Core statistical methods"])
        exec_section = self._extract_section(content_cleaned, ["## Execution requirements"])
        search_content = core_section + "\n" + exec_section
        
        raw_mentions = {}  # {standard name: original keyword list}
        for standard_name, synonyms in self.METHOD_SYNONYMS.items():
            for synonym in synonyms:
                if synonym in search_content or synonym.lower() in search_content.lower():
                    if standard_name not in raw_mentions:
                        raw_mentions[standard_name] = []
                    raw_mentions[standard_name].append(synonym)
        
        alternatives = self._extract_alternative_groups(search_content, raw_mentions)
        
        alt_methods_set = set()
        for group in alternatives:
            for methods_list in group.values():
                for method_name, _ in methods_list:
                    alt_methods_set.add(method_name)
        
        recommended = {}
        for standard_name in raw_mentions.keys():
            if standard_name not in alt_methods_set:
                if standard_name in self.METHOD_PATTERNS:
                    recommended[standard_name] = self.METHOD_PATTERNS[standard_name]
        
        self.logger.debug(
            f"Extract methods: Alternative groups={len(alternatives)}, Recommended={list(recommended.keys())}"
        )
        
        return {
            'required': {},     
            'alternatives': alternatives,
            'recommended': recommended
        }
    
    def _extract_alternative_groups(self, content: str, raw_mentions: Dict) -> List[Dict]:
        """Identify alternative method groups
        
        Identification patterns:
        - "If...then..."   
        - "Preferred...then...Alternative..."   
        - "If convergence issues then...then...use..."
        """
        alternatives = []

        if 'If convergence issues then...then...use...' in content:
            if 'log_binomial' in raw_mentions and 'quasipoisson' in raw_mentions:
                alternatives.append({
                    'Binary outcome model': [
                        ('log_binomial', self.METHOD_PATTERNS['log_binomial']),
                        ('quasipoisson', self.METHOD_PATTERNS['quasipoisson']),
                    ]
                })
                self.logger.debug("Identify alternative group: Log binomial <-> Quasipoisson")
        
        return alternatives
    
    def _extract_output_files(self, content: str) -> tuple[List[str], List[str]]:
        """Extract output file requirements"""
        recommended = []
        optional = []
        
        output_section = self._extract_section(content, ["## Output requirements", "## Output files"])
        
        if output_section:
            file_pattern = r'`([^`]+\.(csv|json|png|pdf|txt|rds|RDS))`'
            files = re.findall(file_pattern, output_section)
            
            for filename, ext in files:
                if filename not in ['main_output.csv', 'analysis_summary.json']:
                    if 'Required' in output_section or 'Required' in output_section:
                        recommended.append(filename)
                    else:
                        optional.append(filename)
        
        return recommended, optional
    
    def _check_validation_template(self, content: str) -> bool:
        """Check if there is a validation template requirement"""
        return '## Validation template' in content or '## Validation requirements' in content
    
    def _extract_validation_patterns(self, content: str) -> List[str]:
        """Extract validation patterns from validation template"""
        patterns = []
        
        validation_section = self._extract_section(content, ["## Validation template", "## Validation requirements"])
        
        if validation_section:
            if 'if(!exists(' in validation_section or 'if (!exists(' in validation_section:
                patterns.append('if(!exists(')
            if 'stop(' in validation_section:
                patterns.append('stop(')
            if 'cat(' in validation_section:
                patterns.append('cat(')
        
        return patterns
    
    def _extract_packages(self, content: str) -> List[str]:
        """Extract R package requirements"""
        packages = []

        package_patterns = [
            r'library\(([^)]+)\)',
            r'use\s*([a-zA-Z0-9]+)\s*package',
            r'need\s*([a-zA-Z0-9]+)\s*package',
        ]
        
        for pattern in package_patterns:
            matches = re.findall(pattern, content)
            packages.extend(matches)

        if any(word in content for word in ['GLMM', 'glmer', 'lmer', 'Mixed-effects model']):
            packages.append('lme4')
        
        if any(word in content for word in ['Cox', 'coxph', 'Survival analysis']):
            packages.append('survival')
        
        if any(word in content for word in ['Survey', 'survey', 'svydesign']):
            packages.append('survey')
        
        if any(word in content for word in ['mice', 'Multiple imputation']):
            packages.append('mice')

        packages = list(dict.fromkeys(packages))
        
        return packages
    
    def _extract_section(self, content: str, section_headers: List[str]) -> str:
        """Extract the content of the specified section"""
        for header in section_headers:
            if header in content:
                start = content.find(header)
                if start == -1:
                    continue
                
                rest = content[start + len(header):]
                next_section = re.search(r'\n#{1,2}\s+', rest)
                
                if next_section:
                    end = start + len(header) + next_section.start()
                    return content[start:end]
                else:
                    return content[start:]
        
        return ""


__all__ = ['ContractExtractor', 'DynamicContract']

