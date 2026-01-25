# Cross-Sectional Study Design and Analysis Agent (AgenMed_CSS)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![R 4.0+](https://img.shields.io/badge/R-4.0+-blue.svg)](https://www.r-project.org/)

An AI-powered cross-sectional study design and statistical analysis automation system that provides an end-to-end solution from research protocol generation to data analysis report output.

## Core Features

- **Intelligent Research Protocol Generation**: Research design planning system based on n8n workflows
- **Automated Statistical Analysis**: Automatically extracts requirements from research protocols, generates and executes R code
- **Intelligent Report Generation**: Automatically generates standardized Word-format statistical analysis reports
- **User-Friendly Web Interface**: Intuitive graphical interface supporting protocol generation and analysis task management

---

## System Architecture

```
AgenMed_CSS/
├── frontend/                          # Frontend interface
│   ├── Cross-Sectional Study Design and Analysis Agent (AgenMed_CSS).html
│   ├── protocol_generation.html       # Research protocol generation interface
│   └── statistical_analysis.html      # Statistical analysis interface
├── n8n—The Planning Design Agent/     # n8n workflow configurations
│   ├── A_Research_Question_Framework_Confirmation.json
│   ├── B_1.Study_Design_Information_Storage.json
│   ├── B_2.Statistical Analysis Plan Storage.json
│   ├── B_3. Verification and Dissemination Information Storage.json
│   ├── C_Write_Intelligent_Design_Proposal.json
│   ├── Check Workflow Status.json
│   └── Retrieve Session Data.json
├── src/                                # Core source code
│   ├── api/                           # API server
│   │   └── api_server.py
│   ├── core/                          # Core orchestrator
│   │   └── orchestrator.py
│   └── modules/                       # Functional modules
│       ├── code_executor.py          # R code executor
│       ├── code_generator.py         # R code generator
│       ├── contract_extractor.py    # Method contract extractor
│       ├── data_cleaner.py           # Data cleaner
│       ├── data_profiler.py          # Data profiler
│       ├── data_quality_controller.py # Data quality controller
│       ├── decision_manager.py       # Decision manager
│       ├── document_processor.py     # Document processor
│       ├── error_fix_manager.py      # Error fix manager
│       ├── estimand_classifier.py    # Estimand classifier
│       ├── file_path_manager.py      # File path manager
│       ├── llm_client.py             # LLM client
│       ├── prompt_builder.py          # Prompt builder
│       ├── r_code_templates.py      # R code templates
│       ├── report_generator.py       # Report generator
│       ├── statistical_consistency_checker.py # Statistical consistency checker
│       └── survey_design_validator.py # Survey design validator
├── templates/                         # Template files
│   └── prompts/
│       └── meta_prompt.md            # Meta prompt template
├── example_data/                     # Example data
│   ├── protocol.docx                 # Example research protocol
│   └── data_simulated.csv            # Example dataset
├── workspace/                         # Workspace (generated at runtime)
├── config.json                        # Configuration file (user configuration required)
├── config.json.example               # Configuration file example
└── start.py                          # System startup script
```

## System Requirements

