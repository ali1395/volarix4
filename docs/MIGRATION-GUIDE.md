# Volarix 4 - Package Reorganization Migration Guide

## Summary

The Volarix 4 codebase has been reorganized from a flat, root-level structure to a professional Python package structure. This improves maintainability, testability, and scalability.

## What Changed

### Before (Root-level files)
```
volarix4/
├── main.py
├── config.py
├── data.py
├── sr_levels.py
├── rejection.py
├── trade_setup.py
├── utils.py
├── logger.py
├── monitor.py
├── start.py
├── test_api.py
└── backtest.py
```

### After (Package structure)
```
volarix4/
├── volarix4/                    # Main package
│   ├── __init__.py             # Package exports
│   ├── config.py               # Configuration
│   ├── api/                    # API layer
│   │   ├── __init__.py
│   │   └── main.py             # FastAPI app (was root main.py)
│   ├── core/                   # Trading logic
│   │   ├── __init__.py
│   │   ├── data.py             # MT5 integration
│   │   ├── sr_levels.py        # S/R detection
│   │   ├── rejection.py        # Pattern recognition
│   │   └── trade_setup.py      # Risk management
│   └── utils/                  # Utilities
│       ├── __init__.py
│       ├── helpers.py          # Was utils.py
│       ├── logger.py           # Logging
│       └── monitor.py          # Performance monitoring
├── tests/                       # Separated tests
│   ├── __init__.py
│   ├── test_api.py
│   └── backtest.py
├── scripts/                     # Utility scripts
│   └── start.py
├── docs/                        # Documentation
├── run.py                       # NEW: Main entry point
├── PROJECT-STRUCTURE.md         # NEW: Structure documentation
└── MIGRATION-GUIDE.md          # NEW: This file
```

## Key Changes

### 1. New Entry Point

**Old way**:
```bash
python main.py
# or
python start.py
```

**New way**:
```bash
python run.py
# or
python scripts/start.py
```

### 2. Import Changes

**Old imports** (within project files):
```python
from data import fetch_ohlc
from sr_levels import detect_sr_levels
from rejection import find_rejection_candle
from trade_setup import calculate_trade_setup
from utils import calculate_pip_value
from config import SR_CONFIG
from logger import setup_logger
from monitor import monitor
```

**New imports**:
```python
from volarix4.core.data import fetch_ohlc
from volarix4.core.sr_levels import detect_sr_levels
from volarix4.core.rejection import find_rejection_candle
from volarix4.core.trade_setup import calculate_trade_setup
from volarix4.utils.helpers import calculate_pip_value
from volarix4.config import SR_CONFIG
from volarix4.utils.logger import setup_logger
from volarix4.utils.monitor import monitor
```

### 3. File Renames

| Old Location | New Location | Notes |
|--------------|--------------|-------|
| `main.py` | `volarix4/api/main.py` | FastAPI app |
| `config.py` | `volarix4/config.py` | Configuration |
| `data.py` | `volarix4/core/data.py` | MT5 data |
| `sr_levels.py` | `volarix4/core/sr_levels.py` | S/R detection |
| `rejection.py` | `volarix4/core/rejection.py` | Pattern matching |
| `trade_setup.py` | `volarix4/core/trade_setup.py` | Trade calculation |
| `utils.py` | `volarix4/utils/helpers.py` | **RENAMED** |
| `logger.py` | `volarix4/utils/logger.py` | Logging |
| `monitor.py` | `volarix4/utils/monitor.py` | Monitoring |
| `start.py` | `scripts/start.py` | Startup script |
| `test_api.py` | `tests/test_api.py` | API tests |
| `backtest.py` | `tests/backtest.py` | Backtest |

### 4. New Files

| File | Purpose |
|------|---------|
| `run.py` | Simple entry point to start the API |
| `volarix4/__init__.py` | Package initialization and exports |
| `volarix4/api/__init__.py` | API package initialization |
| `volarix4/core/__init__.py` | Core logic package initialization |
| `volarix4/utils/__init__.py` | Utils package initialization |
| `tests/__init__.py` | Tests package initialization |
| `PROJECT-STRUCTURE.md` | Detailed structure documentation |
| `MIGRATION-GUIDE.md` | This migration guide |
| `.gitignore` | Git ignore patterns |

