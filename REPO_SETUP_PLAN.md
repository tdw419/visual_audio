# Visual Audio Repository Setup Plan

## Current State Analysis

**Location**: `/home/jericho/projects/zion/projects/visual_audio/`
**Repository**: Currently in `ai_autodev_coreutils` monorepo
**Project Scope**: Multi-phase audio synthesis system with UPIC-inspired drawing interface

**Completed Components:**
- Phase 3.1: UPIC-Inspired Drawing Interface (complete)
- Phase 3.3: Variophone Integration (complete)
- MP3 to UPIC Converter (complete)
- Test suites (35+ tests passing)
- CLI tools (upic.py, mp3_to_upic.py, demo scripts)
- Documentation (PHASE3.1_COMPLETE.md, PHASE3.3_COMPLETE.md, ROADMAP.md)

**Technical Assets:**
- Core synthesis engine (upic_engine.py)
- Project management system (JSON-based)
- Audio analysis tools (librosa integration)
- Multi-component test coverage
- CLI interfaces for all operations

## Recommendation: Dedicated Repository

### Rationale
1. **Clear Scope**: Audio synthesis and graphical composition system
2. **Self-Contained**: Independent dependencies, tools, tests
3. **Release-Ready**: Production-quality code with documentation
4. **Different Domain**: Audio/visual vs other monorepo projects
5. **Growth Potential**: Roadmap shows future phases and features

## Repository Structure

```
visual_audio/
├── README.md                    # Main documentation
├── LICENSE                      # MIT License
├── pyproject.toml               # Project configuration
├── requirements.txt             # Dependencies
├── ROADMAP.md                   # Project roadmap
├── .gitignore                   # Git ignore patterns
├── src/                         # Core source code
│   └── upic_engine.py          # UPIC synthesis engine
├── tests/                       # Test suite
│   ├── test_upic_engine.py
│   ├── phase3_upic_integration_test.py
│   └── test_mp3_to_upic.py
├── tools/                       # CLI tools
│   ├── upic.py                 # Main UPIC CLI
│   ├── mp3_to_upic.py          # Audio converter
│   └── demo_upic.py            # Demo script
├── docs/                        # Documentation
│   ├── PHASE3.1_COMPLETE.md
│   ├── PHASE3.3_COMPLETE.md
│   ├── MP3_UPIC_CONVERTER.md
│   └── API_REFERENCE.md
├── examples/                    # Example projects
│   ├── basic_demo.upic.json
│   └── demo_projects/
└── completion/                  # Phase completion docs
    ├── PHASE3.1_COMPLETE.md
    └── PHASE3.3_COMPLETE.md
```

## Release Strategy

### Version 0.1.0 (Alpha)
- Core UPIC synthesis engine
- Basic CLI interface
- MP3 to UPIC converter
- Test suite
- Documentation

### Version 0.2.0 (Beta)
- Enhanced envelope system
- Additional wavetables
- Performance optimizations
- More examples

### Version 1.0.0 (Release)
- Complete roadmap Phase 3
- Stable API
- Comprehensive documentation
- Production-ready

## Migration Steps

### 1. Create New Repository
```bash
# Create on GitHub
gh repo create visual_audio --public --description "UPIC-inspired audio synthesis system with graphical composition interface"

# Clone new repo
git clone https://github.com/tdw419/visual_audio.git
cd visual_audio
```

### 2. Migrate Code
```bash
# Copy project files
rsync -av --exclude='.git' \
  --exclude='*.pyc' \
  --exclude='__pycache__' \
  --exclude='*.upic.json' \
  --exclude='*.wav' \
  --exclude='*.mp3' \
  /home/jericho/projects/zion/projects/visual_audio/ \
  /home/jericho/visual_audio/

# Set up directory structure
cd /home/jericho/visual_audio
mkdir -p src tests tools docs examples completion
mv upic_engine.py src/
mv upic.py tools/
mv mp3_to_upic.py tools/
mv demo_upic.py tools/
mv test_*.py tests/
mv PHASE*.md completion/
mv *.md docs/ 2>/dev/null || true
```

### 3. Update Project Metadata
```bash
# Update pyproject.toml with proper project info
# Update README.md with comprehensive documentation
# Create LICENSE file
# Create .gitignore
```

### 4. Setup Documentation
```bash
# Create main README.md
# Create API documentation
# Create usage examples
# Create contribution guidelines
```

