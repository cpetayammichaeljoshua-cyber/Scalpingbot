
#!/usr/bin/env python3
"""
Comprehensive Dependency Fixer and Error Handler
Fixes all import errors and missing dependencies dynamically
"""

import subprocess
import sys
import os
import importlib
from pathlib import Path

def install_package(package_name):
    """Install a package using pip"""
    try:
        print(f"📦 Installing {package_name}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
        print(f"✅ Successfully installed {package_name}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install {package_name}: {e}")
        return False

def check_and_install_dependencies():
    """Check and install all required dependencies"""
    required_packages = {
        'schedule': 'schedule',
        'numpy': 'numpy',
        'telegram': 'python-telegram-bot==20.7',
        'aiohttp': 'aiohttp',
        'scikit-learn': 'scikit-learn',
        'pandas': 'pandas',
        'matplotlib': 'matplotlib',
        'seaborn': 'seaborn',
        'requests': 'requests',
        'httpx': 'httpx',
        'websockets': 'websockets',
        'python-binance': 'python-binance',
        'ta': 'ta',
        'asyncio': None,  # Built-in
        'sqlite3': None,  # Built-in
        'json': None,     # Built-in
        'datetime': None, # Built-in
        'pathlib': None,  # Built-in
        'threading': None, # Built-in
        'logging': None,   # Built-in
    }
    
    missing_packages = []
    
    for module_name, package_name in required_packages.items():
        if package_name is None:  # Built-in module
            continue
            
        try:
            importlib.import_module(module_name.replace('-', '_'))
            print(f"✅ {module_name} is available")
        except ImportError:
            print(f"❌ {module_name} is missing")
            missing_packages.append(package_name)
    
    # Install missing packages
    for package in missing_packages:
        install_package(package)
    
    return len(missing_packages) == 0

def fix_import_paths():
    """Fix Python import paths"""
    current_dir = Path(__file__).parent
    signal_maestro_path = current_dir / "SignalMaestro"
    
    paths_to_add = [
        str(current_dir),
        str(signal_maestro_path),
    ]
    
    for path in paths_to_add:
        if path not in sys.path:
            sys.path.insert(0, path)
            print(f"📁 Added {path} to Python path")

def create_missing_init_files():
    """Create __init__.py files if missing"""
    directories = [
        Path("SignalMaestro"),
        Path("utils"),
        Path("ml_models"),
    ]
    
    for directory in directories:
        if directory.exists() and directory.is_dir():
            init_file = directory / "__init__.py"
            if not init_file.exists():
                init_file.write_text("# Auto-generated __init__.py\n")
                print(f"📝 Created {init_file}")

def verify_critical_files():
    """Verify that critical files exist"""
    critical_files = [
        "SignalMaestro/hourly_automation_scheduler.py",
        "SignalMaestro/automated_backtest_optimizer.py",
        "SignalMaestro/fxsusdt_telegram_bot.py",
        "SignalMaestro/fxsusdt_trader.py",
        "SignalMaestro/ichimoku_sniper_strategy.py",
        "start_hourly_automation.py",
    ]
    
    missing_files = []
    for file_path in critical_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
            print(f"❌ Missing critical file: {file_path}")
        else:
            print(f"✅ Found: {file_path}")
    
    return len(missing_files) == 0

def main():
    """Main function to fix all dependencies and errors"""
    print("🔧 Starting comprehensive dependency and error fixing...")
    print("=" * 60)
    
    # Step 1: Check and install dependencies
    print("\n📦 Checking and installing dependencies...")
    deps_ok = check_and_install_dependencies()
    
    # Step 2: Fix import paths
    print("\n📁 Fixing Python import paths...")
    fix_import_paths()
    
    # Step 3: Create missing __init__.py files
    print("\n📝 Creating missing __init__.py files...")
    create_missing_init_files()
    
    # Step 4: Verify critical files
    print("\n📋 Verifying critical files...")
    files_ok = verify_critical_files()
    
    # Summary
    print("\n" + "=" * 60)
    if deps_ok and files_ok:
        print("✅ All dependencies and files are ready!")
        print("🚀 You can now run the hourly automation system:")
        print("   python start_hourly_automation.py")
    else:
        print("⚠️ Some issues were found:")
        if not deps_ok:
            print("   - Some dependencies may need manual installation")
        if not files_ok:
            print("   - Some critical files are missing")
        print("📞 Please check the output above for details")
    
    print("=" * 60)

if __name__ == "__main__":
    main()
