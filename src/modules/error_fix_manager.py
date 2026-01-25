#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Error fix manager - intelligent R code error fixing system based on knowledge base"""

import os
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging


class ErrorFixManager:
    """Error fix manager, responsible for fixing R code errors"""
    
    def __init__(self):
        """
        Initialize error fix manager
        """
        self.logger = logging.getLogger(__name__)

        self.error_patterns = {
            'survey_weight_missing': r'object[\'"]survey_weight[\'"] not found',
            'package_not_found': r'there is no package called|不存在叫.*这个名称的程序包',
            'function_not_found': r'could not find function',
            'object_not_found': r'object.*not found',
            'data_type_error': r'should be a matrix or data frame|must be numeric|必需是数值|无法 xtfrm',
            'column_mismatch': r'names do not match previous names',
            'dimension_mismatch': r'arguments imply differing number of rows|参数值意味着不同的行数',
            'mice_data_structure': r'参数值意味着不同的行数.*\d+.*\d+.*\d+.*\d+.*\d+',
            'model_convergence': r'Model failed to converge|nearly unidentifiable',
            'mice_collinear': r'constant and/or collinear variables|No predictors were left',
            'zero_length_variable': r'cannot use zero-length variable name|不能用零长度变量名',
            'ggplot_missing_column': r'Problem while computing aesthetics|object not found.*in.*aesthetics|找不到对象.*|找不到对象',
            'subscript_out_of_bounds': r'下标出界|subscript out of bounds',
            'invalid_dollar_operator': r'\$ operator is invalid for atomic vectors',
            'survey_design_missing_vars': r'all variables must be in design= argument',
            'undefined_columns_selected': r'选择了未定义的列|undefined columns selected',
            'evalue_measure_error': r'evalue\.default.*找不到对象[\'"]measure[\'"]|找不到对象[\'"]measure[\'"].*evalue',
        }

        self.fix_stats = {
            'total_attempts': 0,
            'successful_fixes': 0,
            'llm_fixes': 0
        }
    
    def identify_error_type(self, error_message: str) -> Optional[str]:
        """
        Identify error type using regular expressions                                              
        
        Args:
            error_message: Error message
            
        Returns:
            Error type (if identified)
        """
        for error_type, pattern in self.error_patterns.items():
            if re.search(pattern, error_message, re.IGNORECASE):
                self.logger.info(f"Identified error type: {error_type}")
                return error_type
        
        return None
    
    def apply_simple_fix(self, code: str, error_type: str) -> Tuple[str, bool]:
        """
        Apply simple quick fix
        
        Args:
            code: Original R code
            error_type: Error type
            
        Returns:
            (Fixed code, whether the fix was applied)
        """
        modified_code = code
        fix_applied = False
        
        try:
            if error_type == 'survey_weight_missing':
                if 'survey_weight' not in modified_code:
                    weight_code = '\nif(!"survey_weight" %in% names(data)) {\n  data$survey_weight <- 1\n  cat("No survey weight variable, create equal weight variable\\n")\n} else {\n  cat("Use existing survey_weight variable\\n")\n}\n'
                    
                    if '# 3. Basic data cleaning' in modified_code:
                        modified_code = modified_code.replace('# 3. Basic data cleaning', weight_code + '\n# 3. Basic data cleaning')
                    elif 'library(dplyr)' in modified_code:
                        modified_code = modified_code.replace('library(dplyr)', weight_code + '\nlibrary(dplyr)')
                    else:
                        modified_code = modified_code.replace('data <- read.csv', 'data <- read.csv') + weight_code
                    
                    fix_applied = True
                    self.logger.info("Added survey_weight variable creation code")
            
            elif error_type == 'package_not_found':
                if 'BaylorEdPsych' in code:
                    modified_code = modified_code.replace('library(BaylorEdPsych)', 'library(naniar)')
                    fix_applied = True
                    self.logger.info("Replaced BaylorEdPsych with naniar package")
                elif 'qgraph' in code:
                    lines = modified_code.split('\n')
                    filtered_lines = [line for line in lines if 'qgraph' not in line]
                    modified_code = '\n'.join(filtered_lines)
                    fix_applied = True
                    self.logger.info("Removed qgraph related code")
            
            elif error_type == 'column_mismatch':
                if 'rbind(' in modified_code:
                    modified_code = modified_code.replace('rbind(', 'dplyr::bind_rows(')
                    if 'library(dplyr)' not in modified_code:
                        modified_code = 'library(dplyr)\n' + modified_code
                    fix_applied = True
                    self.logger.info("Replaced rbind with bind_rows to fix column name mismatch error")
            
            elif error_type == 'mice_data_structure':
                self.logger.info("MICE data structure inconsistency detected - requires LLM fix with data validation")
            
            elif error_type == 'dimension_mismatch':
                if 'lapply' in modified_code and 'as.data.frame' in modified_code:
                    self.logger.info("Dimension mismatch in lapply/as.data.frame - requires LLM fix with row count validation")
            
            elif error_type == 'function_not_found':
                if 'gather' in code and 'library(tidyr)' not in modified_code:
                    modified_code = 'library(tidyr)\n' + modified_code
                    fix_applied = True
                    self.logger.info("Added library(tidyr) to fix gather function error")
                elif 'dotplot' in code and 'library(lattice)' not in modified_code:
                    modified_code = 'library(lattice)\n' + modified_code
                    fix_applied = True
                    self.logger.info("Added lattice package to support dotplot function")
            
            elif error_type in ['mice_collinear', 'model_convergence']:
                self.logger.info(f"{error_type} error - suggest using LLM to fix")
        
        except Exception as e:
            self.logger.error(f"Simple fix failed: {e}")
            return code, False
        
        return modified_code, fix_applied
    
    def get_simple_fix_prompt(self, original_code: str, error_message: str, 
                            data_summary: str = None, data_snapshot: str = None, fix_history: List = None,
                            sub_prompt_content: str = None) -> str:
        """
        Generate fix prompt (supports progressive enhancement)
        
        Args:
            original_code: Original code
            error_message: Error message
            data_summary: Data summary information
            data_snapshot: Current stage data snapshot (real-time, accurate)
            fix_history: Fix history record (advanced repair strategy)
            
        Returns:
            Fix prompt
        """
        prompt_parts = [
            "The following R code execution resulted in an error, please analyze the error reason and provide the corrected complete code:",
            "",
            "**Error information:**",
            f"```",
            f"{error_message}",
            f"```",
        ]

        if fix_history and len(fix_history) > 0:
            prompt_parts.extend([
                "",
                "**All previous fix attempts failed, please use a different approach:**",
                "",
            ])
            for i, hist in enumerate(fix_history[-3:], 1):  
                prompt_parts.append(f"Attempt {hist.get('attempt', i)}: {hist.get('error', '')[:100]}...")
            prompt_parts.extend([
                "",
                "**Note:**",
                "- The previous repair methods did not solve the problem",
                "- It may be necessary to re-examine the entire code logic",
                "- Consider whether a more fundamental modification is needed (such as changing the statistical method, simplifying the model, etc.)",
                "",
            ])

        if data_snapshot:
            prompt_parts.extend([
                "",
                "**Current stage data actual situation (please strictly follow):**",
                f"```",
                f"{data_snapshot}",
                f"```",
                "",
                "**Important note:**",
                "- The actual data may be different from your expectations",
                "- Pay special attention to the actual number of levels of factor variables",
                "- Do not use strict stop() verification, but should use friendly data processing",
                "- For example: do not assume that the variable is always binary, but process it according to the actual number of levels",
            ])

        if sub_prompt_content:
            prompt_parts.extend([
                "",
                "**Original sub prompt key requirements (please strictly follow):**",
                "```",
                f"{sub_prompt_content}",
                "```",
                "",
                "- Do not change the established statistical method and downgrade order when repairing",
                "- If the current method fails, you must try the alternative solutions in the sub prompt in order",
            ])

        prompt_parts.extend([
            "",
            "**Original code:**",
            f"```r",
            f"{original_code}",
            f"```"
        ])
        
        if data_summary:
            prompt_parts.extend([
                "",
                "**Additional data structure information:**",
                f"{data_summary}"
            ])
        
        # 针对特定错误类型添加特殊指导
        special_guidance = []
        if ('找不到对象' in error_message or 'object not found' in error_message.lower() or 'Problem while computing aesthetics' in error_message) and ('geom_line' in error_message or 'ggplot' in error_message or 'Problem while computing aesthetics' in error_message):
            special_guidance.extend([
                "",
                "**⚠️ Critical: ggplot2 Missing Column Error Detected**",
                "",
                "The error 'object not found' (找不到对象) in ggplot2 indicates that a column/variable referenced in the plot aesthetics does not exist in the data frame.",
                "",
                "**Common causes:**",
                "1. **Column name mismatch**: The column name used in `aes()` or `aes_string()` does not match the actual column name in the data frame",
                "2. **Missing data preparation**: The required column was not created before plotting (e.g., 'Predicted_Probability' not computed)",
                "3. **Variable name typo**: Typo in variable name (e.g., 'Predicted_Prob' vs 'Predicted_Probability')",
                "4. **Data frame not passed correctly**: The data frame containing the column was not passed to `ggplot()` or `geom_line()`",
                "",
                "**Required fixes:**",
                "1. **Check column names**: Before plotting, verify the column exists: `if(!'Predicted_Probability' %in% names(df)) { stop('Column missing') }`",
                "2. **Create missing columns**: If the column should exist but doesn't, create it before plotting:",
                "   ```r",
                "   df$Predicted_Probability <- predict(model, type = 'response')",
                "   ```",
                "3. **Use correct column names**: Check the actual column names in the data frame: `names(df)` or `colnames(df)`",
                "4. **Validate data frame structure**: Before `geom_line()`, ensure the data frame has all required columns:",
                "   ```r",
                "   required_cols <- c('Predicted_Probability', 'x_variable')",
                "   missing_cols <- setdiff(required_cols, names(df))",
                "   if(length(missing_cols) > 0) {",
                "     stop(paste('Missing columns:', paste(missing_cols, collapse=', ')))",
                "   }",
                "   ```",
                "5. **Use data parameter**: Ensure the data frame is passed correctly: `ggplot(data = df, aes(x = x_var, y = Predicted_Probability))`",
                "6. **Check variable names in model output**: If using model predictions, verify the exact column names returned by `predict()` or model summary functions",
                "",
            ])
        elif 'cannot use zero-length variable name' in error_message.lower() or '不能用零长度变量名' in error_message:
            special_guidance.extend([
                "",
                "**⚠️ Critical: Zero-Length Variable Name Error Detected**",
                "",
                "The error 'cannot use zero-length variable name' occurs when trying to use an empty string (\"\") as a variable name.",
                "",
                "**Common causes in MICE code:**",
                "1. **names(meth) contains empty strings**: When creating imputation_methods data.frame, if meth has empty string keys, filtering with `names(meth) != \"\"` may not be sufficient",
                "2. **Column names with empty strings**: Data may have columns with empty names",
                "3. **Subsetting with empty names**: Operations like `meth[names(meth) != \"\"]` may still preserve empty string keys",
                "",
                "**Required fixes:**",
                "1. **Filter empty names properly**: Use `nzchar()` to filter: `valid_names <- names(meth)[nzchar(names(meth))]`",
                "2. **Check data column names**: Ensure `names(data)` has no empty strings before MICE",
                "3. **Safe data.frame creation**: When creating imputation_methods, use:",
                "   ```r",
                "   valid_names <- names(meth)[nzchar(names(meth)) & names(meth) != \"\"]",
                "   if(length(valid_names) > 0) {",
                "     imputation_methods <- data.frame(",
                "       Variable = valid_names,",
                "       Method = meth[valid_names],",
                "       stringsAsFactors = FALSE",
                "     )",
                "   } else {",
                "     imputation_methods <- data.frame(Variable = character(0), Method = character(0))",
                "   }",
                "   ```",
                "4. **Validate before use**: Always check `nzchar(names(x))` before using names in data.frame creation",
                "",
            ])
        elif 'arguments imply differing number of rows' in error_message.lower() or '参数值意味着不同的行数' in error_message:
            special_guidance.extend([
                "",
                "**⚠️ Critical: Data Structure Consistency Issue Detected**",
                "",
                "The error indicates that when combining results from multiple MICE imputed datasets, different results have different row counts (e.g., 20, 0, 3, 39, 11 rows).",
                "",
                "**Required fixes:**",
                "1. **Validate each result before combining**: Check that each lapply iteration returns a result with consistent structure",
                "2. **Handle empty results**: If some iterations return 0 rows, either skip them or fill with NA",
                "3. **Ensure type consistency**: Convert all results to the same data type before combining (e.g., all numeric or all data.frame)",
                "4. **Use safe combination**: Instead of direct as.data.frame(list(...)), use:",
                "   - Check lengths first: lengths <- sapply(results, length); if(length(unique(lengths)) > 1) { handle inconsistency }",
                "   - Or use: do.call(rbind, lapply(results, function(x) if(nrow(x) == 0) NULL else x))",
                "5. **For MICE imputed data**: Ensure each imputed dataset is processed identically and returns the same structure",
                "",
            ])
        
        if "'x' must be numeric" in error_message.lower() or '必需是数值' in error_message:
            special_guidance.extend([
                "",
                "**⚠️ Data Type Issue Detected**",
                "",
                "A variable expected to be numeric is not numeric (possibly factor or character after MICE imputation).",
                "",
                "**Required fixes:**",
                "1. **Check variable types after MICE**: Use class() or is.numeric() to verify types",
                "2. **Convert if needed**: Use as.numeric(as.character(x)) for factors, or ensure MICE preserves numeric types",
                "3. **For Age or other continuous variables**: Ensure they remain numeric throughout the imputation process",
                "",
            ])
        elif 'subscript out of bounds' in error_message.lower() or '下标出界' in error_message:
            special_guidance.extend([
                "",
                "**⚠️ Critical: Subscript Out of Bounds Error Detected**",
                "",
                "The error 'subscript out of bounds' (下标出界) occurs when trying to access a row or column that doesn't exist in a matrix or data frame.",
                "",
                "**Common causes:**",
                "1. **Row name mismatch**: The row name used in indexing (e.g., `coef_summary[\"Exercise_FrequencyDaily\", \"Estimate\"]`) doesn't match actual row names",
                "2. **Factor level naming**: Factor levels may have different names than expected (e.g., 'Daily' vs 'Exercise_FrequencyDaily')",
                "3. **Model coefficient names**: Coefficient names from model summary may differ from expected format",
                "",
                "**Required fixes:**",
                "1. **Check actual row/column names**: Before indexing, verify names: `rownames(coef_summary)` or `names(coef_summary)`",
                "2. **Use safe indexing**: Instead of direct indexing, use:",
                "   ```r",
                "   if(\"Exercise_FrequencyDaily\" %in% rownames(coef_summary)) {",
                "     value <- coef_summary[\"Exercise_FrequencyDaily\", \"Estimate\"]",
                "   } else {",
                "     matching_rows <- grep(\"Exercise_Frequency\", rownames(coef_summary))",
                "     if(length(matching_rows) > 0) {",
                "       value <- coef_summary[matching_rows[1], \"Estimate\"]",
                "     }",
                "   }",
                "   ```",
                "3. **Check factor levels**: Verify actual factor levels: `levels(data$Exercise_Frequency)`",
                "4. **Use grep for pattern matching**: If exact name is unknown, use `grep()` to find matching rows",
                "",
            ])
        elif '$ operator is invalid for atomic vectors' in error_message.lower():
            special_guidance.extend([
                "",
                "**⚠️ Critical: Invalid Dollar Operator Error Detected**",
                "",
                "The error '$ operator is invalid for atomic vectors' occurs when trying to use `$` on an atomic vector (numeric, character, etc.) instead of a list or data frame.",
                "",
                "**Common causes:**",
                "1. **EValue package return type**: The `evalue()` function may return an atomic vector instead of a list",
                "2. **Wrong extraction method**: Using `$` on a numeric vector instead of `[[]]` or `[]`",
                "3. **Function return type mismatch**: Expected a list but got a vector",
                "",
                "**Required fixes:**",
                "1. **Check return type**: Before using `$`, check the type: `class(evalue_result)` or `is.list(evalue_result)`",
                "2. **Use appropriate extraction**: For atomic vectors, use `[[]]` or `[]` instead of `$`:",
                "   ```r",
                "   if(is.list(evalue_obj)) {",
                "     evalues <- evalue_obj$evalues",
                "   } else if(is.atomic(evalue_obj)) {",
                "     evalues <- evalue_obj",
                "   }",
                "   ```",
                "3. **For EValue package**: Check the actual return structure:",
                "   ```r",
                "   evalue_result <- evalue(est, lo, hi)",
                "   if(is.list(evalue_result)) {",
                "     evalues <- evalue_result$evalues",
                "   } else {",
                "     evalues <- evalue_result",
                "   }",
                "   ```",
                "4. **Use str() to inspect**: Use `str(evalue_obj)` to see the actual structure",
                "",
            ])
        elif 'all variables must be in design= argument' in error_message.lower():
            special_guidance.extend([
                "",
                "**⚠️ Critical: Survey Design Missing Variables Error Detected**",
                "",
                "The error 'all variables must be in design= argument' occurs when using `svyglm()` with variables that are not included in the survey design object created by `svydesign()`.",
                "",
                "**Common causes:**",
                "1. **Variables not in design**: Variables used in the model formula are not present in the data frame used to create `svydesign()`",
                "2. **Missing PSU/stratum IDs**: Required variables like `PSU_ID` or `Stratum_ID` are missing from the data",
                "3. **Data frame mismatch**: The data frame used for `svydesign()` differs from the one used for modeling",
                "",
                "**Required fixes:**",
                "1. **Verify variables in design data**: Check that all model variables exist in the design data frame:",
                "   ```r",
                "   required_vars <- c(\"Osteoporosis_Binary\", \"Exercise_Frequency\", \"PSU_ID\", \"Stratum_ID\", \"survey_weight\")",
                "   missing_vars <- setdiff(required_vars, names(design_data))",
                "   if(length(missing_vars) > 0) {",
                "     stop(paste(\"Missing variables in design data:\", paste(missing_vars, collapse=\", \")))",
                "   }",
                "   ```",
                "2. **Create design with all variables**: Ensure `svydesign()` includes all variables needed for modeling:",
                "   ```r",
                "   svydesign_data <- data[, c(\"PSU_ID\", \"Stratum_ID\", \"survey_weight\", model_vars)]",
                "   svydesign_obj <- svydesign(id = ~PSU_ID, strata = ~Stratum_ID, weights = ~survey_weight, data = svydesign_data)",
                "   ```",
                "3. **Check for missing PSU/stratum**: If `PSU_ID` or `Stratum_ID` are missing, create them or use a simpler design:",
                "   ```r",
                "   if(!\"PSU_ID\" %in% names(data)) {",
                "     data$PSU_ID <- 1:nrow(data)",
                "   }",
                "   if(!\"Stratum_ID\" %in% names(data)) {",
                "     data$Stratum_ID <- data$Geographic_Region",
                "   }",
                "   ```",
                "4. **Use same data frame**: Ensure the data frame used for `svydesign()` contains all variables used in `svyglm()`",
                "",
            ])
        elif ('evalue.default' in error_message.lower() and '找不到对象' in error_message) or ('找不到对象[\'"]measure[\'"]' in error_message and 'evalue' in error_message.lower()):
            special_guidance.extend([
                "",
                "**⚠️ Critical: EValue Package Function Call Error Detected**",
                "",
                "The error '找不到对象\'measure\'' (object 'measure' not found) in evalue.default() indicates incorrect usage of the EValue package.",
                "",
                "**Root cause:**",
                "The code is using `evalue.default()` or `evalue()` function, which is incorrect. The EValue package uses `evalues.RR()` (note: plural 'evalues') for relative risk calculations.",
                "",
                "**Required fixes:**",
                "1. **Replace evalue.default() with evalues.RR()**: The correct function name is `evalues.RR()` (plural), not `evalue()` or `evalue.default()`",
                "2. **Use correct parameter names**: The function signature is:",
                "   ```r",
                "   evalues.RR(est, lo, hi, true = 1, rare = FALSE)",
                "   ```",
                "3. **For Prevalence Ratio (PR)**: Convert PR to RR format correctly:",
                "   ```r",
                "   # If PR < 1 (protective effect), use reciprocal",
                "   if (pr < 1) {",
                "     e_result <- evalues.RR(est = 1/pr, lo = 1/pr_upper, hi = 1/pr_lower, true = 1)",
                "   } else {",
                "     # If PR >= 1 (risk effect)",
                "     e_result <- evalues.RR(est = pr, lo = pr_lower, hi = pr_upper, true = 1)",
                "   }",
                "   ```",
                "4. **Extract E-values from result**: The result is a matrix/data frame, extract values correctly:",
                "   ```r",
                "   e_val_point <- e_result[1, 2]  # First row, second column (point estimate E-value)",
                "   e_val_ci <- e_result[2, 2]     # Second row, second column (CI limit E-value)",
                "   ```",
                "5. **For continuous outcomes (Beta coefficients)**: Convert to approximate RR first:",
                "   ```r",
                "   rr_approx <- exp(beta)",
                "   rr_lower_approx <- exp(beta_lower)",
                "   rr_upper_approx <- exp(beta_upper)",
                "   if (rr_approx < 1) {",
                "     e_result <- evalues.RR(est = 1/rr_approx, lo = 1/rr_upper_approx, hi = 1/rr_lower_approx, true = 1)",
                "   } else {",
                "     e_result <- evalues.RR(est = rr_approx, lo = rr_lower_approx, hi = rr_upper_approx, true = 1)",
                "   }",
                "   ```",
                "6. **Ensure EValue package is loaded**: Make sure `library(EValue)` is called before using the function",
                "7. **Handle NA values**: Check that est, lo, hi are not NA before calling evalues.RR():",
                "   ```r",
                "   if (!is.na(pr) && !is.na(pr_lower) && !is.na(pr_upper)) {",
                "     e_result <- evalues.RR(est = pr, lo = pr_lower, hi = pr_upper, true = 1)",
                "   }",
                "   ```",
                "",
                "**Common mistakes to avoid:**",
                "- DO NOT use `evalue()` or `evalue.default()` - these functions don't exist or have different signatures",
                "- DO NOT use `RR = pr` parameter - use `est = pr` instead",
                "- DO NOT use `rare = FALSE` as a separate parameter in the wrong function",
                "- DO NOT assume the result is a list - it's typically a matrix/data frame",
                "",
            ])
        elif 'undefined columns selected' in error_message.lower() or '选择了未定义的列' in error_message:
            special_guidance.extend([
                "",
                "**⚠️ Critical: Undefined Columns Selected Error Detected**",
                "",
                "The error 'undefined columns selected' (选择了未定义的列) occurs when trying to select columns that don't exist in a data frame.",
                "",
                "**Common causes:**",
                "1. **Column name mismatch**: Column names used in selection don't match actual column names",
                "2. **Missing variables**: Variables were removed or renamed in previous steps",
                "3. **Typo in column names**: Misspelling or incorrect capitalization",
                "",
                "**Required fixes:**",
                "1. **Check column names**: Before selecting, verify column names exist:",
                "   ```r",
                "   required_vars <- c(\"var1\", \"var2\", \"var3\")",
                "   missing_vars <- setdiff(required_vars, names(data))",
                "   if(length(missing_vars) > 0) {",
                "     cat(\"Missing variables:\", paste(missing_vars, collapse=\", \"), \"\\n\")",
                "     cat(\"Available variables:\", paste(names(data), collapse=\", \"), \"\\n\")",
                "   }",
                "   ```",
                "2. **Use safe selection**: Only select columns that exist:",
                "   ```r",
                "   available_vars <- intersect(required_vars, names(data))",
                "   if(length(available_vars) > 0) {",
                "     data_subset <- data[, available_vars, drop = FALSE]",
                "   }",
                "   ```",
                "3. **Check variable names**: Use `names(data)` or `colnames(data)` to see actual column names",
                "",
            ])
        
        prompt_parts.extend(special_guidance)
        
        prompt_parts.extend([
            "",
            "**Repair requirements:**",
            "1. Fix the problem that caused the error",                
            "2. Keep the original analysis logic and statistical methods",
            "3. Use R syntax and commonly used packages compatible with the current version",
            "4. Avoid using packages that do not exist (such as BaylorEdPsych, qgraph, lavaan.survey, etc.)",
            "5. Ensure that main_output.csv and analysis_summary.json are generated and saved (using jsonlite::write_json)",
            "6. **For MICE imputed data processing**: Always validate data structure consistency before combining results",
            "7. Only return the corrected complete R code, no other explanation"
        ])

        return "\n".join(prompt_parts)
    
    def attempt_fix(self, original_code: str, error_message: str, 
                   data_summary: str = None, llm_fix_function=None, data_snapshot: str = None,
                   force_llm: bool = False, fix_history: List = None, sub_prompt_content: str = None) -> Tuple[str, bool, str]:
        """
        Progressive repair process: quick repair → LLM repair → enhanced LLM repair
        
        Args:
            original_code: Original code
            error_message: Error message
            data_summary: Data summary information
            llm_fix_function: LLM repair function
            data_snapshot: Current stage data snapshot (real-time, accurate)
            force_llm: Whether to force using LLM repair (skip quick repair)
            fix_history: Fix history record (for advanced repair strategy)
            
        Returns:
            (Fixed code, whether successful, repair method)
        """
        self.fix_stats['total_attempts'] += 1

        if not force_llm:
            error_type = self.identify_error_type(error_message)
            if error_type:
                fixed_code, success = self.apply_simple_fix(original_code, error_type)
                if success and fixed_code != original_code:
                    self.fix_stats['successful_fixes'] += 1
                    return fixed_code, True, f"quick_fix_{error_type}"

        if llm_fix_function:
            self.logger.info("Using LLM repair" + ("（enhanced mode）" if fix_history else ""))
            try:
                self.logger.info("Building fix prompt...")
                fix_prompt = self.get_simple_fix_prompt(
                    original_code, error_message, data_summary, data_snapshot, fix_history,
                    sub_prompt_content=sub_prompt_content
                )
                self.logger.info(f"Fix prompt built, length: {len(fix_prompt)} characters")
                self.logger.info("Calling LLM fix function...")
                fixed_code = llm_fix_function(
                    system_prompt="You are an R programming expert. Please carefully analyze the error reason and provide a concise and effective repair solution.",
                    user_prompt=fix_prompt
                )
    
                if '```r' in fixed_code:
                    fixed_code = fixed_code.split('```r')[1].split('```')[0].strip()
                elif '```' in fixed_code:
                    fixed_code = fixed_code.split('```')[1].split('```')[0].strip()
                
                if fixed_code and fixed_code != original_code:
                    self.fix_stats['successful_fixes'] += 1
                    self.fix_stats['llm_fixes'] += 1
                    return fixed_code, True, "llm_fix"
                    
            except Exception as e:
                self.logger.error(f"LLM repair failed: {e}")
        
        self.logger.warning("Repair failed")
        return original_code, False, "fix_failed"
    
    def get_fix_statistics(self) -> Dict:
        """Get repair statistics"""
        stats = self.fix_stats.copy()
        if stats['total_attempts'] > 0:
            stats['success_rate'] = stats['successful_fixes'] / stats['total_attempts']
        else:
            stats['success_rate'] = 0.0
        
        return stats
    
    def log_fix_result(self, error_message: str, success: bool, method: str):
        """
        Log repair result
        
        Args:
            error_message: Error message
            success: Whether the repair was successful
            method: Repair method
        """
        if success:
            self.logger.info(f"Repair successful: {method} - {error_message[:50]}...")
        else:
            self.logger.warning(f"Repair failed: {error_message[:50]}...")