### 5. Initialize Git
```bash
cd /home/jericho/visual_audio
git init
git add .
git commit -m "Initial commit: UPIC-inspired audio synthesis system"

# Add remote and push
git remote add origin https://github.com/tdw419/visual_audio.git
git branch -M main
git push -u origin main
```

### 6. Tag Release
```bash
git tag -a v0.1.0 -m "Alpha release: Core UPIC synthesis system"
git push origin v0.1.0
```

## Repository Configuration

### .gitignore
```
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
ENV/
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Testing
.pytest_cache/
.coverage
htmlcov/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# Project specific
*.upic.json
*.wav
*.mp3
*.ogg
!examples/*.upic.json
!examples/*.wav

# Documentation builds
docs/_build/
site/

# OS
.DS_Store
Thumbs.db
```

### pyproject.toml
```toml
[build-system]
requires = ["setuptools>=45", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "visual_audio"
version = "0.1.0"
description = "UPIC-inspired audio synthesis system with graphical composition interface"
readme = "README.md"
requires-python = ">=3.8"
license = {text = "MIT"}
authors = [
    {name = "Jericho", email = "tdw419@github.com"}
]
keywords = ["audio", "synthesis", "UPIC", "composition", "music"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "Intended Audience :: Musicians",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.8",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Topic :: Multimedia :: Sound/Audio",
    "Topic :: Multimedia :: Sound/Audio :: Sound Synthesis",
]
dependencies = [
    "numpy>=1.21.0",
    "scipy>=1.7.0",
    "soundfile>=0.11.0",
    "librosa>=0.9.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "black>=23.0.0",
    "flake8>=6.0.0",
    "mypy>=1.0.0",
]

[project.scripts]
upic = "visual_audio.cli:main"
mp3-to-upic = "visual_audio.converter:main"

[project.urls]
Homepage = "https://github.com/tdw419/visual_audio"
Documentation = "https://github.com/tdw419/visual_audio#readme"
Repository = "https://github.com/tdw419/visual_audio"
Issues = "https://github.com/tdw419/visual_audio/issues"

[tool.setuptools.packages.find]
where = ["src"]

[tool.black]
line-length = 100
target-version = ['py38']

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
addopts = "-v --cov=src --cov-report=html"
```

## Documentation Requirements

### README.md Sections
1. **Project Overview**
   - What is Visual Audio?
   - Historical context (UPIC system)
   - Key features
   - Use cases

2. **Installation**
   - Requirements
   - Setup instructions
   - Platform support

3. **Quick Start**
   - Basic usage examples
   - Create first project
   - Synthesize audio

4. **Documentation Links**
   - API reference
   - User guide
   - Examples gallery

5. **Contributing**
   - Development setup
   - Code style
   - Testing
   - Pull request process

6. **License**
   - MIT License text

### Additional Documentation
- **MP3_UPIC_CONVERTER.md**: Detailed converter guide
- **API_REFERENCE.md**: Complete API documentation
- **EXAMPLES.md**: Usage examples and tutorials
- **ARCHITECTURE.md**: System architecture and design decisions
- **ROADMAP.md**: Future development plans

## Testing Strategy

### Continuous Integration
```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.8, 3.9, 3.10, 3.11]
    
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    - name: Install dependencies
      run: |
        pip install -e ".[dev]"
    - name: Run tests
      run: pytest
    - name: Run linter
      run: flake8 src tests
```

## Success Criteria

✅ Repository created on GitHub
✅ Code migrated with proper structure  
✅ Documentation comprehensive and clear
✅ Tests passing in CI
✅ Examples working
✅ Version tagged and released
✅ README properly indexed on GitHub

## Next Steps

1. Create GitHub repository
2. Migrate code and documentation
3. Set up CI/CD pipeline
4. Create comprehensive README
5. Tag and release v0.1.0
6. Share with community
7. Gather feedback for improvements

## Benefits of Dedicated Repository

1. **Clearer Identity**: Standalone project with clear purpose
2. **Better Discoverability**: Easier for users to find and understand
3. **Independent Development**: Can evolve without monorepo constraints
4. **Version Management**: Clean semantic versioning
5. **Community Growth**: Easier for contributors to engage
6. **Release Management**: Can have own release cycle
7. **Documentation Focus**: Dedicated docs for audio synthesis