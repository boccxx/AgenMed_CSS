#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Estimand Classifier - Distinguish causal vs predictive research goals"""

import logging
import re
from typing import Dict, Any, List, Optional


class EstimandClassifier:
    """Classify research question and enforce appropriate analysis framework"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def classify_research_goal(
        self,
        protocol_text: str,
        objective_section: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Classify research goal as causal, predictive, or descriptive
        
        Args:
            protocol_text: Full protocol text
            objective_section: Extracted objective section if available
            
        Returns:
            Classification result with enforced framework
        """
        result = {
            'research_type': 'descriptive',  # causal | predictive | descriptive
            'estimand': None,
            'exposure': None,
            'outcome': None,
            'required_adjustments': [],
            'forbidden_terms': [],
            'required_terms': [],
            'modeling_framework': 'exploratory'
        }
        
        text = objective_section if objective_section else protocol_text
        text_lower = text.lower()
        
        # Causal keywords
        causal_keywords = [
            'effect of', 'impact of', 'influence of', 'caused by',
            'causal', 'intervention', 'treatment effect',
            'exposure', 'risk factor', 'etiology'
        ]
        
        # Predictive keywords
        predictive_keywords = [
            'predict', 'prediction', 'forecasting', 'risk score',
            'classification', 'diagnostic', 'prognostic',
            'accuracy', 'auc', 'sensitivity', 'specificity'
        ]
        
        # Count keyword occurrences
        causal_score = sum(1 for kw in causal_keywords if kw in text_lower)
        predictive_score = sum(1 for kw in predictive_keywords if kw in text_lower)
        
        if causal_score > predictive_score:
            result['research_type'] = 'causal'
            result['modeling_framework'] = 'causal_inference'
            result = self._configure_causal_framework(result, text)
        elif predictive_score > 0:
            result['research_type'] = 'predictive'
            result['modeling_framework'] = 'prediction'
            result = self._configure_predictive_framework(result, text)
        else:
            result['research_type'] = 'descriptive'
            result['modeling_framework'] = 'descriptive'
            result = self._configure_descriptive_framework(result, text)
        
        result['covariate_strategy'] = self._detect_covariate_strategy(text)
        
        return result
    
    def _configure_causal_framework(
        self,
        result: Dict[str, Any],
        text: str
    ) -> Dict[str, Any]:
        """Configure requirements for causal inference"""
        result['estimand'] = 'average_causal_effect'  # or specific estimand
        
        # Extract exposure and outcome
        # Simple heuristic - can be enhanced with NLP
        exposure_match = re.search(
            r'(?:effect of|impact of|exposure to)\s+([A-Za-z_]+)',
            text,
            re.IGNORECASE
        )
        outcome_match = re.search(
            r'(?:on|outcome:)\s+([A-Za-z_]+)',
            text,
            re.IGNORECASE
        )
        
        if exposure_match:
            result['exposure'] = exposure_match.group(1)
        if outcome_match:
            result['outcome'] = outcome_match.group(1)
        
        result['required_adjustments'] = [
            'Identify confounders from DAG or domain knowledge',
            'Exclude mediators and colliders from main model',
            'Check positivity and overlap assumptions',
            'Consider effect modification in stratified analysis'
        ]
        
        result['forbidden_terms'] = [
            'prediction accuracy',
            'model performance',
            'AUC',
            'classification'
        ]
        
        result['required_terms'] = [
            'causal effect',
            'adjusted effect estimate',
            'confounding control',
            'estimand'
        ]
        
        return result
    
    def _configure_predictive_framework(
        self,
        result: Dict[str, Any],
        text: str
    ) -> Dict[str, Any]:
        """Configure requirements for predictive modeling"""
        result['estimand'] = 'prediction_accuracy'
        
        result['required_adjustments'] = [
            'Train-test split or cross-validation',
            'Report discrimination (AUC, C-statistic)',
            'Report calibration metrics',
            'Variable selection based on predictive performance'
        ]
        
        result['forbidden_terms'] = [
            'causal effect',
            'treatment effect',
            'adjusted for confounding',
            'estimand'
        ]
        
        result['required_terms'] = [
            'prediction',
            'model performance',
            'discrimination',
            'calibration'
        ]
        
        return result
    
    def _configure_descriptive_framework(
        self,
        result: Dict[str, Any],
        text: str
    ) -> Dict[str, Any]:
        """Configure requirements for descriptive analysis"""
        result['estimand'] = 'association'
        
        result['required_adjustments'] = [
            'Report associations without causal interpretation',
            'Focus on strength and direction of associations',
            'Multiple testing correction if appropriate'
        ]
        
        result['forbidden_terms'] = [
            'causal effect',
            'treatment effect',
            'prediction accuracy'
        ]
        
        result['required_terms'] = [
            'association',
            'correlation',
            'relationship'
        ]
        
        return result
    
    def _detect_covariate_strategy(self, text: str) -> Dict[str, Any]:
        """
        Detect covariate adjustment strategy from protocol
        
        Args:
            text: Protocol text
            
        Returns:
            Strategy specification with mode and constraints
        """
        text_lower = text.lower()
        
        dag_keywords = ['dag', 'directed acyclic', 'causal diagram', 'backdoor', 
                       'a priori', 'prespecified covariate', 'minimal adjustment']
        baseline_keywords = ['baseline imbalance', 'unbalanced variable', 
                           'standardized mean difference', 'smd', 'propensity']
        
        has_dag = any(kw in text_lower for kw in dag_keywords)
        has_baseline = any(kw in text_lower for kw in baseline_keywords)
        
        mediator_pattern = re.search(
            r'(?:mediator|mediation|intermediate variable|pathway).*?:?\s*([A-Za-z_,\s]+)',
            text,
            re.IGNORECASE
        )
        mediators = []
        if mediator_pattern:
            mediators = [m.strip() for m in mediator_pattern.group(1).split(',')]
        
        if has_dag:
            return {
                'mode': 'DAG_prespecified',
                'forbidden_practices': [
                    'baseline_imbalance_selection',
                    'p_value_selection',
                    'stepwise_selection',
                    'including_mediators_in_main_model'
                ],
                'mediators': mediators,
                'enforcement': 'strict'
            }
        elif has_baseline:
            return {
                'mode': 'data_driven',
                'allowed_practices': [
                    'baseline_imbalance_selection',
                    'smd_threshold_selection'
                ],
                'forbidden_practices': [
                    'including_outcomes',
                    'including_colliders'
                ],
                'enforcement': 'moderate'
            }
        else:
            return {
                'mode': 'flexible',
                'allowed_practices': [
                    'clinical_judgment',
                    'literature_based'
                ],
                'enforcement': 'minimal'
            }
    
    def validate_analysis_alignment(
        self,
        research_type: str,
        r_code: str,
        analysis_summary: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Validate if analysis aligns with declared research type
        
        Returns:
            Validation result with alignment issues
        """
        validation = {
            'aligned': True,
            'violations': [],
            'recommendations': []
        }
        
        if research_type == 'causal':
            # Check for DAG or confounder specification
            if 'dag' not in r_code.lower() and 'confounder' not in r_code.lower():
                validation['violations'].append(
                    'Causal analysis requires explicit confounder specification'
                )
            
            # Check for mediator/collider warnings
            if 'mediator' in r_code.lower() or 'collider' in r_code.lower():
                validation['recommendations'].append(
                    'Verify mediators/colliders are handled in separate stratified analysis'
                )
            
            # Check for prediction metrics
            if any(term in r_code.lower() for term in ['auc', 'roc', 'accuracy']):
                validation['violations'].append(
                    'Causal analysis should not report prediction metrics'
                )
                validation['aligned'] = False
        
        elif research_type == 'predictive':
            # Check for train-test split
            if 'train' not in r_code.lower() and 'cv' not in r_code.lower():
                validation['violations'].append(
                    'Predictive modeling requires train-test split or cross-validation'
                )
            
            # Check for causal language
            if any(term in r_code.lower() for term in ['causal', 'confound', 'estimand']):
                validation['violations'].append(
                    'Predictive modeling should not use causal inference language'
                )
                validation['aligned'] = False
        
        return validation
    
    def generate_analysis_constraints(
        self,
        research_type: str
    ) -> str:
        """Generate analysis constraints for R code generation prompt"""
        
        if research_type == 'causal':
            return """
**CAUSAL INFERENCE FRAMEWORK (MANDATORY)**:
- Define estimand: e.g., "Effect of [exposure] on [outcome]"
- Specify exposure variable and outcome variable explicitly
- Identify confounding set from DAG or prior knowledge
- DO NOT include mediators or colliders in main adjustment set
- Report effect estimates (PR, OR, HR) with causal interpretation
- Check positivity/overlap for exposure groups
- Consider interaction terms for effect modification (separate stratified analysis)
- FORBIDDEN: prediction metrics (AUC, accuracy), "model performance" language
- REQUIRED: "causal effect", "adjusted for confounding", "estimand"
"""
        
        elif research_type == 'predictive':
            return """
**PREDICTIVE MODELING FRAMEWORK (MANDATORY)**:
- Goal: maximize prediction accuracy, NOT causal inference
- Use train-test split or cross-validation
- Report discrimination metrics: AUC, C-statistic, sensitivity, specificity
- Report calibration: calibration plot, Brier score
- Variable selection based on predictive performance (not confounding theory)
- FORBIDDEN: "causal effect", "confounder adjustment", "estimand"
- REQUIRED: "prediction", "model performance", "discrimination", "calibration"
"""
        
        else:  # descriptive
            return """
**DESCRIPTIVE ANALYSIS FRAMEWORK (MANDATORY)**:
- Goal: describe associations, NOT causal inference or prediction
- Report associations with confidence intervals
- Do not interpret as causal effects
- Focus on strength and direction of associations
- Multiple testing correction if exploring many associations
- FORBIDDEN: "causal effect", "prediction accuracy"
- REQUIRED: "association", "correlation", "relationship observed in this sample"
"""