## Migration Steps for Existing Users

### Step 1: Update Your Workflow

**If you were running**:
```bash
python main.py
```

**Now run**:
```bash
python run.py
```

### Step 2: Update Custom Scripts

If you have custom scripts that import from Volarix 4, update the imports:

**Example custom script**:
```python
# OLD
from data import fetch_ohlc
from sr_levels import detect_sr_levels

# NEW
from volarix4.core.data import fetch_ohlc
from volarix4.core.sr_levels import detect_sr_levels
```

### Step 3: Update MT5 Integration (if applicable)

If you're calling the API from MT5, **no changes needed**. The API endpoints remain the same:
- `POST /signal`
- `GET /health`
- `GET /`

### Step 4: Verify Installation

```bash
# 1. Test import
python -c "from volarix4.core import detect_sr_levels; print('✓ Import successful')"

# 2. Test API
python run.py &
sleep 5
curl http://localhost:8000/health
```

## Benefits of New Structure

### 1. **Clear Organization**
- Easy to find files (API code in `api/`, core logic in `core/`, utilities in `utils/`)
- Obvious where to add new features
- Reduced cognitive load

### 2. **Better Testing**
- Tests separated from source code
- Each package can be tested independently
- Easier to mock dependencies

### 3. **Improved Maintainability**
- Changes to one module don't affect unrelated code
- Clear dependency graph
- Easier to refactor

### 4. **Scalability**
- Can add new packages without cluttering root
- Supports future features (e.g., `volarix4/database/`, `volarix4/ui/`)
- Professional structure for team collaboration

### 5. **Distribution Ready**
- Can be packaged as a pip-installable library
- Can be imported by other projects
- Supports development installation (`pip install -e .`)

## Backward Compatibility

### API Compatibility: ✅ **FULL**
- All API endpoints remain unchanged
- Request/response formats identical
- Drop-in replacement for Volarix 3

### Code Compatibility: ⚠️ **REQUIRES UPDATES**
- Internal imports need updating (see Step 2 above)
- Old root-level files removed (superseded by volarix4/ package)

## Troubleshooting

### ImportError: No module named 'volarix4'

**Cause**: Python can't find the package

**Solution**: Run from project root directory
```bash
cd /path/to/volarix4
python run.py
```

### ImportError: No module named 'data'

**Cause**: Using old import style

**Solution**: Update imports
```python
# OLD
from data import fetch_ohlc

# NEW
from volarix4.core.data import fetch_ohlc
```

### ModuleNotFoundError: No module named 'utils'

**Cause**: `utils.py` was renamed to `helpers.py`

**Solution**: Update imports
```python
# OLD
from utils import calculate_pip_value

# NEW
from volarix4.utils.helpers import calculate_pip_value
```

### API won't start

**Cause**: Running old entry point

**Solution**: Use new entry point
```bash
# Don't use: python main.py
# Use instead:
python run.py
```

## Rollback (If Needed)

**Note:** The old root-level files have been removed as the package structure is now stable and production-ready.

If you need an older version:
1. Check out the previous commit from git history
2. Or download a previous release from GitHub

## Getting Help

- **Structure questions**: See [PROJECT-STRUCTURE.md](PROJECT-STRUCTURE.md)
- **API questions**: See [docs/04-API-REFERENCE.md](04-API-REFERENCE.md)
- **Development questions**: See [docs/05-DEVELOPMENT-GUIDE.md](05-DEVELOPMENT-GUIDE.md)

## Feedback

If you encounter issues with the new structure:
1. Check this migration guide
2. Review [PROJECT-STRUCTURE.md](PROJECT-STRUCTURE.md)
3. Check logs in `logs/` directory
4. Open a GitHub issue with details

## Summary

✅ **More organized**: Clear package structure
✅ **Better tested**: Separated test files
✅ **More maintainable**: Logical grouping
✅ **Scalable**: Ready for future growth
✅ **Professional**: Industry-standard Python package

**API compatibility**: No changes needed for API consumers
**Code updates**: Update imports in custom scripts
**Entry point**: Use `python run.py` instead of `python main.py`