- **Python** 3.8+
- **R** 4.0+ (Rscript required)
- **n8n** (Optional, for research protocol generation; supports [online version](https://n8n.io/) or local deployment)
- **LLM API** (OpenAI / OpenRouter / Azure OpenAI or other compatible APIs)

---

## Quick Start

### 1. Installation and Configuration

```bash
# Clone repository
git clone https://github.com/boccxx/AgenMed_CSS.git
cd AgenMed_CSS

# Install Python dependencies
pip install -r requirements.txt

# Configure API key
cp config.json.example config.json
# Edit config.json and fill in your LLM API key
```

**Core Configuration Items**:
- `openai_api_key`: LLM API key
- `api_base`: API base URL (supports OpenAI, OpenRouter, Azure OpenAI, etc.)
- `model`: Model name
- `r_executable`: R script executor path (default: `Rscript`)

### 2. Start the System

```bash
# One-click startup (recommended)
python start.py

# Or manually start API server
python -m src.api.api_server
```

Access in browser: `http://localhost:8001`

### 3. Test with Example Data

The system provides complete example data (`example_data/`), including research protocol and simulated dataset, for direct testing of the complete workflow.

---

## User Guide

### Part I: Research Protocol Generation (n8n Workflows)

#### 1. Deploy n8n

**Option A: Use n8n Online (Recommended)**
- Visit [n8n.io](https://n8n.io/) to register an account
- No local installation required, use directly online

**Option B: Local Deployment**
```bash
# Using npm
npm install n8n -g && n8n

# Using Docker
docker run -it --rm -p 5678:5678 -v ~/.n8n:/home/node/.n8n n8nio/n8n
```

#### 2. Import Workflows

In the n8n interface, click **Import from File** or use shortcut `Ctrl+I` / `Cmd+I`, and import workflows from the `n8n—The Planning Design Agent/` directory in order:

| Workflow | Function | Webhook Path |
|----------|----------|-------------|
| `A_Research_Question_Framework_Confirmation.json` | Research question framework confirmation | `/bochunxinprotocola` |
| `B_1.Study_Design_Information_Storage.json` | Study design information storage | `/bochunxinprotocolb1` |
| `B_2.Statistical Analysis Plan Storage.json` | Statistical analysis plan storage | `/bochunxinprotocolb2` |
| `B_3. Verification and Dissemination Information Storage.json` | Verification and dissemination information storage | `/bochunxinprotocolb3` |
| `C_Write_Intelligent_Design_Proposal.json` | Generate research design proposal | `/bochunxinprotocolc` |

#### 3. Configure and Activate

- Configure LLM API credentials (if needed)
- Configure database connection (if using persistent storage)
- Activate workflows (click the "Active" switch in the top right corner)

#### 4. Usage Examples

Call workflows via Webhook to generate research protocols:

```bash
# 1. Confirm research framework
curl -X POST http://localhost:5678/webhook/bochunxinprotocola \
  -H "Content-Type: application/json" \
  -d '{"sessionId": "my-study-001", "framework": "cross-sectional", ...}'

# 2. Store study design
curl -X POST http://localhost:5678/webhook/bochunxinprotocolb1 \
  -H "Content-Type: application/json" \
  -d '{"sessionId": "my-study-001", "study_type": "cross-sectional", ...}'

# 3. Generate complete research protocol
curl -X POST http://localhost:5678/webhook/bochunxinprotocolc \
  -H "Content-Type: application/json" \
  -d '{"sessionId": "my-study-001"}'
```

### Part II: Statistical Analysis (Python System)

#### 1. Upload Files

- **Research Protocol**: `.docx` format (can be generated by n8n workflows)
- **Data File**: `.csv` format, must include headers

#### 2. Start Analysis

Click the "Start Statistical Analysis" button, and the system will automatically execute:
- Parse research protocol document
- Data quality assessment
- Generate and execute R code
- Generate analysis report

#### 3. View Results

Analysis results are saved in `workspace/analysis_YYYYMMDD_HHMMSS_<session_id>/`:
- `02_r_scripts/`: Generated R scripts
- `03_results/`: Analysis results (charts, data tables)
- `04_reports/statistical_analysis_report.docx`: Final report

---

## Frequently Asked Questions

**API server fails to start?**
- Check if port 8001 is occupied
- Confirm `config.json` is properly configured
- Check logs: `workspace/api_*.log`

**R code execution fails?**
- Confirm R is installed: `Rscript --version`
- System will automatically prompt for missing R packages
- Check logs: `workspace/analysis_*/analysis_*.log`

**Analysis process interrupted?**
- Check if LLM API key is valid
- Check network connection
- System supports resume from breakpoint, can restart

---

## Technical Architecture

- **Frontend**: Native HTML/CSS/JavaScript, no build required
- **Backend**: Flask API + Python 3.8+
- **Statistical Analysis**: R 4.0+ automatically generates and executes code
- **Document Processing**: python-docx (reading) + LLM (generation)
- **Workflow Orchestration**: n8n (optional, for research protocol generation)

## Development and Extension

```python
# Add new analysis module
# 1. Create new module in src/modules/
# 2. Register in orchestrator.py
# 3. Update meta_prompt.md template

# Customize R code templates
# Modify src/modules/r_code_templates.py
```

---

## Citation

```bibtex
@software{agenmed_css_2026,
  title = {Cross-Sectional Study Design and Analysis Agent (AgenMed_CSS)},
  author = {Chunxin Bo},
  year = {2026},
  url = {https://github.com/boccxx/AgenMed_CSS}
}
```

---

## License

MIT License - See [LICENSE](LICENSE) file for details

## Contributing

Contributions via Issues and Pull Requests are welcome. Please report problems or suggest improvements.

---

**Disclaimer**: The statistical analysis results and reports generated by this system are for reference only. Professional statistician review is required before use in actual research.
